# NPLAN-6618: Architectural Decision Record

Decisions made during review of PRs #14206 and #14246, informing ENG-970460.
Each point is discussed and resolved before implementation begins.

**Sections:**
- Points 1–4: Implementation decisions for PR #14246 (original scope)
- Points 5–8: Additional items from merged #14206 findings, carried to ENG-710107
- Point 9: Domain fronting — known gap in NPLAN-6618 scope, not addressed by either PR

---

## Final Decision: Path Forward for PR #14246

1. ~~**Wait for #14206 to merge**~~ — **DONE** (merged 2026-04-27, commit `8d5d362579`).
2. **Start fresh on top of merged develop** — the old #14246 branch is superseded.
   The naming changes that landed in develop (from #14206) are the canonical names to use:

   | Name in develop (use these) |
   |---|
   | `IpSource` enum (was `HostIpSource`) |
   | `ResolvedIpFromSni` (was `DnsResolvedIpUsingSni`) |
   | `ResolvedIpFromHttpConnectHost` (was `DnsResolvedIpUsingConnectHost`) |
   | `isDestHostIpResolved()` (was `destHostIpIsResolvedIp()`) |
   | `IpSource::OriginalDestIpFromSni` (unchanged) |

3. **Implement Points 1+2** — remove `svcResolvedDestAddr`, implement ordered enum +
   advancement-only rule in `setDestHostResolvedIp()`, bake GeoIP in atomically, clear
   `ip` when setting `DnsAttemptedAndFailed`.
4. **Implement Point 3** — add `DnsAttemptedAndFailed` to the renamed enum.
5. **Implement Point 4** — rewrite `get_dstip()` driven by `IpSource`, retire
   `isSslLayerDnsResolutionEnabled()` from all downstream consumers.
6. **Implement Point 5** — fix `get_dstip()` dangling `c_str()` pointer (Finding 2 from
   #14206 review).
7. **Implement Point 6** — structural `defer-dns-error` fix at SSL layer: call
   `dnsErrorShouldSuppressClientIp()` from `dnsLookupFailureHandler()` (Finding 3 from
   #14206 review). Depends on Point 3 (`DnsAttemptedAndFailed` + `dnsErrorShouldSuppressClientIp()`).
8. **Implement Point 7** — fix SNI source field correctness in `handleNoSniScenario()`
   (Finding 7 from #14206 review).
9. **Implement Point 8** — fix inverted assertion in `SslLayerDnsResolutionFailure` test
   (Finding 4 from #14206 review).

---

## Implementation Order

| Point | Description | Depends on |
|---|---|---|
| 1 | Remove `svcResolvedDestAddr`; ordered `IpSource` enum; advancement-only rule | Rebase on #14206 first |
| 2 | Bake GeoIP into `setDestHostResolvedIp()` | Must be done together with Point 1 |
| 3 | Add `DnsAttemptedAndFailed` to enum; implement `dnsErrorShouldSuppressClientIp()` | Point 1 (enum must exist first) |
| 4 | `IpSource`-driven `get_dstip()`; retire per-connection flag | Points 1 and 3 |
| 5 | Fix `get_dstip()` dangling `c_str()` — restore buffer-copy or document lifetime contract | Point 4 (same function) |
| 6 | Structural `defer-dns-error` fix at SSL layer — `dnsLookupFailureHandler()` calls `dnsErrorShouldSuppressClientIp()` | Point 3 (`dnsErrorShouldSuppressClientIp()` must exist) |
| 7 | Fix SNI source field correctness in `handleNoSniScenario()` | — (independent) |
| 8 | Fix inverted assertion in `SslLayerDnsResolutionFailure` test | — (independent) |

**Points 1 and 2 must be implemented together.** Point 2 moves `populateBackGeoInfo()`
from `setSvcResolvedDestAddr()` to `setDestHostResolvedIp()`. Implementing Point 2 without
Point 1 leaves `setSvcResolvedDestAddr()` with a duplicate GeoIP call and the codebase in
an inconsistent intermediate state. A single pass removes `svcResolvedDestAddr` and
installs the new GeoIP coupling cleanly.

**Point 3 is trivial** for the enum value — add `DnsAttemptedAndFailed` after rebasing on
#14206's renames. `dnsErrorShouldSuppressClientIp()` is the substantive addition (reads
`defer-dns-error` tenant config).

**Point 4 is independent of Points 2 and 3** — it is about how `get_dstip()` reads the
result, not how it is produced. It can follow after Points 1+2 and 3 are complete.

**Point 5 follows Point 4** — both touch `get_dstip()` and should be done in the same pass
to avoid conflicting edits to the same function.

**Point 6 follows Point 3** — `dnsLookupFailureHandler()` cannot call
`dnsErrorShouldSuppressClientIp()` until it is defined.

**Points 7 and 8 are independent** — both are bug fixes that do not interact with the
enum or `get_dstip()` changes. They can be done at any point in the sequence.

**Recommended implementation sequence:** 1+2 → 3 → 4+5 → 6 → 7 → 8

---

## Point 1 — `svcResolvedDestAddr`: keep or remove?

**Status: Resolved — remove it**

### Background

`svcResolvedDestAddr` was introduced in PR #14246 as a dedicated, stable, session-level
field for the service-resolved destination IP. It was designed to solve two problems:

1. **Write-once / immutability** — `m_destHost` is mutable; `svcResolvedDestAddr` ensured
   the service-resolved IP could not be overwritten by a later stage.
2. **Sentinel** — its empty vs. set state distinguished "DNS not run" from "DNS ran and
   succeeded," enabling `get_dstip()` to suppress the client IP for the "no dest IP"
   fallback case (row 4 of the table).

hpandey21 argued in PR #14206 that `svcResolvedDestAddr` is redundant with `m_destHost`
and creates a single-source-of-truth violation — two objects tracking the same destination
data, with every consumer forced to decide which is authoritative.

### Decision

Both purposes of `svcResolvedDestAddr` can be absorbed into `m_destHost` with two additions:

1. **Sentinel absorbed by `HostIpSource`** — Add `DnsAttemptedAndFailed` as a new
   `HostIpSource` value. When DNS fails, `dnsLookupFailureHandler()` sets
   `m_destHost.ipSource = DnsAttemptedAndFailed` instead of leaving it as `OriginalDestIp`.
   `get_dstip()` can then distinguish "DNS not run" from "DNS failed" and return `nullptr`
   for row 4.

   Note: PR #14206 will not implement the sentinel — it is focused on functionality and
   accuracy, not error condition handling. PR #14246 will implement the sentinel after
   #14206 merges.

2. **Immutability absorbed by advancement-only rule** — Implement an ordered `HostIpSource`
   enum and enforce in `setDestHostResolvedIp()` that `ipSource` can only advance, never
   regress. Once a DNS-resolved IP is stored, no subsequent call with a lower `ipSource`
   value can overwrite it. `m_destHost` gains effective write-once semantics for
   DNS-resolved IPs.

With both additions in place, `svcResolvedDestAddr` has no remaining purpose that
`m_destHost` + enhanced `HostIpSource` does not already cover.

### Consequence for PR #14246

Rather than introducing `svcResolvedDestAddr`, PR #14246 should:
- Add `DnsAttemptedAndFailed` to `HostIpSource`
- Implement the advancement-only rule in `setDestHostResolvedIp()`
- Have `get_dstip()` read from `m_destHost` directly, gated on `HostIpSource`

This requires significant restructuring of #14246 after #14206 merges — not just minor
additions.

### Ordered `HostIpSource` enum (proposed)

```cpp
enum class HostIpSource : int {
    Unknown                       = 0,
    OriginalDestIp                = 1,  // client-provided, least trusted
    DnsAttemptedAndFailed         = 2,  // sentinel: DNS tried, failed
    DnsResolvedIpUsingConnectHost = 3,  // resolved via HTTP CONNECT
    DnsResolvedIpUsingSni         = 4,  // resolved via SNI, most trusted
};
```

The ordering encodes the trust hierarchy directly. A single `<=` comparison in
`setDestHostResolvedIp()` enforces advancement-only for all current and future values —
no need to enumerate cases explicitly.

### Advancement-only rule in `setDestHostResolvedIp()` (proposed)

```cpp
void setDestHostResolvedIp(std::string ip, ns::host::HostIpSource ipSource)
{
    if (ipSource <= m_destHost.ipSource) {
        // Never regress to a less reliable source
        DLOG(2) << "Ignoring setDestHostResolvedIp: current ipSource="
                << static_cast<int>(m_destHost.ipSource)
                << " >= requested ipSource=" << static_cast<int>(ipSource);
        return;
    }
    m_destHost.ip = std::move(ip);
    m_destHost.ipSource = ipSource;
}
```

Key properties:
- `DnsResolvedIpUsingSni = 4` cannot be overwritten by `DnsResolvedIpUsingConnectHost = 3`
  if SNI was resolved first — the more trusted source is preserved
- `DnsAttemptedAndFailed = 2` is a valid advancement from `OriginalDestIp = 1` — the
  failure is "better known" than the original client state, but below any successful resolution
- The rule applies only to `setDestHostResolvedIp()`. `setDestHost()` (called during
  connection setup from InlineConnInfo) is a separate setter and is not subject to this rule

### `dnsErrorShouldSuppressClientIp()` — definition and what it reads

This function answers: "given that DNS was attempted at the SSL layer and failed,
should the client-provided IP be suppressed from policy evaluation?"

It reads the `defer-dns-error` configuration for the tenant. `defer-dns-error`
is a per-tenant config that governs what nsproxy does when DNS fails. Its values
map as follows:

| `defer-dns-error` value | `dnsErrorShouldSuppressClientIp()` returns | Effect |
|---|---|---|
| `allow` (use client IP) | `false` | Client IP falls through to policy engine |
| `block` / `no-dest-ip` | `true` | `nullptr` returned; client IP suppressed |

**Where the config lives:** `defer-dns-error` is a tenant-level feature config,
accessible via `NetLayerTenantFeatureCfgMgr`. The function should read it from
the tenant feature config for `m_conn->getTenantId()`, the same pattern used by
other tenant feature flags in `SslServerLayer`.

**Proposed implementation location:** `NetSession.hpp` as an inline accessor on
`NSessionBypassArgs`, reading from the tenant config. Alternatively it can be a
free function in the SSL layer that is called before returning from
`dnsLookupFailureHandler()` — but placing it on `NSessionBypassArgs` keeps all
`get_dstip()` logic in one place.

**Dependency note:** Implementing `dnsErrorShouldSuppressClientIp()` in PR #14246
also unblocks a fix in PR #14206's code. `SslServerLayer::dnsLookupFailureHandler()`
currently unconditionally advances to `SSL_CHECK_POLICY_ACTION` on DNS failure without
evaluating `defer-dns-error`. Once this function exists, `dnsLookupFailureHandler()` can
call it to decide whether to proceed or terminate — completing the structural fix at the
SSL layer rather than relying on the App layer retry workaround. This follow-up change
to #14206's code should be tracked as part of the #14246 deliverable.

---

### Complete `get_dstip()` behaviour matrix

The simplified 4-row table used during early design is incomplete. The correct
matrix adds F2P policy presence and `defer-dns-error` as independent dimensions.

| Row | Flag | ipSource | F2P policy | `defer-dns-error` | `get_dstip()` returns | Outcome |
|-----|------|----------|------------|-------------------|----------------------|---------|
| 1 | off | `OriginalDestIp` | either | n/a | client IP | Legacy path — unchanged |
| 2 | on | `DnsResolvedIpUsingSni` or `DnsResolvedIpUsingConnectHost` | either | n/a | service-resolved IP | Correct ✓ |
| 3 | on | `DnsAttemptedAndFailed` | absent | `allow` | client IP (fall-through) | Allowed with client IP ✓ |
| 4a | on | `DnsAttemptedAndFailed` | absent | `block`/`no-dest-ip` | `nullptr` | Blocked — client IP suppressed ✓ |
| 4b | on | `DnsAttemptedAndFailed` | **present** | either | `nullptr` | F2P routes it; chain proxy does DNS ✓ |

**Key insight for row 4b:** When F2P policy is present, returning `nullptr` is
safe regardless of `defer-dns-error`. F2P routing is determined by
`lookupPolicyAction()` independently of `get_dstip()` — F2P rules are
domain/user-based, not IP-based. The chain proxy performs its own DNS resolution.
`nullptr` from `get_dstip()` does not block an F2P flow; it only removes the
untrusted client IP from IP-based policy condition evaluation during
`lookupPolicyAction()`.

**Note on row 3:** Row 3 only arises in transparent proxy mode. In explicit proxy,
the CONNECT host was already service-resolved at Stage 1 — DNS failure at the SSL
layer leaves `DnsResolvedIpUsingConnectHost` in place (from Stage 1), so
`destHostIpIsResolvedIp()` returns true and the session takes row 2, not row 3.
Row 3 is the transparent proxy case where the client-provided IP is the only IP
available and the operator has explicitly configured tolerance for DNS failures.

---

### `get_dstip()` shape after this decision

```cpp
if (m_nsession.isSslLayerDnsResolutionEnabled()) {

    // Row 2: DNS succeeded
    if (m_nsession.destHostIpIsResolvedIp()) {
        // return m_destHost.ip via buf
    }

    // Rows 3, 4a, 4b: DNS attempted but failed
    if (m_nsession.getDestHost().ipSource == HostIpSource::DnsAttemptedAndFailed) {
        if (m_nsession.dnsErrorShouldSuppressClientIp()) {
            return nullptr;   // Rows 4a and 4b: suppress client IP
                              // 4a: no F2P → connection blocked
                              // 4b: F2P present → chain proxy handles it
        }
        // Row 3: defer-dns-error = allow, no F2P → fall through to client IP
    }
}
// Client IP fallback (rows 1 and 3)
```

---

## Point 2 — GeoIP baked into `setDestHostResolvedIp()`?

**Status: Resolved — yes, bake it in**

### Background

PR #14246 originally tied GeoIP population to `setSvcResolvedDestAddr()` — a write-once
field. hpandey21 proposed instead baking `populateBackGeoInfo()` directly into
`setDestHostResolvedIp()`:

```cpp
void setDestHostResolvedIp(std::string ip, ns::host::HostIpSource ipSource)
{
    m_destHost.ip = std::move(ip);
    m_destHost.ipSource = ipSource;
    if (!m_destHost.ip.empty()) {
        populateBackGeoInfo(m_destHost.ip.c_str());
    }
}
```

This means every DNS resolution — SSL layer, HTTP layer, wherever — automatically
populates GeoIP. One central place, impossible to forget at any call site.

The key difference from the PR #14246 approach:
- PR #14246 tied GeoIP to `setSvcResolvedDestAddr()` — a write-once field
- hpandey21's approach ties it to `setDestHostResolvedIp()` — which can be called
  multiple times as `m_destHost` progresses through stages. Each call represents a
  better (more specific) DNS resolution, so re-populating GeoIP with the latest
  resolved IP is correct.

### Decision

With Point 1 resolved (`svcResolvedDestAddr` removed, `m_destHost` as single source of
truth), this follows naturally: GeoIP must be baked into `setDestHostResolvedIp()`.
There is no longer a `setSvcResolvedDestAddr()` to attach it to.

The advancement-only rule from Point 1 interacts correctly: each advancement of
`ipSource` represents a more trusted IP, and re-populating GeoIP on each advancement
is correct — the latest (most trusted) IP is always used.

### Constraint: `DnsAttemptedAndFailed` must clear the IP

When DNS fails and `ipSource` is set to `DnsAttemptedAndFailed`, `m_destHost.ip` must
be cleared. Without this, `m_destHost.ip` would still hold the client-provided IP from
InlineConnInfo, `!m_destHost.ip.empty()` would be true, and `populateBackGeoInfo()`
would be called on the client IP — defeating the purpose of the sentinel.

With `m_destHost.ip` cleared, the `!m_destHost.ip.empty()` guard in
`setDestHostResolvedIp()` prevents GeoIP from being called on a failed DNS resolution.

### Full proposed implementation

```cpp
void setDestHostResolvedIp(std::string ip, ns::host::HostIpSource ipSource)
{
    if (ipSource <= m_destHost.ipSource) {
        // Advancement-only: never regress to a less reliable source
        return;
    }
    m_destHost.ip = std::move(ip);
    m_destHost.ipSource = ipSource;
    // Atomically populate GeoIP whenever a resolved IP is stored.
    // The !empty() guard prevents GeoIP calls when DNS failed and ip was cleared.
    if (!m_destHost.ip.empty()) {
        populateBackGeoInfo(m_destHost.ip.c_str());
    }
}
```

### Consequence for PR #14246

- The `populateBackGeoInfo()` call we added to `setSvcResolvedDestAddr()` is removed
  (that field is being removed entirely per Point 1)
- `setDestHostResolvedIp()` handles GeoIP atomically instead
- When setting `DnsAttemptedAndFailed`, the caller passes an empty string for `ip`

---

## Point 3 — Naming changes (`HostIpSource` → `IpSource`, function renames)

**Status: Resolved — 14246's only responsibility is adding `DnsAttemptedAndFailed`**

All renames of existing symbols (`HostIpSource` → `IpSource`, function renames, member
renames) are 14206's concern. PR #14246 does not own them.

PR #14246's sole responsibility under Point 3: add the `DnsAttemptedAndFailed` sentinel
value to the enum — whatever name that enum carries after 14206's renames are applied.
14246 should be rebased on top of 14206 so the sentinel value is added to the already-
renamed enum without conflict.

---

## Point 4 — Tenant flag vs per-connection flag for `get_dstip()`

**Status: Resolved — `HostIpSource` alone drives `get_dstip()` and AppModuleLayer**

### Background

PR #14206 gates `get_dstip()` on `isSslLayerDnsResolutionEnabled()` — a per-connection
flag set by `SslLayer`'s constructor. hpandey21 identified two blind spots:

- **Explicit proxy, SSL process config off**: CONNECT DNS already resolved the IP
  (`DnsResolvedIpUsingConnectHost`), but `isSslLayerDnsResolutionEnabled()` is false.
  AppModuleLayer's guard is skipped → DNS runs again redundantly even though CONNECT
  already resolved the destination.
- **Plaintext HTTP, no SSL layer**: tenant has the feature enabled but the per-connection
  flag is never set → `get_dstip()` uses the legacy path even though `m_destHost`
  already holds the right IP.

hpandey21 suggested gating on the **tenant feature flag** directly instead of the
per-connection flag.

### Decision

With Points 1–3 resolved, `get_dstip()` needs no feature flag at all — neither
per-connection nor tenant. It is driven entirely by `HostIpSource`.

`HostIpSource` already encodes exactly the state `get_dstip()` needs:

| `ipSource` value | Meaning | `get_dstip()` action |
|---|---|---|
| `>= DnsResolvedIpUsingConnectHost` | DNS succeeded | return `m_destHost.ip` |
| `DnsAttemptedAndFailed` | DNS failed | apply sentinel logic (rows 3/4) |
| `OriginalDestIp` | DNS never ran | legacy path — return client IP |

The feature flag only controls whether `SslLayer` *attempts* DNS. The outcome is fully
captured in `HostIpSource`. Reading `HostIpSource` directly is both simpler and more
correct than checking any flag.

The same applies to AppModuleLayer's DNS skip decision: gate on
`destHostIpIsResolvedIp()` rather than `isSslLayerDnsResolutionEnabled()`. This also
fixes the explicit proxy blind spot — CONNECT-resolved IPs are correctly recognised
regardless of whether the SSL layer's process config is on.

### Consequence

- `isSslLayerDnsResolutionEnabled()` is retired from all downstream consumers
  (`get_dstip()`, AppModuleLayer). It stays only in `SslLayer`'s constructor where it
  governs whether DNS is attempted.
- `get_dstip()` shape driven by `HostIpSource` (combined with Points 1–3):

```cpp
const char *get_dstip(char *buf, size_t bufsz) const
{
    const auto &destHost = m_nsession.getDestHost();

    // DNS succeeded — return service-resolved IP
    if (m_nsession.destHostIpIsResolvedIp()) {
        if (buf != nullptr && bufsz > 0) {
            ns_strncpy(buf, destHost.ip.c_str(), bufsz);
            return buf;
        }
        return nullptr;
    }

    // DNS attempted but failed — apply fallback policy
    if (destHost.ipSource == HostIpSource::DnsAttemptedAndFailed) {
        if (m_nsession.dnsErrorShouldSuppressClientIp()) {
            return nullptr;   // Row 4: suppress client IP
        }
        // Row 3: fall through to client IP intentionally
    }

    // DNS never ran — legacy path
    auto *res = m_nsession.getBackGeoIpResult();
    if (res) {
        return res->ipaddr.ptr;
    }
    auto fconn = m_nsession.frontConn();
    if (fconn) {
        auto originalDest = fconn->getOriginalDestHost().c_str();
        if (ns_netutil_is_ip_addr(originalDest, nullptr)) {
            return originalDest;
        }
    }
    return nullptr;
}
```

---

## Point 5 — Fix `get_dstip()` dangling `c_str()` pointer

**Status: Carry to PR #14246 — not fixed in #14206 (Finding 2 in review findings)**

`get_dstip()` in `libs/netsvc/src/NetSession.cpp` returns `destHost.ip.c_str()` directly
— a pointer into `m_destHost.ip`'s `std::string` internal storage. The legacy path also
calls `fconn->getOriginalDestHost().c_str()` on a temporary (undefined behaviour once the
statement ends).

**Required fix:** Either restore the buffer-copy approach (copy into caller-provided `buf`
before returning) or explicitly document the lifetime constraint and audit all call sites.
The buffer copy is the safer option.

See `~/.claude/review-context/netSkope-dataplane-14206-review-findings.md` Issue 2 for
full context.

---

## Point 6 — Structural `defer-dns-error` fix at SSL layer

**Status: Carry to PR #14246 — depends on Point 3 (Finding 3 in review findings)**

`SslServerLayer::dnsLookupFailureHandler()` currently only logs on DNS failure and
unconditionally allows the state machine to advance to `SSL_CHECK_POLICY_ACTION`. The App
layer retry workaround handles `defer-dns-error` indirectly, but the SSL layer itself never
evaluates it.

Once `dnsErrorShouldSuppressClientIp()` is implemented (Point 3), `dnsLookupFailureHandler()`
should call it to decide whether to proceed to policy evaluation or terminate the connection.

See `~/.claude/review-context/netSkope-dataplane-14206-review-findings.md` Issue 3 for
full context. Also documented in the `dnsErrorShouldSuppressClientIp()` section under
Point 1 above (Dependency note).

---

## Point 7 — Fix SNI source field correctness in `handleNoSniScenario()`

**Status: Carry to PR #14246 — not fixed in #14206 (Finding 7 in review findings)**

In `SslServerLayer::handleNoSniScenario()`, several branches call `setSslSni()` with values
that did not originate from an actual TLS SNI extension (CONNECT host domain, inline conn
info IP). `getPolicyAction()` reads `getSslSniSource()` to populate `destHost.source` for
policy evaluation — if the source is wrong, policy evaluates against a mislabelled
destination.

**Required fix:** Audit every branch of `handleNoSniScenario()` that calls `setSslSni()`
and confirm the `source` argument is semantically correct. Verify `getPolicyAction()`
receives the correct source for every code path through `preprocessForPolicyLookup()`.

This is independent of Points 1–6 and can be implemented in any order.

See `~/.claude/review-context/netSkope-dataplane-14206-review-findings.md` Issue 7 for
full context.

---

## Point 8 — Fix inverted assertion in `SslLayerDnsResolutionFailure` test

**Status: Carry to ENG-710107 — not fixed in #14206 (Finding 4 in review findings)**

`SslLayerDnsResolutionFailure` in `main_sni.cpp` has `ASSERT_EQ(ret, 1)` with comment
"Expected SSL_connect to fail due to DNS failure". In OpenSSL, `SSL_connect` returns `1`
on success. The assertion and comment contradict each other.

Read the test setup to determine which is correct, then align both.

See `~/.claude/review-context/netSkope-dataplane-14206-review-findings.md` Finding 4.

---

## Point 9 — Domain Fronting: NPLAN-6618 Gap Analysis

**Status: Partially addressed — detection and blocking already exist; bypass path is the remaining gap**

### What is domain fronting

A technique that exploits the gap between the TLS SNI (visible to the network
before decryption) and the HTTP `Host` header (visible only after decryption):

```
Client sends:  SNI  = allowed.com     ← seen by network, used for policy eval
Client sends:  Host: blocked.com      ← seen only after TLS decrypt
```

The CDN/server at `allowed.com` receives the connection, reads the `Host`
header, and forwards the request to `blocked.com`. From nsproxy's perspective,
policy was evaluated against `allowed.com` and allowed — but the actual content
served is from `blocked.com`.

### Correction: detection and blocking already exist

**Initial analysis was incomplete.** `detectDomainFronting()` already exists in
`HttpRequestEngine::runRequestHeader()` (line 1071 of `HttpRequestEngine.cpp`)
and already:

- Detects SNI ≠ Host header mismatch using `m_nsession.frontConn()->getSslSni()`
  vs the HTTP Host/URL host fields
- Performs cert-based exception check (`domainFrontingCertCheck()`)
- Checks global and per-tenant exception lists
- **Blocks the connection** when `isPolicyBypass(DOMAIN_FRONTING)` is false —
  calls `sendDomainFrontingErrToFront()` and returns `NS_NBERR`
- Sets transaction event fields: `setDomainFronting()`, `setDomainFrontingAction(BLOCK)`

The check runs in `runRequestHeader()` — **before** `updateNetSessionDestHost()`
runs in `runRequestModProcess()`. So detection happens at the right point.

**Option 2 (block unconditionally) is therefore already implemented.**

### The attack path that remains open — the bypass path

The remaining gap is the **bypass/allow path**. When domain fronting is detected
but the connection is allowed through (via bypass policy or exception list),
`updateNetSessionDestHost()` silently updates `m_destHost` to the Host header
domain while the back connection still uses the SNI-resolved IP:

```
1. Client sends SNI = allowed.com
2. SSL layer resolves allowed.com → 1.2.3.4, stores ResolvedIpFromSni
3. getPolicyAction() evaluates against allowed.com / 1.2.3.4 → ALLOW
4. TLS decrypted; HTTP Host: blocked.com arrives
5. detectDomainFronting() detects mismatch → but bypass policy ALLOWS it through
6. updateNetSessionDestHost() sets m_destHost.value = blocked.com
7. Back connection goes to 1.2.3.4 (allowed.com's IP) with Host: blocked.com
8. allowed.com's CDN routes internally to blocked.com
9. Policy was evaluated against allowed.com, not blocked.com — domain fronting
   succeeds at the CDN level despite being "detected"
```

**The proxy correctly detected the mismatch, but the bypass path allows the
attack to succeed anyway** — the back connection uses the wrong IP for the
wrong domain and the CDN completes the fronting.

### Relationship to existing NPLAN-6618 checks

PR #14206 detects SNI ≠ CONNECT host in `handleSniReceivedScenario()` at the
SSL layer (before decryption) and defers proper handling to NPLAN-143 Phase 2.
Domain fronting (SNI ≠ HTTP Host) is handled at the HTTP layer via
`detectDomainFronting()` in `runRequestHeader()` — a separate, later check.
The blocking path is complete. The bypass/allow path is the remaining gap.

### Required behaviour for the remaining gap — Option 1

**Option 1 — Re-evaluate policy against the Host header domain (correct end state)**

When domain fronting is detected and the connection is allowed through (bypass
or exception), the proxy must not use the SNI-resolved IP for the back
connection. Instead:
1. Resolve the Host header domain via fresh DNS (SNI-resolved IP is for the
   wrong domain and must not be reused)
2. Re-run `lookupPolicyAction()` against the Host domain and its resolved IP
3. If the new decision is BLOCK → terminate with a domain-fronting block event
4. If the new decision is ALLOW → connect to the Host domain's resolved IP

**Option 2 (block unconditionally) — already implemented** in
`detectDomainFronting()` + `isPolicyBypass(DOMAIN_FRONTING)`.

**Option 3 (log and allow) — not an acceptable end state.**

### Where to implement Option 1

**File:** `libs/http/src/HttpRequestEngine.cpp`
**Location:** In the bypass path after `detectDomainFronting()` returns true
and `isPolicyBypass(DOMAIN_FRONTING)` is true — before the back connection is
established. The new work replaces the current silent pass-through with a
fresh DNS + policy re-evaluation against the Host domain.

### Implementation note — exclude IP-in-SNI from the check

When a client sends a raw IP address in the SNI field with a domain in the
HTTP Host header (e.g., `SNI = 1.2.3.4`, `Host: example.com`), this is **not**
domain fronting — it is legitimate HTTP/1.1 behavior for IP-direct connections.

**Correction (2026-06-03):** The earlier claim that `detectDomainFronting()`
handles this correctly was wrong. `detectDomainFronting()` only returns false
early for empty SNI or SNI == host. It does **not** check whether the SNI is
an IP address. If `SNI = 1.2.3.4` and `Host: example.com`, the function
proceeds past all checks and returns true — `domainFronted = true`. Without an
explicit IP guard, the bypass fix (`HTTP_DOMAIN_FRONTING_BYPASSED`) would fire
for legitimate IP-direct connections.

The guard must be added explicitly in `runRequestHeader()` before setting the
flag:

```cpp
if (domainFronted &&
    isPolicyBypass(DOMAIN_FRONTING) &&
    !ns_netutil_is_ip_addr(m_nsession.frontConn()->getSslSni().c_str(), nullptr)) {
    // check tenant exception list, then set HTTP_DOMAIN_FRONTING_BYPASSED
}
```

This is verified against `detectDomainFronting()` source (line 1077–1197 of
`HttpRequestEngine.cpp`): no `ns_netutil_is_ip_addr` guard exists there.

---

### Implementation approach decision

**Jira:** ENG-1036449

**Decision: Option 1 (re-evaluate policy in the bypass path) is the sole
remaining deliverable. Option 2 (blocking) is already implemented.**

#### Why Option 1 is the correct end state

The HTTP Host header is the true application-layer destination. When the proxy
allows a domain-fronted connection through (via bypass or exception), it must
still ensure the back connection goes to the correct IP and policy is evaluated
against the true destination. Using the SNI-resolved IP with a different Host
header is a security control failure even when the fronting is "known".

#### Option 1 prerequisites

1. **`ResolvedIpFromHttpHost` (ipSource = 8) production** — this enum value
   exists but no code path sets it. Option 1 requires advancing `ipSource` to
   `ResolvedIpFromHttpHost` when the Host-header domain is DNS-resolved. This
   closes ENG-970460 Known Gap #1 (see `2026-05-19-eng-970460-geoip-consolidation-design.md`).

2. **Async DNS mid-flow** — a fresh DNS lookup for the Host header domain
   requires going async mid-HTTP-processing — the same mechanism NPLAN-6618
   added at the SSL layer, but at a later, more complex point in the pipeline.

3. **`lookupPolicyAction()` re-evaluation** — re-running policy with a different
   domain requires carefully resetting session state (`m_destHost`, GeoIP,
   policy result) without leaving the session inconsistent.

#### ENG-1036449 deliverable

Implement Option 1 in the bypass path:
1. Detect SNI ≠ Host mismatch in the bypass/allow path (after
   `detectDomainFronting()` returns true and connection is allowed through)
2. Resolve Host header domain via fresh DNS
3. Advance `ipSource` to `ResolvedIpFromHttpHost` via `setDestHostResolvedIp()`
   — closes ENG-970460 Known Gap #1
4. Re-run `lookupPolicyAction()` against Host domain and its resolved IP
5. If BLOCK → terminate with domain-fronting block event
6. If ALLOW → connect to Host domain's resolved IP

**Prerequisite:** ENG-970460 Known Gap #1 (`ResolvedIpFromHttpHost` production)
must be resolved first.

#### Option 3 (log and allow) — not in scope

Not an acceptable end state. The existing blocking path already provides
visibility via transaction events. Option 3 is not implemented as a permanent
path.
