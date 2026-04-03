# amitayud-claude-world

Shared Claude Code skills for code review within the netSkope GitHub organization.

## Skills

- `/review` — Auto-detects context and routes to the appropriate review skill. Supports language profiles and strictness levels.
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

### Updating

```bash
cd ~/amitayud-claude-world && git pull
```

No symlink changes needed after the initial setup — symlinks always point to the latest pulled content.
