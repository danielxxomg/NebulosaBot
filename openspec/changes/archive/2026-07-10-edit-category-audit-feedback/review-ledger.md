# Review Ledger — edit-category-audit-feedback

**Phase**: design (Judgment Day Round 1)  
**Artifact store**: openspec  
**Verdict**: APPROVED (no confirmed BLOCKER/CRITICAL)

## Findings

| id | lens | location | severity | status | evidence |
|----|------|----------|----------|--------|----------|
| JD-A-001 | judgment-day | design.md; tickets.py:846-882; ticket_service.py:362-395 | CRITICAL | info | Suspect only (Judge A). Concurrent edits could make the view's pre-snapshot old category diverge from the service's authoritative pre-update value. Judge B did not confirm. Accepted for first slice: concurrent dual-mod category edit is rare; service remains mutation source of truth. |
| JD-A-002 | judgment-day | design.md:49 | WARNING | info | assessment: real. Old category inactive/removed from options may surface raw UUID if fallback is only `or "—"`. |
| JD-B-001 | judgment-day | design.md:49 | WARNING | info | assessment: real. Same root as JD-A-002: use label lookup miss → `"—"` (or cached name), never raw UUID in channel embed. |
| JD-B-002 | judgment-day | specs/ticket-views/spec.md | WARNING | info | assessment: theoretical. Add scenario for deactivated-but-non-None old category. |

## Implementation guidance (non-blocking)

When implementing old-label resolution, prefer:

```python
old_label = next(
    (opt.label for opt in self.options if opt.value == old_category_id),
    None,
)
old_category_name = old_label if old_label is not None else "—"
```

Do **not** fall back to raw UUID in the channel-visible audit embed.

## Confirmed open for fix loop

None.

## Terminal (design)

`JUDGMENT: APPROVED`

---

# Review Ledger — apply phase (Judgment Day Round 1)

**Verdict**: APPROVED (no BLOCKER/CRITICAL)

| id | lens | location | severity | status | evidence |
|----|------|----------|----------|--------|----------|
| JD-B-001 | judgment-day | tests/test_tickets_i18n.py | WARNING | info | assessment: theoretical. i18n tests use fixture-injected keys; production JSON verified manually in review. |
| JD-B-002 | judgment-day | tests/test_ticket_views.py | WARNING | info | assessment: theoretical. Deactivated-but-non-None covered implicitly by success test; no dedicated named scenario. |

Judge A: CLEAN. Judge B: 2 WARNING info only.

## Terminal (apply)

`JUDGMENT: APPROVED`
