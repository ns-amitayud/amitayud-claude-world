# Release Readiness Review Skill — Design Spec
**Date:** 2026-05-14
**Author:** Amitayu Das
**Status:** Draft

---

## Problem

R138 (and future releases) have ~111 tickets going into a release. Each ticket has 8 release-readiness questions (risk level, regression, flags, rollback plan, etc.) that must be answered by someone other than the original dev — a "second reviewer." Today, only ~10% of tickets have these fields filled in. SREs and support need this information to safely manage the release and respond to incidents.

## Goal

A skill that processes the NSProxy rows of a release CSV, drafts answers to the 8 release-readiness questions for each ticket, routes them for human approval, writes the approved answers back into the CSV, converts the CSV to XLSX, and outputs a file ready for manual upload to the release tracking Google Sheet.

---

## Inputs

| Input | Source |
|-------|--------|
| Release CSV file | Path provided by user at invocation (e.g., `~/R138.csv`) |
| Release-readiness questions | Columns 23–30 of the CSV (see Appendix A) |
| Jira ticket data | Fetched live via Jira CLI (`jira issue <KEY>`) |
| PR diff + review comments | Fetched live via `gh pr view` and `gh api` |

---

## Questions the Skill Ponders

For each ticket, the skill works through 8 release-readiness questions. These questions are sourced directly from the column headers of the release tracking CSV (columns 23–30) and are reproduced in full in Appendix A. In brief:

- **Q1** Risk level (Low / Medium / High)
- **Q2** Regression introduced?
- **Q3** Regression impact details
- **Q4** Flag of any kind introduced?
- **Q5** Default state of the flag
- **Q6** Flag details
- **Q7** IMF / rollback action
- **Q8** Wiki link

Answers to these questions are what the skill drafts, presents for approval, and ultimately writes back into those same CSV columns.

---

## Write Target

Answers are written directly into columns 23–30 of the CSV file in place. After all approvals are collected, the skill:

1. Writes the approved answer strings into the correct CSV columns for each ticket row
2. Converts the updated CSV to XLSX using `pandas` + `openpyxl`
3. Saves the XLSX as `<original-name>-reviewed.xlsx` alongside the input CSV
4. Instructs the user to manually upload the XLSX to the Google Sheet at:
   `https://docs.google.com/spreadsheets/d/10vOTPLLhV_xPBp8CobpNidSIk3SVH7-3aymUI9l9sfA/`

**Why this target:** All 111 tickets are visible in one place, preserving the release team's existing workflow. No Jira custom field IDs are needed. The only manual step is the final upload.

**Con:** The upload is manual. If the sheet is edited between CSV export and upload, those edits will be overwritten for the NSProxy rows. Mitigant: run the skill promptly after export and communicate to the team before uploading.

## Column Map (CSV columns 23–30)

| Col | Question |
|-----|---------|
| 23 | Risk level |
| 24 | Regression? |
| 25 | Regression detail |
| 26 | Flag present? |
| 27 | Flag default state |
| 28 | Flag details |
| 29 | IMF/rollback action |
| 30 | Wiki link |

---

## Workflow

### Phase 1: Filter
1. Load the CSV
2. Filter rows where `Components` contains `nsproxy` (case-insensitive)
3. Skip rows where all 8 answer columns are already filled (already reviewed)
4. Report: "Found N NSProxy tickets, M already answered, processing K remaining"

### Phase 2: Per-ticket analysis
For each remaining ticket:

1. **Fetch Jira issue** — get summary, description, existing field values
2. **Find the PR** — search GitHub for a merged PR referencing the Jira key in its title or body
3. **Read the PR** — fetch diff, review comments, PR description
4. **Draft answers** to all 8 questions based on evidence from the above
5. **Classify risk tier:**
   - **High** if: Q4 (flag) = YES, OR Q2 (regression) = Yes, OR diff touches >5 files in hot paths (policy engine, session management, crypto, event dispatch)
   - **Low** otherwise

### Phase 3: Batch presentation and approval

**Low-risk batch:**
Present a compact table of all low-risk tickets with their drafted answers. Example:

