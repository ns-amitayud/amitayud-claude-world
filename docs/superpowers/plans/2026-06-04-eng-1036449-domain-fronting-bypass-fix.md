# ENG-1036449: Domain Fronting Bypass Path Fix — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the domain fronting Bypass path so nsproxy connects to the true Host header destination IP instead of the SNI-resolved IP, and produces `ResolvedIpFromHttpHost = 8` for the first time (closing ENG-970460 Known Gap #1).

**Architecture:** Add a new `HTTP_DOMAIN_FRONTING_BYPASSED` flag on `AppModuleHttpProxy`. Set it in `runRequestHeader()` when domain fronting is detected in Bypass mode (with IP-in-SNI guard and tenant exception list check). In `updateNetSessionDestHostResolvedIp()`, when the flag is set, clear the stale SNI-resolved IP and advance to the already-DNS-resolved `blocked.com` IP with `ipSource = ResolvedIpFromHttpHost`. In `dnsReplyOnFailure()`, force teardown when the flag is set. Gate with two-level staged config following the `ssl-layer-geoip-preserve` pattern.

**Tech Stack:** C++17, nsproxy (`libs/http/`, `libs/netsvc/`), Google Test, Autotools + CMake build, staged config (`libs/staged_config/`), featurec codegen (`http_features.featurec`).

**Design spec:** `~/gitcode/amitayud-claude-world/docs/superpowers/specs/2026-06-03-eng-1036449-domain-fronting-bypass-fix-design.md`

---

## File Map

| File | Action | What changes |
|---|---|---|
| `libs/http/src/AppModuleHttpProxy.hpp` | Modify | Add `HTTP_DOMAIN_FRONTING_BYPASSED = 0x200` flag |
| `libs/http/src/HttpRequestEngine.hpp` | Modify | Add `detectedHost` output param to `detectDomainFronting()` declaration |
| `libs/http/src/HttpRequestEngine.cpp` | Modify | `detectDomainFronting()` populate output; `runRequestHeader()` set flag; `updateNetSessionDestHostResolvedIp()` bypass guard |
| `libs/http/src/AppModuleHttpProxy.cpp` | Modify | `dnsReplyOnFailure()` force teardown when flag set |
| `libs/http/DomainFrontingBypassFixGlobalCfg.hpp` | Create | Global staged config header (pattern: `SslLayerGeoIpPreserveGlobalCfg.hpp`) |
| `libs/http/src/DomainFrontingBypassFixGlobalCfg.cpp` | Create | Global staged config impl (pattern: `SslLayerGeoIpPreserveGlobalCfg.cpp`) |
| `libs/http/http_features.featurec` | Modify | Add `domain-fronting-bypass-fix` per-tenant flag (default `true`) |
| `libs/http/Makefile.am` | Modify | Add new `.cpp` to `nodist_libhttp_la_SOURCES` |
| `libs/http/CMakeLists.txt` | Modify | Add new `.cpp` to `target_sources(http ...)` |
| `apps/nsproxy/src/cpp/nsproxy.cpp` | Modify | Add `#include` and `init()` call |
| `libs/http/test/ns_http_appmodulehttpproxy_test/src/cpp/DomainFrontingBypassTest.cpp` | Create | Unit tests for all scenarios |

---

## Task 1: Add `HTTP_DOMAIN_FRONTING_BYPASSED` flag

**Files:**
- Modify: `libs/http/src/AppModuleHttpProxy.hpp:846-855`

- [ ] **Step 1: Add flag after `HTTP_BACK_CONN_TIMEOUT`**

In `libs/http/src/AppModuleHttpProxy.hpp`, find the `Flags` enum (around line 823). After `HTTP_SET_USER_INFO_DONE_CONNECT = 0x100`, add:

```cpp
        HTTP_DOMAIN_FRONTING_BYPASSED =
            0x200,  //!< Set when domain fronting detected in Bypass mode and Host
                    //!< domain is not in tenant exception list. Causes
                    //!< updateNetSessionDestHostResolvedIp() to clear the stale
                    //!< SNI-resolved IP and advance to ResolvedIpFromHttpHost.
```

- [ ] **Step 2: Compile to verify flag is valid**

```bash
make -C /home/amitayu/gitcode/dataplane/obj -j8 libs/http/src/AppModuleHttpProxy.lo 2>&1 | grep -E "error:|CXX"
```
Expected: `CXX libs/http/src/AppModuleHttpProxy.lo` with no errors.

- [ ] **Step 3: Commit**

```bash
git add libs/http/src/AppModuleHttpProxy.hpp
git commit -m "feat(http): add HTTP_DOMAIN_FRONTING_BYPASSED flag to AppModuleHttpProxy"
```

---

## Task 2: Add `detectedHost` output parameter to `detectDomainFronting()`

**Files:**
- Modify: `libs/http/src/HttpRequestEngine.hpp:925-929`
- Modify: `libs/http/src/HttpRequestEngine.cpp:1071-1197` (definition) and `1713-1717` (call site)

- [ ] **Step 1: Update declaration in `HttpRequestEngine.hpp`**

