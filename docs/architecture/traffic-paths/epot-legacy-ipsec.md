# EPoT / Legacy IPsec Traffic Path

> **Status:** First draft 2026-06-26 — authored from ENG-1072419 investigation (Atos/Eviden Germany, TID 24616, FRA1), Miroslaw Pabian's Jun 26 session PDF, and Jira comment thread.
> **Reviewer:** PE team review required for ProxyLB internals (§4) and CONN info protocol (§5). ipsecgw xfrm/DHCP details need confirmation from IPsec team.
> **Update trigger:** After any EPoT-path bug fix, ProxyLB architecture change, or CONN info protocol change.

---

## 1. What Is EPoT / Legacy IPsec?

**EPoT** (Explicit Proxy over Tunnel) is the Legacy IPsec access method — distinct from the newer VPP-based IPsec path. In Legacy IPsec:

- Traffic is **not** processed by VPP. There is no Lightning service chain, no CFW adapter, no iproxy pod.
- After ESP decryption on the ipsecgw, packets are forwarded directly from the ipsecgw kernel to the ProxyLB fleet via standard IP routing, then to dppool/nsproxy.
- User identity is carried in-band in the TCP stream as a proprietary **CONN info** header (see §5).

**Tenant identification:** Legacy IPsec tenants can be identified from nsproxy logs by `tunnel: N` in the TCPNAT allocation line:
```
TCPNAT: ... Allocated dhcp ip 10.77.62.67 Svc thread: svc4 tunnel: 8 QOS: Disabled cfw-ctap: No
```
`cfw-ctap: No` confirms no CFW/VPP involvement.

**Parth Varma (ENG-1072419):** *"This tunnel is landing on Legacy IPsec and not VPP so traffic is directly coming to dppool nodes based on the packet captures."*

---

## 2. Full Traffic Path

```
Customer endpoint (Azure VDI, Windows)
  │  PAC file → explicit proxy 163.116.128.80:80 (FRA1) or 163.116.128.81:80 (DUS1)
  │
  ▼
Customer firewall / router (e.g. Fortigate)
  │  IPsec ESP encapsulated in IKE NAT-T (UDP 4500)
  │  Customer public IP: 40.114.189.54 (Azure Virtual GW in this case)
  │
  ▼
ipsecgw0N.fra1.nskope.net  (e.g. 163.116.178.38)   [§3]
  │
  │  After ESP decryption:
  │  src = allocated DHCP IP (e.g. 10.77.62.67)
  │  dst = ProxyLB VIP    (10.178.0.131)
  │  dport = 8024
  │  via bond0.400 → GW 10.178.6.1
  │
  │  First data packet = [215 B CONN info][HTTP CONNECT ...]   [§5]
  │  CONN info is sent ONCE, never retransmitted
  │
  │  ◄══ PACKET DROPS OBSERVED HERE (ENG-1072419) ══►
  │      Affected: LB06 and LB07 in FRA1
  │      SYN drops  → 1s+2s+4s retransmit backoff → 7 s latency
  │      CONN info drops → permanent stall (browser timeout, no error)
  │
  ▼
ProxyLB fleet  aadpproxylb01–08.fra1.nskope.net     [§4]
  │  Linux-based L4 load balancer (DLT=LINUX_SLL in pcap)
  │  Packets arrive duplicated on LB (ECMP/bonding artifact — expected)
  │  Forwards: src=10.77.62.67  dst=10.178.0.131:8024
  │
  ▼
dppool10-N.fra1.nskope.net  (10.178.0.131 loopback VIP)  [§6]
  │  nsproxy listens on :8024
  │  tcp_syncookies=1 — always responds to SYN, no silent drops
  │  Reads CONN info → establishes user/tenant context
  │  Reads HTTP CONNECT → opens back-connection to destination
  │
  ▼
Destination server (internet)
```

---

## 3. ipsecgw Internals

### 3.1 Per-tenant interfaces

Each IPsec tunnel gets its own set of kernel virtual interfaces:

```
xfrm<N>@bond0.400   — XFRM policy interface, decrypts ESP inbound
tunc<N>             — TUN interface carrying decrypted inner packets
vrfx<N>             — VRF for the xfrm interface
vrft<N>             — VRF for the tun interface
```

Example (tenant 24616, tunnel ID 10240):
```
xfrm10240@bond0.400  mtu 1500
tunc10240            mtu 1500  (qlen 4000)
vrfx10240            mtu 65536
vrft10240            mtu 65536
```

The tunnel ID maps to the interface index in strongSwan logs:
```
Tunnel is Up for connection: tenant-24616-8 peer-id: 40.114.189.54
  interface: xfrm10240, tunc10240, vrfx10240, vrft10240
```

### 3.2 DHCP IP allocation

