# Near-miss deposit Telegram DM — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When an unmatched treasury transfer near-misses a pending invoice (±1 USDT), queue one Telegram user notification without auto-crediting.

**Architecture:** Pure helper in `deposit_mismatch.py` picks the best pending invoice for a deposit; `apply_transfer` unmatched branch queues `user_notifications` via `_queue_notification` with dedupe key `deposit-mismatch:{invoice_id}:{chain_deposit_id}`.

**Tech Stack:** Python 3.12, aiosqlite, existing `user_notifications` worker, pytest

**Spec:** `docs/superpowers/specs/2026-09-10-near-miss-deposit-telegram-dm-design.md`

## Global Constraints

- Channel: Telegram via `user_notifications` only (no required in-app UI change)
- Trigger: new unmatched `chain_deposit` only (not duplicate; not exact match)
- Invoice status: `pending` only (not expired)
- Reuse `select_mismatch_candidate` / `_in_time_window` / `_amount_matches` / `MISMATCH_AMOUNT_TOLERANCE_MINOR` (1 USDT)
- No auto-credit; exact-match economics unchanged
- Dedupe: `deposit-mismatch:{invoice_id}:{chain_deposit_id}`
- RU telegram_html exactly as in the spec
- Queue failure must not roll back chain_deposit commit semantics

## File map

| File | Responsibility |
|------|----------------|
| `delta_backend/deposit_mismatch.py` | `select_pending_invoice_for_unmatched_deposit(invoices, deposit) -> dict \| None` |
| `tests/test_deposit_mismatch.py` | Unit tests for reverse helper |
| `delta_backend/repository.py` | Load pending invoices + queue notification on unmatched path |
| `tests/test_deposit_mismatch.py` (or new focused async test) | Integration: `apply_transfer` queues notification |

---

### Task 1: Reverse-lookup helper + unit tests

**Files:**
- Modify: `delta_backend/deposit_mismatch.py`
- Test: `tests/test_deposit_mismatch.py`

**Interfaces:**
- Produces: `select_pending_invoice_for_unmatched_deposit(invoices: list[dict], deposit: dict) -> dict | None`
- Consumes: existing `_in_time_window`, `_amount_matches` (same rules as `select_mismatch_candidate`)
- `deposit` keys used: `id`, `amount_minor`, `created_at`, `matched` (treat missing matched as 0)
- `invoice` keys used: `id`, `created_at`, `expires_at`, `base_minor`, `exact_minor`, `user_id` (and any fields already on invoice rows)
- Selection: keep invoices where `select_mismatch_candidate(invoice, [deposit])` is not None; among them sort by `(abs(deposit.created_at - invoice.created_at), abs(deposit.amount_minor - invoice.exact_minor), invoice.id)` and return the first. If deposit `matched != 0`, return None.

- [ ] **Step 1: Write failing tests**

```python
from delta_backend.deposit_mismatch import (
    select_mismatch_candidate,
    select_pending_invoice_for_unmatched_deposit,
)

def test_reverse_select_picks_near_miss_pending_invoice():
    deposit = {
        "id": 9,
        "amount_minor": 100_370000 + usdt_to_minor("1"),
        "created_at": 1010,
        "matched": 0,
    }
    invoices = [
        {"id": 1, "user_id": 10, "created_at": 1000, "expires_at": 5000,
         "base_minor": 100_000000, "exact_minor": 100_370000},
        {"id": 2, "user_id": 11, "created_at": 1000, "expires_at": 5000,
         "base_minor": 50_000000, "exact_minor": 50_120000},
    ]
    chosen = select_pending_invoice_for_unmatched_deposit(invoices, deposit)
    assert chosen is not None
    assert chosen["id"] == 1


def test_reverse_select_none_when_far_or_matched():
    deposit = {"id": 9, "amount_minor": 10_000000, "created_at": 1010, "matched": 0}
    invoices = [
        {"id": 1, "user_id": 10, "created_at": 1000, "expires_at": 5000,
         "base_minor": 100_000000, "exact_minor": 100_370000},
    ]
    assert select_pending_invoice_for_unmatched_deposit(invoices, deposit) is None
    matched = {"id": 9, "amount_minor": 100_370000, "created_at": 1010, "matched": 1}
    assert select_pending_invoice_for_unmatched_deposit(invoices, matched) is None


def test_reverse_select_prefers_closer_invoice_time():
    deposit = {"id": 9, "amount_minor": 100_000000, "created_at": 1100, "matched": 0}
    invoices = [
        {"id": 1, "user_id": 10, "created_at": 1000, "expires_at": 5000,
         "base_minor": 100_000000, "exact_minor": 100_370000},
        {"id": 2, "user_id": 11, "created_at": 1080, "expires_at": 5000,
         "base_minor": 100_000000, "exact_minor": 100_370000},
    ]
    assert select_pending_invoice_for_unmatched_deposit(invoices, deposit)["id"] == 2
```

