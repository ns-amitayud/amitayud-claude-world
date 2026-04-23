# Confluence BFS Crawler Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python script that crawls Confluence pages starting from the NSProxy New Hire Guide using BFS (max depth 2), scores each page for relevance to NSProxy topics, and outputs a ranked list of relevant pages.

**Architecture:** Single self-contained Python script using the Confluence REST API directly (same credentials as the confluence CLI). BFS implemented with a queue, visited set deduplication, relevance scoring by keyword matching against page title + body text, scope-filtered to DP and DAP spaces. Output written to a markdown file in `docs/architecture/`.

**Tech Stack:** Python 3, `requests` library, Confluence REST API v1, environment variables (`ATLASSIAN_API_TOKEN`, `ATLASSIAN_EMAIL`, `ATLASSIAN_SITE`).

---

## File Structure

| File | Action | Purpose |
|------|--------|---------|
| `scripts/confluence-bfs-crawler.py` | Create | BFS crawler — fetches pages, extracts links, scores relevance, outputs ranked list |
| `docs/architecture/confluence-bfs-results.md` | Create (at runtime) | Output file — ranked list of relevant pages produced by the crawler |

---

### Task 1: Scaffold the script with argument parsing and Confluence auth

**Files:**
- Create: `scripts/confluence-bfs-crawler.py`

- [ ] **Step 1: Create scripts directory**

```bash
mkdir -p ~/amitayud-claude-world/scripts
```

Expected: directory created, no output.

- [ ] **Step 2: Write the initial scaffold**

Create `~/amitayud-claude-world/scripts/confluence-bfs-crawler.py`:

```python
#!/usr/bin/env python3
"""
Confluence BFS Crawler
Crawls Confluence pages starting from a root page, BFS up to max_depth=2,
scores pages for NSProxy relevance, outputs a ranked markdown report.

Usage:
    python3 confluence-bfs-crawler.py [--root PAGE_ID] [--depth N] [--output FILE]

Defaults:
    --root   3407972646  (New Hire Guide - Data Path)
    --depth  2
    --output docs/architecture/confluence-bfs-results.md
"""

import argparse
import os
import re
import sys
from collections import deque

import requests
from requests.auth import HTTPBasicAuth


RELEVANCE_KEYWORDS = [
    "nsproxy", "iproxy", "adapter", "pod", "lightning", "cfw",
    "halbagent", "watchdog", "etcd", "vpp", "dppool", "healthcheck",
    "lifecycle",
]

ALLOWED_SPACES = {"DP", "DAP"}

ROOT_PAGE_ID = "3407972646"
DEFAULT_DEPTH = 2
DEFAULT_OUTPUT = "docs/architecture/confluence-bfs-results.md"


def get_auth():
    """Return (base_url, HTTPBasicAuth) from environment variables."""
    token = os.environ.get("ATLASSIAN_API_TOKEN")
    email = os.environ.get("ATLASSIAN_EMAIL")
    site = os.environ.get("ATLASSIAN_SITE")
    if not all([token, email, site]):
        print("ERROR: Set ATLASSIAN_API_TOKEN, ATLASSIAN_EMAIL, ATLASSIAN_SITE", file=sys.stderr)
        sys.exit(1)
    # site can be "netskope" or "netskope.atlassian.net"
    if "." not in site:
        site = f"{site}.atlassian.net"
    base_url = f"https://{site}/wiki/rest/api"
    return base_url, HTTPBasicAuth(email, token)


def parse_args():
    parser = argparse.ArgumentParser(description="Confluence BFS Crawler")
    parser.add_argument("--root", default=ROOT_PAGE_ID, help="Root page ID")
    parser.add_argument("--depth", type=int, default=DEFAULT_DEPTH, help="Max BFS depth")
    parser.add_argument("--output", default=DEFAULT_OUTPUT, help="Output markdown file path")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    base_url, auth = get_auth()
    print(f"Root: {args.root}, Depth: {args.depth}, Output: {args.output}")
    print("Auth OK")
```