When a user's traffic arrives through a tunnel, ipsecgw allocates a per-user DHCP IP:
```
TCPNAT: rip='40.114.189.54', cip='10.183.39.132' Allocated dhcp ip 10.77.62.67
```
- `rip` = customer public IP (outer ESP src)
- `cip` = user's private IP inside the VDI
- `dhcp ip` = the source IP used for all connections from this user to the ProxyLB

The DHCP IP is the identity of the user **within the Netskope internal network**. It is what appears as the source IP in ipsecgw → ProxyLB packets.

### 3.3 Forwarding path from ipsecgw to ProxyLB

After decryption and DHCP assignment, packets are forwarded via:
```
bond0.400  (VLAN 400, MTU 1500)
  └── GW 10.178.6.1
       └── 10.178.0.131:8024  (ProxyLB VIP)
```

**MTU constraint:** bond0/eth0/eth1 carry jumbo frames (MTU 9000), but bond0.400 is MTU 1500. The effective path MTU from ipsecgw to ProxyLB is 1500 bytes. This is expected and not a problem for normal TCP traffic — SYN packets are ~60 bytes, HTTP CONNECT ~200-500 bytes.

### 3.4 Network health indicators (from ENG-1072419)

| Metric | Value | Interpretation |
|---|---|---|
| ping ipsecgw → dppool10-2 | 0.06–0.25 ms | Path latency healthy |
| bond0.400 TX drops | 0 | No egress drops on LAN transit |
| conntrack entries | 6,809 / 2,097,152 | 0.3% — no pressure |
| softnet drops | 97,381 cumulative since boot | Not incident-causal |
| `ip route get 10.178.0.131` | via 10.178.6.1 dev bond0.400 | Routing correct |

---

## 4. ProxyLB Fleet (aadpproxylb0N)

### 4.1 What it is

`aadpproxylb01–08.fra1.nskope.net` is a fleet of **Linux-based L4 load balancers** that sit between the ipsecgw and the dppool nodes.

**Critical distinction:** This is **not** the same as `dpsvclb01–02.fra1` (which is an Arista switch used for a different purpose). ENG-1072419 initial analysis incorrectly dismissed dpsvclb and concluded no LB was involved. The ProxyLB fleet was the actual missing component.