- [ ] **Step 2: Run — expect FAIL**

Run: `python -m pytest tests/test_deposit_mismatch.py::test_reverse_select_picks_near_miss_pending_invoice tests/test_deposit_mismatch.py::test_reverse_select_none_when_far_or_matched tests/test_deposit_mismatch.py::test_reverse_select_prefers_closer_invoice_time -q`
Expected: FAIL (import / missing function)

- [ ] **Step 3: Implement helper**

```python
def select_pending_invoice_for_unmatched_deposit(
    invoices: list[dict], deposit: dict
) -> dict | None:
    if int(deposit.get("matched") or 0) != 0:
        return None
    eligible: list[dict] = []
    for invoice in invoices:
        if select_mismatch_candidate(invoice, [deposit]) is None:
            continue
        eligible.append(invoice)
    if not eligible:
        return None
    created = int(deposit["created_at"])
    amount = int(deposit["amount_minor"])
    eligible.sort(
        key=lambda inv: (
            abs(created - int(inv["created_at"])),
            abs(amount - int(inv["exact_minor"])),
            int(inv["id"]),
        )
    )
    return eligible[0]
```

- [ ] **Step 4: Run — expect PASS**

Run: `python -m pytest tests/test_deposit_mismatch.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add delta_backend/deposit_mismatch.py tests/test_deposit_mismatch.py
git commit -m "feat: reverse near-miss invoice picker for unmatched deposits"
```

---

### Task 2: Queue Telegram notification from `apply_transfer` unmatched path

**Files:**
- Modify: `delta_backend/repository.py` (`apply_transfer` unmatched branch)
- Test: `tests/test_deposit_mismatch.py` (async integration)

**Interfaces:**
- Consumes: `select_pending_invoice_for_unmatched_deposit`
- Inside unmatched branch (same transaction as audit + before exit), after writing `ops_unmatched`:
  1. `SELECT` pending invoices with `status='pending'` and `expires_at >= now` and user not blocked (enough columns for helper + `user_id`)
  2. Build deposit dict `{id, amount_minor, created_at, matched: 0}`
  3. `chosen = select_pending_invoice_for_unmatched_deposit(rows, deposit)`
  4. If chosen: `_queue_notification(...)` with spec fields

Notification fields (verbatim):
- category=`deposit`, event_type=`deposit_amount_mismatch`
- title=`Сумма перевода не совпала`
- body=`Ожидали {expected} USDT, в сети {observed} USDT. Нужна точная сумма с хвостом.`
- telegram_html as in spec (use `minor_to_text(..., trim=False)` for amounts if that matches invoice API; otherwise default `minor_to_text` — **prefer same as `get_user_invoice` mismatch observed/expected**)
- dedupe_key=`deposit-mismatch:{invoice_id}:{chain_deposit_id}`
- data=`{"target_view": "wallet", "invoice_id": ..., "chain_deposit_id": ...}`

Import the new helper next to existing `select_mismatch_candidate` import.

- [ ] **Step 1: Write failing integration test**

Pattern from `test_get_user_invoice_mismatch_hint` / ops chat tests: ensure user+wallet, create pending invoice, `apply_transfer` with amount = exact±1 USDT (unmatched), assert one `user_notifications` row with `event_type='deposit_amount_mismatch'` and expected dedupe_key. Second identical transfer (different log_index) with same invoice still only one row for first pair; call apply twice with same tx/log → duplicate, no second notify for same deposit id.

Also assert: amount far from invoice → unmatched but **zero** mismatch notifications.

Use `TransferEvent` model as other repository transfer tests do — search `apply_transfer(` in tests for the exact constructor.

- [ ] **Step 2: Implement repository hook**

- [ ] **Step 3: Run**

Run: `python -m pytest tests/test_deposit_mismatch.py -q`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add delta_backend/repository.py tests/test_deposit_mismatch.py
git commit -m "feat: Telegram DM on pending invoice near-miss unmatched deposit"
```

---

### Task 3: Verify

- [ ] **Step 1:** `python -m pytest tests/test_deposit_mismatch.py tests/test_ops_chat.py -q` — expect PASS
- [ ] **Step 2:** Deploy only if owner asks (`scripts/safe_update_remote.ps1 -Mode full`)
- [ ] **Step 3:** Manual: create pending invoice, send near-miss amount to treasury (or staging fixture) → expect bot DM

---

## Spec coverage

| Spec item | Task |
|-----------|------|
| Reverse candidate helper | 1 |
| apply_transfer unmatched hook | 2 |
| Dedupe key | 2 |
| pending-only | 2 (SQL filter) |
| No auto-credit | 1–2 (notify only) |
| Tests listed in spec | 1–2 |

## Self-review

- No TBD placeholders
- Helper name consistent across tasks
- Explicit: notification queued inside unmatched transaction branch (INSERT OR IGNORE dedupe), ops schedule remains after commit