- [ ] **Step 3: Make it executable and test auth**

```bash
chmod +x ~/amitayud-claude-world/scripts/confluence-bfs-crawler.py
cd ~/amitayud-claude-world
python3 scripts/confluence-bfs-crawler.py
```

Expected output:
```
Root: 3407972646, Depth: 2, Output: docs/architecture/confluence-bfs-results.md
Auth OK
```

If you see `ERROR: Set ATLASSIAN_API_TOKEN...`, run `source ~/.bashrc` or `source ~/.zshrc` first.

- [ ] **Step 4: Commit**

```bash
cd ~/amitayud-claude-world
git add scripts/confluence-bfs-crawler.py
git commit -m "feat(scripts): scaffold confluence-bfs-crawler with auth and arg parsing"
```

---

### Task 2: Implement page fetching and link extraction

**Files:**
- Modify: `scripts/confluence-bfs-crawler.py`

- [ ] **Step 1: Add `fetch_page` function**

Add the following function after `get_auth()` and before `parse_args()`:

```python
def fetch_page(page_id, base_url, auth):
    """
    Fetch a Confluence page by ID with body.storage expanded.
    Returns dict with keys: id, title, space_key, body_storage, web_url
    Returns None if fetch fails (403, 404, etc).
    """
    url = f"{base_url}/content/{page_id}"
    params = {"expand": "body.storage,space"}
    try:
        resp = requests.get(url, params=params, auth=auth, timeout=10)
    except requests.RequestException as e:
        print(f"  [WARN] Network error fetching {page_id}: {e}", file=sys.stderr)
        return None
    if resp.status_code == 403:
        print(f"  [SKIP] 403 on page {page_id}", file=sys.stderr)
        return None
    if resp.status_code == 404:
        print(f"  [SKIP] 404 on page {page_id}", file=sys.stderr)
        return None
    if not resp.ok:
        print(f"  [WARN] HTTP {resp.status_code} on page {page_id}", file=sys.stderr)
        return None
    data = resp.json()
    space_key = data.get("space", {}).get("key", "")
    links = data.get("_links", {})
    base = links.get("base", "")
    web_ui = links.get("webui", "")
    return {
        "id": data["id"],
        "title": data.get("title", ""),
        "space_key": space_key,
        "body_storage": data.get("body", {}).get("storage", {}).get("value", ""),
        "web_url": f"{base}{web_ui}" if base and web_ui else "",
    }
```

- [ ] **Step 2: Add `extract_links` function**

Add after `fetch_page`:

```python
def extract_links(page, base_url, auth):
    """
    Extract linked page IDs from a page's body.storage.
    Handles two cases:
      - <ri:page ri:content-title="Title" ri:space-key="DP" /> — resolve by title+space
      - <ri:page ri:content-title="Title" /> — resolve using page's own space
    Returns list of page ID strings.
    """
    body = page["body_storage"]
    default_space = page["space_key"]

    # Parse all ri:page tags
    pattern = re.compile(r'<ri:page([^/]*)/>', re.IGNORECASE)
    ids = []
    seen_titles = set()

    for match in pattern.finditer(body):
        attrs = match.group(1)
        title_m = re.search(r'ri:content-title="([^"]+)"', attrs)
        space_m = re.search(r'ri:space-key="([^"]+)"', attrs)
        if not title_m:
            continue
        title = title_m.group(1)
        space = space_m.group(1) if space_m else default_space

        # Only follow links in allowed spaces
        if space not in ALLOWED_SPACES:
            continue

        key = (space, title)
        if key in seen_titles:
            continue
        seen_titles.add(key)

        page_id = resolve_title_to_id(title, space, base_url, auth)
        if page_id:
            ids.append(page_id)

    return ids


def resolve_title_to_id(title, space_key, base_url, auth):
    """Resolve a page title + space key to a page ID. Returns None if not found."""
    url = f"{base_url}/content"
    params = {"spaceKey": space_key, "title": title, "limit": 1}
    try:
        resp = requests.get(url, params=params, auth=auth, timeout=10)
    except requests.RequestException:
        return None
    if not resp.ok:
        return None
    results = resp.json().get("results", [])
    return results[0]["id"] if results else None
```

