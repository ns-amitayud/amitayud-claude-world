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
import datetime
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

ALLOWED_SPACES = {"DP", "DAP", "ENG", "CF"}

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


def extract_links(page, base_url, auth):
    """
    Extract linked page IDs from a page's body.storage.
    Handles two cases:
      - <ri:page ri:content-title="Title" ri:space-key="DP" /> — resolve by title+space
      - <ri:page ri:content-title="Title" /> — resolve using page's own space
    Only follows links in ALLOWED_SPACES.
    Returns list of page ID strings.
    """
    body = page["body_storage"]
    default_space = page["space_key"]

    pattern = re.compile(r'<ri:page([^/]*)/?>', re.IGNORECASE)
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


def relevance_score(page):
    """
    Score a page for NSProxy relevance by counting keyword matches
    in the title and plain-text body. Title matches count double.
    Returns (score, matched_keywords).
    """
    title_lower = page["title"].lower()
    body_text = re.sub(r'<[^>]+>', ' ', page["body_storage"]).lower()

    matched = set()
    for kw in RELEVANCE_KEYWORDS:
        if kw in title_lower or kw in body_text:
            matched.add(kw)

    score = sum(
        (2 if kw in title_lower else 1)
        for kw in matched
    )
    return score, sorted(matched)


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


def write_report(results, output_path, root_id, max_depth):
    """Write BFS results to a markdown file."""
    os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else ".", exist_ok=True)
    with open(output_path, "w") as f:
        f.write("# Confluence BFS Crawl Results\n\n")
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