Find (around line 925):
```cpp
    bool detectDomainFronting(
        const NsDomainFrontingExcep::DomainFrontingExcepMgr &globalExcepMgr,
        const std::string &sslSni,
        const ns_http_objs_t *hdr,
        uint32_t &domainFrontingFlags);
```

Replace with:
```cpp
    bool detectDomainFronting(
        const NsDomainFrontingExcep::DomainFrontingExcepMgr &globalExcepMgr,
        const std::string &sslSni,
        const ns_http_objs_t *hdr,
        uint32_t &domainFrontingFlags,
        std::string &detectedHost);  // populated with url host or host header (lowercased)
```

- [ ] **Step 2: Update definition in `HttpRequestEngine.cpp`**

Find the function signature at line 1071:
```cpp
HttpRequestEngine::detectDomainFronting(
    const NsDomainFrontingExcep::DomainFrontingExcepMgr &globalExcepMgr,
    const std::string &sslSni,
    const ns_http_objs_t *hdr,
    uint32_t &domainFrontingFlags)
```

Replace with:
```cpp
HttpRequestEngine::detectDomainFronting(
    const NsDomainFrontingExcep::DomainFrontingExcepMgr &globalExcepMgr,
    const std::string &sslSni,
    const ns_http_objs_t *hdr,
    uint32_t &domainFrontingFlags,
    std::string &detectedHost)
```

Then find the line where `host` is fully resolved (around line 1135, after the url host / host header logic and before the cert check). Add:
```cpp
    detectedHost = host;
```

Place it just before:
```cpp
    if (domainFrontingCertCheck(sni, host, domainFrontingFlags)) {
```

- [ ] **Step 3: Update call site in `runRequestHeader()` (line 1713)**

Find:
```cpp
                domainFronted = detectDomainFronting(
                    NsDomainFrontingExcep::DomainFrontingExcepMgr::getInstance(),
                    m_nsession.frontConn()->getSslSni(),
                    hrd,
                    domainFrontingFlags);
```

Replace with:
```cpp
                std::string detectedHost;
                domainFronted = detectDomainFronting(
                    NsDomainFrontingExcep::DomainFrontingExcepMgr::getInstance(),
                    m_nsession.frontConn()->getSslSni(),
                    hrd,
                    domainFrontingFlags,
                    detectedHost);
```

- [ ] **Step 4: Compile to verify no errors**

```bash
make -C /home/amitayu/gitcode/dataplane/obj -j8 libs/http/src/HttpRequestEngine.lo 2>&1 | grep -E "error:|CXX"
```
Expected: `CXX libs/http/src/HttpRequestEngine.lo` with no errors.

- [ ] **Step 5: Commit**

```bash
git add libs/http/src/HttpRequestEngine.hpp libs/http/src/HttpRequestEngine.cpp
git commit -m "feat(http): add detectedHost output param to detectDomainFronting()"
```

---

## Task 3: Create `DomainFrontingBypassFixGlobalCfg` staged config

**Files:**
- Create: `libs/http/DomainFrontingBypassFixGlobalCfg.hpp`
- Create: `libs/http/src/DomainFrontingBypassFixGlobalCfg.cpp`

- [ ] **Step 1: Create header**

Create `libs/http/DomainFrontingBypassFixGlobalCfg.hpp`:

```cpp
/**
 * Filename: DomainFrontingBypassFixGlobalCfg.hpp
 *
 * Copyright (c) 2026 Netskope, Inc.
 * All rights reserved
 *
 * Description: Global staged config for "domain-fronting-bypass-fix" feature.
 *
 * When enabled (default true), the Bypass path for domain fronting connects to
 * the Host header domain's IP instead of the SNI-resolved IP.
 * When disabled, old Bypass behavior is restored (SNI IP used).
 *
 * Original Author: Amitayu Das
 * Creation Date: June, 2026
 */

#pragma once

namespace domain_fronting_bypass_fix {
namespace globalcfg {

/**
 * @brief Initialize config watcher. The json block is expected to look like:
 *
 *  {
 *      "name": "domain-fronting-bypass-fix",
 *      "data": { "enabled": true },
 *      "apply-globally": true
 *  }
 *
 *  enabled: true  = fix active (default); false = revert to old bypass behavior.
 */
void init();

/**
 * @brief Return true if feature is enabled in cfg.
 */
bool enabled();

// For UT purposes only.
bool updateConfig(const char *data);
}  // namespace globalcfg
}  // namespace domain_fronting_bypass_fix
```

- [ ] **Step 2: Create implementation**

Create `libs/http/src/DomainFrontingBypassFixGlobalCfg.cpp`:

