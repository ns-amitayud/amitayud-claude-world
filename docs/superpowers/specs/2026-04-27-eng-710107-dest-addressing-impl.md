# ENG-710107: Destination Addressing — Implementation Brief

**Date:** 2026-04-27
**Branch base:** `develop` (post #14206 merge, commit `8d5d362579`)
**Jira:** ENG-710107
**Related spec:** `2026-04-14-nplan6618-architectural-decisions.md` (decision rationale)

This file is the **forward-looking implementation guide** for a new feature branch on top
of develop. It describes the current state of each affected function and exactly what must
change. Do not reference the old #14246 branch — that work is superseded.

---

## Context: What #14206 delivered and what it left incomplete

PR #14206 (merged 2026-04-27) introduced DNS resolution at the SSL layer before
`getPolicyAction()`. The core machinery works. The following gaps remain in develop:

1. No `DnsAttemptedAndFailed` sentinel — `get_dstip()` cannot distinguish "DNS never ran"
   from "DNS failed". Row 3 of the behaviour matrix (DNS fail + allow with client IP) is
   broken.
2. `get_dstip()` returns `c_str()` — dangling pointer risk.
3. `dnsLookupFailureHandler()` does not evaluate `defer-dns-error`.
4. `get_dstip()` is still gated on `isSslLayerDnsResolutionEnabled()` flag rather than
   being driven purely by `IpSource` state.
5. GeoIP is not populated at SSL layer DNS resolution time.
6. SNI source field set incorrectly in some `handleNoSniScenario()` branches.
7. `SslLayerDnsResolutionFailure` unit test has an inverted assertion: `ASSERT_EQ(ret, 1)`
   with comment "Expected SSL_connect to fail due to DNS failure" — but `1` is
   `SSL_connect` success in OpenSSL. The test does not verify what it claims to verify.

Additionally, one **verification item** must be confirmed before the PR is considered
complete — it may or may not require a code change:

V1. TOCTOU on `m_state` after `performDnsLookup()` — the implementer of #14206 claimed
    `dnsLookupReply()` always executes on the same service thread, making the apparent
    race between `performDnsLookup()` returning and the `m_state == SSL_DO_DNS_LOOKUP`
    check impossible. This was accepted but never independently verified. Confirm or
    refute by reading the task-notify dispatch code.

This PR addresses all seven gaps and resolves the verification item.

---

## Current state of develop — affected code

### `IpSource` enum — `libs/netsvc/NsHost.hpp`

```cpp
enum class IpSource : unsigned int {
    Unknown = 0,
    OriginalDestIp,                  // client-provided IP from InlineConnInfo
    OriginalDestIpFromSni,           // raw IP address found in SNI field
    OriginalDestIpFromConnect,       // raw IP address found in CONNECT Host header
    ResolvedIpFromInlineConnInfoDn,  // DNS resolved using domain from InlineConnInfo
    ResolvedIpFromHttpConnectHost,   // DNS resolved using HTTP CONNECT host
    ResolvedIpFromSni,               // DNS resolved using SNI domain
    ResolvedIpFromHttpHost,          // DNS resolved using HTTP Host header or URI
    Last
};
```

**Missing:** `DnsAttemptedAndFailed` sentinel value.

---

### `setDestHostResolvedIp()` — `libs/netsvc/NetSession.hpp:1736`

```cpp
void setDestHostResolvedIp(std::string ip, ns::host::IpSource ipSource,
                           int64_t dnsLatencyNsec = 0)
{
    m_destHost.ip = std::move(ip);
    m_destHost.ipSource = ipSource;
    m_destHost.dnsLatencyNsec = dnsLatencyNsec;
}
```

**Missing:**
- Advancement-only rule: lower-trust sources should not overwrite higher-trust ones.
- GeoIP population: `populateBackGeoInfo()` should be called atomically here.
- Clear `ip` when `ipSource == DnsAttemptedAndFailed`.

---

### `isDestHostIpResolved()` — `libs/netsvc/NetSession.hpp:1753`

```cpp
bool isDestHostIpResolved() const
{
    return m_destHost.ipSource == ns::host::IpSource::ResolvedIpFromSni ||
           m_destHost.ipSource == ns::host::IpSource::ResolvedIpFromHttpConnectHost ||
           m_destHost.ipSource == ns::host::IpSource::ResolvedIpFromInlineConnInfoDn;
}
```

This will need updating once `DnsAttemptedAndFailed` is added, but the function itself
is correct for the success cases.

---

### `get_dstip()` — `libs/netsvc/src/NetSession.cpp:93`

```cpp
const char *
NSessionBypassArgs::get_dstip(char *buf, size_t bufsz) const
{
    // If SSL Layer DNS Resolution is enabled
    if (m_nsession.isSslLayerDnsResolutionEnabled()) {
        const auto &destHost = m_nsession.getDestHost();
        if (!destHost.ip.empty()) {
            return destHost.ip.c_str();   // ← dangling pointer risk
        }
        return nullptr;   // ← covers both "DNS never ran" and "DNS failed" — wrong
    }

    // DEPRECATED: Legacy path
    auto *res = m_nsession.getBackGeoIpResult();
    if (res) { return res->ipaddr.ptr; }

    auto fconn = m_nsession.frontConn();
    if (fconn) {
        auto originalDest = fconn->getOriginalDestHost().c_str();  // ← dangling pointer
        if (ns_netutil_is_ip_addr(originalDest, nullptr)) {
            return originalDest;
        }
    }
    return nullptr;
}
```

**Problems:**
- Gated on `isSslLayerDnsResolutionEnabled()` flag — should be driven by `IpSource` alone.
- Returns `c_str()` directly — dangling pointer when `m_destHost.ip` is mutated.
- `nullptr` returned for both "DNS never ran" and "DNS failed" — cannot distinguish.
- Legacy path `getOriginalDestHost().c_str()` on a temporary — UB.

---

### `dnsLookupFailureHandler()` — `libs/netlayer/src/SslServerLayer.cpp:803`

```cpp
void SslServerLayer::dnsLookupFailureHandler()
{
    ns_swatch_stop(&m_dnsLookupTimer);
    ns_swatch_diff(&m_dnsLookupTimer);
    LDLOG(1) << "DNS resolution failed for m_destHost:"
             << m_conn->netSession()->getDestHostStr();
}
```

**Problem:** Does not set sentinel, does not evaluate `defer-dns-error`. State machine
unconditionally advances to `SSL_CHECK_POLICY_ACTION` regardless.

---

### `handleNoSniScenario()` — `libs/netlayer/src/SslServerLayer.cpp:599`

The function has four branches. The source correctness issue is in the branch where
`destHost.ipSource == ResolvedIpFromHttpConnectHost` (no SNI, CONNECT already resolved):

```cpp
m_conn->setSslSni(destHost.value.c_str(), destHost.value.length(), destHost.source);
```

`destHost.source` here is `Source::HttpConnectHost` — correct for this branch. The
concern raised by ns-lwu (comment `3090889639`) is that in `getPolicyAction()`:

```cpp
destHost.value = m_conn->getSslSni();
destHost.source = m_conn->getSslSniSource();
```

If `setSslSni()` was called with a non-SNI source in any branch, `getSslSniSource()`
will return that wrong source to `getPolicyAction()`. Audit each branch carefully.

---

## What must be built — Point by Point

### Point 1+2: Ordered `IpSource` enum + advancement-only `setDestHostResolvedIp()` + GeoIP

**Step 1:** Add `DnsAttemptedAndFailed` to the `IpSource` enum in `NsHost.hpp`, with
integer values encoding the trust order:

```cpp
enum class IpSource : int {
    Unknown                       = 0,
    OriginalDestIp                = 1,   // client-provided, least trusted
    OriginalDestIpFromSni         = 2,   // raw IP in SNI
    OriginalDestIpFromConnect     = 3,   // raw IP in CONNECT
    DnsAttemptedAndFailed         = 4,   // sentinel: DNS tried, failed — no IP
    ResolvedIpFromInlineConnInfoDn = 5,
    ResolvedIpFromHttpConnectHost  = 6,
    ResolvedIpFromSni              = 7,
    ResolvedIpFromHttpHost         = 8,
    Last
};
```

Note: changing the underlying type from `unsigned int` to `int` is needed for the `<=`
comparison in the advancement-only rule.

**Step 2:** Rewrite `setDestHostResolvedIp()`:

```cpp
void setDestHostResolvedIp(std::string ip, ns::host::IpSource ipSource,
                           int64_t dnsLatencyNsec = 0)
{
    // Advancement-only: never regress to a less trusted source
    if (static_cast<int>(ipSource) <= static_cast<int>(m_destHost.ipSource)) {
        return;
    }
    m_destHost.ip = std::move(ip);
    m_destHost.ipSource = ipSource;
    m_destHost.dnsLatencyNsec = dnsLatencyNsec;
    // Atomically populate GeoIP for every DNS-resolved IP.
    // The empty() guard prevents GeoIP calls when DNS failed (ip was cleared).
    if (!m_destHost.ip.empty()) {
        populateBackGeoInfo(m_destHost.ip.c_str());
    }
}
```

When `dnsLookupFailureHandler()` calls this with `DnsAttemptedAndFailed`, it passes
an empty string for `ip`:
```cpp
setDestHostResolvedIp("", ns::host::IpSource::DnsAttemptedAndFailed);
```

---

### Point 3: `dnsErrorShouldSuppressClientIp()` + update `dnsLookupFailureHandler()`

**Step 1:** Add `dnsErrorShouldSuppressClientIp()` to `NetSession` (or as a method on
`NSessionBypassArgs`). It reads `defer-dns-error` from the tenant feature config:

```cpp
bool dnsErrorShouldSuppressClientIp() const
{
    auto tenantFeature =
        NetLayerTenantFeatureCfgMgr::getInstance().getFeatureCfg(frontConn()->getTenantId());
    if (!tenantFeature) return false;
    // defer-dns-error = "block" or "no-dest-ip" → suppress client IP
    return tenantFeature->m_deferDnsErrorBlock;  // verify exact field name
}
```

**Step 2:** Update `dnsLookupFailureHandler()`:

```cpp
void SslServerLayer::dnsLookupFailureHandler()
{
    ns_swatch_stop(&m_dnsLookupTimer);
    ns_swatch_diff(&m_dnsLookupTimer);

    if (!m_conn->netSession()->isDestHostIpResolved()) {
        // DNS failed and no prior resolution (e.g. from CONNECT) is available.
        // Set the sentinel so get_dstip() can distinguish this from "DNS never ran".
        m_conn->netSession()->setDestHostResolvedIp(
            "", ns::host::IpSource::DnsAttemptedAndFailed);
    }
    LDLOG(1) << "DNS resolution failed for m_destHost:"
             << m_conn->netSession()->getDestHostStr();
}
```

---

### Point 4: `IpSource`-driven `get_dstip()`, retire flag

Replace the current `isSslLayerDnsResolutionEnabled()` gated implementation with one
driven purely by `IpSource`:

```cpp
const char *
NSessionBypassArgs::get_dstip(char *buf, size_t bufsz) const
{
    const auto &destHost = m_nsession.getDestHost();

    // DNS succeeded — return service-resolved IP via caller-provided buffer
    if (m_nsession.isDestHostIpResolved()) {
        if (buf != nullptr && bufsz > 0) {
            ns_strncpy(buf, destHost.ip.c_str(), bufsz);
            return buf;
        }
        return nullptr;  // caller must always pass a valid buffer
    }

    // DNS attempted but failed — apply defer-dns-error policy
    if (destHost.ipSource == ns::host::IpSource::DnsAttemptedAndFailed) {
        if (m_nsession.dnsErrorShouldSuppressClientIp()) {
            return nullptr;   // rows 4a and 4b: block or F2P
        }
        // row 3: defer-dns-error = allow → fall through to client IP
    }

    // DNS never ran — legacy path (feature off, or no domain available)
    auto *res = m_nsession.getBackGeoIpResult();
    if (res) { return res->ipaddr.ptr; }

    auto fconn = m_nsession.frontConn();
    if (fconn) {
        // Store in local variable to avoid c_str() on temporary
        m_cachedOrigDest = fconn->getOriginalDestHost();
        if (ns_netutil_is_ip_addr(m_cachedOrigDest.c_str(), nullptr)) {
            return m_cachedOrigDest.c_str();
        }
    }
    return nullptr;
}
```

Note: the legacy path dangling pointer fix requires either a cached member or passing
a caller-owned buffer. Verify the cleanest approach by checking all call sites of
`get_dstip()`.

**Retire `isSslLayerDnsResolutionEnabled()`** from `get_dstip()` and `AppModuleLayer`.
It stays only in `SslServerLayer`'s constructor where it governs whether DNS is attempted.

---

### Point 5: Fix dangling pointer in legacy path

As noted in Point 4 above — `fconn->getOriginalDestHost()` returns `std::string` by
value. Store it in a local variable before calling `c_str()`.

---

### Point 6: `defer-dns-error` at SSL layer (depends on Point 3)

Covered by the `dnsLookupFailureHandler()` update in Point 3 above.

---

### Point 7: Fix inverted assertion in `SslLayerDnsResolutionFailure` test

**File:** `libs/netlayer/test/ns_ssl_server_layer_test/src/main_sni.cpp`

Current code:
```cpp
// Connection should fail due to DNS failure and/or forced readFront error
ASSERT_EQ(ret, 1) << "Expected SSL_connect to fail due to DNS failure";
```

`SSL_connect` returns `1` on **success** and `-1` on failure (OpenSSL convention). The
comment says "Expected to fail" but the assertion checks for success. This means the test
passes only if the connection succeeds — which contradicts its stated purpose.

**Required fix:** Determine the actual intended behaviour. Two possibilities:

1. **If the test intends to verify the connection fails:** change to `ASSERT_EQ(ret, -1)`.
2. **If the SSL handshake succeeds despite DNS failure** (because `forceStopReadFrontWError`
   causes the failure at a later stage, after `SSL_connect` returns 1): the assertion is
   correct but the comment is wrong — change the comment to "Expected SSL_connect to
   succeed; DNS failure is detected at AppModule layer".

Read the test setup (`setupTlsConnectionWithInlineConnInfo`, `forceStopReadFrontWError`)
to determine which scenario applies before changing the assertion.

---

### Point 8: SNI source field correctness in `handleNoSniScenario()`

Audit every branch of `handleNoSniScenario()` that calls `setSslSni()`. Confirm the
`source` argument passed matches the actual origin of the value:

| Branch | Value passed to `setSslSni()` | Expected source |
|---|---|---|
| `ResolvedIpFromHttpConnectHost` — use CONNECT host as SNI | `destHost.value` | `destHost.source` (currently `HttpConnectHost`) ✓ |
| CONNECT/inline conn domain, no SNI — DNS lookup | `destHost.value` | `destHost.source` ✓ |
| SNI is IP address | `m_conn->getSslSni()` | No `setSslSni()` called (uses `setDestHostResolvedIp`) ✓ |
| CONNECT host is IP address | `destHost.value` | `destHost.source` — **verify `HttpConnectHost` check is explicit** |
| Inline conn info IP fallback | `destHost.ip` | `destHost.source` — **verify source is correct here** |

In `getPolicyAction()`, `getSslSniSource()` is used as `destHost.source`. Verify that
for every path through `preprocessForPolicyLookup()`, the source returned matches the
true origin of the domain/IP being evaluated.

Note: Point 8 is independent of Points 1–7 and can be implemented in any order.

---

### Verification Item V1: TOCTOU on `m_state` after `performDnsLookup()`

**File:** `libs/netlayer/src/SslLayer.cpp` (state machine), `libs/netlayer/src/SslServerLayer.cpp`

The state machine checks `m_state` after `performDnsLookup()` returns to detect whether
an async DNS operation is in progress:

```cpp
case SSL_DO_DNS_LOOKUP: {
    performDnsLookup();
    if (m_state == SSL_DO_DNS_LOOKUP) {
        ret = true;   // async in progress
    } else {
        continue;
    }
    break;
}
```

`dnsLookupReply()` (the async callback) calls `setState(SSL_CHECK_POLICY_ACTION)` then
immediately calls `readData()`, re-entering the state machine. If the callback could fire
between `performDnsLookup()` returning and the `m_state` check, the outer call would see
`SSL_CHECK_POLICY_ACTION` and double-execute policy lookup.

The implementer of #14206 claimed this is impossible because `dnsLookupReply()` always
executes on the same service thread as `performDnsLookup()` — the task-notify mechanism
guarantees same-thread dispatch.

**Verification steps:**
1. Find where `TaskNotify` dispatches its callback — locate the dispatch path from
   `DnsCache::lookup()` through the task system to `SslServerLayer::dnsLookupReply()`.
2. Confirm whether the dispatch is synchronous on the calling thread or posted to a
   thread pool.
3. **If same-thread confirmed:** add a comment in the state machine code documenting
   the thread-safety guarantee so future readers don't re-raise this concern.
4. **If cross-thread possible:** add a state snapshot before calling `performDnsLookup()`
   and compare after, or have `performDnsLookup()` return an explicit status enum
   rather than relying on post-call state inspection.

---

## Behaviour matrix (target state)

| Row | ipSource | F2P | defer-dns-error | `get_dstip()` returns | Outcome |
|---|---|---|---|---|---|
| 1 | `OriginalDestIp` | either | n/a | client IP (legacy) | Feature off |
| 2 | `ResolvedIpFrom*` | either | n/a | service-resolved IP via buf | Correct ✓ |
| 3 | `DnsAttemptedAndFailed` | absent | `allow` | client IP (fall-through) | Allow with client IP ✓ |
| 4a | `DnsAttemptedAndFailed` | absent | `block`/`no-dest-ip` | `nullptr` | Blocked ✓ |
| 4b | `DnsAttemptedAndFailed` | present | either | `nullptr` | F2P handles it ✓ |

---

## Design contracts (reviewer checklist)

1. After DNS failure at SSL layer, `m_destHost.ipSource == IpSource::DnsAttemptedAndFailed`
   and `m_destHost.ip` is empty.
2. `setDestHostResolvedIp()` with a lower-trust `ipSource` than the current value is a
   no-op — the existing value is preserved.
3. Every successful call to `setDestHostResolvedIp()` with a non-empty IP triggers
   `populateBackGeoInfo()` atomically.
4. `get_dstip()` never reads `isSslLayerDnsResolutionEnabled()` — it is driven solely
   by `IpSource`.
5. `get_dstip()` returns the service-resolved IP via the caller-provided buffer, never
   via a raw `c_str()` pointer into `std::string` storage.
6. Row 3 of the behaviour matrix: when `ipSource == DnsAttemptedAndFailed` and
   `dnsErrorShouldSuppressClientIp()` returns `false`, `get_dstip()` falls through to
   return the client IP from InlineConnInfo.
7. Row 4: when `ipSource == DnsAttemptedAndFailed` and `dnsErrorShouldSuppressClientIp()`
   returns `true`, `get_dstip()` returns `nullptr`.
8. In `handleNoSniScenario()`, the `source` argument to every `setSslSni()` call
   correctly identifies the origin of the value being stored.
9. `SslLayerDnsResolutionFailure` test assertion is consistent with its comment — either
   both assert failure, or both assert success with a correct explanation of why.

---

## Implementation sequence

```
1+2 (ordered enum + advancement-only + GeoIP)
  → 3 (DnsAttemptedAndFailed sentinel + dnsErrorShouldSuppressClientIp() + dnsLookupFailureHandler)
    → 4+5 (IpSource-driven get_dstip() + dangling pointer fix)
      → 6 (covered by 3)
        → 7 (test assertion fix — independent)
        → 8 (handleNoSniScenario source audit — independent)
        → V1 (TOCTOU verification — do early; may produce a code change or just a comment)
```

---

## Files to modify

| File | Change |
|---|---|
| `libs/netsvc/NsHost.hpp` | Add `DnsAttemptedAndFailed` to `IpSource`; change underlying type to `int` |
| `libs/netsvc/NetSession.hpp` | Rewrite `setDestHostResolvedIp()`; add `dnsErrorShouldSuppressClientIp()` |
| `libs/netsvc/src/NetSession.cpp` | Rewrite `get_dstip()` |
| `libs/netlayer/src/SslServerLayer.cpp` | Update `dnsLookupFailureHandler()`; audit `handleNoSniScenario()` |
| `libs/netlayer/test/ns_ssl_server_layer_test/src/main_sni.cpp` | Fix inverted assertion in `SslLayerDnsResolutionFailure` (Gap 7); add tests for rows 3, 4a, 4b of behaviour matrix |
