# Release Review Skill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a `release-review` Claude Code skill that reads a release tracking CSV, drafts answers to 8 release-readiness questions per NSProxy ticket using Jira + GitHub evidence, presents them for human approval (batch for low-risk, per-ticket for high-risk), and writes approved answers back to the CSV then converts to XLSX.

**Architecture:** A `prompt.md` skill definition drives the agent behaviour (filtering, evidence gathering, drafting, approval loop). A `scripts/review.py` Python helper handles all mechanical CSV/XLSX I/O and Jira CLI calls, so the skill prompt stays readable and the Python logic is independently testable.

**Tech Stack:** Python 3 (pandas, openpyxl, csv, subprocess), Jira CLI (`~/.claude/plugins/cache/netskope/eng-skills/1.6.2/skills/jira/scripts/jira`), GitHub CLI (`gh`), Claude Code skill system (`prompt.md`).

---

## File Structure

| File | Responsibility |
|------|---------------|
| `docs/specs/2026-05-14-release-readiness-review-skill-design.md` | Design spec — why the skill exists and how it behaves |
| `docs/plans/2026-05-15-release-review-skill.md` | This implementation plan |
| `skills/release-review/prompt.md` | Skill definition — tells the agent the full workflow: filter, analyze, present, approve, write |
| `skills/release-review/scripts/review.py` | Python helper — CSV loading/filtering, answer writing, XLSX conversion, and utility subcommands the skill calls via Bash |

---

### Task 1: Clone the repo, commit spec and plan, set up the skill skeleton

**Files:**
- Clone: `~/gitcode/amitayud-claude-world`
- Copy: `~/docs/superpowers/specs/2026-05-14-release-readiness-review-skill-design.md` → `~/gitcode/amitayud-claude-world/docs/specs/`
- Copy: `~/docs/superpowers/plans/2026-05-15-release-review-skill.md` → `~/gitcode/amitayud-claude-world/docs/plans/`
- Create: `~/gitcode/amitayud-claude-world/skills/release-review/prompt.md`
- Create: `~/gitcode/amitayud-claude-world/skills/release-review/scripts/review.py`

- [ ] **Step 1: Clone the repo**

```bash
git clone git@github.com:ns-amitayud/amitayud-claude-world.git ~/gitcode/amitayud-claude-world
```

Expected: repo cloned to `~/gitcode/amitayud-claude-world`

- [ ] **Step 2: Verify existing skill structure**

```bash
ls ~/gitcode/amitayud-claude-world/skills/
```

Expected: `pr-reply-ad-hoc  research-architecture  review  review-feature-flag-cm  review-pr`

- [ ] **Step 3: Copy spec and plan into the repo**

```bash
mkdir -p ~/gitcode/amitayud-claude-world/docs/specs
mkdir -p ~/gitcode/amitayud-claude-world/docs/plans
cp ~/docs/superpowers/specs/2026-05-14-release-readiness-review-skill-design.md \
   ~/gitcode/amitayud-claude-world/docs/specs/
cp ~/docs/superpowers/plans/2026-05-15-release-review-skill.md \
   ~/gitcode/amitayud-claude-world/docs/plans/
```

- [ ] **Step 4: Commit spec and plan**

```bash
cd ~/gitcode/amitayud-claude-world
git add docs/
git commit -m "docs: add release-review design spec and implementation plan"
```

- [ ] **Step 5: Create the skill directory and empty placeholder files**

```bash
mkdir -p ~/gitcode/amitayud-claude-world/skills/release-review/scripts
touch ~/gitcode/amitayud-claude-world/skills/release-review/prompt.md
touch ~/gitcode/amitayud-claude-world/skills/release-review/scripts/review.py
```

- [ ] **Step 6: Commit skeleton**

```bash
cd ~/gitcode/amitayud-claude-world
git add skills/release-review/
git commit -m "chore: scaffold release-review skill directory"
```

---

### Task 2: Write the Python helper — CSV loading and filtering

**Files:**
- Write: `~/gitcode/amitayud-claude-world/skills/release-review/scripts/review.py`
- Test manually: `python3 review.py filter ~/R138.csv`

The helper is a CLI tool invoked with subcommands. This task implements the `filter` subcommand which prints the list of NSProxy ticket keys that still need answering.

- [ ] **Step 1: Write the filter subcommand**