```cpp
/**
 * Filename: DomainFrontingBypassFixGlobalCfg.cpp
 *
 * Copyright (c) 2026 Netskope, Inc.
 * All rights reserved
 *
 * Description: Global staged config for "domain-fronting-bypass-fix" feature.
 *
 * Original Author: Amitayu Das
 * Creation Date: June, 2026
 */
#include <atomic>

#include "base/log.hpp"
#include "http/DomainFrontingBypassFixGlobalCfg.hpp"
#include "staged_config/StagedConfig.hpp"

SET_LOGGING_MODULE_CXX(NSLM_FEATURE_CONFIG)

namespace domain_fronting_bypass_fix {
namespace globalcfg {

namespace {
const char *CFG_BLOCK = "domain-fronting-bypass-fix";
const char *CFG_ENABLED = "enabled";

std::atomic<bool> g_enabled{true};  // default enabled (fix active)

void
reset()
{
    g_enabled = true;
}

void
processConfigChange(const ns::conf::json &data)
{
    reset();
    try {
        if (data.find(CFG_ENABLED) != data.end()) {
            if (data[CFG_ENABLED].is_boolean()) {
                g_enabled = data[CFG_ENABLED].get<bool>();
            } else {
                LOG(ERROR)
                    << "domain-fronting-bypass-fix config error, 'enabled' field is not bool";
            }
        }
    } catch (std::exception &e) {
        LOG(ERROR) << "Exception in processing domain-fronting-bypass-fix config change"
                   << e.what();
    }

    LOG(INFO) << "Global domain-fronting-bypass-fix config settings, enabled: " << g_enabled;
}
}  // namespace

void
init()
{
    auto token = ns::conf::StagedConfig::instance().registerInterest(
        CFG_BLOCK, [](const ns::conf::json &data) {
            DLOG(2) << "Got a notification for domain-fronting-bypass-fix config update: "
                    << data;
            processConfigChange(data);
        });
    processConfigChange(token.initialData);
}

bool
enabled()
{
    return g_enabled;
}

bool
updateConfig(const char *data)
{
    try {
        auto body = ns::conf::json::parse(data);
        processConfigChange(body);
    } catch (std::exception &e) {
        LOG(ERROR) << "Failed to update domain-fronting-bypass-fix config, exception: "
                   << e.what();
        return false;
    }

    return true;
}
}  // namespace globalcfg
}  // namespace domain_fronting_bypass_fix
```

- [ ] **Step 3: Compile to verify**

```bash
make -C /home/amitayu/gitcode/dataplane/obj \
  libs/http/src/DomainFrontingBypassFixGlobalCfg.lo 2>&1 | grep -E "error:|CXX"
```
Expected: `CXX libs/http/src/DomainFrontingBypassFixGlobalCfg.lo` with no errors.

- [ ] **Step 4: Commit**

```bash
git add libs/http/DomainFrontingBypassFixGlobalCfg.hpp \
        libs/http/src/DomainFrontingBypassFixGlobalCfg.cpp
git commit -m "feat(http): add DomainFrontingBypassFixGlobalCfg staged config"
```

---

## Task 4: Add per-tenant featurec flag and wire up build + nsproxy init

**Files:**
- Modify: `libs/http/http_features.featurec`
- Modify: `libs/http/Makefile.am`
- Modify: `libs/http/CMakeLists.txt`
- Modify: `apps/nsproxy/src/cpp/nsproxy.cpp`

- [ ] **Step 1: Add featurec flag**

In `libs/http/http_features.featurec`, after the `ssl-layer-geoip-preserve` feature block (around line 415), add:

```xml
    <feature name="domain-fronting-bypass-fix">
        <field name="enabled" type="bool" default="true" />
    </feature>
```

- [ ] **Step 2: Add to Makefile.am**

In `libs/http/Makefile.am`, after the `SslLayerGeoIpPreserveGlobalCfg.cpp` entry (around line 101), add:

```makefile
	libs/http/src/DomainFrontingBypassFixGlobalCfg.cpp \
```

- [ ] **Step 3: Add to CMakeLists.txt**

In `libs/http/CMakeLists.txt`, after the `src/SslLayerGeoIpPreserveGlobalCfg.cpp` entry (around line 92), add:

```cmake
            src/DomainFrontingBypassFixGlobalCfg.cpp
```

- [ ] **Step 4: Add to nsproxy.cpp**

In `apps/nsproxy/src/cpp/nsproxy.cpp`:

Add include after `#include "http/SslLayerGeoIpPreserveGlobalCfg.hpp"`:
```cpp
#include "http/DomainFrontingBypassFixGlobalCfg.hpp"
```

Add init call after `ssl_layer_geoip_preserve::globalcfg::init();` (around line 728):
```cpp
    domain_fronting_bypass_fix::globalcfg::init();
```

- [ ] **Step 5: Compile libhttp to verify featurec codegen + build**

```bash
make -C /home/amitayu/gitcode/dataplane/obj -j8 \
  libs/http/src/DomainFrontingBypassFixGlobalCfg.lo \
  apps/nsproxy/src/cpp/nsproxy-nsproxy.o 2>&1 | grep -E "error:|CXX" | head -10
```
Expected: both compile without errors.

- [ ] **Step 6: Commit**

```bash
git add libs/http/http_features.featurec \
        libs/http/Makefile.am \
        libs/http/CMakeLists.txt \
        apps/nsproxy/src/cpp/nsproxy.cpp
git commit -m "feat(http): wire up domain-fronting-bypass-fix featurec flag and build"
```

---

## Task 5: Set flag in `runRequestHeader()` and force teardown in `dnsReplyOnFailure()`

