# ENG-1036449: Domain Fronting Bypass Path Fix — Design Context

**Jira:** ENG-1036449
**Date:** 2026-06-03
**Author:** Amitayu Das
**Status:** Delivered (PR #15237, implementation complete)
**Related specs:**
- `2026-04-14-nplan6618-architectural-decisions.md` — ADR Point 9: domain fronting gap analysis
- `2026-05-19-eng-970460-geoip-consolidation-design.md` — Known Gap #1: `ResolvedIpFromHttpHost` production
- `2026-04-28-eng-710107-dest-addressing-design.md` — predecessor: SSL-layer DNS resolution

---

## Problem Statement

When "Domain Fronting Protections" (Error Settings UI) is set to **Bypass**, nsproxy
correctly detects SNI ≠ HTTP Host header mismatch via `detectDomainFronting()` in
`HttpRequestEngine::runRequestHeader()` and logs it in transaction events. However, the
back connection uses the **SNI-resolved IP** (`allowed.com`'s IP) while carrying
`Host: blocked.com`. The CDN at `allowed.com` routes internally to `blocked.com`. Domain
fronting succeeds at the CDN level despite detection.

**Block path (already correct):** When policy is set to Block, `detectDomainFronting()`
calls `sendDomainFrontingErrToFront()` and returns `NS_NBERR`, terminating the connection
immediately. `updateNetSessionDestHostResolvedIp()` is never reached.

**Bypass path (this fix):** When policy is set to Bypass, `detectDomainFronting()` detects
the mismatch but does not terminate — execution falls through to
`updateNetSessionDestHostResolvedIp()`. The three-condition guard in that function fires
(SNI-resolved IP is non-empty), causing an early return with the stale IP in place.
ENG-1036449 fixes this path.

### Root cause

`updateNetSessionDestHostResolvedIp()` in `runRequestModProcess()` has a guard at line 5389:

```cpp
if (!destHost.ip.empty() || ...) {
    return;  // Do not update resolved ip
}
```

In the bypass path, `destHost.ip = "1.2.3.4"` (set by SSL-layer DNS for `allowed.com`,
`ipSource = ResolvedIpFromSni = 7`) is non-empty — the guard fires,
`setDestHostResolvedIp()` is never called with `blocked.com`'s IP, and `get_dstip()`
returns `1.2.3.4` (the wrong server) to the policy engine.

DNS for `blocked.com` **already runs** — `getDestInfo()` in `runRequestHeaderResume()`
sets `m_proxy.m_newDest.domain = blocked.com` from the HTTP Host header, and
`doDnsLookup()` resolves it. The resolved IP is available in `destinfo->addr.ipstr`. It
never reaches `m_destHost` because of the guard.

### Additional deliverable: `ResolvedIpFromHttpHost` production

`getIpSourceFromDestInfo()` already maps `NS_HOSTSRC_HOST_HEADER` →
`ResolvedIpFromHttpHost = 8`. The fix calls `setDestHostResolvedIp(blocked.com_ip,
ResolvedIpFromHttpHost)` — this is the **first code path that produces
`ResolvedIpFromHttpHost`**, closing ENG-970460 Known Gap #1. The two deliverables are
causally coupled and cannot be separated.

---

## Scope

**In scope:**
- Fix the Bypass path: clear stale SNI-resolved IP, set `blocked.com`'s IP via
  `setDestHostResolvedIp()` with `ipSource = ResolvedIpFromHttpHost = 8`
- Produce `ResolvedIpFromHttpHost = 8` — closes ENG-970460 Known Gap #1
- Staged config gate for deployment safety
- DNS failure handling in bypass path

**Out of scope:**
- Block path — already correct, no changes
- SNI ≠ CONNECT host policy (NPLAN-143 Phase 2): today the proxy hard-codes "SNI takes
  priority" when SNI ≠ CONNECT host; configurable policy is deferred
- HTTP/2 — needs separate analysis
- Global exception list — already checked in both Block and Bypass modes; no change needed

---

## Architecture and Data Flow

### Current flow (broken)

```
runRequestHeader()                      [state: HTTP_REQ_HDR]
  parseHeaders() — complete
  detectDomainFronting() → true
  isPolicyBypass(DOMAIN_FRONTING) → true
  → falls through silently
  setState(HTTP_REQ_HDR_RESUME)         ← state transition happens HERE,
  returns NS_NBOK                          inside runRequestHeader()

  [state machine calls processRequest() → picks up HTTP_REQ_HDR_RESUME]

runRequestHeaderResume()                [state: HTTP_REQ_HDR_RESUME]
  getDestInfo() → m_newDest.domain = "blocked.com"   ← correct
  doDnsLookup("blocked.com") → NS_NBEAGAIN
  setNextDnsState(current), setState(APPHP_CONNECTING)

  [DNS resolves asynchronously]

destDnsReply(blocked.com_ip)
  m_newDest.addr = blocked.com_ip                    ← correct IP resolved
  setState(getNextDnsState())
  processRequest() →

  [state machine calls processRequest() → picks up next state]

runRequestModProcess()
  updateNetSessionDestHostResolvedIp():
    destHost.ip = "1.2.3.4" (non-empty) → GUARD FIRES → returns early  ← BUG
    setDestHostResolvedIp() never called with blocked.com_ip
  m_destHost.ip still = "1.2.3.4" (allowed.com's IP)                  ← stale
  m_modEngine.requestHeaders():
    get_dstip() returns "1.2.3.4"                                       ← wrong
    policy evaluated against allowed.com / 1.2.3.4
  setupBack() → connects to 1.2.3.4 with Host: blocked.com
  CDN routes to blocked.com — domain fronting succeeds
```

### Fixed flow

```
runRequestHeader()                      [state: HTTP_REQ_HDR]
  parseHeaders() — complete
  detectDomainFronting(... &detectedHost) → true    ← detectedHost = "blocked.com"
  isPolicyBypass(DOMAIN_FRONTING) → true
  check IP-in-SNI guard → SNI is a hostname, not IP  ← NEW
  check staged config (global + per-tenant) → enabled ← NEW
  m_proxy.setFlag(HTTP_DOMAIN_FRONTING_BYPASSED)     ← NEW
  setState(HTTP_REQ_HDR_RESUME)         ← state transition unchanged
  returns NS_NBOK

  [state machine calls processRequest() → picks up HTTP_REQ_HDR_RESUME]

runRequestHeaderResume()                [state: HTTP_REQ_HDR_RESUME]
  getDestInfo() → m_newDest.domain = "blocked.com"  (unchanged)
  doDnsLookup("blocked.com") → NS_NBEAGAIN           (unchanged)

  [DNS resolves asynchronously]

destDnsReply(blocked.com_ip)            (unchanged)

  [state machine calls processRequest() → picks up next state]

runRequestModProcess()
  updateNetSessionDestHostResolvedIp():
    HTTP_DOMAIN_FRONTING_BYPASSED set? → YES         ← NEW CHECK
    clearFlag(HTTP_DOMAIN_FRONTING_BYPASSED)
    clearDestHostResolvedIp()           ← clears stale 1.2.3.4, ip now empty
    getIpSourceFromDestInfo() → ResolvedIpFromHttpHost = 8
                                        ← closes ENG-970460 Known Gap #1
    setDestHostResolvedIp("blocked.com_ip", ResolvedIpFromHttpHost)
      → m_destHost.ip = "blocked.com_ip"
      → m_destHost.ipSource = 8
      → populateDestGeoInfo() → m_destGeoIpResult for blocked.com
    return
  updateNetSessionDestHost():           (unchanged, line 5910)
    m_destHost.value = "blocked.com"
  m_modEngine.requestHeaders():
    get_dstip() returns "blocked.com_ip"             ← correct
    get_dst_country() returns blocked.com's country  ← correct
    policy evaluated against blocked.com / blocked.com_ip
    → BLOCK: teardown with block event
    → ALLOW: continue
  setupBack() → connects to blocked.com_ip with Host: blocked.com  ← correct
```

---

## Exception List Applicability

### Global exception list
Checked inside `detectDomainFronting()` regardless of policy mode. If a domain matches
the global exception list, `detectDomainFronting()` returns false and the bypass fix never
fires. This is unchanged.

### Tenant exception list — does not apply in Bypass mode
`detectDomainFronting()` already skips the tenant exception list when
`isPolicyBypass(DOMAIN_FRONTING)` is true (line 1161). The final implementation does
**not** re-add a tenant exception list check in the Bypass path.

**Rationale (PM confirmed 2026-06-15; see Open Design Questions → Q2):** The exception
list was designed exclusively for Block mode — "block domain fronting globally, except
for these trusted domains." Under the confirmed semantics of Bypass (enforce HTTP Host
destination unconditionally), there is nothing to except: destination enforcement applies
to every domain in Bypass mode. The exception list is semantically incoherent in Bypass
mode.

An earlier draft of this spec included a tenant exception list check in the Bypass path.
That code was removed after PM confirmation.

---

## Code Changes

### Files changed

| File | Change |
|---|---|
| `libs/http/src/AppModuleHttpProxy.hpp` | Add `HTTP_DOMAIN_FRONTING_BYPASSED` flag |
| `libs/http/src/HttpRequestEngine.hpp` | Add `detectedHost` output param to `detectDomainFronting()` |
| `libs/http/src/HttpRequestEngine.cpp` | `detectDomainFronting()`: populate output param; `runRequestHeader()`: set flag + tenant exception check; `updateNetSessionDestHostResolvedIp()`: bypass guard when flag set |
| `libs/http/src/AppModuleHttpProxy.cpp` | `dnsReplyOnFailure()`: force teardown when `HTTP_DOMAIN_FRONTING_BYPASSED` set |
| `libs/http/http_features.featurec` | Add `domain-fronting-bypass-fix` flag (default `true`) |
| `libs/http/SslLayerGeoIpPreserveGlobalCfg.hpp` / `src/` | Reuse pattern for new `DomainFrontingBypassFixGlobalCfg` staged config |
| `libs/http/Makefile.am` + `CMakeLists.txt` | Add new staged config source |
| `apps/nsproxy/src/cpp/nsproxy.cpp` | Add `init()` call for new staged config |

### Key changes

**`AppModuleHttpProxy.hpp` — new flag:**
```cpp
HTTP_DOMAIN_FRONTING_BYPASSED = 0x<next_bit>,
// Set when domain fronting detected in Bypass mode and Host is not in
// tenant exception list. Causes updateNetSessionDestHostResolvedIp()
// to clear the stale SNI-resolved IP and advance to ResolvedIpFromHttpHost.
```

**`detectDomainFronting()` — new output parameter:**
```cpp
bool detectDomainFronting(
    const NsDomainFrontingExcep::DomainFrontingExcepMgr &globalExcepMgr,
    const std::string &sslSni,
    const ns_http_objs_t *hdr,
    uint32_t &domainFrontingFlags,
    std::string &detectedHost);   // NEW: populated with url host / host header
```

**`runRequestHeader()` — set flag after bypass fall-through:**
```cpp
std::string detectedHost;
domainFronted = detectDomainFronting(
    ..., domainFrontingFlags, detectedHost);

// IP-in-SNI guard: detectDomainFronting() does NOT exclude the case where
// SNI is a raw IP (e.g., SNI=1.2.3.4, Host: example.com). That is legitimate
// HTTP/1.1 behavior, not domain fronting. Without this guard, the bypass fix
// would fire for IP-direct connections. Verified: no ns_netutil_is_ip_addr
// check exists in detectDomainFronting() (HttpRequestEngine.cpp:1077-1197).
const auto &sni = m_nsession.frontConn()->getSslSni();
if (domainFronted &&
    isPolicyBypass(NetLayerPolicyCfg::DOMAIN_FRONTING) &&
    !ns_netutil_is_ip_addr(sni.c_str(), nullptr) &&
    ::domain_fronting_bypass_fix::globalcfg::enabled() &&
    m_hsession.m_newConfig->domain_fronting_bypass_fix().enabled()) {
    // Tenant exception list intentionally NOT checked here.
    // Exception list has no meaning in Bypass mode — see Exception List
    // Applicability section and Open Design Questions → Q2.
    m_proxy.setFlag(AppModuleHttpProxy::HTTP_DOMAIN_FRONTING_BYPASSED);
}
```

**`updateNetSessionDestHostResolvedIp()` — bypass guard when flag set:**
```cpp
void HttpRequestEngine::updateNetSessionDestHostResolvedIp(
    ns_http_destinfo_t *destinfo)
{
    if (!destinfo) return;

    if (m_proxy.isFlagSet(AppModuleHttpProxy::HTTP_DOMAIN_FRONTING_BYPASSED)) {
        // Domain fronting bypass: clear stale SNI-resolved IP and advance
        // to blocked.com's IP with ResolvedIpFromHttpHost.
        // The three-condition guard below would otherwise block this because
        // m_destHost.ip is non-empty (SNI-resolved) and m_destHost.value
        // (SNI domain) != destinfo->client_domain (Host header domain).
        m_proxy.clearFlag(AppModuleHttpProxy::HTTP_DOMAIN_FRONTING_BYPASSED);
        ns::host::IpSource ipSource = getIpSourceFromDestInfo(destinfo);
        if (ipSource != ns::host::IpSource::Unknown) {
            m_nsession.clearDestHostResolvedIp();
            m_nsession.setDestHostResolvedIp(destinfo->addr.ipstr, ipSource);
            // ipSource = ResolvedIpFromHttpHost = 8 — closes ENG-970460 Gap #1
            // setDestHostResolvedIp atomically calls populateDestGeoInfo()
        }
        return;
    }

    // ... existing guard logic unchanged ...
    const auto &destHost = m_nsession.getDestHost();
    if (!destHost.ip.empty() ||
        destHost.value.empty() ||
        destHost.value != destinfo->client_domain) {
        return;
    }
    ns::host::IpSource ipSource = getIpSourceFromDestInfo(destinfo);
    if (ipSource != ns::host::IpSource::Unknown) {
        m_nsession.setDestHostResolvedIp(destinfo->addr.ipstr, ipSource);
    }
}
```

**`dnsReplyOnFailure()` — force teardown in bypass path:**
```cpp
// If domain fronting bypass was in progress and DNS failed,
// do not defer — we cannot proceed without the true destination IP.
if (isFlagSet(HTTP_DOMAIN_FRONTING_BYPASSED)) {  // note: AppModuleHttpProxy flag
    clearFlag(HTTP_DOMAIN_FRONTING_BYPASSED);
    sendErrHtmlPageForDnsFailure();
    return false;
}
```

---

## Error Handling

**DNS failure for `blocked.com`:** `HTTP_DOMAIN_FRONTING_BYPASSED` is cleared and the
connection is torn down regardless of `defer-dns-error` configuration. The proxy cannot
proceed without the true destination IP — using the SNI-resolved IP would reintroduce the
attack. A 502 error is sent to the client.

**Staged config gate:** New global staged config `domain-fronting-bypass-fix` (default
`true` — fix active) and per-tenant `http_features.featurec` flag (default `true`). Either
set to `false` reverts to old Bypass behavior. Follows the `ssl-layer-geoip-preserve`
two-level gate pattern.

---

## Design Contracts

1. When `HTTP_DOMAIN_FRONTING_BYPASSED` is set and DNS succeeds, `m_destHost.ip` will
   be `blocked.com`'s IP and `m_destHost.ipSource = ResolvedIpFromHttpHost = 8` after
   `updateNetSessionDestHostResolvedIp()` runs.

2. `get_dstip()` returns `blocked.com`'s IP to the policy engine — policy is evaluated
   against the true destination, not the SNI domain.

3. ~~The tenant exception list is respected in Bypass mode.~~ **Removed (2026-06-15,
   confirmed by PM):** the exception list has no meaning in Bypass mode. Destination
   enforcement applies unconditionally to all Bypass-mode domain fronting detections.
   Exception list check removed from `runRequestHeader()`.

4. **IP-in-SNI connections are excluded.** When the SNI field contains a raw IP address
   (e.g., `SNI = 1.2.3.4`, `Host: example.com`), `HTTP_DOMAIN_FRONTING_BYPASSED` is
   not set. `detectDomainFronting()` does not perform this exclusion — the guard
   `!ns_netutil_is_ip_addr(sni.c_str(), nullptr)` is added explicitly in
   `runRequestHeader()` before setting the flag.

5. DNS failure in the bypass path always results in connection teardown, regardless of
   `defer-dns-error` configuration.

6. `ResolvedIpFromHttpHost = 8` is produced for the first time in this code path —
   closing ENG-970460 Known Gap #1. No separate ticket required.

---

## Open Design Questions

These questions were identified after the PR was floated (ENG-1036449, PR #15237) and
sent to the product management team for confirmation.

### Q1 — What is the intended behavior of "Bypass" in the face of domain fronting?

**Working definition (confirmed by PM, 2026-06-15):**
- **Block:** Domain fronting detected → connection terminated immediately. No traffic flows.
- **Bypass:** Domain fronting detected → do not terminate, but enforce the destination the
  HTTP Host header actually declares. Connect to the Host domain's own IP, not the
  SNI-routed IP. Policy is evaluated against the true destination.

PM's framing: "the goal is to never trust the original destination IP for the requested
domain when we have it. For domain fronting exceptions, the main question is which domain
the proxy should connect to: SNI or HTTP Host. Then use this to do DNS resolution."

Answer: **HTTP Host domain**. The SNI-resolved IP is the CDN's IP, not the actual
requested domain's IP. ENG-1036449 replaces it with the correct one.

**Status:** Confirmed. ✓

### Q2 — Should the tenant exception list apply in Bypass mode?

**Answer (confirmed, 2026-06-15):** No.

**Reasoning (pre-confirmation analysis):**

An early draft of the implementation added a tenant exception list check in the Bypass
path, interpreting it as: "for these specific domains, let CDN routing proceed even in
Bypass mode." Two concerns were identified with this approach:

1. **Semantic mismatch.** The exception list was designed for Block mode: "block domain
   fronting globally, except for these trusted domains." In Bypass mode, re-using the
   exception list would extend its semantics to "don't enforce correct destination for
   these domains." A tenant who added a domain to the exception list may have done so
   only to avoid *blocking* — they may not have intended to also waive destination
   enforcement in Bypass mode.

2. **Dead configuration / unreachability.** A tenant in Bypass mode is unlikely to also
   have domains on the exception list. The exception list is only meaningful in Block
   mode. In Bypass mode it is effectively dead configuration — the check would never be
   triggered in practice.

The cleaner framing that resolves both concerns: if Bypass means "enforce the HTTP Host
header destination," then there is *nothing to except* — every domain in Bypass mode
gets destination enforcement applied, unconditionally. The exception list belongs
exclusively to Block mode. Under this framing, the question of whether the exception
list check is reachable in Bypass mode becomes moot: it is not consulted at all.

**Implementation consequence:** The tenant exception list check was removed from the
Bypass path in `runRequestHeader()`. `HTTP_DOMAIN_FRONTING_BYPASSED` is set
unconditionally for all Bypass-mode domain fronting detections (subject to IP-in-SNI
guard and two-level feature flag). Design Contract 3 (exception list respected in Bypass
mode) is removed.

**Status:** Confirmed. ✓ Code change applied in PR #15237.

### Process note

These questions should have been raised and answered during the brainstorming/research
phase, before any design was written. The design was built on an assumed interpretation
of "Bypass" that was inferred from code behavior rather than confirmed with PM. This is
a process gap — see ADR `2026-04-14-nplan6618-architectural-decisions.md` for the lesson
recorded.

---

## Known Gaps and Deferred Work

1. **HTTP/2:** Domain fronting detection behavior under HTTP/2 needs separate analysis.
   `detectDomainFronting()` is currently skipped for RBI listener; HTTP/2 handling is
   not verified.

2. **SNI ≠ CONNECT host policy (NPLAN-143 Phase 2):** Today hard-coded to SNI priority.
   Configurable policy is out of scope.

3. **`defer-dns-error` interaction in bypass path:** When `defer-dns-error` is enabled
   and DNS fails for `blocked.com`, the current fix forces teardown. A future enhancement
   could consider whether falling through to a block event (rather than teardown) is more
   appropriate, but this is deferred.

---

## Testing

**Unit tests — `libs/http/test/ns_http_appmodulehttpproxy_test/`:**

| Test | Scenario | Expected |
|---|---|---|
| `DomainFrontingBypass_CorrectIpUsed` | SNI=allowed.com, Host=blocked.com, Bypass policy, DNS succeeds | `m_destHost.ip = blocked.com_ip`, `ipSource = ResolvedIpFromHttpHost = 8` |
| `DomainFrontingBypass_DnsFailure_Teardown` | DNS fails for blocked.com | Teardown, `HTTP_DOMAIN_FRONTING_BYPASSED` cleared |
| ~~`DomainFrontingBypass_TenantException_NotTriggered`~~ | ~~Host in tenant exception list~~ | Removed — exception list not consulted in Bypass mode (PM confirmed 2026-06-15) |
| `DomainFrontingBypass_GlobalFlagOff_OldBehavior` | Global staged config disabled | SNI IP used (old behavior) |
| `DomainFrontingBypass_TenantFlagOff_OldBehavior` | Per-tenant flag disabled | SNI IP used (old behavior) |
| `DomainFrontingBypass_GlobalException_NotTriggered` | SNI in global exception list | `detectDomainFronting()` returns false, flag not set |
| `DomainFrontingBypass_IpInSni_NotTriggered` | SNI=1.2.3.4, Host=example.com, Bypass policy | Flag not set — legitimate IP-direct connection |
| `DomainFrontingBlock_Unchanged` | Block policy configured | Existing block behavior unchanged |

**Regression:** All existing `detectDomainFronting` and `DomainFronting*` tests must
pass unchanged.
