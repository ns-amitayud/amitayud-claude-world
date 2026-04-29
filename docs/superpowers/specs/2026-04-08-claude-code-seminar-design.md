# Claude Code Productivity Seminar — Design Spec

**Date:** 2026-04-08
**Duration:** 60 minutes
**Format:** ~35 min slides, ~15 min live demo, ~10 min Q&A
**Audience:** Developers who already use Claude Code + one manager
**Goals:**
- Concrete habits attendees can adopt immediately
- Team adoption of shared practices (especially the code-review skill)

---

## Structure: "Before/After" Story Arc

Frame the entire talk around a developer's typical day — what it looks like *without* Claude Code used well, vs. *with* it. The demo lands as the natural climax of the "after" story.

---

## Section 1: Opening (5 min)

**Slide: The problem we all recognize**
- "You're mid-task. You need to review a 400-line PR in C++. You have 2 other PRs waiting. A bug just got filed."
- This is the *before*. The talk is about what the *after* looks like.

**Slide: What this talk covers**
- How Claude Code works (mental model, not a product tour)
- Individual habits you can adopt today
- Team practices we can standardize together
- Live demo of the code-review skill

Quick note for the manager: Claude Code isn't just an autocomplete — it's an agent that reads your repo, runs commands, and acts on your behalf.

---

## Section 2: Mental Model — What Claude Code Actually Is (5 min)

**Slide: Not a chatbot in a terminal**
- Has real tools: reads files, runs bash, searches code, writes/edits files
- Works *inside* your repo with full context — not copy-paste snippets
- Two modes: interactive (you guide it) and headless/agentic (it executes plans autonomously)
- Key shift: you're not asking "what should I write?" — you're delegating tasks

**Slide: The trust hierarchy**
- Claude reads your CLAUDE.md for project conventions — it follows your rules
- Skills = reusable task definitions you (or the team) author
- Hooks = shell commands that fire automatically on events (pre-commit, post-tool-call, etc.)
- MCP servers = extend Claude's reach to external systems (Jira, GitHub, Confluence)

**Do's and Don'ts — set 1:**

| Do | Don't |
|---|---|
| Give it context (CLAUDE.md, PR descriptions) | Expect it to guess your conventions |
| Use plan mode for non-trivial tasks | Let it run destructive git ops without review |
| Read what it produces before accepting | Rubber-stamp large diffs |

---

## Section 3: Individual Productivity — Before/After (15 min)

### Code Review
- **Before:** Read diff manually, miss subtle bugs, write comments from memory
- **After:** `/review <PR-URL> --lang cpp --strict` → precise file:line citations, blocking vs. suggestions separated, gap analysis against pre-PR design
- *Sets up the demo — audience sees the payoff is coming*

### Understanding Unfamiliar Code
- **Before:** grep + read + ask a colleague
- **After:** "Explain how `dest_profile_lookup` works and trace the data flow from incoming request to policy decision" — Claude reads the actual files, not a stale doc

### Debugging
- **Before:** Add printfs, guess, recompile
- **After:** Describe the symptom, let Claude read relevant files, trace the execution path, form a hypothesis before touching code
- Key habit: use `systematic-debugging` skill — forces hypothesis-first thinking

### Writing New Code
- **Before:** Write, then review, then fix
- **After:** Write the failing test first (`test-driven-development` skill), implement minimal passing code, run `verification-before-completion` before claiming done

**Do's and Don'ts — set 2:**

| Do | Don't |
|---|---|
| Describe *what* you want, not *how* to do it | Micromanage tool calls |
| Use skills for repeatable workflows | Re-explain the same context every session |
| Let it run tests and verify its own work | Trust "looks good" without running verification |
| Keep CLAUDE.md updated with real conventions | Add speculative features or abstractions it wasn't asked for |

---

## Section 4: Team Practices — Scaling It (10 min)

**Slide: The problem with individual AI usage**
- Everyone uses Claude differently → inconsistent output quality
- Knowledge of good prompts/workflows stays siloed
- New team members start from zero