**pcap evidence** (Miroslaw's session, Jun 26): Captures taken simultaneously on all 8 ProxyLB nodes (aadpproxylb01–08) showed that for a dropped SYN or CONN info packet, the packet appeared on exactly **one LB node** (e.g. LB06) but not the other 7 — confirming the ProxyLB is the last hop where the packet is observed before disappearing.

### 4.2 Packet duplication

In the ProxyLB pcap, every packet appears **twice** in rapid succession (same timestamp, identical content):
```
11:25:40.581757 IP 10.77.45.43.11770 > 10.178.0.131.8024: Flags [S] length 0
11:25:40.581773 IP 10.77.45.43.11770 > 10.178.0.131.8024: Flags [S] length 0
```
This is an **expected artifact** of ECMP or bonding on the LB node — not packet corruption or retransmission. Every forwarded packet is seen twice on the capture interface.

### 4.3 Failure mode: packet loss between ipsecgw and ProxyLB

In ENG-1072419, the drops were localized to packets that never arrived at any of the 8 ProxyLB nodes:
- SYN for a connection: 5 retransmits sent by ipsecgw, 5 absent from all 8 ProxyLB captures; only the 6th SYN arrived
- CONN info packet: never arrived at any ProxyLB; only the retransmitted HTTP CONNECT arrived

The drop therefore occurs **between ipsecgw and the ProxyLB** — in the network path (bond0.400 → GW 10.178.6.1 → LB ingress). The root cause of these drops is assigned to the PE team as of 2026-06-26.

### 4.4 What is known vs unknown

| Aspect | Status |
|---|---|
| Physical location in path | Confirmed (ipsecgw → aadpproxylb0N → dppool) |
| Software/OS | Linux (DLT=LINUX_SLL confirmed) |
| Internal forwarding mechanism | Unknown — needs PE team input |
| Whether it maintains per-flow state | Unknown — whether CONN info is processed here or passed through opaquely |
| Why drops are localized to LB06/LB07 | Under investigation |
| Load distribution algorithm | Unknown |

---

## 5. CONN Info Protocol

This is the most important protocol detail for diagnosing EPoT issues. **It is not documented elsewhere in this knowledge base.**

### 5.1 What it is

When ipsecgw opens a new TCP connection to the ProxyLB/nsproxy, the **very first data segment** (immediately after the TCP handshake) is a proprietary header called **CONN info**, approximately **215 bytes**.

This packet carries user identity and tunnel context that nsproxy needs to set up the proxy session:
- User's original IP (cip)
- Customer's public IP (rip)
- Tenant ID
- Tunnel ID / DHCP-allocated IP
- Possibly: service thread assignment, QoS flags

### 5.2 Critical behavior: sent once, never retransmitted

**By design, CONN info is sent exactly once as the first data segment and is never independently retransmitted.**

The TCP stack will retransmit the segment if no ACK is received (standard TCP retransmission). However, if the segment is ACK'd but the *content* is silently dropped somewhere in the network (i.e., the ACK comes back but the data never reaches nsproxy), there is no recovery mechanism.

**Evidence from ENG-1072419 Issue 2** (Miroslaw's PDF, page 7):
```
Packet 773454: CONN info (215 bytes) sent by ipsecgw
Packet 773462: HTTP CONNECT (232 bytes) sent immediately after
Packet 774551: Client retransmits HTTP CONNECT (no ACK seen)
Packet 774559: Proxy sent ACK, but SLE=216 SRE=448
               → Proxy received CONNECT bytes 216–448 only
               → CONN info (bytes 1–215) was never received by proxy
```

*"As per design CONN info is only sent with first Data packet so missing 215 bytes will never be retransmitted and CONNECT cannot be completed by Proxy"* — Miroslaw Pabian, ENG-1072419

### 5.3 Failure consequence

| What is dropped | Observable symptom | Recovery |
|---|---|---|
| SYN packet | 1–7 second delay on initial connect (TCP retransmit backoff) | Automatic — ipsecgw retransmits SYN |
| CONN info packet | Browser timeout; HTTP CONNECT never completes; nsproxy receives CONNECT with no context | **None** — connection must be torn down and re-opened |
| Regular data packet | Standard TCP retransmit, brief stall | Automatic |

### 5.4 Diagnostic implication

If a user reports intermittent **permanent stalls** (not just delays) that require browser refresh/retry to recover, the symptom is CONN info drop, not SYN drop. The pcap signature:
- ipsecgw sends CONN info (215 B) immediately after handshake
- ProxyLB pcap shows only the retransmitted HTTP CONNECT, no 215 B segment
- dppool/nsproxy pcap shows ACK with SLE/SRE gap: `SLE=216 SRE=448` (CONNECT received, CONN info not)

---

## 6. dppool / nsproxy Role

### 6.1 What nsproxy does in this path

nsproxy listens on `:8024` (the `gre-gateway` listener mode in nsproxy config). On a new connection:
1. Kernel completes TCP handshake (SYN/SYN-ACK/ACK) — **nsproxy is not involved in this**
2. Kernel hands completed connection to nsproxy via `accept4()` (`NetListener.cpp:1165`)
3. nsproxy reads the CONN info header to get user/tunnel context
4. nsproxy reads the HTTP CONNECT request
5. nsproxy opens a back-connection to the destination on the user's behalf
6. Proxy session proceeds normally

### 6.2 Why nsproxy is not the problem for EPoT SYN/CONN drops

| Fact | Source |
|---|---|
| `tcp_syncookies=1` on dppool — kernel always sends SYN-ACK | Harsh Pandey, ENG-1072419 |
| 116µs handshake completion once SYN arrives | Pcap correlation, ENG-1072419 |
| No Prism queue anomalies during incident | Harsh Pandey, ENG-1072419 |
| No `#dp-oncall` alerts for FRA1 | Harsh Pandey, ENG-1072419 |
| Drops localized to before any ProxyLB — nsproxy never receives the packet | Miroslaw Pabian, ENG-1072419 |

**The TCP handshake and CONN info are handled by the kernel and the ipsecgw respectively, before nsproxy's `accept()` call runs.** Investigating nsproxy for SYN-level drops is a dead end for Legacy IPsec.

### 6.3 nsproxy config for this listener

From `nsproxy_with_chain.cfg` and local tenant configs:
```json
{
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

Note: `backlog=1024` in config. The `ss -tlnp` on dppool showed `Send-Q=16384` — this is the kernel's effective backlog, capped by `net.core.somaxconn` on the dppool host. nsproxy never sees a SYN — kernel handles that.

---

## 7. Diagnostic Checklist (EPoT-specific)

When investigating EPoT latency or connection stalls, run these checks **in this order** before forming a hypothesis:

### Step 1: Confirm this is Legacy IPsec (not VPP)

```bash
# In nsproxy TCPNAT log — presence of "tunnel: N" and "cfw-ctap: No" confirms Legacy
grep "TCPNAT.*tenantid=<TID>" /opt/ns/log/mtnsproxy.log | grep "cfw-ctap: No"
```

### Step 2: Confirm the drop location with multi-point pcap

Capture **simultaneously** on:
- ipsecgw (`tcpdump -i tunc<N>` or `bond0.400`)
- All 8 ProxyLB nodes (`tcpdump -i any port 8024`)
- dppool (`tcpdump -i lo port 8024`)

For each affected flow (identified by src port from client pcap):
```bash
# On ProxyLB nodes — check which LB saw the packet
for lb in {1..8}; do
  tcpdump -r aadpproxylb0${lb}.fra1:/tmp/<capture>.pcap port <src_port>
done
```

A packet visible at ipsecgw but absent from all 8 ProxyLB nodes = drop is **between ipsecgw and ProxyLB**.
A packet visible at one ProxyLB but absent at dppool = drop is **between ProxyLB and dppool** (rare).

### Step 3: Distinguish SYN drop from CONN info drop

| Symptom | Packet signature | Impact |
|---|---|---|
| Delay then recovery | SYN absent from LB, retransmit SYN present | 1–7 s latency, recovers |
| Permanent stall | 215 B segment absent from LB; retransmit CONNECT present with `SLE=216` | No recovery, requires retry |

### Step 4: Check ipsecgw network health

```bash
# Confirm forwarding path is healthy
ip route get 10.178.0.131              # should via 10.178.6.1 dev bond0.400
ip -s link show bond0.400             # TX dropped should be 0
sudo conntrack -C                     # << 2,000,000
sudo netstat -s | grep "listen queue" # low rate (not spike)
```

### Step 5: Do NOT investigate nsproxy accept-queue for SYN drops

`tcp_syncookies=1` on dppool makes kernel-level SYN drops from accept-queue overflow impossible. The `netstat -s` listen-queue overflow counter is **cumulative since boot** on a high-traffic node — it does not indicate an active incident. Do not use it as incident evidence without a delta measurement.

---

## 8. Known Failure Modes (EPoT-specific)

| Failure Mode | Symptom | Root Cause | Who investigates |
|---|---|---|---|
| SYN drops between ipsecgw and ProxyLB | 1–7 s initial connect delay; SYN retransmits visible at ipsecgw, absent at ProxyLB | Unknown as of 2026-06-26; packet loss in ipsecgw→LB network segment | PE team |
| CONN info drop between ipsecgw and ProxyLB | Browser timeout on specific resources; HTTP CONNECT retransmitted but never completes | Same underlying drop — but consequence is permanent stall not retryable delay | PE team |
| Both affect LB06/LB07 specifically | Localized to specific ProxyLB nodes | Possible: asymmetric routing, NIC issue, or switch port problem on those nodes | PE / Ops |

---

## 9. What This Path Shares With GRE

The GRE access path (GRE Gateway) also terminates on nsproxy port 8024 (`gre-gateway` mode) via the same ProxyLB fleet. Many of the same diagnostic steps apply. The key difference: GRE uses a GRE tunnel for encapsulation rather than IPsec ESP, and the customer-side hardware is typically a data-center router rather than a VPN gateway.

---

## Appendix: Key IPs and Hostnames (FRA1, ENG-1072419)

| Role | Hostname / IP |
|---|---|
| Customer VDI | 10.183.39.132 |
| Customer public IP (Azure VGW) | 40.114.189.54 |
| ipsecgw | ipsecgw06.fra1.nskope.net (163.116.178.38) |
| User DHCP IP (allocated by ipsecgw) | 10.77.62.67 |
| ProxyLB VIP (loopback on dppool) | 10.178.0.131 |
| nsproxy listen port | 8024 |
| ProxyLB fleet | aadpproxylb01–08.fra1.nskope.net |
| dppool (received traffic) | dppool10-2.fra1.nskope.net |
| Proxy explicit endpoint | 163.116.128.80:80 (FRA1), 163.116.128.81:80 (DUS1) |

## Appendix: Evidence Sources for This Document

| Source | What it contributed |
|---|---|
| ENG-1072419 Jira thread | Symptom description, MTR/psping results, SAR data, ipsecgw/dppool RTF logs |
| dppool102.rtf (attached to ticket) | dppool socket stats, netstat -s overflow counter, ss -s connection count |
| ipsecgw06.rtf (attached to ticket) | Bond, conntrack, routing, MTU, softnet stats |
| dpsvclb0102fra1.rtf (attached to ticket) | Confirmed Arista switch — ruled out as ProxyLB |
| claude-session-73f92c26.txt (attached) | Pcap analysis: 6 SYN sent, only 6th received; 116µs transit time |
| Miroslaw Pabian's session PDF (Jun 26) | Identified aadpproxylb0N fleet; CONN info protocol; two-issue framing; root cause localization |
| Harsh Pandey's Jira comments (Jun 26) | tcp_syncookies=1; no Prism anomaly; nsproxy ruled out; redirected to IPsec team |
| Parth Varma's Jira comment | Confirmed Legacy IPsec (not VPP) |
| Deepak Kumar's Jira comment | Service chain output (no qos/ctap/adapter); confirmed cfw not in play |