```python
#!/usr/bin/env python3
"""
release-review helper
Usage:
  review.py filter <csv_path>
      Print NSProxy ticket keys with any of columns 23-30 still empty.

  review.py write <csv_path> <key> <q1> <q2> <q3> <q4> <q5> <q6> <q7> <q8>
      Write answers for one ticket into the CSV (in place).

  review.py convert <csv_path>
      Convert CSV to XLSX saved as <csv_path>.xlsx (stem + -reviewed.xlsx).
"""
import sys
import csv
import re

COMPONENT_COL = 10   # Components
KEY_COL = 1
ANSWER_COLS = list(range(23, 31))   # cols 23-30 inclusive (Q1-Q8)


def load_csv(path):
    with open(path, newline='', encoding='utf-8') as f:
        return list(csv.reader(f))


def is_nsproxy_row(row):
    if len(row) <= COMPONENT_COL:
        return False
    return bool(re.search(r'nsproxy', row[COMPONENT_COL], re.IGNORECASE))


def needs_answers(row):
    """True if any of the 8 answer columns is blank."""
    for col in ANSWER_COLS:
        if len(row) <= col or not row[col].strip():
            return True
    return False


def cmd_filter(csv_path):
    rows = load_csv(csv_path)
    results = []
    for row in rows[1:]:   # skip header
        if is_nsproxy_row(row) and needs_answers(row):
            results.append(row[KEY_COL])
    print('\n'.join(results))


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    cmd = sys.argv[1]
    path = sys.argv[2]
    if cmd == 'filter':
        cmd_filter(path)
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)
```

- [ ] **Step 2: Run filter against R138.csv and verify output**

```bash
python3 ~/gitcode/amitayud-claude-world/skills/release-review/scripts/review.py filter ~/R138.csv | head -10
```

Expected: list of ENG-XXXXXX keys, one per line. Should be ~100 tickets (101 had blank risk fields).

- [ ] **Step 3: Verify the count**

```bash
python3 ~/gitcode/amitayud-claude-world/skills/release-review/scripts/review.py filter ~/R138.csv | wc -l
```

Expected: a number between 90 and 111.

- [ ] **Step 4: Commit**

```bash
cd ~/gitcode/amitayud-claude-world
git add skills/release-review/scripts/review.py
git commit -m "feat(release-review): add filter subcommand to list unanswered NSProxy tickets"
```

---

### Task 3: Write the Python helper — answer writing and XLSX conversion

**Files:**
- Modify: `~/gitcode/amitayud-claude-world/skills/release-review/scripts/review.py`

- [ ] **Step 1: Add the `write` subcommand**

Add after the `cmd_filter` function:

```python
def cmd_write(csv_path, key, answers):
    """answers: list of 8 strings for cols 23-30."""
    rows = load_csv(csv_path)
    header = rows[0]
    matched = False
    for row in rows[1:]:
        if row[KEY_COL] == key:
            # Pad row if shorter than col 30
            while len(row) <= 30:
                row.append('')
            for i, ans in enumerate(answers):
                row[ANSWER_COLS[i]] = ans
            matched = True
            break
    if not matched:
        print(f"ERROR: key {key} not found in {csv_path}", file=sys.stderr)
        sys.exit(1)
    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerows(rows)
    print(f"OK: wrote answers for {key}")
```

- [ ] **Step 2: Add the `convert` subcommand**

Add after `cmd_write`:

```python
def cmd_convert(csv_path):
    import pandas as pd
    from pathlib import Path
    df = pd.read_csv(csv_path, dtype=str).fillna('')
    out_path = Path(csv_path).with_stem(Path(csv_path).stem + '-reviewed').with_suffix('.xlsx')
    df.to_excel(out_path, index=False, engine='openpyxl')
    print(f"Saved: {out_path}")
```

- [ ] **Step 3: Wire both subcommands into `__main__`**

Replace the `if __name__ == '__main__'` block with:

```python
if __name__ == '__main__':
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    cmd = sys.argv[1]
    path = sys.argv[2]
    if cmd == 'filter':
        cmd_filter(path)
    elif cmd == 'write':
        # args: review.py write <csv> <key> <q1> .. <q8>
        if len(sys.argv) != 12:
            print("write requires: csv_path key q1 q2 q3 q4 q5 q6 q7 q8")
            sys.exit(1)
        cmd_write(path, sys.argv[3], sys.argv[4:12])
    elif cmd == 'convert':
        cmd_convert(path)
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)
```

