# Component: ProxyLB Fleet (aadpproxylb0N)

> **Status:** First draft 2026-06-26 — authored from ENG-1072419 investigation.
> **Reviewer:** PE team review required for all of §2 (internal architecture), §3 (forwarding mechanism), §4 (failure modes). Most of what is documented here is inferred from pcap evidence — structural details need confirmation.
> **Update trigger:** After any ProxyLB architecture change, PE team investigation of ENG-1072419, or any ticket where drops are localized to this component.

---

## 1. Identity and Role

The **ProxyLB fleet** (`aadpproxylb01–08.<pop>.nskope.net`) is the L4 load balancer tier that sits between the IPsec/GRE gateways (ipsecgw, gregw) and the dppool nodes running nsproxy. It is the **ingress LB for all EPoT (Legacy IPsec) and GRE access method traffic**.

**Name pattern:** `aadpproxylb0<N>.<pop>.nskope.net` — for example:
- `aadpproxylb01.fra1.nskope.net` through `aadpproxylb08.fra1.nskope.net` (FRA1 has 8 nodes)

**Naming confusion to avoid:**
- `dpsvclb01–02.<pop>` is a **separate Arista switch** used for a different purpose. It is not the ProxyLB. In ENG-1072419, this caused early investigators (including initial AI analysis) to incorrectly conclude no load balancer was in the path.

---

## 2. What We Know (from pcap evidence)

### 2.1 OS / capture type

pcap captures taken on ProxyLB nodes show `link-type LINUX_SLL` (DLT=113, Linux cooked capture), confirming these are **Linux hosts**, not hardware appliances.

### 2.2 Position in path

```
ipsecgw / gregw
    │
    │  src=<DHCP IP>  dst=10.178.0.131:8024
    ▼
aadpproxylb0N  (one of N nodes, traffic reaches exactly one LB per flow)
    │
    │  forwarded to dppool
    ▼
dppool  (nsproxy :8024)
```

### 2.3 Per-flow stickiness

From ENG-1072419 pcap analysis (Miroslaw Pabian): for any given src port (user flow), traffic appeared on **exactly one LB node** across all 8. This confirms per-flow consistent hashing or similar stickiness — all packets for a given TCP connection go through the same LB node.

### 2.4 Packet duplication on capture

Every packet seen on a ProxyLB capture appears **twice** in rapid succession at the same timestamp:
```
11:25:40.581757 IP 10.77.45.43.11770 > 10.178.0.131.8024: Flags [S] length 0
11:25:40.581773 IP 10.77.45.43.11770 > 10.178.0.131.8024: Flags [S] length 0
```
This is an **expected artifact** (ECMP, bonding, or capture interface mirroring), not a bug or retransmit. Do not treat duplicated ProxyLB packets as evidence of packet duplication in the actual network flow.

### 2.5 Traffic to nsproxy VIP

The ProxyLB forwards traffic to `10.178.0.131:8024` — a loopback VIP on the dppool nodes. This is the `gre-gateway` listener in nsproxy.

---

## 3. What We Do Not Know (requires PE team)

| Unknown | Why it matters |
|---|---|
| Internal forwarding mechanism (IPVS, eBPF, custom?) | Determines what state is maintained and what can fail silently |
| Whether CONN info is inspected or passed through opaquely | If the LB inspects CONN info, it may be the source of processing bugs |
| Whether it maintains per-flow connection tracking | Determines whether CONN info drop is a LB bug or a network bug upstream |
| Load distribution algorithm across 8 nodes | Needed to diagnose why LB06/LB07 were preferentially affected |
| Why packets disappear between ipsecgw and ProxyLB | The open question from ENG-1072419 assigned to PE team |
| Relationship to VPP-path LBs | Whether the same fleet or separate infrastructure |

---

## 4. Known Failure Modes

### 4.1 Silent packet drop between ipsecgw and ProxyLB

**Observed in:** ENG-1072419 (FRA1, Jun 24–26, 2026)

Packets (SYNs and CONN info segments) sent by ipsecgw never arrive at any of the 8 ProxyLB nodes. The drop occurs in the network segment between ipsecgw egress (bond0.400, GW 10.178.6.1) and ProxyLB ingress.

Two failure patterns with different consequences:
- **SYN drop:** TCP stack retransmits automatically; 1–7 s latency; recovers
- **CONN info drop:** Non-retransmittable by design; connection permanently stalls until browser retries

**Scope:** Observed with LB06 and LB07 being the affected nodes (traffic from ipsecgw destined to those LBs was being dropped). Other LBs (01–05, 08) appeared unaffected in the same window.

**Root cause:** Under investigation by PE team as of 2026-06-26.

---

## 5. Diagnostic Commands

```bash
# Confirm which ProxyLB node handles a specific flow (by src port)
for lb in {1..8}; do
  echo "=== LB $lb ==="
  tcpdump -r aadpproxylb0${lb}.<pop>:/tmp/<capture>.pcap port <src_port> 2>/dev/null
done

# If a packet is visible on ipsecgw but absent from ALL 8 LB nodes:
# → drop is between ipsecgw and ProxyLB fleet (network problem)

# If a packet is visible on one LB node but absent at dppool:
# → drop is between ProxyLB and dppool (rare, would be LB forwarding bug)
```

---

## Appendix: Evidence Sources

| Source | What it contributed |
|---|---|
| Miroslaw Pabian's Jun 26 session PDF | Identified aadpproxylb0N fleet as the correct LB; confirmed LINUX_SLL pcap type; per-flow stickiness; packet duplication artifact |
| ENG-1072419 initial investigation | dpsvclb misidentification, then correction by Parth Varma and Harsh Pandey |