**Slide: Skills — shareable task definitions**
- A skill is a markdown file with instructions Claude follows when you run `/skill-name`
- The `amitayud-claude-world` model: one repo, symlinked into `~/.claude/skills/` on each machine
- Anyone on the team pulls the repo → gets the same review workflow instantly
- Updating the skill = `git pull`, no reconfiguration

**Slide: CLAUDE.md — team conventions in code**
- Lives in the repo, checked in alongside the code
- Encodes: coding standards, testing philosophy, commit conventions, what to avoid
- Claude reads it every session — your rules enforced automatically

**Slide: What this means for the team (manager-facing)**
- PR reviews: consistent structure, nothing important missed
- Onboarding: new devs get team conventions enforced from day one
- Institutional knowledge: captured in skills and CLAUDE.md, not in people's heads

**Do's and Don'ts — set 3 (team):**

| Do | Don't |
|---|---|
| Version-control your skills | Keep skills local only — share them |
| Treat CLAUDE.md like living documentation | Write it once and forget it |
| Review skill outputs before acting on them | Let Claude push/merge without human review |
| Start with one shared skill, prove value, expand | Try to automate everything at once |

---

## Section 5: Live Demo (15 min)

Single narrative using a real PR from `netSkope/dataplane`.

**Pre-demo prep (do before the seminar):**
- Select a specific merged PR that is safe to show publicly (no sensitive business logic or credentials in the diff)
- Pre-run the background analysis on it and let it save to `~/.claude/review-context/` — during the live demo, accept the cached version rather than generating it live to avoid unpredictable timing

### Beat 1 — Setup (1 min)
- Show the `amitayud-claude-world` repo: three skill files, a README, symlinks
- Point: "This is all it takes to share a workflow with a team"

### Beat 2 — Run `/review` (5 min)
- Pick a real merged PR (safe to show, no sensitive info)
- Run `/review <PR-URL> --lang cpp --strict`
- Show: smart routing, fetches PR metadata + diff, resolves actual file:line numbers (not diff-relative)
- Pause: "Notice it's citing `file.cpp:247`, not `+34 in the diff` — it fetches the file at the head SHA"

### Beat 3 — Background analysis (5 min)
- Show the prompt: "Background analysis found for PR X. Load it? (Y/N)"
- Accept the cached version (pre-run during prep) — show it tracing pre-PR dataflow, identifying gaps, mapping PR claims to gaps
- Highlight the Gap Coverage table in output
- Point: "This is what a senior reviewer builds in their head over 20 minutes. Claude does it in 90 seconds."

### Beat 4 — The skill file (2 min)
- Open `~/.claude/skills/review/prompt.md` — show it's readable markdown, ~150 lines
- Point: "Any developer can read this, improve it, and the whole team benefits on next `git pull`"

### Beat 5 — Wrap (2 min)
- Show output structure: Critical → Minor → Suggestions → Verdict
- "This is what every PR review on this team could look like"

---

## Section 6: Closing + Q&A (10 min)

**Slide: The three things to do this week**
1. Add a `CLAUDE.md` to your repo (or improve the one that exists) with your real coding conventions
2. Clone `amitayud-claude-world` and run `/review` on your next PR
3. Identify one repetitive task in your workflow — write a 10-line skill for it

**Slide: Master Do's and Don'ts**

| Do | Don't |
|---|---|
| Use plan mode before non-trivial changes | Let it make large changes without reviewing the plan |
| Run verification before claiming work is done | Accept "it looks correct" without running tests |
| Share skills via git — treat them as code | Keep useful skills local |
| Keep CLAUDE.md current | Set it once and never update it |
| Delegate tasks, not micro-steps | Micromanage every tool call |
| Review diffs before committing | Rubber-stamp outputs |
| Use headless/agent mode for well-defined tasks | Use it for ambiguous tasks without a plan |

**Slide: Q&A**
- Seed question for the manager: "What workflows would you most want to see consistent across the team?"
- Seed question for devs: "What's the most painful repetitive task in your day?"

---

## Timing Summary

| Section | Time |
|---|---|
| Opening | 5 min |
| Mental model | 5 min |
| Individual productivity (before/after) | 15 min |
| Team practices | 10 min |
| Live demo | 15 min |
| Closing + Q&A | 10 min |
| **Total** | **60 min** |