- [ ] **Step 4: Test `write` on a throwaway copy**

```bash
cp ~/R138.csv /tmp/R138_test.csv
python3 ~/gitcode/amitayud-claude-world/skills/release-review/scripts/review.py \
  write /tmp/R138_test.csv ENG-974050 \
  "Low" "No" "" "NO" "NA" "" "Revert the PR" ""
```

Expected: `OK: wrote answers for ENG-974050`

- [ ] **Step 5: Verify the write landed in the right columns**

```bash
python3 -c "
import csv
with open('/tmp/R138_test.csv') as f:
    rows = list(csv.reader(f))
for row in rows[1:]:
    if 'ENG-974050' in row[1]:
        for i in range(23, 31):
            print(f'col {i}: {row[i] if len(row) > i else \"(missing)\"}')
"
```

Expected: col 23=Low, col 24=No, col 25=(empty), col 26=NO, col 27=NA, col 28=(empty), col 29=Revert the PR, col 30=(empty)

- [ ] **Step 6: Test `convert`**

```bash
python3 ~/gitcode/amitayud-claude-world/skills/release-review/scripts/review.py convert /tmp/R138_test.csv
ls /tmp/R138_test-reviewed.xlsx
```

Expected: file exists, no error.

- [ ] **Step 7: Commit**

```bash
cd ~/gitcode/amitayud-claude-world
git add skills/release-review/scripts/review.py
git commit -m "feat(release-review): add write and convert subcommands"
```

---

### Task 4: Write the skill prompt — startup, filtering, and risk criteria menu

**Files:**
- Write: `~/gitcode/amitayud-claude-world/skills/release-review/prompt.md`

This task writes the first half of the skill: startup checks, filter phase, and the risk criteria menu.

- [ ] **Step 1: Write the prompt**

```markdown
# release-review skill

Use this skill when the user invokes `/release-review <csv_path>`.
Goal: draft release-readiness answers for NSProxy tickets, get human approval, write to CSV, convert to XLSX.

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

3. Confirm Jira CLI is available:
   ```bash
   ~/.claude/plugins/cache/netskope/eng-skills/1.6.2/skills/jira/scripts/jira issue ENG-1 2>&1 | head -2
   ```
   If 401/not found, warn: "Jira credentials may be missing. Answers based on Jira data will be limited."

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

Press Enter for defaults (A+B active), or type letters to toggle (e.g. "CD"):
```

Record the active criteria set. Default = A and B active. Apply throughout Phase 2.

---

## Phase 2: Category spotlight

Before processing individual tickets, query Jira for historical incident density:

```bash
~/.claude/plugins/cache/netskope/eng-skills/1.6.2/skills/jira/scripts/jira search \
  "project = ENG AND component = 'NS Proxy (NSP)' AND labels in ('PROD-INCIDENT', 'customer-escalation') AND resolved >= -365d ORDER BY updated DESC" \
  2>/dev/null | head -50
```

Group results by Sub-Component. Combine with blast-radius knowledge (SSL = all tenants, policy = all tenants, session = subset) to score categories. Print the top 3:

```
Category spotlight — handle these with extra care:

  1. <sub-component> (<N> tickets) — blast radius: <scope>, incidents in past year: <count>
  2. ...
  3. ...

Tickets in these categories will always get per-ticket review.
Press Enter to accept, or type changes:
```

---

## Phase 3: Per-ticket analysis

For each ticket key from the filter list, in order:

### 3a. Fetch evidence

**Tier 1 (always):**
```bash
~/.claude/plugins/cache/netskope/eng-skills/1.6.2/skills/jira/scripts/jira issue <KEY>
```

Find the PR:
```bash
gh api "search/issues?q=org:netSkope+<KEY>+is:pr+is:merged" \
  --jq '.items[0] | {number: .number, title: .title, repo: .repository_url}'
```

If PR found, fetch:
```bash
gh pr view <NUMBER> --repo <OWNER/REPO> \
  --json title,body,additions,deletions,changedFiles,files
gh api repos/<OWNER/REPO>/pulls/<NUMBER>/reviews \
  --jq '[.[] | {user: .user.login, state: .state, body: .body}]'
gh api repos/<OWNER/REPO>/pulls/<NUMBER>/comments \
  --jq '[.[] | {user: .user.login, body: .body[:200]}]'
```