- [ ] **Step 3: Test link extraction on root page**

Update the `if __name__ == "__main__":` block temporarily:

```python
if __name__ == "__main__":
    args = parse_args()
    base_url, auth = get_auth()
    print("Fetching root page...")
    page = fetch_page(args.root, base_url, auth)
    print(f"Title: {page['title']}")
    print(f"Space: {page['space_key']}")
    print("Extracting links (DP/DAP only)...")
    links = extract_links(page, base_url, auth)
    print(f"Found {len(links)} linked pages in DP/DAP spaces:")
    for lid in links:
        print(f"  {lid}")
```

Run:
```bash
cd ~/amitayud-claude-world
python3 scripts/confluence-bfs-crawler.py
```

Expected: prints root page title ("New Hire Guide - Data Path") and a list of page IDs from DP/DAP spaces. The list may be short (0-5 pages) since the root page links to many non-DP spaces.

- [ ] **Step 4: Commit**

```bash
cd ~/amitayud-claude-world
git add scripts/confluence-bfs-crawler.py
git commit -m "feat(scripts): add page fetching and link extraction to bfs crawler"
```

---

### Task 3: Implement relevance scoring and BFS loop

**Files:**
- Modify: `scripts/confluence-bfs-crawler.py`

- [ ] **Step 1: Add `relevance_score` function**

Add after `resolve_title_to_id`:

```python
def relevance_score(page):
    """
    Score a page for NSProxy relevance by counting keyword matches
    in the title and plain-text body. Title matches count double.
    Returns (score, matched_keywords).
    """
    title_lower = page["title"].lower()
    # Strip HTML tags from body for text matching
    body_text = re.sub(r'<[^>]+>', ' ', page["body_storage"]).lower()

    matched = set()
    for kw in RELEVANCE_KEYWORDS:
        in_title = kw in title_lower
        in_body = kw in body_text
        if in_title or in_body:
            matched.add(kw)

    # Title matches count double
    score = sum(
        (2 if kw in title_lower else 1)
        for kw in matched
    )
    return score, sorted(matched)
```

- [ ] **Step 2: Add `bfs_crawl` function**

Add after `relevance_score`:

```python
def bfs_crawl(root_id, max_depth, base_url, auth):
    """
    BFS crawl starting from root_id up to max_depth.
    Returns list of dicts: {page, score, matched_keywords, depth}
    sorted by score descending.
    """
    queue = deque([(root_id, 0)])
    visited = set()
    relevant = []
    total_fetched = 0

    while queue:
        page_id, depth = queue.popleft()
        if page_id in visited:
            continue
        visited.add(page_id)

        print(f"  [depth={depth}] Fetching {page_id}...", end=" ", flush=True)
        page = fetch_page(page_id, base_url, auth)
        if page is None:
            print("skipped")
            continue
        total_fetched += 1
        print(page["title"])

        score, matched = relevance_score(page)
        if score > 0:
            relevant.append({
                "page": page,
                "score": score,
                "matched_keywords": matched,
                "depth": depth,
            })

        if depth < max_depth:
            linked_ids = extract_links(page, base_url, auth)
            for lid in linked_ids:
                if lid not in visited:
                    queue.append((lid, depth + 1))

    print(f"\nCrawl complete: {total_fetched} pages fetched, {len(relevant)} relevant.")
    return sorted(relevant, key=lambda x: x["score"], reverse=True)
```

- [ ] **Step 3: Replace `__main__` block with BFS invocation**

Replace the entire `if __name__ == "__main__":` block with:

