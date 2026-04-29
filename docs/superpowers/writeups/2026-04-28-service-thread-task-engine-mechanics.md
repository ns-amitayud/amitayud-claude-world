# Service Thread / Task Engine Mechanics

*Context: Written during ENG-710107 implementation as background on why the
`dnsLookupReply()` same-thread guarantee holds. See V1 in
`2026-04-27-eng-710107-dest-addressing-impl.md`.*

---

There is one `ServiceThread` per configured service thread (e.g. 4 or 8 in a
typical nsproxy deployment). Each `ServiceThread` owns a single `TaskEngine`,
which is a **single-threaded epoll loop**. The engine watches a set of file
descriptors — one per registered `Taskpipe` socket (ZMQ DEALER sockets). When a
socket becomes readable, `TaskEngine::dispatchTaskpipe()` drains it
message-by-message in a tight inner loop, calling the registered `TaskHandler`
for each message's task ID.

The `NS_NETSVC_TPIPE_UTIL` socket is one of those watched sockets. It is a ZMQ
DEALER connected to the utility thread's router. When the service thread sends a
DNS request on it, ZMQ records the sender identity (the service thread's socket
identity) in the message envelope. When the utility thread replies with
`ns_msgpkt_swap_sender_dest()`, ZMQ routes the reply back to that exact socket
on that exact service thread — no other thread can receive it.

When the reply arrives, it sits in the socket's OS-level receive buffer. The
service thread's epoll wakes up only after it has finished its current work and
returned to the `epoll_wait()` call at the top of the engine loop. So from the
state machine's perspective, the reply is physically unreachable until the
current event-loop iteration ends. `dnsLookupReply()` is the handler registered
for `NS_UTILTASK_DNS_LKUP_REPLY` (installed via `NetSvc::taskNotify` →
`TaskNotify::run()` → `DnsNotify::dnsReply()` → `m_upstreamNotify->run()`) —
it can only fire in a future iteration.

This is the same guarantee that makes the entire nsproxy networking stack safe
without locks: all per-connection state is owned and mutated exclusively by one
service thread, and all callbacks for that connection arrive on that same thread.