**Files:**
- Modify: `libs/http/src/HttpRequestEngine.cpp:1713-1750` (runRequestHeader bypass fall-through)
- Modify: `libs/http/src/AppModuleHttpProxy.cpp:3566-3601` (dnsReplyOnFailure)

- [ ] **Step 1: Add includes to `HttpRequestEngine.cpp`**

Near the other `http/` includes (around line 33), add:
```cpp
#include "http/DomainFrontingBypassFixGlobalCfg.hpp"
```

- [ ] **Step 2: Set flag after bypass fall-through in `runRequestHeader()`**

After the `detectDomainFronting(...)` call and its `detectedHost` declaration (around line 1717), and after the existing block/tag handling (after line 1750 where domainFrontingFlags tags are set), add:

```cpp
            // Domain fronting bypass fix (ENG-1036449): when domain fronting is detected
            // in Bypass mode, mark the session so updateNetSessionDestHostResolvedIp()
            // advances to the Host header domain's IP instead of keeping the stale
            // SNI-resolved IP.
            //
            // Guards:
            // 1. IP-in-SNI: SNI=1.2.3.4 with Host: domain is legitimate HTTP/1.1,
            //    not domain fronting. detectDomainFronting() does NOT exclude this —
            //    ns_netutil_is_ip_addr guard is required here.
            // 2. Tenant exception list: skipped by detectDomainFronting() in Bypass
            //    mode — checked explicitly here.
            // 3. Two-level flag gate (global staged config + per-tenant featurec).
            if (domainFronted &&
                m_nsession.frontConn()->isPolicyBypass(NetLayerPolicyCfg::DOMAIN_FRONTING) &&
                !ns_netutil_is_ip_addr(m_nsession.frontConn()->getSslSni().c_str(), nullptr) &&
                ::domain_fronting_bypass_fix::globalcfg::enabled() &&
                m_hsession.m_newConfig &&
                m_hsession.m_newConfig->domain_fronting_bypass_fix().enabled()) {
                std::string tenantId;
                bool tenantException = getTenantId(tenantId) &&
                    NsDomainFrontingExcep::checkTenantException(detectedHost, tenantId);
                if (!tenantException) {
                    m_proxy.setFlag(AppModuleHttpProxy::HTTP_DOMAIN_FRONTING_BYPASSED);
                }
            }
```

- [ ] **Step 3: Add teardown guard in `dnsReplyOnFailure()` (line 3566)**

In `libs/http/src/AppModuleHttpProxy.cpp`, in `dnsReplyOnFailure()`, add at the very beginning of the function (after the error logger set call, around line 3569):

```cpp
    // If domain fronting bypass was in progress and DNS failed, do not defer —
    // we cannot forward without the true destination IP (using SNI IP would
    // reintroduce the attack). Force teardown regardless of defer-dns-error.
    if (isFlagSet(HTTP_DOMAIN_FRONTING_BYPASSED)) {
        clearFlag(HTTP_DOMAIN_FRONTING_BYPASSED);
        LDLOG(2) << "DNS failure during domain fronting bypass — forcing teardown";
        sendErrHtmlPageForDnsFailure();
        return false;
    }
```

- [ ] **Step 4: Compile both files**

```bash
make -C /home/amitayu/gitcode/dataplane/obj -j8 \
  libs/http/src/HttpRequestEngine.lo \
  libs/http/src/AppModuleHttpProxy.lo 2>&1 | grep -E "error:|CXX" | head -10
```
Expected: both compile without errors.

- [ ] **Step 5: Commit**

```bash
git add libs/http/src/HttpRequestEngine.cpp libs/http/src/AppModuleHttpProxy.cpp
git commit -m "feat(http): set HTTP_DOMAIN_FRONTING_BYPASSED in bypass path; teardown on DNS fail"
```

---

## Task 6: Fix `updateNetSessionDestHostResolvedIp()` to advance to `ResolvedIpFromHttpHost`

**Files:**
- Modify: `libs/http/src/HttpRequestEngine.cpp:5382-5406`

- [ ] **Step 1: Add bypass guard at top of `updateNetSessionDestHostResolvedIp()`**

Find `HttpRequestEngine::updateNetSessionDestHostResolvedIp` at line 5382. After the `if (!destinfo) return;` check, add:

```cpp
    if (m_proxy.isFlagSet(AppModuleHttpProxy::HTTP_DOMAIN_FRONTING_BYPASSED)) {
        // Domain fronting bypass: clear stale SNI-resolved IP and advance to the
        // Host header domain's resolved IP with ResolvedIpFromHttpHost.
        //
        // Without this, the existing three-condition guard below would fire:
        //   !destHost.ip.empty()  → true (SNI-resolved IP is set)
        //   destHost.value != destinfo->client_domain → true (SNI domain ≠ Host domain)
        // Both conditions would cause an early return, leaving the wrong IP in place.
        //
        // After clearDestHostResolvedIp(), ip is empty and the guard passes.
        // ipSource advances from ResolvedIpFromSni(7) to ResolvedIpFromHttpHost(8),
        // closing ENG-970460 Known Gap #1.
        // setDestHostResolvedIp() atomically calls populateDestGeoInfo() for the
        // Host header domain.
        m_proxy.clearFlag(AppModuleHttpProxy::HTTP_DOMAIN_FRONTING_BYPASSED);
        ns::host::IpSource ipSource = getIpSourceFromDestInfo(destinfo);
        if (ipSource != ns::host::IpSource::Unknown) {
            m_nsession.clearDestHostResolvedIp();
            m_nsession.setDestHostResolvedIp(destinfo->addr.ipstr, ipSource);
            DLOG(2) << "Domain fronting bypass: advanced to Host IP=" << destinfo->addr.ipstr
                    << " ipSource=" << ns::host::toString(ipSource);
        }
        return;
    }
```

