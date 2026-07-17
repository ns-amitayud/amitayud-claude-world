# raise-pr Bug-Fix Flow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the `raise-pr` skill a second, lightweight PR-description path for
standalone bug fixes (no spec file, no design contracts), while keeping the existing
spec/contract-based path fully intact, and add a causal-evidence checklist item that
would have caught the two gaps found in PR #15752's description.

**Architecture:** Single-file skill-definition edit. No application code, no tests in
the pytest/gtest sense — the "tests" here are structural (grep/diff checks that the
markdown file has the right sections, in the right order, with the removed/added text
exactly matching spec) plus a final full-file read-through.

**Tech Stack:** Markdown skill definition (`SKILL.md`), edited via the `Edit` tool,
committed to the `~/.claude` git repo (remote: `netSkope/amitayud-claude`).

## Global Constraints

- Target file: `/home/amitayu/.claude/skills/raise-pr/SKILL.md` (tracked in the
  `~/.claude` git repo, remote `netSkope/amitayud-claude`).
- The existing contract-based flow (current Steps 1–5, 2.5, 2.6, 3.5, 3.6) must remain
  **byte-for-byte unchanged** except for the Prerequisite section itself. Do not
  reword, reformat, or "clean up" anything outside the sections this plan touches.
- New content must match the design doc
  (`/home/amitayu/gitcode/amitayud-claude-world/docs/superpowers/specs/2026-07-17-raise-pr-bugfix-flow-design.md`)
  verbatim for: the Step 2.7 body (including the "Baseline failure (PR-15752)"
  paragraph) and the bug-fix PR description template. Do not paraphrase these.
- New section headers use the same `##`/`###` markdown levels as the surrounding
  existing sections (see file structure below) — don't introduce a new heading depth.

## File Structure

Single file touched:

- Modify: `/home/amitayu/.claude/skills/raise-pr/SKILL.md`
  - `## Prerequisite` (currently lines 23–32) — replaced with the branch logic.
  - New `## Bug-Fix Flow` section — inserted immediately after the existing
    `### Step 5 — Link spec file in PR description (optional but recommended)`
    section and before `## What makes a good PR description` (i.e., before current
    line 397). Contains: the step-mapping table, `### Step 2.7 — Causal-evidence
    check`, the bug-fix `### Step 3 (bug-fix template) — Compose the PR description`,
    and `## What makes a good bug-fix PR description`.

No other files change. This plan has one cohesive deliverable (the edited skill file),
split into tasks by section so each is independently reviewable, plus a final
consistency-check task.

---

### Task 1: Replace the Prerequisite section with the branch logic

**Files:**
- Modify: `/home/amitayu/.claude/skills/raise-pr/SKILL.md:23-32`

**Interfaces:**
- Consumes: nothing (first edit).
- Produces: a `## Prerequisite` section whose content Task 2/3 do not depend on
  structurally (Task 2 inserts elsewhere in the file), but which must remain
  consistent in spirit with the new `## Bug-Fix Flow` section added in Task 2 (the
  branch's "Bug fix" arm must point at the section Task 2 creates).

- [ ] **Step 1: Read the current Prerequisite section to confirm exact text before editing**

Run:
```bash
sed -n '23,32p' /home/amitayu/.claude/skills/raise-pr/SKILL.md
```
Expected output (must match exactly, otherwise stop and re-sync line numbers before
editing):
```
## Prerequisite

A spec file must exist at:
```
~/docs/superpowers/specs/<date>-<jira-id>-<short-name>-design.md
```

If no spec file exists, run the **capture-design-context** skill first.
Do not proceed without it — a PR description without design context is
incomplete.
```

- [ ] **Step 2: Replace the Prerequisite section**

Use the `Edit` tool on `/home/amitayu/.claude/skills/raise-pr/SKILL.md` with:

old_string:
```
## Prerequisite

A spec file must exist at:
```
~/docs/superpowers/specs/<date>-<jira-id>-<short-name>-design.md
```

If no spec file exists, run the **capture-design-context** skill first.
Do not proceed without it — a PR description without design context is
incomplete.
```

new_string:
```
## Prerequisite

Determine which flow applies before doing anything else:

```
Does a spec file exist at
~/docs/superpowers/specs/<date>-<jira-id>-<short-name>-design.md ?
├─ Yes → Contract-based flow (Steps 1-5 below)
└─ No  → Ask the implementer:
          "No spec file found. Is this a standalone bug fix (no new design
           decisions, no spec expected), or should capture-design-context
           run first?"
          ├─ Bug fix        → Bug-Fix Flow (see "## Bug-Fix Flow" below)
          └─ Needs a spec   → run capture-design-context, then
                               Contract-based flow (Steps 1-5 below)
