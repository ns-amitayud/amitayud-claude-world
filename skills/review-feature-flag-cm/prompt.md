---
name: review-feature-flag-cm
description: Review feature-flag automation CM tickets from Jira. Applies generic and flag-specific checklists. Use when asked to review feature flag CMs, or invoked as /review-feature-flag-cm [CM-KEY]. With no argument, fetches the full pending-review queue. With a CM key, reviews that single ticket.
allowed-tools:
  - Bash(~/.claude/plugins/cache/netskope/eng-skills/*/skills/jira/scripts/jira *)
  - AskUserQuestion
---

## Parse arguments

Check `$ARGUMENTS`:
- If a CM key is provided (e.g. `CM-232884`) → **Single CM mode**
- If no argument → **Queue mode**

---

## Queue mode (no argument)

### Step 1: Fetch pending queue

Run:
```bash
~/.claude/plugins/cache/netskope/eng-skills/*/skills/jira/scripts/jira search "project = CM AND labels = \"feature-flag-automation\" AND status in (\"Needs Peer Review\") ORDER BY created DESC"
```

Announce: "Found N CMs pending review."

If 0 results: "No CMs pending review. Done."

### Step 2: Review each CM

For each CM key in the results, follow the **Review procedure** below.

After each CM (if more remain), ask via AskUserQuestion:
- question: "Continue to next CM?"
- options:
  - label: "Yes, continue"
  - label: "Stop here"

Stop if user selects "Stop here".

### Step 3: Summary table

After all CMs reviewed, present:

| CM | Summary | Flag | Overall |
|----|---------|------|---------|
| CM-XXXXX | [summary] | [flag] | LGTM / NEEDS ATTENTION |

---

## Single CM mode (CM key provided)

Follow the **Review procedure** below for the specified CM key only. No continuation prompt. No summary table.

---

## Review procedure

Given a CM key:

### Fetch data

Run in sequence:
```bash
~/.claude/plugins/cache/netskope/eng-skills/*/skills/jira/scripts/jira issue <CM-KEY>
~/.claude/plugins/cache/netskope/eng-skills/*/skills/jira/scripts/jira comments <CM-KEY>
```

From `linked_issues`, identify the related ENG ticket (key starting "ENG-", direction "outward", or summary describing the customer request). Fetch it:
```bash
~/.claude/plugins/cache/netskope/eng-skills/*/skills/jira/scripts/jira issue <ENG-KEY>
```

Extract from CM:
- `customer_name`, `tenant_id`, `home_pop` from inputs JSON in description
- Current Jira status (e.g. Draft, Needs Peer Review, Change Approved, Change In Progress, Change Closed)
- Maintenance command (curl POST) from Maintenance Tasks field or execution log in comments
- Pre-maintenance stdout (state before change) from Pre-maintenance Tasks field or execution log
- Post-execution verification output (state after change) from execution log, if present
- The bot-posted "Maintenance Execution Report" comment, if present — contains `Pre-maintenance Validation: PASSED/FAILED` and `Verification Validation: PASSED/FAILED` lines
- Feature flag name (from `Extracted feature flag:` line in execution log, or from the field descriptions)

**Execution-report lifecycle:** this automation only posts the "Maintenance Execution Report" comment (with the PASSED/FAILED lines) *after* the CM is approved and actually run. A CM sitting at Draft/Needs Peer Review/Change Approved with no such comment yet is normal and expected — it has not been executed, not failed. Only treat validation as failed when the report comment exists and says FAILED, or when the CM is at Change In Progress/Change Closed with no report comment at all (execution should have logged one by then).

Extract from ENG ticket:
- Tenant name, tenant ID, tenant URL, home POP from description
- What was explicitly requested (the customer's ask)

### Generic checklist

Apply all six checks to every CM regardless of flag type:

1. **Customer name match** — Does CM `customer_name` match tenant name or URL in the ENG ticket?
2. **Tenant ID + home POP match** — Do CM and ENG ticket agree on both?
3. **Request vs deployed** — Does what the ENG ticket explicitly requested match what the maintenance/planned command says (executed or not)?
4. **Pre-maintenance validation** — PASSED if the report comment says so, or if no report comment exists yet (not-yet-executed — mark N/A, not a failure). FAILED only if the report comment explicitly says FAILED.
5. **Post-execution verification** — Same rule as #4: N/A if not yet executed, PASSED/FAILED from the report comment once it exists.
6. **No unexpected side effects** — Based on the pre-maintenance snapshot vs. the maintenance command (or, once executed, vs. the verification output): is existing config fully preserved, is only the requested change applied?

Use ⏳ (not ❌) for checks 4-5 when the CM hasn't executed yet — an N/A is not a fail. Only ❌ when there is a report comment and it says FAILED.

### Flag-specific checklist

Identify the flag from the execution log (`Extracted feature flag:` line) and apply the relevant rules:

#### `http2`

Determine if this is **first-time enablement** by checking whether pre-maintenance stdout shows no existing `http2` config (null or absent).

If **first-time enablement**:
- Check: if `use-global-config` and/or `dynamic-alpn-detection` are present in the executed command, they are set to `false` (a present-but-non-`false` value is a real defect — flag NEEDS ATTENTION).
- If either field is *absent* from the command, this is **not** a defect by itself — precedent (e.g. CM-141717) shows Ursa's own default enablement omits both fields and defaults apply, and that pattern has been reviewed and approved before. Note it (non-blocking): "`use-global-config`/`dynamic-alpn-detection` not explicitly set — relies on defaults; both explicit-false and omitted are established patterns, confirm which the reviewer prefers."

If **adding to existing config**:
- Check: all domains present in pre-maintenance state are preserved in post-execution verification output
  — EXCEPTION: an entry with a literal `*.` prefix (e.g. `*.example.com`) is a non-functional no-op in
  the http2 domain matcher (suffix-matching trie, no glob support — the `*` is stored as a literal
  character and never matches a real hostname). Removing such a dead wildcard entry and replacing it
  with the bare apex form (`example.com`) is a coverage *expansion* (apex + all subdomains), not a
  regression — do not flag this as an unexpected side effect. Precedent: CM-283328.
- Check: `use-global-config` and `dynamic-alpn-detection` values are unchanged from pre-maintenance state
- Note (non-blocking) if `use-global-config` is absent from the config

#### `xff_config`

- Check: for a simple enable, `globals` field is `{}` (no unintended overrides)
- Check: include/exclude domain lists are empty unless the ENG ticket explicitly requested domain-specific changes

#### `tcp-keepalive-back-conn`

- Check: `time`, `interval`, and `probes` fields are all present in the executed command
- Check: when adding domains, all domains present in pre-maintenance state are preserved in post-execution verification output

#### `lookup-steering-exceptions`

- Check: `enabled` value in executed command matches what was requested (enable → `true`, disable → `false`)

#### Unknown flag

Apply generic checklist only. Note in output: "Flag-specific rules not defined for `<flag-name>` — generic checks only."

### Output format

Present the result for this CM as:

```
## CM-XXXXXX: [summary line]
**Status:** [current Jira status]
**Flag:** [flag name]
**Tenant:** [customer name] (ID: [tenant_id], POP: [home_pop])

### Generic checks
✅/❌ Customer name match — [detail]
✅/❌ Tenant ID + POP match — [detail]
✅/❌ Request vs deployed — [detail]
✅/❌/⏳ Pre-maintenance validation — PASSED/FAILED/⏳ not yet executed
✅/❌/⏳ Post-execution verification — PASSED/FAILED/⏳ not yet executed
✅/❌ No unexpected side effects — [detail]

### Flag-specific checks (`<flag-name>`)
✅/❌ [check] — [detail]
✅/❌ [check] — [detail]

**Notes:** [anything worth flagging that is not a hard fail — including non-blocking precedent notes — or "None"]
**Overall: LGTM** / **Overall: NEEDS ATTENTION**
```

Use ✅ for pass, ❌ for fail, ⏳ for not-yet-applicable (CM not yet executed). If a flag-specific section has no applicable checks, omit it. A ⏳ never by itself causes an "Overall: NEEDS ATTENTION" verdict — only an actual ❌ does.
