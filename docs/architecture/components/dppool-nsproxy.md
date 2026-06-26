# Component: dppool / nsproxy (Port 8024 — EPoT/GRE Ingress)

> **Status:** First draft 2026-06-26 — authored from ENG-1072419 investigation and nsproxy codebase (`libs/netsvc/`).
> **Reviewer:** nsproxy team review required for §3 (CONN info processing), §4 (backlog reconciliation). Codebase references are from R138 branch.
> **Update trigger:** After nsproxy listener config changes, backlog/sysctl tuning, or any EPoT/GRE ingress bug.

---

## 1. Role in EPoT/GRE Path

The dppool node is the final hop in the EPoT (Legacy IPsec) and GRE traffic paths. nsproxy listens on port **8024** for connections arriving from the ProxyLB fleet (`aadpproxylb0N`). Each connection represents one user TCP flow decapsulated from the IPsec/GRE tunnel.

nsproxy does **not** participate in:
- TCP handshake (kernel handles SYN/SYN-ACK/ACK)
- Connection routing to the ProxyLB (that is the ipsecgw's job)
- CONN info forwarding (ipsecgw sends it directly as the first data segment)

nsproxy's work begins only after `accept4()` returns a completed connection.

---

## 2. Listener Configuration

**Source:** `cfg/nsproxy_with_chain.cfg`, tenant configs in `/opt/ns/tenant/<tid>/cfg/netskope.nsproxy.cfg`

```json
{
  "name"    : "gre-gateway-proxy",
  "type"    : "net",
  "ip"      : "0.0.0.0",
  "port"    : 8024,
  "mode"    : "gre-gateway",
  "backlog" : 1024,
  "bypass-policy-lookup" : true,
  "bypass-settings" : {
    "no-sni"  : true,
    "non-ssl" : true
  }
}
```

**`bypass-policy-lookup: true`** — nsproxy does not perform URL lookup for the initial CONNECT on this listener. User identity and context come from the CONN info header instead.

**`backlog: 1024`** — this is the value passed to `listen(2)` (`NetListener.cpp:918`). The kernel caps it at `min(1024, net.core.somaxconn)`. On production dppools, `net.core.somaxconn=16384`, so the effective backlog is 1024.

**`mode: gre-gateway`** — the connection processing path in nsproxy for EPoT/GRE connections. Different from `explicit` (standard forward proxy) and `st-gateway` (SSL inspection gateway).

---

## 3. SO_REUSEPORT Architecture

nsproxy uses `SO_REUSEPORT` to distribute incoming connections across service threads without a single accept bottleneck. Each service thread creates its own socket on port 8024.

From `ss -tlnp | grep 8024` on dppool10-2.fra1 (ENG-1072419):
```
LISTEN  0  16384  0.0.0.0:8024  0.0.0.0:*  users:(("nsproxy",pid=2842072,fd=837))
LISTEN  0  16384  0.0.0.0:8024  0.0.0.0:*  users:(("nsproxy",pid=2842072,fd=781))
... (59 sockets total)
```

59 listening sockets = 59 service threads, each with its own accept queue.

The kernel distributes incoming SYNs across the 59 sockets using a hash of the 4-tuple (src IP, src port, dst IP, dst port). Each service thread calls `accept4()` in `NetListener.cpp:1165` in a non-blocking loop, draining its own queue.

---

## 4. Key Sysctl Facts (dppool, EPoT-relevant)

| Sysctl | Value on dppool10-2 (ENG-1072419) | Implication |
|---|---|---|
| `net.ipv4.tcp_syncookies` | **1** | Kernel sends SYN-ACK to every SYN regardless of accept queue state. Silent SYN drops from queue overflow are **impossible** with this setting. |
| `net.core.somaxconn` | 16384 | Effective backlog = min(1024, 16384) = 1024 per socket. But syncookies makes this moot for SYN handling. |
| `net.ipv4.tcp_max_syn_backlog` | (not checked) | Secondary queue depth — also irrelevant with syncookies=1 |

**Critical implication:** Any investigation that attributes SYN drops to nsproxy accept-queue overflow on a production dppool is almost certainly wrong. Check `tcp_syncookies` first. This was the error in the initial ENG-1072419 analysis.

---

## 5. Connection Count and Load Indicators

From `ss -s` on dppool10-2.fra1 during ENG-1072419:
```
Total: 90,871
TCP:   87,948 established, 17,787 timewait, 18,062 closed
```

87,948 established TCP connections is a high but plausible load for a busy dppool. This is not an anomaly by itself — do not treat high connection counts as evidence of a problem.

**Useful delta check** (if re-running `netstat -s | grep overflow` twice 60s apart shows a large increment, that *is* active evidence of overflow — but a large cumulative count since boot is not):
```bash
# Measure active overflow rate — not cumulative
netstat -s | grep "listen queue" | tee /tmp/before.txt
sleep 60
netstat -s | grep "listen queue" | tee /tmp/after.txt
diff /tmp/before.txt /tmp/after.txt
```

---

## 6. accept() Code Path

**Source:** `libs/netsvc/src/NetListener.cpp`

```
epoll EPOLLIN event on listening fd
    → NetListener::processTaskReq() dispatched by TaskEngine
        → NetListener::acceptNewTcpConn()  [line ~1157]
            → while (true):
                cfd = accept4(linfo.fd(), ..., SOCK_NONBLOCK|SOCK_CLOEXEC)  [line 1165]
                if EAGAIN: break  // queue drained
                → createConnInfo(cfd, ...)
                → NetSvc::currentServiceThread()->processNewConnRequest(...)
                   [SO_REUSEPORT immediate-accept path, line 1229]
```

The accept loop drains the entire queue in one epoll wake-up (no `break` after first accept). Each accepted fd immediately enters `processNewConnRequest` on the current service thread — no bouncing between threads in `SO_REUSEPORT` mode.

---

## 7. What nsproxy Does After accept()

1. Reads the first data segment — expects CONN info (215 bytes) providing user/tunnel context
2. Parses CONN info to set `tenantid`, user identity, DHCP IP, tunnel ID
3. Reads the HTTP CONNECT request (the actual proxy request from the browser)
4. Opens a back-connection to the destination server
5. Proxies traffic bidirectionally

If CONN info is absent (because it was dropped in transit), nsproxy receives the HTTP CONNECT with no context — the result is an indeterminate stall. nsproxy logs will show the connection with no `tenantid` or with a parsing error.

---

## 8. Diagnostic Commands

```bash
# Confirm tcp_syncookies — ALWAYS check this before any accept-queue theory
sysctl net.ipv4.tcp_syncookies

# Current connection count
ss -s | grep estab

# Active overflow rate (measure delta, not snapshot)
netstat -s | grep "listen queue"
sleep 60
netstat -s | grep "listen queue"

# Count listening sockets on 8024 (= number of service threads)
ss -tlnp | grep ":8024 " | wc -l

# Watson debug for a specific EPoT flow
# (only useful after TCP handshake — not for SYN-level drops)
set log tenantid <tid>
set log user <user@email>
set log level cfg tcp 1 http2 2 appmodule httpdump 3 httpreq httpres httpmod 4
```

---

## Appendix: Evidence Sources

| Source | What it contributed |
|---|---|
| dppool102.rtf (ENG-1072419) | 59 SO_REUSEPORT sockets on :8024, ss -s stats, netstat -s overflow counter |
| Harsh Pandey's comments (ENG-1072419) | tcp_syncookies=1, softnet drops negligible, no Prism anomaly |
| `libs/netsvc/src/NetListener.cpp` | accept4() loop, backlog config, SO_REUSEPORT path |
| `cfg/nsproxy_with_chain.cfg` | backlog=1024, gre-gateway mode, bypass-policy-lookup |
