# Release Review Skill — Fine-Tuning Notes

## Run 1 — Date: 2026-05-15

### Setup findings

- Subagent-driven development is not functional on this Bedrock setup.
  The Agent tool always dispatches using `claude-haiku-4-5-20251001` regardless
  of the `model` parameter, which is an invalid identifier on AWS Bedrock.
  Workaround: execute inline using `superpowers:executing-plans`.
  Long-term fix: requires Claude Code to honour `modelOverrides` for subagent dispatch.

---

### Filter phase findings

**Fix 1 — Jira credential check used a hardcoded ticket (ENG-974050)**
- Problem: Phase 0 pinged a specific ticket to test Jira auth, which was confusing
  and could be mistaken for actual processing.
- Fix: Changed to `jira projects` which is a neutral credential check.
- Status: ✅ Fixed, committed.

**Fix 2 — Filter included In Progress / Reopened / Open tickets**
- Problem: `review.py filter` returned tickets with status=Open, In Progress,
  or Reopened. These are not R138 deliverables.
- Fix: Added `is_release_ready()` check: status must be in
  {Closed, Resolved, Pending Close} AND resolution must be Fixed/Done.
- Result: 111 → 97 tickets.
- Status: ✅ Fixed, committed.

**Fix 3 — Filter included tickets from prior releases**
- Problem: ENG-779909 (resolved 2025-11-10) appeared in the filter despite
  belonging to a prior release. It had `fix_versions=138.0.0` set retroactively.
- Fix: Added minimum resolved date filter (default: 2026-01-01). Tickets resolved
  before this date are excluded. Override via `--since=YYYY-MM-DD`.
- Result: 97 → 96 tickets.
- Status: ✅ Fixed, committed.

**Residual data quality issue — tickets in CSV that are not R138 deliverables**
- ENG-501033 and ENG-712642 were initially flagged as not-in-list, but confirmed
  as legitimate R138 tickets. The confusion was human error, not a filter bug.
- ENG-501033 has 40+ sprints in its history — it is a long-running ticket that
  was finally resolved in R138. It belongs in the list.
- Conclusion: the filter is correct. Truly out-of-scope tickets should be handled
  via [S] Skip during the approval phase, not via filter logic.

---

### Interactive prompt findings

**Fix 4 — "Press Enter" instruction doesn't work in Claude Code**
- Problem: Phase 1 and Phase 2 prompts said "Press Enter for defaults" and
  "Press Enter to accept" — but Claude Code skill interactions are conversational,
  not terminal keypresses.
- Fix: Changed to "Reply with your selection, or say 'defaults' to use A+B"
  and "Reply 'accept' to proceed, or describe changes."
- Status: ✅ Fixed in prompt.md and README.md, committed.

---

### Phase 3 analysis findings

**Fix 5 — Phase 4 ambiguity about when to show approval UI**
- Problem: prompt.md said "After processing all tickets, collect the Low-risk ones"
  but did not explicitly say to hold off presenting the batch until ALL tickets
  are analysed. A naive reading could trigger the batch UI mid-analysis.
- Fix: Added explicit note at the top of Phase 4: "Complete Phase 3 analysis for
  ALL tickets before entering Phase 4."
- Status: ✅ Fixed, committed.

**Observation — PR search finds PRs in repos other than dataplane**
- ENG-974050 PR was in netSkope/service, not netSkope/dataplane.
- ENG-712642 PR was also in netSkope/service.
- The `org:netSkope` search works correctly for both — no fix needed.
- Confidence: [T1] answers are reliable when the PR is found in any org repo.

**Observation — .featurec file = flag signal is reliable**
- ENG-705949 changed `libs/http/http_features.featurec`.
- This correctly triggered Q4=YES.
- However Q5 (flag default state) and Q6 (flag details) could not be answered
  from the PR body alone — both came back [?].
- Recommendation for future: when Q4=YES and Q5/Q6 are [?], the skill should
  suggest the reviewer look at the .featurec diff directly before approving.

---

### Tickets processed in Run 1

| Key | Disposition | Risk | Notes |
|-----|-------------|------|-------|
| ENG-573482 | Skipped by user | — | Status=Open, resolved by filter fix |
| ENG-510532 | Approved | High | UAF fix in ContentDispatchMgr, NSP-Core spotlight |
| ENG-705949 | Approved | High | 43-file MIME/DTE change, flag in http_features.featurec |
| ENG-712642 | Queued (Low) | Low | 1-file Python null check fix in monitoring agent |

---

### What to fix before Run 2

1. When Q4=YES and Q5/Q6 are [?], prompt the reviewer to inspect the .featurec
   or flag registration diff before approving — add this hint to the Phase 4
   per-ticket display.

2. Consider adding the `--since` flag usage to the skill's Phase 0 startup output
   so the reviewer knows which date cutoff is active.

3. Run 2 should process a larger batch (20+ tickets) to validate the Low-risk
   batch approval flow end-to-end.

4. Run 2 should verify the Phase 5 write+convert actually produces a correct XLSX
   with answers in the right columns for the approved tickets.