```
Low-risk tickets (N) — review and approve batch write:

KEY          | Risk | Regression | Flag | Rollback         | Wiki
ENG-974050   | Low  | No         | NO   | Revert the PR    | —
ENG-987249   | Low  | No         | NO   | Revert the PR    | —
...

[Approve batch] or [Review individually] or [Skip]
```

User can approve the whole batch, drop into per-ticket review, or skip.

**High-risk tickets:**
Presented one at a time with full drafted answers and the evidence used (PR title, key changed files, review comment excerpts). User approves, edits, or skips each one before moving to the next.

### Phase 4: Write to CSV and convert to XLSX
After all approvals are collected (not per-ticket — one write pass at the end):
1. Write approved answers into columns 23–30 for each approved ticket row in the CSV
2. Leave unapproved/skipped rows unchanged
3. Convert the updated CSV to XLSX (`pandas` + `openpyxl`)
4. Save as `<original-name>-reviewed.xlsx` alongside the input file
5. Print: "Written N tickets. File ready at <path>. Upload to Google Sheet to publish."

---

## Risk Classification Rules (detail)

### Built-in criteria (always evaluated)

| Criterion | Tier |
|-----------|------|
| Flag present (Q4 = YES) | High — always |
| Regression risk (Q2 = Yes) | High — always |
| Diff touches policy engine, session mgmt, crypto, event dispatch | High |
| Dead code removal, config cleanup, test additions, doc changes | Low |
| Bug fix with narrow scope (1–3 files, no interface changes) | Low |
| Everything else | Medium → treat as High for routing |

Medium is treated as High (per-ticket review) to be conservative. If the volume of Mediums is too large after a real run, we can revisit.

### Flexible criteria — user-selectable at invocation time

At startup, before processing any tickets, the skill presents the second reviewer with a menu of additional criteria. The first two (flag, regression) are always active and cannot be deselected. The reviewer chooses zero or more additional ones:

```
High-risk gating criteria — always active:
  [✓] Flag present (FF/Staged Config/etc.)
  [✓] Regression risk

Optional additional criteria — select any to include:
  [ ] A. Diff touches >5 files
  [ ] B. Change in a hot-path component (policy engine, session mgmt, crypto, event dispatch)
  [ ] C. No rollback plan mentioned in PR or Jira
  [ ] D. PR has unresolved review comments at merge time

Press Enter to use defaults (A+B active, C+D inactive), or type letters to toggle (e.g. "CD" to activate C and D):
```

The defaults (A+B) reflect the current built-in rules. The reviewer can override for a specific release without changing the skill.

### Adding a new criterion not on the menu

Two paths:

1. **Ad-hoc (within the session):** The reviewer types a free-text criterion (e.g., "tickets that touch the VPN stack"). The skill treats it as a keyword/component filter applied to the diff and Jira summary. This is best-effort — the skill will say "I will flag any ticket whose diff or summary contains: VPN, vpn_stack, libvpn." Accuracy depends on the quality of the free-text match.

2. **Permanent (via repo maintainer):** If a criterion is wanted for all future releases, the reviewer files a request to the skill maintainer, who adds it as a named option in the menu. This is the clean path for criteria that are structurally well-defined (e.g., "touches IKE negotiation code").

The skill itself documents the request format at the end of a session: "To add a permanent criterion, open a PR to the skill definition with the criterion name, detection logic, and the tier it maps to."

---

## Category Importance: Spotlighting the Most Dangerous Tickets

Not all tickets carry equal blast radius. A single ticket in a critical category — even with only one member — can cause more customer harm than ten low-risk bug fixes. The skill identifies the K most important categories across the ticket set and calls them out explicitly before the review begins.

### How categories are formed

Each ticket is tagged to a category by the skill based on:
- The `Sub-Component` field (e.g., NSP-Policy-Engine, NSP-SSL, NSP-Session)
- Keywords in the Jira summary (e.g., "certificate", "auth", "decryption", "routing", "boot")
- Files touched in the PR diff (e.g., `ssl/`, `policy/`, `session/`, `cfw/`)

### How importance is gauged

Category importance is scored on three signals:

| Signal | Rationale |
|--------|-----------|
| **Customer blast radius** | Does a failure here affect all tenants or just some? (e.g., SSL termination = all, a specific app profile = subset) |
| **Recoverability** | Is a failure here self-healing or does it require manual SRE intervention? (e.g., config reload vs. service restart vs. rollback) |
| **Historical incident density** | Has this category caused prod incidents in recent releases? Queried live from Jira: recently resolved tickets with prod-incident labels, grouped by Sub-Component. |

For the first run, confirm the Jira label names used for prod incidents (see Open Questions). If the query returns no results, the score falls back to blast radius + recoverability only. The reviewer can also provide a list of "known hot categories" as free text at startup to manually boost their score.

### Output

Before processing individual tickets, the skill prints:

```
Category spotlight — handle these with extra care:

  1. NSP-SSL (3 tickets) — blast radius: all tenants, recoverability: service restart
  2. NSP-Policy-Engine (7 tickets) — blast radius: all tenants, recoverability: config reload
  3. NSP-Session (2 tickets) — blast radius: subset, recoverability: manual rollback

These categories will be routed to per-ticket review regardless of individual risk tier.
```

The reviewer can adjust the list before proceeding.

This spotlight is **release-specific** — the skill recomputes it from the actual ticket set each run, so R150 and R151 will produce different spotlights automatically.

---

## Deep Scrutiny: Evidence Sources for a Single Ticket

The quality of the drafted answers depends on how thoroughly the skill reads available evidence. The evidence hierarchy, from most to least reliable:

### Tier 1 — Always fetched
1. **Jira issue** — summary, description, existing field values, linked issues
2. **PR description** — the dev's own explanation of what changed and why
3. **PR diff** — the actual code change (files touched, lines added/removed)
4. **PR review comments** — reviewer observations, concerns raised, approvals

### Tier 2 — Fetched if Tier 1 leaves questions unanswered
5. **Linked Jira issues** — parent Epic, blocking/blocked-by tickets, related bugs. The Epic description often contains the HLD context and links to the design doc.
6. **Confluence pages linked from Jira** — the skill follows any Confluence URL in the Jira description or PR body and reads the page summary. This is where HLD, design decisions, and known limitations live.

### Tier 3 — Fetched only for High-risk or spotlight-category tickets
7. **Other PRs under the same Epic** — the skill looks up the parent Epic, finds all its child tickets across releases, and lists any PRs that touch the same files. This surfaces cross-PR interactions (e.g., "PR A changed the interface that PR B depends on, but PR B hasn't been merged yet").
8. **Historical Jira comments on the same component** — any `PROD-INCIDENT` or `customer-escalation` label on recently resolved tickets in the same sub-component. Signals "this area has burned us before."

### Why this matters

A reviewer reading only the diff sees *what* changed. Reading the Epic + Confluence HLD surfaces *why* the design is shaped this way, *what constraints* the developer was working under, and *what was deliberately left out*. A skill that surfaces "the HLD for this feature is at [link] and it explicitly says the fallback path is unimplemented until R140" gives the second reviewer something actionable — not just a diff summary.

### Confidence annotation

For each drafted answer, the skill annotates its confidence tier:

- `[T1]` — answer derived from PR diff/description/review comments (high confidence)
- `[T2]` — answer derived from Epic/Confluence (medium confidence — inferred)
- `[T3]` — answer derived from cross-PR or historical signals (low confidence — flagged for human)
- `[?]` — could not find evidence (human must fill)

The human second reviewer can immediately see which answers are solid and which need attention.

---

## PR Discovery Logic

The skill needs to find the PR for a given Jira key. Lookup order:

1. GitHub search: `gh api "search/issues?q=repo:netSkope/dataplane+<KEY>+is:pr+is:merged"`
2. GitHub search: `gh api "search/issues?q=org:netSkope+<KEY>+is:pr+is:merged"` (all repos)
3. If no PR found: mark as `PR_NOT_FOUND`, answer Q1–Q3 from Jira description alone, flag for human review

---

## Evidence-to-Answer Mapping

How the skill derives each answer from available data:

| Question | Primary evidence | Fallback |
|----------|-----------------|---------|
| Q1 Risk | Size of diff, files touched, component | Jira priority field |
| Q2 Regression | PR description, review comments mentioning "regression" | diff scope |
| Q3 Regression detail | Review comment excerpts | empty if Q2=No |
| Q4 Flag | grep diff for `StagedConfig`, `FeatureFlag`, `ff_`, `staged_config` | PR description |
| Q5 Flag default | grep diff for flag registration call, default value | PR description |
| Q6 Flag detail | Flag name, type, registration location in diff | empty if Q4=No |
| Q7 Rollback | PR description rollback section, review comments | "Revert the PR" as default |
| Q8 Wiki | Links in PR description or Jira description | empty |

---

## Skill Invocation

```
/r138-review ~/R138.csv
```

Or more generally:

```
/release-review <path-to-csv>
```

The skill is not hardcoded to R138 — it works on any release CSV that follows the same column schema.

---

## What the Skill Does NOT Do

- Does not write anything without explicit human approval
- Does not write to Jira (answers go into the CSV/XLSX only)
- Does not upload to Google Sheets (manual step by the user)
- Does not process non-NSProxy rows (other components are out of scope for now)
- Does not make judgment calls on ambiguous cases — it flags them for human review

---

## Open Questions

1. **Google Sheet overwrite risk**: If the sheet is edited between CSV export and XLSX upload, those edits in the NSProxy rows will be overwritten. Mitigant: communicate to the team before uploading and run promptly after export.

2. **Medium risk volume**: If the real run shows that 40% of tickets are classified Medium (and thus routed to per-ticket review), we may need to tune the classification rules or add a "quick approve" path for Mediums.

3. **PR not found**: ~10% of tickets may have no discoverable PR (e.g., Python/service-side changes, config-only changes in other repos). The fallback path (Jira description only) needs validation.

4. **CSV column schema stability**: This design assumes the R138 column layout. Future releases should verify the column indices haven't shifted before running.

5. **Historical incident density for category scoring**: The skill will query Jira live for recently resolved tickets with prod-incident labels in the NSProxy component (e.g., `labels in (PROD-INCIDENT, customer-escalation)`), grouped by Sub-Component. This requires confirming the actual label names used in the ENG project — if incidents are tracked differently (separate project, different label), the query needs adjustment before the first run.

6. **Confluence access in the skill**: Reading Tier 2 evidence requires the Confluence CLI (`eng-skills:confluence`). The skill must check that Confluence credentials are available at startup and gracefully skip Tier 2 if not, rather than failing mid-run.

7. **Ad-hoc free-text criterion quality**: When a reviewer adds a criterion like "tickets that touch the VPN stack" as free text, the skill's keyword match may miss tickets or produce false positives. This is acceptable for a first version but should be validated on a test run before relying on it for a real release.

---

## Appendix A: Release-Readiness Questions

These 8 questions are taken verbatim from the column headers of the release tracking CSV (columns 23–30). They represent the fields the second reviewer is responsible for filling in for each ticket.

| # | CSV Col | Question (verbatim from CSV header) |
|---|---------|--------------------------------------|
| Q1 | 23 | Risk Level — Change. To be Updated by Dev |
| Q2 | 24 | Does this change introduce any Regression? To be Updated by Dev |
| Q3 | 25 | Details on the Regression impact and callouts. To be Updated by Dev |
| Q4 | 26 | Does this ticket introduce ANY kind of Flag (FF/Staged Config/Global/Inside Library/X-ray/etc...)? To be Updated by Dev |
| Q5 | 27 | If yes, what is the default state of the flag Enable/Disable? To be Updated by Dev |
| Q6 | 28 | Details about the flags — Type, enablement/disablement, etc. To be Updated by Dev |
| Q7 | 29 | In case, if there is an IMF kind of situation or the change has wider/bigger impact, then what would be the appropriate action to take? And most importantly how? To be Updated by Dev |
| Q8 | 30 | Any Link to Wiki — more about the Ticket/Feature/etc. To be Updated by Dev |

The label "To be Updated by Dev" in the original headers reflects that the dev is the primary filler. The second reviewer role (this skill) is to independently verify and fill these fields where the dev has not, or to challenge the dev's self-assessment where they have.
