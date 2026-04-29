# GeoIP Lookup on Service-Resolved Destination Address — Design Spec

**Date:** 2026-04-09
**PR:** https://github.com/netSkope/dataplane/pull/14246
**Jira:** ENG-710107 (Two-Level Destination Addressing, NPLAN-6618)

---

## Problem

PR #14246 introduces `svcResolvedDestAddr` as the canonical session-level field for the
service-resolved destination IP. `get_dstip()` was updated to return this IP at Priority 2,
after `getBackGeoIpResult()` at Priority 1.

However, no GeoIP lookup is performed on the resolved IP when `setSvcResolvedDestAddr` is
called. The result: at SSL DnD evaluation time (before the back connection exists),
`getBackGeoIpResult()` returns null and `get_dstip()` returns the raw resolved IP string via
Priority 2. Policy conditions that depend on destination country, ASN, or other GeoIP
attributes see no GeoIP data and evaluate incorrectly. Transaction events also log the wrong
country/ASN.

The same issue exists in PR #14206 (SSL-layer DNS resolution) which also modifies `get_dstip()`
without triggering a GeoIP lookup.

---

## Design

### Approach

Add a `populateBackGeoInfo()` call inside `setSvcResolvedDestAddr()` in `NetSession.hpp`,
immediately after `m_svcResolvedDestAddr.ip` is stored. This is atomic: every caller that sets
the resolved IP automatically gets GeoIP populated, including the SSL layer path from PR #14206
which calls `setSvcResolvedDestAddr` but is not in this PR's changeset.

### Change 1 — `NetSession.hpp`: `setSvcResolvedDestAddr()`

```cpp
void setSvcResolvedDestAddr(ns::host::Host resolved)
{
    if (m_svcResolvedDestAddr.ip.empty()) {
        m_svcResolvedDestAddr = std::move(resolved);
        // Populate back GeoIP immediately so policy conditions that depend on
        // destination country/ASN (e.g. geo-block rules) work correctly at
        // SSL DnD evaluation time — before the back connection exists and
        // m_back->getGeoIpResult() is available.
        populateBackGeoInfo(m_svcResolvedDestAddr.ip.c_str());
    } else {
        LOG(WARN) << "svcResolvedDestAddr already set to '" << m_svcResolvedDestAddr.ip
                  << "'; ignoring overwrite attempt with '" << resolved.ip << "'";
    }
}
```

### Change 2 — `NetSession.cpp`: `get_dstip()` Priority 2 comment

Keep the Priority 2 `hasSvcResolvedDestAddr()` block as a safety fallback. Add a comment
explaining why it is retained despite Priority 1 now being populated:

```cpp
// Safety fallback: if getBackGeoIpResult() (Priority 1) returned null despite
// svcResolvedDestAddr being set — e.g. if GeoIP lookup failed at DNS resolution
// time or the result was not yet valid — return the raw resolved IP directly.
// This ensures IP-based policy rules still use the service-resolved IP rather
// than the client-provided IP even when GeoIP data is unavailable.
if (m_nsession.hasSvcResolvedDestAddr()) {
    ...
}
```

### Change 3 — Tests

Add a test in `ns_netsvc_policy_test.cpp` verifying that after `setSvcResolvedDestAddr()`,
`getBackGeoIpResult()` returns a valid result whose IP matches the resolved IP — distinct
from the existing tests that only verify `get_dstip()` returns the resolved IP string.

---

## Data Flow After Fix

```
setSvcResolvedDestAddr(ip)
  ├─► m_svcResolvedDestAddr.ip = ip
  └─► populateBackGeoInfo(ip)
        └─► ns_geoip_get_loc(ip, &m_backGeoIpResult)

get_dstip() at SSL policy evaluation time:
  Priority 1: getBackGeoIpResult() → m_backGeoIpResult (now valid) → DNS IP ✓
  Priority 2: hasSvcResolvedDestAddr() → safety fallback if GeoIP lookup failed
  Priority 3: getOriginalDestHost() → client IP (unreachable when feature on + DNS succeeded)
```

---

## Error Handling

If `populateBackGeoInfo` fails (`ns_geoip_get_loc` returns `NS_RESULT_ERR`),
`m_backGeoIpResult` remains zeroed, `getBackGeoIpResult()` returns null, and `get_dstip()`
falls through to Priority 2 — returning the raw resolved IP string. IP-based policy rules
still use the correct IP; GeoIP-based conditions (country, ASN) will not fire.
`populateBackGeoInfo` already logs the failure at ERROR level.

---

## Scope

**Files changed:**
- `libs/netsvc/NetSession.hpp` — `setSvcResolvedDestAddr()` body
- `libs/netsvc/src/NetSession.cpp` — `get_dstip()` Priority 2 comment only
- `libs/netsvc/test/ns_netsvc_policy_test/src/cpp/ns_netsvc_policy_test.cpp` — new test

**Not in scope:**
- `SslLayer.cpp` (PR #14206) — the SSL layer call to `setSvcResolvedDestAddr` will
  automatically benefit from this fix once both PRs are merged; no change needed there.
- Removing Priority 2 from `get_dstip()` — retained as safety fallback by design.