**Tier 2 (if Tier 1 leaves Q7 or Q1 uncertain):**
- Follow any Confluence URL found in the Jira description using `eng-skills:confluence` skill.
- Fetch the parent Epic if present: `jira issue <EPIC-KEY>`

**Tier 3 (only for High-risk or spotlight-category tickets):**
- Query for sibling tickets under the same Epic:
  ```bash
  ~/.claude/plugins/cache/netskope/eng-skills/1.6.2/skills/jira/scripts/jira search \
    "parent = <EPIC-KEY> AND status = Closed"
  ```
- Query for recent incidents in the same sub-component:
  ```bash
  ~/.claude/plugins/cache/netskope/eng-skills/1.6.2/skills/jira/scripts/jira search \
    "project = ENG AND component = 'NS Proxy (NSP)' AND 'Sub-Component' = '<SUB-COMPONENT>' AND labels in ('PROD-INCIDENT') AND resolved >= -365d"
  ```

### 3b. Draft answers

Using the evidence collected, draft answers to Q1–Q8 (see Appendix A of the design spec). For each answer, annotate the confidence tier:
- `[T1]` = derived from PR diff/description/review comments
- `[T2]` = derived from Epic/Confluence
- `[T3]` = derived from cross-PR or historical signals
- `[?]` = no evidence found

Rules for Q4 (flag detection): grep the PR diff for: `StagedConfig`, `FeatureFlag`, `ff_`, `staged_config`, `feature_flag`. If any match, Q4 = YES.

Rules for Q1 (risk classification): apply the active criteria set from Phase 1. Any High criterion → High. All Low criteria → Low. Otherwise → Medium (route as High).

### 3c. Classify tier

- **High** if: Q4=YES, OR Q2=Yes, OR any active optional criterion is triggered.
- **Low** otherwise.

Also mark **High** if the ticket's Sub-Component is in the category spotlight list.

---

## Phase 4: Approval

### Low-risk batch

Collect all Low tickets. Present as a table:

```
Low-risk tickets (N) — drafted answers:

KEY        | Risk | Regression | Flag | Rollback           | Confidence
ENG-XXXXXX | Low  | No [T1]    | NO   | Revert the PR [T1] | all T1
...

Options: [A] Approve all  [R] Review individually  [S] Skip all
```

If user types A: proceed to Phase 5 for all.
If user types R: step through each one individually (same flow as High-risk below).
If user types S: skip all (leave CSV unchanged for these).

### High-risk (per-ticket)

For each High ticket, present:

```
--- ENG-XXXXXX: <summary> ---
PR: <title> (<repo>#<number>)
Files changed: N  |  +X -Y lines
Key files: <list top 5 changed files>

Drafted answers:
  Q1 Risk:        <answer> [T1]
  Q2 Regression:  <answer> [T1]
  Q3 Detail:      <answer> [T1/T2/?]
  Q4 Flag:        <answer> [T1]
  Q5 Flag default:<answer> [T1/?]
  Q6 Flag detail: <answer> [T1/?]
  Q7 Rollback:    <answer> [T1/T2]
  Q8 Wiki:        <answer> [T1/?]

Why High-risk: <reason — e.g. "flag present", "regression mentioned in review", "in SSL spotlight">

[A] Approve  [E] Edit  [S] Skip  [Q] Quit
```

If user types E: ask which question to edit, accept new text, update the draft.
If user types Q: stop processing. Move to Phase 5 with whatever has been approved so far.

---

## Phase 5: Write and convert

After approval loop completes:

1. For each approved ticket, call write subcommand:
   ```bash
   python3 ~/gitcode/amitayud-claude-world/skills/release-review/scripts/review.py \
     write <csv_path> <KEY> "<q1>" "<q2>" "<q3>" "<q4>" "<q5>" "<q6>" "<q7>" "<q8>"
   ```

2. Convert to XLSX:
   ```bash
   python3 ~/gitcode/amitayud-claude-world/skills/release-review/scripts/review.py \
     convert <csv_path>
   ```

3. Print summary:
   ```
   Done.
   Written: N tickets
   Skipped: M tickets
   Output:  <path-to-xlsx>

   Next step: upload the XLSX to:
   https://docs.google.com/spreadsheets/d/10vOTPLLhV_xPBp8CobpNidSIk3SVH7-3aymUI9l9sfA/
   ```

