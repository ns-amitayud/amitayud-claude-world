# ENG-970460: Consolidate Destination GeoIP into Single Session-Level Field

**Jira:** https://netskope.atlassian.net/browse/ENG-970460

---

## Implementation Gate

**Do not start implementation until PRs #14206 and #14246 are both merged.**

The three open questions from earlier review debates are now resolved. See
`2026-04-14-nplan6618-architectural-decisions.md` for full rationale.

**Resolved: `svcResolvedDestAddr` is removed in #14246.** GeoIP early population is
baked into `setDestHostResolvedIp()` instead. Tasks 3 and 4 below are updated to reflect
this — they no longer involve `setSvcResolvedDestAddr()`.

**Resolved: `DnsAttemptedAndFailed` sentinel is implemented in #14246.** When DNS fails,
`m_destHost.ip` is cleared and `ipSource` is set to `DnsAttemptedAndFailed`. The
`!ip.empty()` guard in `setDestHostResolvedIp()` prevents GeoIP from being called on a
failed DNS resolution. Tasks 2 and 3 below account for this.

**Resolved: Domain fronting (stale `m_destHost`) is a pre-existing issue deferred to
a future ticket.** Task 6 remains conditional and is not in scope for ENG-970460.

---

## Goal

Consolidate the destination GeoIP result into a single session-level field (`m_destGeoIpResult`)
on `NetSession`, replacing the current fragmented state where GeoIP data lives in multiple
disconnected places.

---

## Background

`getBackGeoIpResult()` / `m_backGeoIpResult` originally referred to the back connection GeoIP
result. Post-NPLAN-6618 (`setSvcResolvedDestAddr()` now calls `populateBackGeoInfo()` at DNS
resolution time), it is also populated before any back connection exists. The name is misleading.

Rename: `getBackGeoIpResult()` → `getDstGeoIpResult()` as the variable name changes from
`m_backGeoIpResult` to `m_destGeoIpResult`.

Note: ns-rkallidil also suggested renaming `HostIpSource` → `IpSource` in PR #14206. If
accepted, this rename will be in effect by the time ENG-970460 is implemented and all
references here to `HostIpSource` should be read as `IpSource`.

---

## Current Fragmentation

`m_destGeoIpResult` will contain the destination GeoIP result. Currently the source of
information is fragmented across three places:

**Source 1 — `m_backGeoIpResult` on NetSession (`NetSession.cpp:1019`)**
The local cache. After NPLAN-6618, populated by `setSvcResolvedDestAddr()` at DNS resolution
time. Also populated by `populateBackDetailsInNetSession()` when back connection destination
is determined.

**Source 2 — `m_back->getGeoIpResult()` on ConnInfo (`NetSession.cpp:1017`)**
The back connection's own GeoIP result. Takes priority over `m_backGeoIpResult` in
`getBackGeoIpResult()` when the back connection exists.

**Source 3 — `get_dst_country()` live lookup (`NetSession.cpp:218-240`)**
When `getBackGeoIpResult()` returns null, `get_dst_country()` does a fresh
`ns_geoip_get_loc()` call on whatever `get_dstip()` returns. Completely separate path —
result is ephemeral, not stored anywhere on the session.

The fragmentation is:
- Sources 1 and 2 are accessed via `getBackGeoIpResult()` but live in different objects
- Source 3 is a completely disconnected live lookup that doesn't feed back into the session state

Consolidating into `m_destGeoIpResult` on `NetSession` — populated once at the earliest
opportunity and authoritative for the session lifetime — eliminates all three divergence
points cleanly.

---

## Tasks

### Task 1 — Rename
Rename `m_backGeoIpResult` → `m_destGeoIpResult`. Rename `getBackGeoIpResult()` →
`getDstGeoIpResult()`, `populateBackGeoInfo()` → `populateDestGeoInfo()`. Update all
callers. Semantic rename reflecting the field's true purpose (destination GeoIP, not
backend connection GeoIP).

### Task 2 — Eliminate back conn GeoIP redundancy
`getDstGeoIpResult()` currently checks `m_back->getGeoIpResult()` first, then falls back
to `m_destGeoIpResult`. Consolidate into a single `m_destGeoIpResult` on `NetSession`.
When the back connection is established, copy its GeoIP result into `m_destGeoIpResult`.
The guard in `copyGeoIpResultToLocal()` at `NetSession.cpp:771` already prevents
overwriting a valid existing value.

*Constraint (if Open Question 2 resolved):* Do not populate `m_destGeoIpResult` when
`HostIpSource == DnsAttemptedAndFailed` — no valid IP is available for GeoIP lookup.

### Task 3 — Early population from SSL layer (NPLAN-6618)
GeoIP early population is baked into `setDestHostResolvedIp()` (settled in #14246 per
architectural decision Point 2). `populateDestGeoInfo()` is called atomically whenever a
DNS-resolved IP is stored, covering both SSL and HTTP layers in one place. No separate
call site needed.

Constraint: when `DnsAttemptedAndFailed` is set, `m_destHost.ip` is empty — the
`!ip.empty()` guard prevents `populateDestGeoInfo()` from being called on a failed
resolution.

### Task 4 — Conditional re-population at HTTP layer
Subsumed by Task 3. Since GeoIP is baked into `setDestHostResolvedIp()` and the
advancement-only rule prevents regression, `populateBackDetailsInNetSession()` in
`HttpRequestEngine.cpp:2211` no longer needs a separate explicit GeoIP call. The
advancement-only rule and `!ip.empty()` guard together ensure GeoIP is populated
correctly and only once per session at the most trusted IP source.

### Task 5 — Update `get_dst_country()`
Currently has a live `ns_geoip_get_loc()` fallback (`NetSession.cpp:218-240`) for when
`getDstGeoIpResult()` returns null. With `m_destGeoIpResult` reliably populated at DNS
resolution time, this live lookup is eliminated. `get_dst_country()` reads directly from
`m_destGeoIpResult`.

### Task 6 — Domain fronting staleness (conditional)
*Only needed if Open Question 3 is resolved and `m_destHost` is made the single source
of truth for `get_dstip()`.*

hpandey21 identified that when SNI ≠ HTTP Host header (domain fronting, CDN configs),
`m_destHost` can become stale: SSL layer resolves SNI and stores the IP, but the HTTP
layer guard (`!destHost.ip.empty()`) prevents updating `m_destHost` with the Host header's
IP. With `m_destGeoIpResult` populated from `m_destHost`, a stale `m_destHost` means stale
GeoIP. Fix: allow `m_destHost` to be updated when the domain changes (later stage has
better data), then re-populate `m_destGeoIpResult` accordingly.
