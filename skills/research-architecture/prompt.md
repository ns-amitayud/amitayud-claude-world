---
name: research-architecture
description: Use when an engineer needs to understand how an NSProxy/dataplane component currently works before starting a feature, bug investigation, or design discussion — produces a codebase-corroborated architecture doc in docs/architecture/ by combining source code reading with Confluence BFS crawl results.
allowed-tools:
  - Bash(python3 ~/amitayud-claude-world/scripts/confluence-bfs-crawler.py *)
  - Bash(~/.claude/plugins/cache/netskope/eng-skills/*/skills/confluence/scripts/confluence *)
  - Read
  - Bash(grep *)
  - Bash(find *)
  - Bash(cat *)
---

## Purpose

Produce a codebase-corroborated architecture document for a named component or topic.
The output lives in `docs/architecture/<component>.md` and serves as the stable base
that `capture-design-context` reads before producing feature design specs.

---

## Step 1: Check for existing doc

```bash
ls ~/amitayud-claude-world/docs/architecture/
```

If a doc for this component already exists, read it and assess whether it is current
(check the Status line at the top). If current and complete, report its location and stop.
If stale or has open review items, proceed to update it.

---

## Step 2: Run the Confluence BFS crawl

```bash
cd ~/amitayud-claude-world
python3 scripts/confluence-bfs-crawler.py
```

Default crawl starts from the New Hire Guide (DP space) at depth 2 across DP/DAP/ENG/CF spaces.
For a different root page:
```bash
python3 scripts/confluence-bfs-crawler.py --root <PAGE_ID> --depth 2
```

Read the output report at `docs/architecture/confluence-bfs-results.md`.
Identify pages with high relevance scores for the target component.

**Known limitation:** CF space pages are not reachable from the New Hire Guide root.
Fetch them directly by ID if needed:
```bash
~/.claude/plugins/cache/netskope/eng-skills/*/skills/confluence/scripts/confluence page <PAGE_ID>
```

Key CF page for NSProxy pod lifecycle / healthcheck / service chain:
- NPLAN-5483 CFW Failover Design: page ID `5085528065`

---

## Step 3: Read the codebase

For each component section, read the relevant source files in `~/gitcode/dataplane/`
(or the active bugfix/feature worktree). Focus on:

- Startup/initialization sequence
- State written to and read from etcd or shared memory
- Key data structures and their lifecycle
- Error handling and failure modes
- Configuration parameters that alter behavior

Use `grep` and `find` to locate files when paths are unknown:
```bash
grep -r "component_name" ~/gitcode/dataplane/pkg/ --include="*.py" -l
find ~/gitcode/dataplane/pkg -name "*adapter*" -type f
```

---

## Step 4: Synthesize and write the doc

Write `~/amitayud-claude-world/docs/architecture/<component>.md` following this structure:

```markdown
# <Component> Architecture

> **Status:** Generated <YYYY-MM-DD> from <sources>.
> **Reviewer:** Engineer review required for <list open sections>.
> **Update trigger:** After <relevant events>.

---

## 1. Overview
What this component is, its role in the service chain, key relationships.

## 2. <Lifecycle/Startup/Key Flow>
Source-cited sequence with mermaid diagram where helpful.

## 3. <Data Model / State>
etcd keys, config files, or shared memory structures with example values.

## 4. <External Interactions>
How other components read/write this component's state.

## 5. Known Failure Modes
Table: Failure | Symptom | Root Cause | Resolution

## 6. Sharp Edges
Numbered list of non-obvious behaviors that cause bugs.

## Quick Reference: Useful Commands
Bash commands for live inspection on a dppool node or via kubectl.

## Appendix: Sources and Review Status
- Sources used (codebase files, Confluence pages with URLs)
- Sections requiring engineer review (checkboxes)
```

Mark any section derived from log observations rather than source code with
`> **Source:** Observed from <ticket> — engineer review required`.

---

## Step 5: Commit

```bash
cd ~/amitayud-claude-world
git add docs/architecture/<component>.md
git commit -m "docs(architecture): add/update <component> architecture doc"
git push origin master
```

---

## Relationship to Other Skills

- **capture-design-context**: Runs AFTER this skill. Reads the architecture doc produced
  here to populate §3 (Execution Stages Affected) and §8 (Known Gaps) without re-deriving
  from source.
- **`scripts/confluence-bfs-crawler.py`**: The BFS crawl script this skill uses. Parameters
  and space coverage documented in `docs/architecture/README.md`.
