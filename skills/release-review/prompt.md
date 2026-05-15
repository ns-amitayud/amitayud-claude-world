# release-review skill

Use this skill when the user invokes `/release-review <csv_path>`.

**Goal:** Draft release-readiness answers for NSProxy tickets in a release CSV, get human approval, write approved answers back into the CSV, and convert to XLSX ready for upload to the release tracking Google Sheet.

**Helper script:** `~/gitcode/amitayud-claude-world/skills/release-review/scripts/review.py`

**Design spec:** `~/gitcode/amitayud-claude-world/docs/specs/2026-05-14-release-readiness-review-skill-design.md`

---

## Phase 0: Startup checks

Before doing anything else:

1. Verify the CSV path exists:
   ```bash
   ls <csv_path>
   ```
   If missing, stop and ask the user for the correct path.

2. Verify Python deps:
   ```bash
   python3 -c "import pandas, openpyxl"
   ```
   If this fails, run: `pip install pandas openpyxl`

3. Confirm Jira CLI is available and credentials are set:
   ```bash
   ~/.claude/plugins/cache/netskope/eng-skills/1.6.2/skills/jira/scripts/jira projects 2>&1 | head -3
   ```
   If 401 or error, warn: "Jira credentials may be missing. Answers based on Jira data will be limited."

4. Get the list of tickets to process:
   ```bash
   python3 ~/gitcode/amitayud-claude-world/skills/release-review/scripts/review.py filter <csv_path>
   ```
   Report: "Found K NSProxy tickets needing answers."

---

## Phase 1: Risk criteria menu

Present the following to the user **before processing any tickets**:

```
Release-readiness review for: <csv_path>
Tickets to process: K

High-risk gating criteria — always active:
  [✓] Flag present (FF/Staged Config/etc.)
  [✓] Regression risk

Optional additional criteria — select any to add:
  A. Diff touches >5 files
  B. Change in a hot-path component (policy engine, session mgmt, crypto, event dispatch)
  C. No rollback plan mentioned in PR or Jira
  D. PR had unresolved review comments at merge time

Press Enter for defaults (A+B active), or type letters to toggle (e.g. "CD" activates C+D instead):
```

Record the active criteria set. **Default = A and B active.** Apply throughout Phase 3.

---

## Phase 2: Category spotlight

Before processing individual tickets, query Jira for historical incident density:

```bash
~/.claude/plugins/cache/netskope/eng-skills/1.6.2/skills/jira/scripts/jira search \
  "project = ENG AND component = 'NS Proxy (NSP)' AND labels in ('PROD-INCIDENT', 'customer-escalation') AND resolved >= -365d ORDER BY updated DESC" 2>/dev/null
```

Group results by Sub-Component. Combine with blast-radius knowledge:
- SSL termination / crypto = all tenants, hard to recover
- Policy engine = all tenants, config reload recovers
- Session management = subset of tenants, service restart recovers
- Everything else = subset or unknown

Score each category: (blast_radius × 2) + recoverability_cost + incident_count. Print top 3:

```
Category spotlight — handle these with extra care:

  1. <sub-component> (<N> tickets in this release) — blast radius: <scope>, incidents past year: <count>
  2. ...
  3. ...

Tickets in these categories will always get per-ticket review regardless of risk tier.
Press Enter to accept, or describe changes:
```

If the Jira query returns nothing, skip incident count and score on blast radius + recoverability only.

---

## Phase 3: Per-ticket analysis

For each ticket key from the filter list, in order:

### 3a. Fetch evidence

**Tier 1 — always fetch:**

```bash
# Jira issue
~/.claude/plugins/cache/netskope/eng-skills/1.6.2/skills/jira/scripts/jira issue <KEY>

# Find the PR (search all netSkope org repos)
gh api "search/issues?q=org:netSkope+<KEY>+is:pr+is:merged" \
  --jq '.items[0] | {number: .number, title: .title, repo: .repository_url}'
```

If a PR is found, extract `<OWNER/REPO>` from the `repo` URL (last two path segments) and fetch:

```bash
gh pr view <NUMBER> --repo <OWNER/REPO> \
  --json title,body,additions,deletions,changedFiles,files \
  --jq '{title,body,additions,deletions,changedFiles,files: [.files[].path]}'

gh api "repos/<OWNER/REPO>/pulls/<NUMBER>/reviews" \
  --jq '[.[] | {user: .user.login, state: .state, body: .body[:300]}]'

gh api "repos/<OWNER/REPO>/pulls/<NUMBER>/comments" \
  --jq '[.[] | {user: .user.login, body: .body[:300]}]'
```

If no PR found: mark `PR_NOT_FOUND`, answer only from Jira data, set confidence `[?]` for diff-based questions.

**Tier 2 — fetch if Tier 1 leaves Q1 or Q7 uncertain:**
- Fetch the parent Epic if the Jira issue has one: `jira issue <EPIC-KEY>`
- Follow any Confluence URL in the Jira description: use the `eng-skills:confluence` skill to read the page summary

**Tier 3 — fetch only for High-risk or spotlight-category tickets:**
- Sibling tickets under same Epic:
  ```bash
  ~/.claude/plugins/cache/netskope/eng-skills/1.6.2/skills/jira/scripts/jira search \
    "parent = <EPIC-KEY> AND status = Closed" 2>/dev/null
  ```
- Recent incidents in same sub-component:
  ```bash
  ~/.claude/plugins/cache/netskope/eng-skills/1.6.2/skills/jira/scripts/jira search \
    "project = ENG AND component = 'NS Proxy (NSP)' AND labels in ('PROD-INCIDENT') AND resolved >= -365d" 2>/dev/null | head -20
  ```