```python
if __name__ == "__main__":
    args = parse_args()
    base_url, auth = get_auth()
    print(f"Starting BFS crawl from page {args.root}, max depth {args.depth}")
    print(f"Allowed spaces: {sorted(ALLOWED_SPACES)}")
    print(f"Keywords: {RELEVANCE_KEYWORDS}\n")
    results = bfs_crawl(args.root, args.depth, base_url, auth)
    print(f"\nTop relevant pages ({len(results)} total):")
    for r in results[:10]:
        print(f"  [score={r['score']} depth={r['depth']}] {r['page']['title']}")
        print(f"    keywords: {', '.join(r['matched_keywords'])}")
```

- [ ] **Step 4: Run BFS crawl and verify it works**

```bash
cd ~/amitayud-claude-world
python3 scripts/confluence-bfs-crawler.py
```

Expected: crawl output showing pages being fetched at depth 0, 1, 2, followed by a ranked list of relevant pages. This will take 1-5 minutes depending on how many pages are reachable. You should see NSProxy-related pages scoring higher.

If the crawl is very slow (many title-resolution API calls), it's working correctly — each `ri:page` tag requires one API call to resolve the title to an ID.

- [ ] **Step 5: Commit**

```bash
cd ~/amitayud-claude-world
git add scripts/confluence-bfs-crawler.py
git commit -m "feat(scripts): add relevance scoring and BFS loop to crawler"
```

---

### Task 4: Write output to markdown report

**Files:**
- Modify: `scripts/confluence-bfs-crawler.py`

- [ ] **Step 1: Add `write_report` function**

Add after `bfs_crawl`:

```python
def write_report(results, output_path, root_id, max_depth):
    """Write BFS results to a markdown file."""
    import datetime
    os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else ".", exist_ok=True)
    with open(output_path, "w") as f:
        f.write(f"# Confluence BFS Crawl Results\n\n")
        f.write(f"**Generated:** {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
        f.write(f"**Root page:** `{root_id}`\n")
        f.write(f"**Max depth:** {max_depth}\n")
        f.write(f"**Spaces crawled:** {', '.join(sorted(ALLOWED_SPACES))}\n")
        f.write(f"**Total relevant pages found:** {len(results)}\n\n")
        f.write("---\n\n")

        if not results:
            f.write("No relevant pages found.\n")
            return

        for r in results:
            page = r["page"]
            score = r["score"]
            depth = r["depth"]
            keywords = ", ".join(r["matched_keywords"])
            title = page["title"]
            url = page["web_url"]
            space = page["space_key"]

            f.write(f"## [{title}]({url})\n\n")
            f.write(f"- **Space:** {space}\n")
            f.write(f"- **Depth:** {depth}\n")
            f.write(f"- **Score:** {score}\n")
            f.write(f"- **Matched keywords:** {keywords}\n\n")
```

- [ ] **Step 2: Wire `write_report` into `__main__`**

Replace the `if __name__ == "__main__":` block with:

```python
if __name__ == "__main__":
    args = parse_args()
    base_url, auth = get_auth()
    print(f"Starting BFS crawl from page {args.root}, max depth {args.depth}")
    print(f"Allowed spaces: {sorted(ALLOWED_SPACES)}")
    print(f"Keywords: {RELEVANCE_KEYWORDS}\n")
    results = bfs_crawl(args.root, args.depth, base_url, auth)
    write_report(results, args.output, args.root, args.depth)
    print(f"\nReport written to: {args.output}")
    print(f"\nTop 10 relevant pages:")
    for r in results[:10]:
        print(f"  [score={r['score']} depth={r['depth']}] {r['page']['title']}")
        print(f"    keywords: {', '.join(r['matched_keywords'])}")
```

- [ ] **Step 3: Run end-to-end and verify report**

```bash
cd ~/amitayud-claude-world
python3 scripts/confluence-bfs-crawler.py
```

Expected: crawl runs, `docs/architecture/confluence-bfs-results.md` is created, top 10 relevant pages printed to stdout.

