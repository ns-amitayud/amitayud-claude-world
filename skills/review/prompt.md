Determine which review skill to invoke for the given PR URL:
- If the PR has no existing review comments, invoke the `review-pr` skill.
- If the PR has existing unresolved review comments, invoke the `pr-reply-ad-hoc` skill.

Always use the Skill tool to invoke the appropriate skill rather than performing review steps manually.

Operating principles (apply to both sub-skills):
- Focus feedback on correctness, security, performance, and maintainability — in that priority order.
- Be precise about what needs to change and why. Cite specific lines and provide concrete alternatives.
- Distinguish blocking concerns from suggestions. Not everything needs to gate a merge.
- Respect the author's design intent; critique the implementation, not the approach, unless the approach is fundamentally flawed.
