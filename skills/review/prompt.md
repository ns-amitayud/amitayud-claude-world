---
name: review
description: Use when reviewing a PR URL, branch name, or file path for correctness, security, performance, and style. Supports language profiles and strictness levels (e.g. --lang cpp --strict). Triggers on /review commands or requests to review code changes.
---

## Parse arguments

Extract from `$ARGUMENTS`:
- **Target**: PR URL, PR number, branch name, or file path (required)
- **`--lang <language>`**: Language profile to apply. Supported: `cpp`. If omitted, apply general review only.
- **`--strict` / `--standard` / `--lenient`**: Strictness level. Default: `--standard`.

Examples:
```
/review https://github.com/org/repo/pull/123
/review https://github.com/org/repo/pull/123 --lang cpp
/review https://github.com/org/repo/pull/123 --lang cpp --strict
/review feature/my-branch --lang cpp --lenient
```

---

## Fetch PR context

If the argument looks like a PR URL or PR number:
1. Run `gh pr view <url-or-number>` to get title, description, and metadata
2. Run `gh pr diff <url-or-number>` to get the full diff
3. Run `gh pr comments <url-or-number>` (or `gh api .../comments`) to check for existing unresolved review comments

If the argument is a branch name, run `git diff main...<branch>` (or appropriate base branch).

If the argument is a file path, read the file directly.

## Resolve line numbers

After fetching the diff, resolve all cited line numbers to actual file line numbers:

1. Get the PR head SHA:
   ```
   gh api repos/<owner>/<repo>/pulls/<number> --jq '.head.sha'
   ```

2. For each file you intend to cite in the review, fetch it at the head SHA and grep for the relevant code:
   ```
   gh api repos/<owner>/<repo>/contents/<filepath>?ref=<sha> \
     --jq '.content' | base64 -d | grep -n "<pattern>"
   ```

3. Use the line numbers from step 2 in all review comments. Never cite diff-relative line numbers.

> This step is required whenever the target is a PR URL. Skip for branch or file path reviews.

---

## Pre-review context (PR URL only)

Before reviewing, check whether a saved background analysis of the pre-PR design exists.

### Step 1 — Check for saved context

```
ls ~/.claude/review-context/<owner>-<repo>-<pr-number>.md
```

- If the file **exists**: ask the reviewer: *"Background analysis found for PR \<number\>. Load it? (Y/N)"*. If Y, read and present it before proceeding to the review.
- If the file **does not exist**: ask the reviewer: *"No background analysis found. Generate one? This traces the pre-PR dataflow in the changed files to show which gaps the PR addresses. (Y/N)"*.

### Step 2 — Generate (if requested)

1. Get the list of changed files from the diff already fetched.
2. Get the PR base SHA:
   ```
   gh api repos/<owner>/<repo>/pulls/<number> --jq '.base.sha'
   ```
3. For each changed file, read the **base branch** version at that SHA:
   ```
   gh api repos/<owner>/<repo>/contents/<filepath>?ref=<base-sha> \
     --jq '.content' | base64 -d
   ```
4. Trace the relevant data/control flow in the changed areas:
   - What data enters, how it flows, what decisions depend on it.
   - Where the design has gaps or relies on untrusted inputs.
5. Produce a structured document with these sections:
   - **Overview**: one paragraph describing the pre-PR design
   - **Stage-by-stage dataflow**: numbered stages with `file:line` citations
   - **Identified gaps**: numbered list of specific problems in the pre-PR design
   - **What the PR claims to address**: map PR description to the gaps above

### Step 3 — Save automatically after generation

```
mkdir -p ~/.claude/review-context
# write the document to:
~/.claude/review-context/<owner>-<repo>-<pr-number>.md
```

Inform the reviewer: *"Background analysis saved to `~/.claude/review-context/<owner>-<repo>-<pr-number>.md` — will be loaded automatically on future reviews of this PR."*

> Skip this entire section for branch name or file path reviews.

---

## Language profile: C++ (`--lang cpp`)

Apply this profile when `--lang cpp` is specified. Checks are cumulative across levels.

### `--lenient` — Safety-critical only (always apply as a baseline)
Flag as **Critical** (must fix):
- Undefined behavior: out-of-bounds access, null dereference, uninitialized variables, signed integer overflow
- Memory safety: use-after-free, double-free, buffer overflows
- Data races and thread-safety violations without synchronization
- Dangling references or pointers returned from functions

### `--standard` (default) — Idiomatic modern C++
Everything in `--lenient`, plus flag as **Minor** (should fix):
- Raw owning `new`/`delete` — prefer `std::unique_ptr` / `std::shared_ptr`
- Resource leaks (files, sockets, locks) not managed via RAII
- Missing Rule of Five: if a destructor, copy constructor, copy assignment, move constructor, or move assignment is user-defined, all five should be considered
- Exception safety: constructors/assignments should provide at least the basic guarantee
- `NULL` or `0` used instead of `nullptr`
- `reinterpret_cast` without a clear justification comment
- C-style casts `(Type)expr` — prefer `static_cast`, `const_cast`, etc.

### `--strict` — Enforce all C++ idioms
Everything in `--standard`, plus flag as **Suggestions** (optional but idiomatic):
- Const correctness: member functions that don't mutate state should be `const`; pass by `const&` where appropriate; use `constexpr` for compile-time constants
- Virtual functions without `override` or `final` in derived classes
- Single-argument constructors without `explicit` (risk of implicit conversions)
- `[[nodiscard]]` missing on functions whose return value is meaningful (e.g. error codes, allocated resources)
- Raw loops where a `std::` algorithm (`std::transform`, `std::find_if`, etc.) would be clearer
- `using namespace std` in headers
- C-style arrays — prefer `std::array` or `std::vector`
- Functions that cannot throw but lack `noexcept`
- `std::endl` used instead of `'\n'` (flushes unnecessarily)

---

## Route to sub-skill

Determine which review skill to invoke for the given PR URL:
- If the PR has no existing review comments, invoke the `review-pr` skill.
- If the PR has existing unresolved review comments, invoke the `pr-reply-ad-hoc` skill.

Always use the Skill tool to invoke the appropriate skill rather than performing review steps manually.

Operating principles (apply to both sub-skills):
- Focus feedback on correctness, security, performance, and maintainability — in that priority order.
- Be precise about what needs to change and why. Cite specific lines and provide concrete alternatives.
- Distinguish blocking concerns from suggestions. Not everything needs to gate a merge.
- Respect the author's design intent; critique the implementation, not the approach, unless the approach is fundamentally flawed.

## Output format

```
## Summary
[One paragraph overview]

## Issues
### Critical
- file:line — [Must fix before merge]

### Minor
- file:line — [Should fix, not blocking]

### Suggestions
- file:line — [Optional improvements]

## Gap Coverage
(Include only when background analysis was loaded or generated)

| Gap (pre-PR design) | Addressed by PR? | Notes |
|---------------------|-----------------|-------|
| [gap from background analysis] | Yes / Partially / No | [which change covers it, or why not] |

If the PR introduces new gaps or regressions relative to the pre-PR design, note them here.

## Verdict
APPROVE / REQUEST CHANGES / NEEDS DISCUSSION
```
