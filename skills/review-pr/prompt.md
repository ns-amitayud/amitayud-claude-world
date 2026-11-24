---
name: review-pr
description: Perform an initial code review for a given PR URL within the netSkope GitHub organization. Reviews correctness, security, performance, and maintainability, citing file/line and separating blocking from non-blocking. Use when invoked as /review-pr <URL>.
---

Perform an initial code review for the given PR URL within the netSkope GitHub organization.

Steps:
1. Fetch the PR metadata and diff using `gh pr view <URL>` and `gh pr diff <URL>`.
2. Identify the files changed and understand the scope of the change.
3. **Classify the diff for the relocation / hop gate.** The gate applies if either:
   - the diff moves a guard — a skip, strip, gate, validation, or flag check — from a
     condition-scoped site to a broader or "single definitional" site; or
   - the diff adds, relocates, or removes the write/read/strip of a security-sensitive
     header (credentials, identity, auth, or trust-minted headers such as
     `Authorization`, `Proxy-Authorization`, `X-NS-*`).
4. Review for correctness, security, performance, and maintainability — in that priority order.
5. For each concern: cite the specific file and line, explain what is wrong, and provide a concrete alternative.
6. **If the gate applies, produce a Consolidation / Hop Analysis before any verdict:**
   - Old site → new site.
   - Every production caller of the old enclosing function.
   - Every implementation / configuration / listener that can reach the new site
     (e.g. `grep -rn "public I.*ModuleEngine"`, `grep -rn "new .*Engine("`).
   - Delta set: the paths the relocation newly covers, obtained by subtracting the two lists.
   - Precondition per delta path: what the old guard implicitly guaranteed (e.g. "consumer X
     already parsed the header"), and whether it still holds at the new site.
   - Hop matrix: hop → who writes → who reads → who strips → when.
   - Hop-coverage test: which test drives which engine/listener implementation.
   - **Approval gate:** if any delta path fails its precondition, or shared code has no test
     through a second engine/listener, the verdict is at most REQUEST CHANGES.
   Precedent: PR #17449 proved "every mod-chain flow reaches the shared serializer" but never
   checked "every serializer egress already ran the consumer." The strip then fired on the
   EP→worker relay hop, where DAPII never runs, and silently broke identity parsing. No test
   exercised the second engine.
7. Separate blocking concerns (must fix before merge) from suggestions (non-blocking improvements).
8. Summarize findings in a structured report: Blocking Issues → Suggestions → Positives →
   Consolidation / Hop Analysis (when the gate applies).