```

The fork is a direct question to the implementer, not inferred from the
diff — a feature change must not silently slip through the lighter
bug-fix template by omission.
```

- [ ] **Step 3: Verify the replacement landed correctly and nothing else moved**

Run:
```bash
sed -n '1,50p' /home/amitayu/.claude/skills/raise-pr/SKILL.md | grep -n "^##\|Bug fix\|Bug-Fix Flow"
```
Expected: `## Prerequisite` still present, followed by the new branch text containing
`Bug-Fix Flow`, and the next heading after it is still `## Workflow` (confirm with):
```bash
grep -n "^## Workflow" /home/amitayu/.claude/skills/raise-pr/SKILL.md
```
Expected: exactly one match, at or near its original position (line ~34 give or take
the size difference from this edit — a few lines later is expected and fine).

- [ ] **Step 4: Commit**

```bash
cd /home/amitayu/.claude
git add skills/raise-pr/SKILL.md
git commit -m "feat(skills/raise-pr): branch prerequisite into contract vs bug-fix flow

Replaces the hard 'spec file required' gate with an explicit question:
route to the existing contract-based flow if a spec exists, otherwise
ask whether this is a standalone bug fix (routes to the new Bug-Fix
Flow, added in a follow-up commit) or needs capture-design-context
run first.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 2: Add the `## Bug-Fix Flow` section

**Files:**
- Modify: `/home/amitayu/.claude/skills/raise-pr/SKILL.md` — insert a new section
  immediately before `## What makes a good PR description`.

**Interfaces:**
- Consumes: the `## Prerequisite` branch text from Task 1, which references
  `"## Bug-Fix Flow" below` — this task's new section header must be named exactly
  `## Bug-Fix Flow` so that reference resolves.
- Produces: `## Bug-Fix Flow` section containing the step-mapping table,
  `### Step 2.7 — Causal-evidence check`, `### Step 3 (bug-fix template) — Compose
  the PR description`, and `## What makes a good bug-fix PR description`. Task 3's
  verification depends on all four of these headings existing with this exact text.

- [ ] **Step 1: Locate the exact insertion point**

Run:
```bash
grep -n "^### Step 5 — Link spec file\|^## What makes a good PR description" /home/amitayu/.claude/skills/raise-pr/SKILL.md
```
Expected: two matches. Note the line number of `## What makes a good PR description`
— the new section is inserted directly before it.

- [ ] **Step 2: Read the few lines immediately before the insertion point to anchor the edit**

Run:
```bash
grep -n -B3 "^## What makes a good PR description" /home/amitayu/.claude/skills/raise-pr/SKILL.md
```
This confirms the exact preceding text (should be the end of the Step 5 section,
ending in the sentence about future reviewers/bisect investigations finding the full
architectural context) so the `Edit` tool's `old_string` anchors uniquely.

- [ ] **Step 3: Insert the Bug-Fix Flow section**

Use the `Edit` tool on `/home/amitayu/.claude/skills/raise-pr/SKILL.md` with:

old_string:
```
This allows future reviewers and bisect investigations to find the full
architectural context.

## What makes a good PR description
```

