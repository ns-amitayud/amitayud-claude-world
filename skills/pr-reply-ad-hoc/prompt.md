Respond to existing review comments on the given PR URL within the netSkope GitHub organization.

Steps:
1. Fetch existing review comments using `gh api repos/netSkope/<repo>/pulls/<number>/comments`.
2. For each unresolved comment: read the comment, locate the referenced code, and formulate a precise response.
3. Responses should either: acknowledge and explain a fix, push back with technical justification, or ask a clarifying question.
4. Do not blindly agree with every comment — apply the same operating principles used during review.
5. Present all draft responses for the author to review and copy-paste. Do not post responses directly to GitHub.
