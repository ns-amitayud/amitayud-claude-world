# amitayud-claude-world

Shared Claude Code skills for code review within the netSkope GitHub organization.

## Skills

- `/review` — Auto-detects context and routes to the appropriate review skill. Supports language profiles, strictness levels, accurate line number resolution, pre-review background analysis, and gap coverage output.
- `/review-pr` — Performs an initial review of a PR.
- `/pr-reply-ad-hoc` — Fetches existing review comments on a PR and drafts responses for you to copy-paste.

## Setup

### Prerequisites

- [Claude Code](https://claude.ai/code) installed
- [GitHub CLI](https://cli.github.com/) installed and authenticated (`gh auth login`)

### Installation

```bash
git clone git@github.com:ns-amitayud/amitayud-claude-world.git ~/amitayud-claude-world
ln -s ~/amitayud-claude-world/skills/review ~/.claude/skills/review
ln -s ~/amitayud-claude-world/skills/review-pr ~/.claude/skills/review-pr
ln -s ~/amitayud-claude-world/skills/pr-reply-ad-hoc ~/.claude/skills/pr-reply-ad-hoc
```

### Usage

**Basic review:**
```
/review https://github.com/netSkope/dataplane/pull/12345
/review-pr https://github.com/netSkope/dataplane/pull/12345
/pr-reply-ad-hoc https://github.com/netSkope/dataplane/pull/12345
```

**With C++ language profile:**
```
/review https://github.com/netSkope/dataplane/pull/12345 --lang cpp
```

**With strictness level (`--lenient`, `--standard` (default), `--strict`):**
```
/review https://github.com/netSkope/dataplane/pull/12345 --lang cpp --strict
/review https://github.com/netSkope/dataplane/pull/12345 --lang cpp --lenient
```

### C++ Strictness Levels

| Level | Flag | Catches |
|---|---|---|
| Lenient | `--lenient` | UB, memory safety, data races, dangling refs |
| Standard | `--standard` | Above + raw `new`/`delete`, RAII leaks, Rule of Five, exception safety, bad casts |
| Strict | `--strict` | Above + const correctness, `override`, `explicit`, `[[nodiscard]]`, std algorithms, `noexcept`, header hygiene |

Checks are cumulative: `--strict` includes everything in `--standard` and `--lenient`.

### Pre-review Background Analysis

On each PR review, the skill checks for a saved background analysis at
`~/.claude/review-context/<owner>-<repo>-<pr-number>.md`. If none exists, it offers to
generate one by tracing the pre-PR dataflow in the changed files. The analysis is saved
automatically and reused on future reviews of the same PR — avoiding regeneration cost.

The background analysis contains:
- **Overview** of the pre-PR design
- **Stage-by-stage dataflow** with `file:line` citations
- **Identified gaps** in the existing design
- **Gap coverage table** in the review output mapping each gap to whether the PR addresses it

This makes the efficacy of the implementation and testing explicit to the reviewer.

### Accurate Line Numbers

All review comments cite actual file line numbers (resolved against the PR head SHA via
`gh api`), never diff-relative offsets.

### Updating

```bash
cd ~/amitayud-claude-world && git pull
```

No symlink changes needed after the initial setup — symlinks always point to the latest pulled content.
