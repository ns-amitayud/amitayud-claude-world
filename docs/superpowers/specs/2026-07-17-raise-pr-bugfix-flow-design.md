# raise-pr: Bug-Fix Flow — Design

**Date:** 2026-07-17
**Author:** Amitayu Das
**Status:** Approved, pending implementation
**Skill affected:** `raise-pr` (`~/.claude/skills/raise-pr/SKILL.md`)
**Motivated by:** Review of `netSkope/dataplane` PR #15752 (ENG-1077643 — heap buffer
underflow in `ns_get_sanitized_url()`)

---

## Problem Statement

`raise-pr` currently has a single hard prerequisite: a spec file must exist at
`~/docs/superpowers/specs/<date>-<jira-id>-<short-name>-design.md`, produced by
`capture-design-context`. Its PR description template is built entirely around that
spec — "Design contracts implemented," "Design contracts deferred," "Proxy mode
applicability," diagrams derived from the spec's node graph, an HLD appendix footer.

This is the right shape for **feature PRs** that flow through the
`deliver-epic` → `capture-design-context` → `deliver-story` → `raise-pr` pipeline.
It is the wrong shape for a **standalone bug fix**: a bug fix has no design contracts
to select, no "what this ticket delivers" deliverable list, and forcing one through
`capture-design-context` first would fabricate design artifacts for a change that has
no design decision to record — only a defect, a mechanism, and a fix.

Reviewing PR #15752 (not authored via any of these skills) surfaced what a bug-fix
description needs that a feature-contract description doesn't: **causal-evidence
discipline**. That PR's Problem section was factually accurate but had two classes of
gap that a spec-contract template would not have caught, because they are specific to
describing a defect rather than a design decision:

1. **Disconnected cause and effect.** The description stated the root cause
   ("undercounted the buffer... whenever the first character needed encoding") and the
   effect ("wrote past the start... corrupting heap metadata") as two separate facts
   with no sentence connecting them. A reviewer had to independently trace the
   encoder's per-character write loop to discover the missing link: the multi-byte
   write for one entity has no bounds check *between* its own individual byte writes,
   so a miscounted first character causes the write to run past `output[0]` before the
   loop-level guard is re-checked.
2. **Unevidenced reachability and safety claims.** "This is reachable by any end user"
   and "`ns_template_tagmap_add()` copies the value in, so the encoded string only has
   to outlive that one call" were both asserted with no file:line citation. Both turned
   out to be true on inspection — but "true and unverifiable from the text alone" is
   exactly the gap this design closes.

Full detail on the PR itself, the adversarial-hypothesis-verification traces used to
confirm the root cause, and the corrected problem-statement wording are in the
conversation transcript that produced this design (not duplicated here — this doc is
about the skill fix, not the PR's specifics).

## Goal

Give `raise-pr` a second, lightweight path for bug-fix PRs that:
- Does not require a spec file or design contracts.
- Reuses every mechanical step that has nothing to do with specs (diff inspection,
  running affected tests, push/PR-open mechanics, title format).
- Enforces the same evidentiary discipline for causal/reachability/safety claims that
  Step 2.6 already enforces for non-trivial design decisions in the contract-based
  flow — modeled on that existing pattern (trigger → how to write it → the test →
  baseline failure), not invented from scratch.

## Non-Goals

- Not creating a second top-level skill. One skill, one entry point, branching by
  prerequisite.
- Not changing anything about the existing contract-based flow. Steps 1–5 as they
  exist today are unchanged and continue to run exactly as before when a spec file
  exists.
- Not attempting to auto-detect "is this a bug fix" from the diff shape. The fork is
  asked, not inferred (see Section 1), to avoid mis-routing an actual feature change
  through the lightweight template.

## Design

### Section 1 — Prerequisite branch

Replace the current hard gate:

> "If no spec file exists, run the **capture-design-context** skill first. Do not
> proceed without it — a PR description without design context is incomplete."

with:

```
Does a spec file exist at
~/docs/superpowers/specs/<date>-<jira-id>-<short-name>-design.md ?
├─ Yes → Contract-based flow (existing Steps 1-5, unchanged)
└─ No  → Ask the implementer:
          "No spec file found. Is this a standalone bug fix (no new design
           decisions, no spec expected), or should capture-design-context
           run first?"
          ├─ Bug fix        → Bug-fix flow (Section 2)
          └─ Needs a spec   → run capture-design-context, then
                               Contract-based flow
```

The fork is a direct question to the implementer, not inferred from the diff. This
keeps the existing spec-required path fully intact for every feature PR and adds an
explicit opt-in for fixes, so a feature change never silently slips through the
lighter template by omission.

### Section 2 — Bug-fix flow (step mapping)

Reuses the contract-based flow's mechanical steps; skips or replaces the
spec-dependent ones.

| Step | Contract-based flow | Bug-fix flow |
|---|---|---|
| 1 — Understand the diff | `git diff`/`git log` against base | **Unchanged, reused verbatim** |
| 2 — Read the spec | Load spec, select deliverables/contracts | **Skipped** — no spec |
| 2.5 — Run affected tests | Build + run every test binary linking the changed libs | **Unchanged, reused verbatim** — has nothing to do with specs |
| 2.6 — Document non-trivial design decisions | Trigger table (new enum, ordered enum, overlapping flags, etc.) | **Skipped** — no new mechanism is being introduced by a bug fix |
| 2.7 — Causal-evidence check | *(does not exist in this flow)* | **New** (Section 4) |
| 3 — Compose PR description | Contracts template | **New template** (Section 3) |
| 3.5 / 3.6 — Diagrams, HLD footer | From spec's Diagrams section | **Skipped** — no spec, no HLD |
| 4 — Push and open PR | `git push` + `gh pr create --draft ...` | **Unchanged, reused verbatim** |
| 5 — Link spec in PR description | Footer linking spec file | **Skipped** — no spec |

### Section 3 — Bug-fix PR description template

```markdown
## Problem

<State the defect as a causal chain: root cause → mechanism → observable
effect. Each link must be explicit — do not state cause and effect as two
disconnected facts. See baseline failure in Step 2.7.>

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

Only include sections with meaningful content, same convention as the contract-based
template.

### Section 4 — Step 2.7: Causal-evidence check

Inserted at the point in the bug-fix flow where Step 2.6 sits in the contract-based
flow (i.e., immediately before composing the PR description). Mirrors Step 2.6's
structure deliberately: trigger conditions → how to write it → the test → a named
baseline failure — so it reads as a native part of the skill, not a bolted-on rule.

```markdown
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
```

## What Makes a Good Bug-Fix PR Description

Parallel to the contract-based flow's existing closing checklist. A reviewer who has
never read the code should be able to answer from the description alone:

- What is the defect, and what mechanism turns the root cause into the observable
  failure?
- How does an external input reach the vulnerable code path, with citations?
- Does the fix's correctness depend on another function's behavior, and is that
  behavior shown, not just asserted?
- What test(s) cover the regression class, not just the one reported instance?

If the reviewer needs to independently trace code to answer any of these, the
description is incomplete — send it back through Step 2.7 before opening the PR.

## Open Questions / Deferred

- Whether a diff-shape heuristic (no new enum/flag/state → suggest bug-fix flow as the
  default answer to the Section 1 question) is worth adding later to reduce prompting
  friction. Deferred — asking explicitly is deliberately preferred for now (see
  Non-Goals).
- Whether Step 2.7's discipline should also apply retroactively when *reviewing*
  someone else's PR (i.e., a reviewer-side checklist item in `review`/`review-pr`).
  Out of scope for this design, which is authoring-side only per explicit scoping in
  this conversation.