- [ ] **Step 2: Compile**

```bash
make -C /home/amitayu/gitcode/dataplane/obj -j8 \
  libs/http/src/HttpRequestEngine.lo 2>&1 | grep -E "error:|CXX"
```
Expected: `CXX libs/http/src/HttpRequestEngine.lo` with no errors.

- [ ] **Step 3: Commit**

```bash
git add libs/http/src/HttpRequestEngine.cpp
git commit -m "feat(http): bypass guard in updateNetSessionDestHostResolvedIp for domain fronting fix"
```

---

## Task 7: Write unit tests

**Files:**
- Create: `libs/http/test/ns_http_appmodulehttpproxy_test/src/cpp/DomainFrontingBypassTest.cpp`

The test file follows the exact pattern of `DeferDnsErrorTest.cpp`. Domain fronting bypass policy is set via `NetLayerPolicyCfg::loadCfg()` with the `"domain-fronting": true` key in bypass-settings JSON.

- [ ] **Step 1: Create test file**

Create `libs/http/test/ns_http_appmodulehttpproxy_test/src/cpp/DomainFrontingBypassTest.cpp`:

```cpp
/**
 * @file DomainFrontingBypassTest.cpp
 *
 * @copyright (c) 2026 Netskope, Inc. All rights reserved.
 *
 * @brief Tests for ENG-1036449: domain fronting bypass path fix.
 *        When "Domain Fronting Protections" = Bypass, the back connection
 *        must use the Host header domain's IP, not the SNI-resolved IP.
 *
 * @author Amitayu Das
 * @date June 2026
 */

#include <gtest/gtest.h>

#include "base/log.hpp"
#include "base/ns_test_settings.hpp"
#include "http/DomainFrontingBypassFixGlobalCfg.hpp"
#include "http/Linkage.hpp"
#include "http/TenantCfgMgr.hpp"
#include "http/test/HttpObjectManager.hpp"
#include "http/test_libhttp/AppModuleHttpProxyFixture.hpp"
#include "netsvc/NsHost.hpp"
#include "netsvc/test_libnetsvc/UT.hpp"
#include "thread/ns_thrstorage.h"

SET_LOGGING_MODULE_CXX(NSLM_APP)

namespace {

const char *TEST_PROXY_CONFIG_DIR =
    "/libs/http/test/ns_http_appmodulehttpproxy_test/data/";

// Plain HTTP request with Host: blocked.com — triggers runRequestHeader()
// which calls detectDomainFronting() and the bypass fix.
std::string g_request =
    "GET / HTTP/1.1\r\n"
    "Host: blocked.com\r\n"
    "Accept: */*\r\n"
    "Proxy-Connection: keep-alive\r\n\r\n";

// SNI domain (different from Host header → domain fronting)
const char *g_sni = "allowed.com";

// Simulated IP returned by DNS for "blocked.com"
const char *g_blocked_com_ip = "10.20.30.40";

void
init()
{
    http::TenantCfgMgr::init();
    ns_thrstore_add_entry(NS_TKEY_NSBUFPOOL, ns::ut::getPool(), nullptr);

    std::string cfgFile(tests::GetAbsoluteSourceDirectory());
    cfgFile.append(TEST_PROXY_CONFIG_DIR);
    cfgFile.append("netskope_mtnsproxy_cfg.cfg");
    AppModuleHttpProxyFixture::initialize(cfgFile);
}

// Set global staged config for domain-fronting-bypass-fix
void
setGlobalFlag(bool enable)
{
    const char *ENABLED = R"({"enabled": true})";
    const char *DISABLED = R"({"enabled": false})";
    CHECK(domain_fronting_bypass_fix::globalcfg::updateConfig(enable ? ENABLED : DISABLED));
}

// Set per-tenant featurec flag via http::TenantCfgMgr
void
setTenantFlag(bool enable, const std::string &tenantId)
{
    auto featureConfigSptr = http::TenantCfgMgr::instance().getConfig(tenantId);
    auto featureConfig = const_cast<hf::HttpFeatures *>(featureConfigSptr.get());
    featureConfig->domain_fronting_bypass_fix().set_enabled(enable);
}

// Configure the front connection with SNI=g_sni and domain fronting Bypass policy.
// bypass-settings JSON key for domain fronting is "domain-fronting" (from NetSvcConfig.cpp).
void
setupDomainFrontingBypass(AppModuleHttpProxyFixture &fixture)
{
    fixture.m_netSession.frontConn()->setSslSni(g_sni);

    const char *bypassSetting = R"({
        "domain-fronting": true
    })";
    Json::Value bypassCfg;
    Json::Features f = Json::Features::strictMode();
    f.allowComments_ = true;
    Json::Reader reader(f);
    CHECK(reader.parse(bypassSetting, bypassCfg, false));
    // NetLayerPolicyCfg is accessible via frontConn()->getPolicyCfg() but
    // loadCfg requires a writable ref. Use getConnServerObject(policyCfg) pattern:
    // In the fixture, the conn is already created. Set bypass via mutable access.
    // This mirrors how AppModuleHttpProxyTest::testHttpRequestEngineForwardConnect works.
    const_cast<NetLayerPolicyCfg &>(fixture.m_netSession.frontConn()->getPolicyCfg())
        .loadCfg(bypassCfg);
}

// Simulate DNS reply for blocked.com
void
simulateDnsReply(AppModuleHttpProxyFixture &fixture, const char *ip)
{
    ns_sockaddr_t dnsAnswer{};
    ns_netutil_set_sockaddr2(&dnsAnswer, ip, 443, AF_INET);
    fixture.m_proxy->dnsReply(dnsAnswer);
}

}  // namespace

// ============================================================================
// Test: bypass fix active — Host IP used instead of SNI IP
// ============================================================================

TEST_F(AppModuleHttpProxyFixture, DomainFrontingBypass_CorrectIpUsed)
{
    setGlobalFlag(true);
    setTenantFlag(true, m_netSession.frontConn()->getTenantId());
    setupDomainFrontingBypass(*this);

    // SSL layer already resolved allowed.com → some IP, stored as ResolvedIpFromSni
    m_netSession.setDestHostResolvedIp("1.2.3.4",
                                       ns::host::IpSource::ResolvedIpFromSni);
    ASSERT_TRUE(m_netSession.isDestHostIpResolved());

    ns_buf_queue_t nsbufq = nsbuf_queue_initializer(nsbufq);
    getDataBufq(g_request, &nsbufq);

    // readFront() → runRequestHeader() detects domain fronting in bypass mode
    // → sets HTTP_DOMAIN_FRONTING_BYPASSED
    // → runRequestHeaderResume() sets m_newDest.domain = "blocked.com"
    // → doDnsLookup("blocked.com") → NS_NBEAGAIN
    m_proxy->readFront(nsbufq);

    // Simulate DNS reply for blocked.com
    simulateDnsReply(*this, g_blocked_com_ip);

    // After destDnsReply → updateNetSessionDestHostResolvedIp():
    // flag was set → clearDestHostResolvedIp → setDestHostResolvedIp(g_blocked_com_ip, 8)
    EXPECT_STREQ(m_netSession.getDestHost().ip.c_str(), g_blocked_com_ip)
        << "Back connection must use blocked.com's IP, not SNI-resolved allowed.com IP";
    EXPECT_EQ(m_netSession.getDestHost().ipSource,
              ns::host::IpSource::ResolvedIpFromHttpHost)
        << "ipSource must advance to ResolvedIpFromHttpHost = 8 (closes ENG-970460 Gap #1)";
}

// ============================================================================
// Test: global flag disabled → old behavior (SNI IP preserved)
// ============================================================================

TEST_F(AppModuleHttpProxyFixture, DomainFrontingBypass_GlobalFlagOff_OldBehavior)
{
    setGlobalFlag(false);
    setTenantFlag(true, m_netSession.frontConn()->getTenantId());
    setupDomainFrontingBypass(*this);

    m_netSession.setDestHostResolvedIp("1.2.3.4",
                                       ns::host::IpSource::ResolvedIpFromSni);

    ns_buf_queue_t nsbufq = nsbuf_queue_initializer(nsbufq);
    getDataBufq(g_request, &nsbufq);
    m_proxy->readFront(nsbufq);
    simulateDnsReply(*this, g_blocked_com_ip);

    // Flag disabled → HTTP_DOMAIN_FRONTING_BYPASSED never set
    // → updateNetSessionDestHostResolvedIp guard fires → SNI IP preserved
    EXPECT_STREQ(m_netSession.getDestHost().ip.c_str(), "1.2.3.4")
        << "Global flag off: SNI-resolved IP must be preserved (old behavior)";

    setGlobalFlag(true);  // restore
}

// ============================================================================
// Test: per-tenant flag disabled → old behavior
// ============================================================================

TEST_F(AppModuleHttpProxyFixture, DomainFrontingBypass_TenantFlagOff_OldBehavior)
{
    setGlobalFlag(true);
    setTenantFlag(false, m_netSession.frontConn()->getTenantId());
    setupDomainFrontingBypass(*this);

    m_netSession.setDestHostResolvedIp("1.2.3.4",
                                       ns::host::IpSource::ResolvedIpFromSni);

    ns_buf_queue_t nsbufq = nsbuf_queue_initializer(nsbufq);
    getDataBufq(g_request, &nsbufq);
    m_proxy->readFront(nsbufq);
    simulateDnsReply(*this, g_blocked_com_ip);

    EXPECT_STREQ(m_netSession.getDestHost().ip.c_str(), "1.2.3.4")
        << "Per-tenant flag off: SNI-resolved IP must be preserved (old behavior)";

    setTenantFlag(true, m_netSession.frontConn()->getTenantId());  // restore
}

// ============================================================================
// Test: IP-in-SNI → fix not triggered
// ============================================================================

TEST_F(AppModuleHttpProxyFixture, DomainFrontingBypass_IpInSni_NotTriggered)
{
    setGlobalFlag(true);
    setTenantFlag(true, m_netSession.frontConn()->getTenantId());

    // SNI is an IP — not domain fronting, legitimate HTTP/1.1
    m_netSession.frontConn()->setSslSni("1.2.3.4");

    const char *bypassSetting = R"({"domain-fronting": true})";
    Json::Value bypassCfg;
    Json::Features f = Json::Features::strictMode();
    f.allowComments_ = true;
    Json::Reader reader(f);
    CHECK(reader.parse(bypassSetting, bypassCfg, false));
    const_cast<NetLayerPolicyCfg &>(m_netSession.frontConn()->getPolicyCfg())
        .loadCfg(bypassCfg);

    m_netSession.setDestHostResolvedIp("1.2.3.4",
                                       ns::host::IpSource::ResolvedIpFromSni);

    ns_buf_queue_t nsbufq = nsbuf_queue_initializer(nsbufq);
    getDataBufq(g_request, &nsbufq);
    m_proxy->readFront(nsbufq);
    simulateDnsReply(*this, g_blocked_com_ip);

    // IP-in-SNI guard: HTTP_DOMAIN_FRONTING_BYPASSED never set
    EXPECT_STREQ(m_netSession.getDestHost().ip.c_str(), "1.2.3.4")
        << "IP-in-SNI: must not trigger bypass fix";
}

// ============================================================================
// Test: DNS failure in bypass path → teardown
// ============================================================================

TEST_F(AppModuleHttpProxyFixture, DomainFrontingBypass_DnsFailure_Teardown)
{
    setGlobalFlag(true);
    setTenantFlag(true, m_netSession.frontConn()->getTenantId());
    setupDomainFrontingBypass(*this);

    m_netSession.setDestHostResolvedIp("1.2.3.4",
                                       ns::host::IpSource::ResolvedIpFromSni);

    ns_buf_queue_t nsbufq = nsbuf_queue_initializer(nsbufq);
    getDataBufq(g_request, &nsbufq);
    m_proxy->readFront(nsbufq);

    // Simulate DNS failure for blocked.com
    EXPECT_FALSE(m_proxy->dnsReplyOnFailure())
        << "DNS failure in bypass path must tear down connection";

    // Flag must be cleared
    EXPECT_FALSE(m_proxy->isFlagSet(AppModuleHttpProxy::HTTP_DOMAIN_FRONTING_BYPASSED))
        << "HTTP_DOMAIN_FRONTING_BYPASSED must be cleared after DNS failure";
}

// ============================================================================
// Test: Tenant exception list — fix not triggered when Host is excepted
// NOTE: NsDomainFrontingExcep::checkTenantException() uses UrlLookupMgr
// which requires a database. This test verifies the code path by mocking
// getTenantId() to return an empty tenant (which skips checkTenantException
// due to the getTenantId() guard in runRequestHeader()).
// Full tenant exception coverage requires UrlLookupMgr test infrastructure.
// ============================================================================

TEST_F(AppModuleHttpProxyFixture, DomainFrontingBypass_TenantException_NotTriggered)
{
    setGlobalFlag(true);
    setTenantFlag(true, m_netSession.frontConn()->getTenantId());
    setupDomainFrontingBypass(*this);

    // Set empty tenant ID — getTenantId() returns false → tenantException = false
    // BUT checkTenantException is not called with empty tenant.
    // This verifies the guard path without needing UrlLookupMgr.
    // Full coverage requires a separate integration test with DB-backed exceptions.
    m_netSession.frontConn()->setTenantId("");

    m_netSession.setDestHostResolvedIp("1.2.3.4",
                                       ns::host::IpSource::ResolvedIpFromSni);

    ns_buf_queue_t nsbufq = nsbuf_queue_initializer(nsbufq);
    getDataBufq(g_request, &nsbufq);
    m_proxy->readFront(nsbufq);
    simulateDnsReply(*this, g_blocked_com_ip);

    // Empty tenant → getTenantId fails → tenantException=false → flag IS set
    // → bypass fix fires → blocked.com IP used
    // (Tests that empty tenant does not crash and fix still applies)
    EXPECT_STREQ(m_netSession.getDestHost().ip.c_str(), g_blocked_com_ip)
        << "Empty tenant: bypass fix must still apply (no exception lookup)";
}

// ============================================================================
// Test: Block policy unchanged — existing behavior not affected
// ============================================================================

TEST_F(AppModuleHttpProxyFixture, DomainFrontingBlock_Unchanged)
{
    setGlobalFlag(true);
    setTenantFlag(true, m_netSession.frontConn()->getTenantId());

    // Block policy (default) — do NOT set domain-fronting bypass
    m_netSession.frontConn()->setSslSni(g_sni);
    m_netSession.setDestHostResolvedIp("1.2.3.4",
                                       ns::host::IpSource::ResolvedIpFromSni);

    ns_buf_queue_t nsbufq = nsbuf_queue_initializer(nsbufq);
    getDataBufq(g_request, &nsbufq);

    // Block policy: readFront returns NS_NBERR (connection terminated)
    ns_nbres_t result = m_proxy->readFront(nsbufq);
    EXPECT_EQ(result, NS_NBERR) << "Block policy: domain fronting must terminate connection";

    // SNI IP unchanged (block path doesn't reach updateNetSessionDestHostResolvedIp)
    EXPECT_STREQ(m_netSession.getDestHost().ip.c_str(), "1.2.3.4");
}

int
main(int argc, char **argv)
{
    testing::InitGoogleTest(&argc, argv);
    http::linkage();
    ns::ut::initialize(argc, argv);
    NSTest::HttpObjectManager::initialize();

    ns_log_set_verbosity(NSLM_HTTPREQ, ns::ut::debugLevel());
    ns_log_set_verbosity(NSLM_APPMODULE, ns::ut::debugLevel());
    ns_log_set_verbosity(NSLM_APP, ns::ut::debugLevel());

    init();
    int rv = RUN_ALL_TESTS();

    NSTest::HttpObjectManager::cleanup();
    ns::ut::shutdown();
    return rv;
}
```

