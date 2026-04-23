# Design: review-feature-flag-cm Skill

**Date:** 2026-04-22
**Status:** Approved
**Repo:** amitayud-claude-world

---

## Overview

A Claude Code skill for reviewing feature-flag Change Management (CM) tickets created by the feature-flag-automation system. The skill fetches CM data from Jira, applies a structured checklist (generic + flag-specific), and presents analysis. All Jira actions (approval, transition) remain manual.

---

## Skill Identity

| Field | Value |
|-------|-------|
| Name | `review-feature-flag-cm` |
| Location | `~/amitayud-claude-world/skills/review-feature-flag-cm/SKILL.md` |
| Invocation | `/review-feature-flag-cm [CM-KEY]` |
| Repo | `amitayud-claude-world` (personal, not shared) |
| Implementation | Pure SKILL.md — no scripts |

---

## Invocation Modes

### Single CM mode
```
/review-feature-flag-cm CM-232884
```
Fetches and reviews one specified CM. No continuation prompt.

### Queue mode
```
/review-feature-flag-cm
```
Fetches all CMs in `Needs Peer Review` status with `feature-flag-automation` label, works through them one by one with a continuation prompt between each.

---

## Tooling

Uses the eng-skills jira CLI:
```
~/.claude/plugins/cache/netskope/eng-skills/*/skills/jira/scripts/jira
```
(glob pattern — version-independent, consistent with how xray-triage references it)

Commands used:
- `jira search "<JQL>"` — fetch queue in queue mode
- `jira issue <CM-KEY>` — fetch CM details + description
- `jira comments <CM-KEY>` — fetch execution log and reviewer comments
- `jira issue <ENG-KEY>` — fetch linked escalation ticket for customer verification

Also uses `AskUserQuestion` for queue continuation prompt.

---

## Queue JQL

```
project = CM AND labels = "feature-flag-automation" AND status in ("Needs Peer Review") ORDER BY created DESC
```

---

## Review Checklist

### Generic (all flags)

1. **Customer name match** — CM `customer_name` matches tenant name/URL in linked ENG ticket
2. **Tenant ID + home POP match** — CM and ENG ticket agree on both
3. **Request vs deployed** — what the ENG ticket asked for matches what the maintenance command executed
4. **Pre-maintenance validation** — status must be PASSED
5. **Post-execution verification** — status must be PASSED; verified state matches expected state
6. **No unexpected side effects** — existing config fully preserved; only the requested change applied

### Flag-specific

#### `http2`
- Determine if this is first-time enablement by checking whether pre-maintenance stdout shows no existing http2 config
- **First-time enablement:** `use-global-config` must be `false` AND `dynamic-alpn-detection` must be `false`
- **Adding to existing config:** verify existing domains are preserved in the final state; verify `use-global-config` and `dynamic-alpn-detection` are already set correctly
- Note absence of either flag even if not a hard fail

#### `xff_config`
- For simple enable: `globals: {}` expected (no unintended overrides)
- Include/exclude domain lists should be empty unless explicitly requested in ENG ticket

#### `tcp-keepalive-back-conn`
- `time`, `interval`, `probes` values must be present
- When adding domains to existing config: all pre-existing domains must be preserved in final state

#### `lookup-steering-exceptions`
- Simple on/off flag — verify `enabled` value matches the request (enable vs disable)

---

## Output Format (per CM)

```
CM-XXXXXX: [summary line]
Status: [current Jira status]

✅/❌ Customer name match — [detail]
✅/❌ Tenant ID + POP match — [detail]
✅/❌ Request matches deployed — [detail]
✅/❌ Pre-maintenance validation — PASSED/FAILED
✅/❌ Post-execution verification — PASSED/FAILED
✅/❌ No unexpected side effects — [detail]
[flag-specific checks if applicable]

Notes: [anything worth flagging even if not a hard fail]
Overall: LGTM / NEEDS ATTENTION
```

---

## Queue Mode Flow

1. Run `jira search` with queue JQL
2. Announce: "Found N CMs pending review"
3. For each CM:
   a. `jira issue <CM-KEY>` + `jira comments <CM-KEY>`
   b. Identify linked ENG ticket from `linked_issues`; fetch with `jira issue <ENG-KEY>`
   c. Run full checklist
   d. Present output in standard format
   e. If more CMs remain, ask via `AskUserQuestion`: "Continue to next CM?" (Yes / Stop here)
4. After all reviewed: present summary table

| CM | Summary | Flag | Overall |
|----|---------|------|---------|
| CM-XXXXX | ... | http2 | LGTM |
| CM-XXXXX | ... | xff_config | NEEDS ATTENTION |

---

## Single CM Mode Flow

1. `jira issue <CM-KEY>` + `jira comments <CM-KEY>`
2. Identify and fetch linked ENG ticket
3. Run full checklist
4. Present output — no continuation prompt, no summary table

---

## Out of Scope

- Approving, transitioning, or commenting on Jira tickets (all manual)
- Flag types not listed above (treated as generic-only checks)
- Rollback candidates or "Close CM" queue sections
