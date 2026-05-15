# release-review skill

A Claude Code skill that helps a second reviewer fill in release-readiness answers for NSProxy tickets in a release tracking spreadsheet.

## What it does

For each NSProxy ticket in a release CSV that still has unanswered release-readiness fields, the skill:
1. Fetches the Jira ticket and associated PR
2. Reads the PR diff, description, and review comments
3. Drafts answers to 8 release-readiness questions
4. Presents them to you for approval
5. Writes approved answers back into the CSV and converts it to XLSX for upload

## Setup

1. Clone this repo and ensure the skill is linked into Claude Code:
   ```bash
   ln -s ~/gitcode/amitayud-claude-world/skills/release-review ~/.claude/skills/release-review
   ```

2. Install Python dependencies:
   ```bash
   pip install pandas openpyxl
   ```

3. Ensure Jira CLI credentials are configured (see `eng-skills:jira` skill for setup).

4. Ensure GitHub CLI is authenticated:
   ```bash
   gh auth status
   ```

## Usage

```
/release-review <path-to-csv>
```

Example:
```
/release-review ~/R138.csv
```

Output file: `~/R138-reviewed.xlsx` (same directory, `-reviewed.xlsx` suffix).

---

## What the skill asks you

The skill pauses at four points and waits for your input. Here is what to expect at each:

### Pause 1 — Risk criteria menu (Phase 1)

The skill presents the criteria it will use to classify a ticket as High-risk. Two criteria are always active. You can add more:

```
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

**What to do:** Press Enter to accept defaults, or type any combination of A/B/C/D to change which optional criteria are active. For example, typing `CD` activates C and D instead of A and B.

---

### Pause 2 — Category spotlight (Phase 2)

The skill queries Jira for past prod incidents per sub-component, scores categories by blast radius and recoverability, and shows the top 3 most dangerous ones:

```
Category spotlight — handle these with extra care:

  1. NSP-SSL (3 tickets) — blast radius: all tenants, incidents past year: 2
  2. NSP-Policy-Engine (7 tickets) — blast radius: all tenants, incidents past year: 1
  3. NSP-Session (2 tickets) — blast radius: subset, incidents past year: 0

Tickets in these categories will always get per-ticket review.
Press Enter to accept, or describe changes:
```

**What to do:** Press Enter to accept. Or type a change, for example: "remove NSP-Session, add NSP-Crypto instead".

---

### Pause 3 — Low-risk batch approval (Phase 4)

After analysing all tickets, the skill collects the Low-risk ones and shows them as a table:

```
Low-risk tickets (12) — drafted answers ready for batch approval:

KEY          | Risk | Regression | Flag | Rollback        | Confidence
ENG-974050   | Low  | No [T1]    | NO   | Revert the PR   | all T1
ENG-987249   | Low  | No [T1]    | NO   | Revert the PR   | all T1
...

[A] Approve all and write   [R] Review each individually   [S] Skip all
```

**What to do:**
- Type `A` to approve all Low-risk tickets in one go (recommended if confidence is all T1)
- Type `R` to step through each one individually with the same flow as High-risk tickets
- Type `S` to skip all Low-risk tickets (leaves their CSV columns unchanged)

---

### Pause 4 — High-risk per-ticket review (Phase 4)

Each High-risk ticket (and any Low tickets you chose to review individually) is shown one at a time:

```
━━━ ENG-961786: Change policy email notification default from address ━━━
PR: ENG-961786: Change default from address (#14123)  dataplane#14123
Files changed: 2  |  +18 −4 lines
Key files: libs/policy/email_notify.cpp, libs/policy/email_notify.hpp
Why High-risk: flag present (tenant FF: policy_notify_default_from_donotreply)

Drafted answers:
  Q1 Risk:         High [T1]
  Q2 Regression:   No [T1]
  Q3 Detail:
  Q4 Flag:         YES [T1]
  Q5 Flag default: Disabled [T1]
  Q6 Flag detail:  Tenant FF: policy_notify_default_from_donotreply, default disabled [T1]
  Q7 Rollback:     Disable the FF via tenant config [T1]
  Q8 Wiki:         https://netskope.atlassian.net/wiki/spaces/ENG/pages/...

[A] Approve   [E] Edit an answer   [S] Skip   [Q] Quit
```

**What to do:**
- Type `A` to approve this ticket's answers as drafted
- Type `E` to edit one answer — the skill will ask which question (1–8) and the new text
- Type `S` to skip this ticket (leaves its CSV columns unchanged)
- Type `Q` to stop processing and move immediately to writing whatever has been approved so far

---

## Confidence annotations

Each drafted answer carries a confidence annotation:

| Annotation | Meaning |
|-----------|---------|
| `[T1]` | Derived from PR diff, description, or review comments — high confidence |
| `[T2]` | Derived from parent Epic or Confluence page — medium confidence |
| `[T3]` | Derived from sibling PRs or historical incident signals — low confidence |
| `[?]`  | No evidence found — you must fill this in manually |

If an answer is marked `[?]`, consider editing it (option `E`) before approving.

---

## Output

After all approvals:

1. Approved answers are written into the CSV (columns 23–30) in place
2. The CSV is converted to `<input-stem>-reviewed.xlsx`
3. The skill prints the output path and a reminder to upload to the release tracking sheet:
   ```
   Output: ~/R138-reviewed.xlsx

   Next step: upload the XLSX to:
   https://docs.google.com/spreadsheets/d/10vOTPLLhV_xPBp8CobpNidSIk3SVH7-3aymUI9l9sfA/
   ```

Tickets you skipped are left unchanged in the CSV and will appear again on the next run.

---

## Design reference

- **Design spec:** `docs/specs/2026-05-14-release-readiness-review-skill-design.md`
- **Implementation plan:** `docs/plans/2026-05-15-release-review-skill.md`
- **Helper script:** `skills/release-review/scripts/review.py`