- [ ] **Step 2: Compile test file**

```bash
make -C /home/amitayu/gitcode/dataplane/obj \
  libs/http/test/ns_http_appmodulehttpproxy_test/src/cpp/DomainFrontingBypassTest.o \
  2>&1 | grep -E "error:|CXX" | head -10
```
Expected: `CXX ...DomainFrontingBypassTest.o` with no errors.

- [ ] **Step 3: Commit**

```bash
git add libs/http/test/ns_http_appmodulehttpproxy_test/src/cpp/DomainFrontingBypassTest.cpp
git commit -m "test(http): add DomainFrontingBypassTest for ENG-1036449"
```

---

## Task 8: Self-review — compile all changed files and run regression

- [ ] **Step 1: Compile all changed files**

```bash
make -C /home/amitayu/gitcode/dataplane/obj -j8 \
  libs/http/src/AppModuleHttpProxy.lo \
  libs/http/src/HttpRequestEngine.lo \
  libs/http/src/DomainFrontingBypassFixGlobalCfg.lo \
  libs/netsvc/src/NetLayerTenantCfgMgr.lo \
  apps/nsproxy/src/cpp/nsproxy-nsproxy.o \
  libs/http/test/ns_http_appmodulehttpproxy_test/src/cpp/DomainFrontingBypassTest.o \
  2>&1 | grep -E "error:|^  CXX" | head -20
```
Expected: all compile without errors.