---

## Appendix: Question reference

See design spec at:
`~/docs/superpowers/specs/2026-05-14-release-readiness-review-skill-design.md`
Appendix A for full verbatim question text and column mapping.
```

- [ ] **Step 2: Commit**

```bash
cd ~/gitcode/amitayud-claude-world
git add skills/release-review/prompt.md
git commit -m "feat(release-review): add skill prompt covering all 5 phases"
```

---

### Task 5: Sync skill to ~/.claude/skills and do a first test run

**Files:**
- Symlink or copy: `~/.claude/skills/release-review/` → `~/gitcode/amitayud-claude-world/skills/release-review/`

- [ ] **Step 1: Link the skill so Claude Code picks it up**

```bash
ln -s ~/gitcode/amitayud-claude-world/skills/release-review \
      ~/.claude/skills/release-review
```

- [ ] **Step 2: Verify it appears in the skill list**

```bash
ls ~/.claude/skills/
```

Expected: `release-review` appears alongside `review`, `commit`, etc.

- [ ] **Step 3: Run the filter to confirm end-to-end plumbing**

```bash
python3 ~/gitcode/amitayud-claude-world/skills/release-review/scripts/review.py \
  filter ~/R138.csv | wc -l
```

Expected: count of unanswered NSProxy tickets printed, no errors.

- [ ] **Step 4: Push to remote**

```bash
cd ~/gitcode/amitayud-claude-world
git push origin master
```

---

### Task 6: First real run and fine-tuning log

This task is not code — it is the first invocation of the skill against `~/R138.csv` to discover what needs adjustment.

- [ ] **Step 1: Invoke the skill**

In a new Claude Code session, run:
```
/release-review ~/R138.csv
```

Accept the default risk criteria (press Enter at the menu).

- [ ] **Step 2: Record observations**

For each phase, note:
- Did the filter return the expected number of tickets?
- Did the category spotlight produce sensible results?
- For the first 3 tickets processed: were the drafted answers reasonable?
- Were PR lookups successful? Any `PR_NOT_FOUND`?
- Did the confidence annotations (`[T1]`/`[?]`) reflect reality?

- [ ] **Step 3: Create a fine-tuning notes file**

```bash
cat > ~/docs/superpowers/plans/release-review-tuning-notes.md << 'EOF'
# Release Review Skill — Fine-Tuning Notes

## Run 1 — Date: 2026-05-15

### Filter phase
- Tickets returned: 
- Issues observed: 

### Category spotlight
- Top categories shown:
- Issues observed:

### Per-ticket analysis (first 3 tickets)
- Ticket 1 (KEY): answers reasonable? PR found?
- Ticket 2 (KEY): answers reasonable? PR found?
- Ticket 3 (KEY): answers reasonable? PR found?

### What to fix before Run 2
-
EOF
```

- [ ] **Step 4: Apply fixes, commit, re-run**

Based on observations, edit `prompt.md` or `review.py`, commit, and run again. Repeat until results are satisfactory.

---

## Self-Review Against Spec

| Spec requirement | Covered by task |
|-----------------|----------------|
| Filter to NSProxy rows | Task 2 (filter subcommand) |
| Skip already-answered rows | Task 2 (needs_answers check) |
| Risk criteria menu with defaults | Task 4 (Phase 1) |
| Ad-hoc free-text criterion | Not yet — deferred to fine-tuning (Task 6) |
| Category spotlight with Jira query | Task 4 (Phase 2) |
| Tier 1/2/3 evidence hierarchy | Task 4 (Phase 3) |
| Confidence annotations [T1]/[T2]/[T3]/[?] | Task 4 (Phase 3b) |
| Flag detection via diff grep | Task 4 (Phase 3b) |
| Batch approval for low-risk | Task 4 (Phase 4) |
| Per-ticket approval for high-risk | Task 4 (Phase 4) |
| Write answers to CSV | Task 3 (write subcommand) |
| Convert to XLSX | Task 3 (convert subcommand) |
| Print upload instructions | Task 4 (Phase 5) |
| Symlink to ~/.claude/skills | Task 5 |

**Deferred (not in v1, intentional):**
- Ad-hoc free-text criteria (Phase 1 menu item for free text) — add in Task 6 fine-tuning if needed
- Permanent new criterion PR request message — add to prompt.md end-of-session text in fine-tuning
