# amitayud-claude-world

Shared Claude Code skills for code review within the netSkope GitHub organization.

## Skills

- `/review` — Full PR review with language profiles, strictness levels, accurate line numbers, pre-review background analysis, and gap coverage output.
- `/review-pr` — Performs an initial review of a PR.
- `/pr-reply-ad-hoc` — Fetches existing review comments on a PR and drafts responses for you to copy-paste.
- `/review-feature-flag-cm [CM-KEY]` — Reviews feature-flag automation CMs from Jira. No argument = full pending-review queue; with a CM key = single ticket review.
- `/research-architecture <component>` — Produces a codebase-corroborated architecture doc in `docs/architecture/` by combining source code reading with Confluence BFS crawl results. Run before `capture-design-context` when starting feature work on an NSProxy/dataplane component.

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
ln -s ~/amitayud-claude-world/skills/review-feature-flag-cm ~/.claude/skills/review-feature-flag-cm
ln -s ~/amitayud-claude-world/skills/research-architecture ~/.claude/skills/research-architecture
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

---

## Review Workflow

When you invoke `/review <PR-URL>`, the skill executes the following steps in order:

### Step 1 — Fetch PR metadata and diff

```
gh pr view <url>       # title, description, author, reviewers
gh pr diff <url>       # full unified diff
gh pr comments <url>   # check for existing unresolved review comments
```

If unresolved comments exist, the skill routes to reply mode instead of fresh review mode.

### Step 2 — Resolve line numbers

All review comments must cite actual file line numbers, not diff-relative offsets.

```
gh api repos/<owner>/<repo>/pulls/<number> --jq '.head.sha'
gh api repos/<owner>/<repo>/contents/<file>?ref=<sha> --jq '.content' | base64 -d | grep -n ...
```

### Step 3 — Pre-review background analysis

The skill checks for a saved background analysis at:
```
~/.claude/review-context/<owner>-<repo>-<pr-number>.md
```

**If the file exists:**
> *"Background analysis found for PR \<number\>. Load it? (Y/N)"*

On Y: the analysis is loaded and informs the review. Token-free — no regeneration.

**If the file does not exist:**
> *"No background analysis found. Generate one? This traces the pre-PR dataflow in the changed files to show which gaps the PR addresses. (Y/N)"*

On Y: the skill reads each changed file at the PR's **base SHA** (pre-PR state), traces the relevant data/control flow, and produces a structured document:
- **Overview** — one paragraph describing the pre-PR design
- **Stage-by-stage dataflow** — numbered stages with `file:line` citations
- **Identified gaps** — specific weaknesses in the existing design
- **What the PR claims to address** — maps PR description to each gap

The document is then **saved automatically** to `~/.claude/review-context/<owner>-<repo>-<pr-number>.md` and reused on all future reviews of the same PR.

### Step 4 — Code review

The review applies the standard checklist (correctness, security, performance, style, tests, edge cases) plus the selected C++ language profile and strictness level.

### Step 5 — Output

```
## Summary
## Issues
   ### Critical   — must fix before merge   (file:line citations)
   ### Minor      — should fix, not blocking
   ### Suggestions — optional improvements
## Gap Coverage   — only when background analysis was loaded or generated
## Verdict        — APPROVE / REQUEST CHANGES / NEEDS DISCUSSION
```

The **Gap Coverage** table maps each gap identified in the background analysis to whether the PR addresses it:

| Gap (pre-PR design) | Addressed by PR? | Notes |
|---|---|---|
| [gap description] | Yes / Partially / No | [which change covers it, or why not] |

This makes the efficacy of the implementation and testing explicit to the reviewer.

---

## Accurate Line Numbers

All review comments cite actual file line numbers resolved against the PR head SHA — never diff-relative offsets.

---

## Updating

```bash
cd ~/amitayud-claude-world && git pull
```

No symlink changes needed after the initial setup — symlinks always point to the latest pulled content.