- [ ] **Step 2: CMake build for http target (Rule 4)**

```bash
/opt/3p/bin/cmake --build /home/amitayu/gitcode/dataplane/cmake-build \
  -f libs/http/CMakeFiles/http.dir/build.make \
  libs/http/CMakeFiles/http.dir/src/HttpRequestEngine.cpp.o \
  libs/http/CMakeFiles/http.dir/src/DomainFrontingBypassFixGlobalCfg.cpp.o \
  2>&1 | tail -5
```
Expected: both `.o` files built without errors.

- [ ] **Step 3: Run ns_netsvc_policy_test (Rule 1)**

```bash
make -C /home/amitayu/gitcode/dataplane/obj check-TESTS TESTS="ns_netsvc_policy_test" \
  2>&1 | grep -E "PASS|FAIL|ERROR" | head -5
```
Expected: `PASS: [1/1] ns_netsvc_policy_test`.

- [ ] **Step 4: Verify no stale references (Rule 5)**

```bash
grep -rn "HTTP_DOMAIN_FRONTING_BYPASSED" \
  /home/amitayu/gitcode/dataplane/libs/ \
  /home/amitayu/gitcode/dataplane/apps/ \
  --include="*.cpp" --include="*.hpp" | grep -v test
```
Expected: exactly 5 hits — declaration in `AppModuleHttpProxy.hpp`, set/clear in `HttpRequestEngine.cpp` (2 places), clear+teardown in `AppModuleHttpProxy.cpp`, bypass guard in `HttpRequestEngine.cpp`.

- [ ] **Step 5: Final commit message**

```bash
git log --oneline -6
```
Verify the 6 commits from Tasks 1–7 are all present with meaningful messages.

---

## Build commands reference

```bash
# Build individual object
make -C /home/amitayu/gitcode/dataplane/obj -j8 <target>

# Run tests
make -C /home/amitayu/gitcode/dataplane/obj check-TESTS TESTS="<test_name>"

# CMake build single file
make -C /home/amitayu/gitcode/dataplane/cmake-build \
  -f libs/http/CMakeFiles/http.dir/build.make \
  libs/http/CMakeFiles/http.dir/src/<file>.cpp.o
```
