# Architecture Documentation — Concept and Workflow

## Origin

This document captures a discussion from a Claude Code session (2026-04-20) during the investigation of ENG-978048. The core idea emerged from observing that every debugging session independently re-learns the same codebase, paying the same token cost repeatedly.

---

## The Problem

When debugging an NSProxy issue, Claude browses code — grepping, reading files, tracing call paths — to build up architectural context. This is expensive in tokens and time. A second engineer debugging a different NSProxy issue does the same thing, independently, spending the same tokens to re-derive the same understanding.

The possible sources of truth are:
- The codebase itself
- Confluence pages (e.g., New Hire Guide for Data Path)
- Repertoire of old issues and their resolutions

None of these are pre-digested for fast consumption by Claude. Every session starts from scratch.

---

## The Proposed Solution

Generate a **pre-computed architecture document** that Claude reads at the start of a session instead of re-deriving architecture from source. This amortizes the learning cost: pay once, reuse across many sessions and engineers.

Key properties:
- Machine-readable (Claude can parse and reference it efficiently)
- Human-readable (useful for onboarding, context refresh, shared mental models)
- Lives in a repo (versioned, reviewable, PR-able)
- Updated periodically or after major fixes

---

## Design Decisions

### 1. Non-monolithic structure
One large document becomes hard to maintain and loads unnecessary context. Instead, use a tiered structure:

```
docs/architecture/
  nsproxy-overview.md          ← high-level, rarely changes
  nsproxy-pod-lifecycle.md     ← medium-level, changes with CFW versions
  nsproxy-etcd-schema.md       ← detailed, changes often
```

Each document is focused, independently updatable, and loaded only when relevant.

### 2. Dual audience
The same document serves both humans and Claude:
- Prose explanations for human readability
- Code snippets for key data structures
- Mermaid diagrams for visual representation
- File path references (e.g., `libs/cfw/vpp_plugins/`) for navigation

### 3. Workflow change
Current (expensive):
```
Session start → grep broadly → read many files → re-derive architecture → debug
```

With architecture docs (cheap):
```
Session start → read relevant doc → grep only for specifics → debug
```

### 4. Generation model
- **Opus** — for initial generation (reads large amounts of code, synthesizes architecture, makes inferences). One-time expensive operation.
- **Sonnet** — for consuming the doc during bug-fix/feature sessions, and for incremental updates after fixes land.

### 5. Starting point
`nsproxy-pod-lifecycle.md` — most directly relevant to the class of bugs being investigated. Seeded from ENG-978048 findings (pod registration, etcd schema, healthcheck, adapter watchdog, halbagent lifecycle).