new_string:
```
This allows future reviewers and bisect investigations to find the full
architectural context.

## Bug-Fix Flow

Used when the Prerequisite branch above resolves to "bug fix." Reuses the
mechanical steps from the contract-based flow that have nothing to do with
specs; skips the spec-dependent ones; replaces Step 3's template and adds a
new Step 2.7 in place of Step 2.6.

| Step | Contract-based flow | Bug-fix flow |
|---|---|---|
| 1 — Understand the diff | `git diff`/`git log` against base | Unchanged — run Step 1 above verbatim |
| 2 — Read the spec | Load spec, select deliverables/contracts | Skipped — no spec |
| 2.5 — Run affected tests | Build + run every test binary linking the changed libs | Unchanged — run Step 2.5 above verbatim |
| 2.6 — Document non-trivial design decisions | Trigger table (new enum, ordered enum, overlapping flags, etc.) | Skipped — no new mechanism is being introduced by a bug fix |
| 2.7 — Causal-evidence check | *(does not exist in this flow)* | New — see below |
| 3 — Compose PR description | Contracts template | New template — see below |
| 3.5 / 3.6 — Diagrams, HLD footer | From spec's Diagrams section | Skipped — no spec, no HLD |
| 4 — Push and open PR | `git push` + `gh pr create --draft ...` | Unchanged — run Step 4 above verbatim |
| 5 — Link spec in PR description | Footer linking spec file | Skipped — no spec |

### Step 2.7 — Causal-evidence check

For every claim in the Problem/Reachability/Safety-of-the-fix sections, apply:

1. **Causal chain, not disconnected facts.** If the description states a
   root cause and an effect, the mechanism connecting them must be explicit.
   Ask: "why does A lead to B?" If the description doesn't answer that in
   its own text, it's incomplete.

2. **Reachability claims need a cited call chain.** "Reachable by any end
   user" / "attacker-controlled" / similar claims must show the file:line
   path from external input to the vulnerable code, not just assert it.

3. **Safety claims about a callee need a citation.** If the fix's
   correctness depends on some other function's behavior (copy semantics,
   ownership, null-safety), cite that function's file:line. Do not reason
   about a callee's contract without showing it.

**The test:** A reviewer who has never read the code should be able to
verify each causal/reachability/safety claim from the citations alone,
without independently deriving or tracing the code themselves.

**Baseline failure (PR-15752):** The original description stated
"undercounted the buffer... whenever the first character needed encoding"
and separately "wrote past the start... corrupting heap metadata" as two
facts with no connecting sentence — a reviewer had to independently trace
the encoder's per-character write loop to find that the missing link was
"no bounds check between the individual bytes of one entity's write."
It also asserted "reachable by any end user" and "ns_template_tagmap_add()
copies the value in" with no file:line for either. Step 2.7 exists to
prevent this.

### Step 3 (bug-fix template) — Compose the PR description

Use this template instead of the contract-based one. Only include sections
with meaningful content.

```markdown
## Problem

<State the defect as a causal chain: root cause → mechanism → observable
effect. Each link must be explicit — do not state cause and effect as two
disconnected facts. See Step 2.7's baseline failure.>

## Reachability

<How does an external input/user actually reach the buggy code path? Cite
file:line for the call chain. If the answer is "any end user," show the
chain that makes that true — don't assert it.>

## Fix

<What changed and why this approach closes the bug class rather than just
the instance, if applicable.>

## Safety of the fix

<If the fix relies on a claim about another function's behavior (e.g. "X
copies the value in, so Y doesn't need to outlive Z"), cite file:line of
that function's actual implementation. Do not assert callee behavior
without showing it.>

## Tests

<New/modified tests and what regression class each covers.>

## Notes

<Anything else: superseded PRs, unrelated build fixes bundled in, etc.>
```

## What makes a good bug-fix PR description

Parallel to "What makes a good PR description" below, for the bug-fix flow.
A reviewer who has never read the code should be able to answer from the
description alone:

- What is the defect, and what mechanism turns the root cause into the
  observable failure?
- How does an external input reach the vulnerable code path, with
  citations?
- Does the fix's correctness depend on another function's behavior, and is
  that behavior shown, not just asserted?
- What test(s) cover the regression class, not just the one reported
  instance?

If the reviewer needs to independently trace code to answer any of these,
the description is incomplete — send it back through Step 2.7 before
opening the PR.

## What makes a good PR description
```

Note: the `old_string` above includes the original `## What makes a good PR
description` heading at the end, and the `new_string` reproduces it again after the
new content — this is deliberate so the original heading and everything after it
(unchanged) is preserved immediately following the new section.

- [ ] **Step 4: Verify the new section landed with correct heading order and nothing after it shifted content**

Run:
```bash
grep -n "^## Bug-Fix Flow$\|^### Step 2.7 — Causal-evidence check$\|^### Step 3 (bug-fix template)\|^## What makes a good bug-fix PR description$\|^## What makes a good PR description$\|^## Relationship to Other Skills$" /home/amitayu/.claude/skills/raise-pr/SKILL.md
```
Expected: six matches, in this order top to bottom:
1. `## Bug-Fix Flow`
2. `### Step 2.7 — Causal-evidence check`
3. `### Step 3 (bug-fix template) — Compose the PR description`
4. `## What makes a good bug-fix PR description`
5. `## What makes a good PR description`
6. `## Relationship to Other Skills`

- [ ] **Step 5: Confirm the Step 2.7 baseline-failure paragraph matches the design doc verbatim**