Verify the output file exists and has content:
```bash
head -20 ~/amitayud-claude-world/docs/architecture/confluence-bfs-results.md
```

Expected: markdown header with generation date, root page ID, and first few page entries.

- [ ] **Step 4: Commit script and add output file to .gitignore**

The results file is generated at runtime — it should not be committed (it will be re-generated each run and may contain stale data).

```bash
cd ~/amitayud-claude-world
echo "docs/architecture/confluence-bfs-results.md" >> .gitignore
git add scripts/confluence-bfs-crawler.py .gitignore
git commit -m "feat(scripts): add markdown report output to bfs crawler"
```

---

### Task 5: Update architecture README with crawl status

**Files:**
- Modify: `docs/architecture/README.md`

- [ ] **Step 1: Mark crawl tasks as complete in README**

In `~/amitayud-claude-world/docs/architecture/README.md`, find the Status checklist under "Confluence BFS Crawl Plan" and update it:

```markdown
### Status

- [x] Implement BFS crawler script (`scripts/confluence-bfs-crawler.py`)
- [ ] Run crawl from New Hire Guide root
- [ ] Review ranked output
- [ ] Update `nsproxy-pod-lifecycle.md` with Confluence-sourced corrections
- [ ] Identify new documents to create
```

Also add the script location and usage under the "Tooling" section:

```markdown
### Tooling

The crawler is implemented at `scripts/confluence-bfs-crawler.py`.

Usage:
```bash
cd ~/amitayud-claude-world
python3 scripts/confluence-bfs-crawler.py                    # default settings
python3 scripts/confluence-bfs-crawler.py --depth 1         # shallower crawl
python3 scripts/confluence-bfs-crawler.py --output /tmp/out.md  # custom output
```

Requires env vars: `ATLASSIAN_API_TOKEN`, `ATLASSIAN_EMAIL`, `ATLASSIAN_SITE`.
```

- [ ] **Step 2: Commit and push**

```bash
cd ~/amitayud-claude-world
git add docs/architecture/README.md
git commit -m "docs(architecture): mark bfs crawler implemented, add usage instructions"
git push origin master
```

---

## Self-Review

**Spec coverage check:**
- ✅ BFS algorithm with queue + visited set — Task 3 (`bfs_crawl`)
- ✅ Max depth=2 — Task 3 (`args.depth`, default `DEFAULT_DEPTH=2`)
- ✅ Scope filter DP + DAP only — Task 2 (`ALLOWED_SPACES`, `extract_links`)
- ✅ Relevance keywords list — Task 3 (`RELEVANCE_KEYWORDS`, `relevance_score`)
- ✅ `<ri:page>` tag parsing — Task 2 (`extract_links`)
- ✅ Title-to-ID resolution — Task 2 (`resolve_title_to_id`)
- ✅ Pages without `ri:space-key` default to parent's space — Task 2 (`extract_links`, `default_space`)
- ✅ Ranked output by score — Task 3 (`sorted(..., reverse=True)`)
- ✅ Output format: title, URL, score, matched keywords, depth — Task 4 (`write_report`)
- ✅ Markdown output file — Task 4
- ✅ Output file excluded from git — Task 4 (`.gitignore`)
- ✅ README status updated — Task 5

**Placeholder scan:** None found.

**Type consistency:**
- `fetch_page` returns dict with keys `id`, `title`, `space_key`, `body_storage`, `web_url` — used consistently in `extract_links`, `relevance_score`, `bfs_crawl`, `write_report`
- `bfs_crawl` returns list of `{page, score, matched_keywords, depth}` — used consistently in `write_report` and `__main__`
- `resolve_title_to_id` returns string ID or `None` — checked with `if page_id:` in `extract_links`

**Note on TDD:** This script interacts with a live external API (Confluence). Unit tests would require mocking the API, which adds significant complexity for a one-shot utility script. The plan uses manual verification steps (run and observe output) in place of automated tests. This is acceptable for a personal utility script — not for production code.
