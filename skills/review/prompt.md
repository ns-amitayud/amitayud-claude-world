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