### 3b. Draft answers to Q1–Q8

Use the evidence to draft answers. Annotate each with its confidence tier:
- `[T1]` = derived from PR diff/description/review comments (high confidence)
- `[T2]` = derived from Epic/Confluence (medium confidence)
- `[T3]` = derived from cross-PR or historical signals (low confidence)
- `[?]` = no evidence found (human must fill)

**Q1 — Risk level:**
Apply the active criteria from Phase 1:
- Flag present (Q4=YES) → High
- Regression (Q2=Yes) → High
- If criterion A active: diff touches >5 files → High
- If criterion B active: files include `policy/`, `ssl/`, `session/`, `crypto/`, `cfw/` → High
- If criterion C active: no rollback info in PR or Jira → High
- If criterion D active: PR had CHANGES_REQUESTED state at merge → High
- Dead code removal, test additions, doc changes, config cleanup → Low
- Narrow bug fix (≤3 files, no interface changes) → Low
- Everything else → Medium (route as High)

**Q2 — Regression introduced?**
Look for the word "regression" in PR description or review comments. If mentioned: Yes. Otherwise: No. `[T1]`

**Q3 — Regression detail:**
If Q2=Yes, quote the relevant sentence from the PR/review. If Q2=No, leave empty.

**Q4 — Flag introduced?**
Search the list of changed files for names containing `staged_config`, `feature_flag`, `ff_`. Also check PR body for mentions of `StagedConfig`, `FeatureFlag`, `FF_`. If any match: YES. Otherwise: NO. `[T1]`

**Q5 — Flag default state:**
If Q4=YES, look in PR description or diff for the default value (enabled/disabled). If not found: `[?]`

**Q6 — Flag details:**
If Q4=YES, note the flag name and type from PR description or diff. If not found: `[?]`

**Q7 — IMF / rollback action:**
Look for a rollback section in the PR description. If found: quote it. `[T1]`
If not in PR, check Epic description. `[T2]`
If nowhere: default to "Revert the PR" and mark `[T1]` (always safe).

**Q8 — Wiki link:**
Extract any URL from the Jira description or PR body that points to Confluence or an internal wiki. If none: leave empty.

### 3c. Classify risk tier

- **High** if: Q4=YES, OR Q2=Yes, OR any active optional criterion triggered, OR ticket's Sub-Component is in the Phase 2 spotlight list.
- **Low** otherwise.

---

## Phase 4: Approval loop

**Important:** Complete Phase 3 analysis for ALL tickets before entering Phase 4. Do not show the approval UI ticket-by-ticket during analysis — hold all results until the full list is processed, then present them as described below.

### Low-risk batch

After processing all tickets, collect the Low-risk ones. Present as a compact table:

```
Low-risk tickets (N) — drafted answers ready for batch approval:

KEY          | Risk | Regression | Flag | Rollback        | Confidence
ENG-XXXXXX   | Low  | No [T1]    | NO   | Revert the PR   | all T1
ENG-YYYYYY   | Low  | No [T1]    | NO   | Revert the PR   | all T1
...

[A] Approve all and write   [R] Review each individually   [S] Skip all
```

- **A**: proceed to Phase 5 for all Low tickets
- **R**: step through each one with the High-risk flow below
- **S**: leave CSV unchanged for all Low tickets

### High-risk (per-ticket)

For each High-risk ticket (and any Low ones the user chose to review individually):

```
━━━ ENG-XXXXXX: <summary> ━━━
PR: <title> (<repo>#<number>)
Files changed: N  |  +X −Y lines
Key files: <top 5 changed files>
Why High-risk: <reason>

Drafted answers:
  Q1 Risk:         <answer> [T1]
  Q2 Regression:   <answer> [T1]
  Q3 Detail:       <answer or empty>
  Q4 Flag:         <answer> [T1]
  Q5 Flag default: <answer or [?]>
  Q6 Flag detail:  <answer or [?]>
  Q7 Rollback:     <answer> [T1]
  Q8 Wiki:         <answer or empty>

[A] Approve   [E] Edit an answer   [S] Skip   [Q] Quit
```

- **E**: ask "Which question? (1-8)" then "New answer:", update the draft, show updated answers, re-prompt
- **Q**: stop processing remaining tickets, move immediately to Phase 5 with whatever is approved so far

---

## Phase 5: Write and convert

After the approval loop, write all approved answers in one pass:

```bash
# For each approved ticket:
python3 ~/gitcode/amitayud-claude-world/skills/release-review/scripts/review.py \
  write <csv_path> "<KEY>" "<q1>" "<q2>" "<q3>" "<q4>" "<q5>" "<q6>" "<q7>" "<q8>"
```

Then convert:

```bash
python3 ~/gitcode/amitayud-claude-world/skills/release-review/scripts/review.py \
  convert <csv_path>
```

Print final summary:

```
━━━ Done ━━━
Written:  N tickets
Skipped:  M tickets
Output:   <path-to-xlsx>

Next step: upload the XLSX to the release tracking sheet:
https://docs.google.com/spreadsheets/d/10vOTPLLhV_xPBp8CobpNidSIk3SVH7-3aymUI9l9sfA/
```

---

## Appendix: Question reference (Q1–Q8)

These questions come directly from columns 23–30 of the release tracking CSV. Full verbatim text is in the design spec Appendix A.

| # | Col | Short name |
|---|-----|-----------|
| Q1 | 23 | Risk level |
| Q2 | 24 | Regression? |
| Q3 | 25 | Regression detail |
| Q4 | 26 | Flag present? |
| Q5 | 27 | Flag default state |
| Q6 | 28 | Flag details |
| Q7 | 29 | IMF / rollback action |
| Q8 | 30 | Wiki link |