### 6. Maintenance model
- Claude generates the first version by reading the codebase
- Engineers review and correct it (catches errors in Claude's understanding)
- Lives in the repo alongside code
- Updated after major fixes or CFW version changes

### 7. Validation loop
Human review of Claude-generated docs creates a feedback loop:
- Errors in Claude's architectural understanding get caught and corrected
- The document becomes more trustworthy over time
- Reduces "tribal knowledge" locked in individuals

### 8. Token efficiency at scale
When multiple engineers are simultaneously debugging NSProxy issues:
- Without docs: N engineers × M tokens per session = N×M total cost
- With docs: M tokens once (generation) + N × small tokens (doc read) = much lower total

### 9. Reduced tribal knowledge dependency
New hires and engineers switching between components can read the architecture doc instead of asking colleagues or spelunking through code for days. The doc is a first-class artifact, not a side effect.

---

## Next Steps

1. Generate `nsproxy-pod-lifecycle.md` as the first concrete document
   - Use Opus in plan mode
   - Seed with ENG-978048 findings (pod registration, etcd keys, healthcheck flow, adapter watchdog, halbagent)
   - Engineer reviews and corrects

2. Define update trigger — when should the doc be updated?
   - After a major bug fix that reveals new architectural understanding
   - After a CFW version upgrade that changes pod lifecycle behavior
   - Periodically (e.g., quarterly) as a hygiene task

3. Establish convention for Claude sessions to consume the doc
   - Add to CLAUDE.md: "Before debugging NSProxy issues, read `docs/architecture/nsproxy-pod-lifecycle.md`"
   - Or encode in a skill (`/bug-triage` reads relevant architecture docs automatically)

---

---

## Confluence BFS Crawl Plan

### Motivation

`nsproxy-pod-lifecycle.md` was generated entirely from the codebase and ENG-978048 log observations. Confluence pages were not a source (403 at time of generation). The crawl is intended to:
- Corroborate or contradict what's in the codebase
- Fill in sections of `nsproxy-pod-lifecycle.md` currently marked for engineer review
- Identify gaps that warrant new architecture documents (e.g., `nsproxy-etcd-schema.md`, `nsproxy-healthcheck.md`)

### Parameters

| Parameter | Value |
|-----------|-------|
| Start URL | `https://netskope.atlassian.net/wiki/spaces/DP/pages/3407972646` (New Hire Guide — Data Path) |
| Max depth | 2 |
| Scope filter | `spaces/DP/` and `spaces/DAP/` only |
| Relevance keywords | `nsproxy`, `iproxy`, `adapter`, `pod`, `lightning`, `CFW`, `halbagent`, `watchdog`, `etcd`, `VPP`, `dppool`, `healthcheck`, `lifecycle` |
| Output | Ranked list of relevant pages with title + one-line summary |

### Algorithm

```
Queue  = [(root_page_id, depth=0)]
Visited = {}

while Queue not empty:
    (page_id, depth) = dequeue
    if page_id in Visited: continue
    Visited.add(page_id)

    page = fetch(page_id)           # GET /rest/api/content/{id}?expand=body.storage
    links = extract_ri_page_links(page.body.storage)   # parse <ri:page> tags
    score = relevance_score(page, keywords)

    if score > 0:
        Relevant.append((page, score, depth))

    if depth < max_depth:
        for linked_id not in Visited:
            enqueue (linked_id, depth+1)

sort Relevant by score descending
output ranked list
```

### Link Extraction

Confluence storage format uses `<ri:page>` tags for internal links:
```xml
<ac:link><ri:page ri:content-title="Some Page" ri:space-key="DP"/></ac:link>
```
These are parsed from `body.storage` and resolved to page IDs via:
```
GET /rest/api/content?spaceKey=DP&title=Some+Page
```

### Tooling

The crawler is implemented at `scripts/confluence-bfs-crawler.py`.

```bash
cd ~/amitayud-claude-world
python3 scripts/confluence-bfs-crawler.py                        # default settings
python3 scripts/confluence-bfs-crawler.py --depth 1             # shallower crawl
python3 scripts/confluence-bfs-crawler.py --output /tmp/out.md  # custom output path
```

Requires env vars: `ATLASSIAN_API_TOKEN`, `ATLASSIAN_EMAIL`, `ATLASSIAN_SITE`.

Output is written to `docs/architecture/confluence-bfs-results.md` (runtime-generated, not committed).

### Output Format

Each relevant page entry in the markdown report:

```markdown
## [Page Title](https://netskope.atlassian.net/wiki/...)

- **Space:** DP
- **Depth:** 1
- **Score:** 4
- **Matched keywords:** etcd, lifecycle, nsproxy, pod
```

### Status

- [x] Implement BFS crawler script (`scripts/confluence-bfs-crawler.py`)
- [x] Run crawl from New Hire Guide root (31 pages fetched, 20 relevant — 2026-04-23)
- [ ] Review ranked output and annotate with relevance to architecture docs
- [ ] Update `nsproxy-pod-lifecycle.md` with Confluence-sourced corrections
- [ ] Identify new documents to create

---

## Related

- ENG-978048 — the investigation that prompted this discussion
- [New Hire Guide — Data Path](https://netskope.atlassian.net/wiki/spaces/DP/pages/3407972646/New+Hire+Guide+-+Data+Path)
