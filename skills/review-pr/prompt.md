Perform an initial code review for the given PR URL within the netSkope GitHub organization.

Steps:
1. Fetch the PR metadata and diff using `gh pr view <URL>` and `gh pr diff <URL>`.
2. Identify the files changed and understand the scope of the change.
3. Review for correctness, security, performance, and maintainability — in that priority order.
4. For each concern: cite the specific file and line, explain what is wrong, and provide a concrete alternative.
5. Separate blocking concerns (must fix before merge) from suggestions (non-blocking improvements).
6. Summarize findings in a structured report: Blocking Issues → Suggestions → Positives.