Run:
```bash
diff <(sed -n '/^\*\*Baseline failure (PR-15752):\*\*/,/prevent this\.$/p' /home/amitayu/.claude/skills/raise-pr/SKILL.md) \
     <(sed -n '/^\*\*Baseline failure (PR-15752):\*\*/,/prevent this\.$/p' /home/amitayu/gitcode/amitayud-claude-world/docs/superpowers/specs/2026-07-17-raise-pr-bugfix-flow-design.md)
```
Expected: no output (empty diff — the paragraphs are byte-identical). If this prints a
diff, fix the `SKILL.md` text to match the design doc exactly before proceeding.

- [ ] **Step 6: Commit**

```bash
cd /home/amitayu/.claude
git add skills/raise-pr/SKILL.md
git commit -m "feat(skills/raise-pr): add Bug-Fix Flow with Step 2.7 causal-evidence check

Adds the lightweight bug-fix path referenced by the Prerequisite branch:
reuses Steps 1/2.5/4 verbatim, skips the spec-dependent steps, and
replaces Step 2.6/Step 3 with a new causal-evidence check (Step 2.7)
and a Problem/Reachability/Fix/Safety-of-the-fix/Tests/Notes template.

Motivated by PR #15752 (ENG-1077643): the original PR description
stated root cause and effect as disconnected facts and asserted
reachability/callee-safety claims with no file:line evidence.

Design: docs/superpowers/specs/2026-07-17-raise-pr-bugfix-flow-design.md
(amitayud-claude-world repo)

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 3: Full-file consistency check

**Files:**
- Read only: `/home/amitayu/.claude/skills/raise-pr/SKILL.md`

**Interfaces:**
- Consumes: the fully edited file from Tasks 1–2.
- Produces: nothing new — this is a verification-only task with no further
  downstream consumer.

- [ ] **Step 1: Confirm the contract-based flow is untouched outside the Prerequisite section**

Run:
```bash
cd /home/amitayu/.claude
git diff HEAD~2 -- skills/raise-pr/SKILL.md | grep "^-" | grep -v "^--- "
```
Expected: every removed line (`-` prefixed) belongs only to the old Prerequisite
section text from Task 1's `old_string`. If any line from the contract-based Steps
1–5, 2.5, 2.6, 3.5, or 3.6 sections shows up as removed, stop — something outside
scope was altered; revert and redo the edit with a narrower `old_string`.

- [ ] **Step 2: Confirm markdown table in `## Bug-Fix Flow` has consistent column count**

Run:
```bash
awk '/^\| Step \| Contract-based flow \| Bug-fix flow \|$/{p=1} p{print; c++} p&&c==11{exit}' /home/amitayu/.claude/skills/raise-pr/SKILL.md | awk -F'|' '{print NF}'
```
Expected: every printed line has the same field count (`NF`) as the header row —
confirms no row lost or gained a `|` delimiter during the edit.

- [ ] **Step 3: Read the full file once end-to-end**

Use the `Read` tool on `/home/amitayu/.claude/skills/raise-pr/SKILL.md` (no
offset/limit — full file) and confirm by eye:
- The Prerequisite branch reads naturally as a continuation of the file's existing
  voice (imperative, second-person-implicit instructions to the agent executing the
  skill).
- `## Bug-Fix Flow`'s step-mapping table correctly cross-references step numbers that
  exist elsewhere in the file (Step 1, 2.5, 4 in the contract-based `## Workflow`
  section).
- No duplicate anchor text that would make an internal reference ambiguous (e.g. two
  headings with identical exact text).

- [ ] **Step 4: Push**

```bash
cd /home/amitayu/.claude
git push origin master
```

(Adjust branch name if `~/.claude`'s default branch is not `master` — check with
`git branch --show-current` first if unsure.)

## Self-Review Notes

- **Spec coverage:** Design doc Section 1 (prerequisite branch) → Task 1. Section 2
  (step mapping) → Task 2's table. Section 3 (bug-fix template) → Task 2's Step 3
  insertion. Section 4 (Step 2.7) → Task 2's Step 2.7 insertion. The design's "What
  Makes a Good Bug-Fix PR Description" closing section → Task 2's `## What makes a
  good bug-fix PR description`. All design sections have a corresponding task.
- **Placeholder scan:** no TBD/TODO in any inserted text; every template field is a
  concrete `<...>` prompt matching the design doc's own placeholder style, not a plan
  placeholder.
- **Type consistency:** N/A (markdown skill file, no code types) — but heading text is
  cross-checked in Task 2 Step 4 and Task 3 Step 3 for exact-match consistency between
  the Prerequisite's forward reference (`"## Bug-Fix Flow" below`) and the actual new
  heading.
