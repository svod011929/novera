# Unmatched deposit UX + admin recovery — План реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Показать пользователю near-miss по сумме на invoice и дать админу явный match unmatched `chain_deposit` → invoice с депозитом на фактическую on-chain сумму.

**Architecture:** Фаза 1 — read-only эвристика в `get_user_invoice` + UI phase `amount_mismatch`. Фаза 2 — `admin_match_chain_deposit` переиспользует логику открытия депозита из хвоста `apply_transfer` (без изменения exact-match монитора). Админ HTTP + вкладка Unmatched.

**Tech Stack:** Python/FastAPI/aiosqlite, vanilla Mini App JS, pytest, `scripts/safe_update_remote.ps1` для деплоя.

**Spec:** `docs/superpowers/specs/2026-09-09-unmatched-deposit-recovery-design.md`

## Global Constraints

- Обычный `apply_transfer` exact-match **не менять**.
- Юзерский hint — только read-only; **нет** самозачисления.
- Admin match: invoice `pending|expired` only (никогда `paid`); principal = `chain_deposits.amount_minor`.
- `reason` обязателен для match; audit `deposit_recovery_matched`.
- UI тексты RU (+ EN ключи); commits только по запросу владельца, если не сказано иное в сессии.
- Deploy через `safe_update_remote.ps1 -Mode full` только после явного OK владельца (если не сказано «деплой без ожидания»).

---

## File map

| File | Responsibility |
|------|----------------|
| `delta_backend/deposit_mismatch.py` | Чистые функции: эвристика выбора кандидата, константы окна/tolerance |
| `delta_backend/repository.py` | `find_invoice_mismatch_hint`, расширить `get_user_invoice`; `list_unmatched_chain_deposits`, `admin_match_chain_deposit` |
| `delta_backend/api.py` | Поля в GET invoice; `GET/POST /api/admin/chain-deposits…` |
| `frontend/assets/app.js` | phase `amount_mismatch`, copy, support CTA; admin unmatched UI |
| `frontend/index.html` | admin section + cache bump `app.js?v=` |
| `tests/test_deposit_mismatch.py` | unit эвристики + repo hint |
| `tests/test_deposit_recovery.py` | admin match money-safety |

---

### Task 1: Эвристика mismatch (pure + tests)

**Files:**
- Create: `delta_backend/deposit_mismatch.py`
- Create: `tests/test_deposit_mismatch.py`

**Interfaces:**
- Produces: `MISMATCH_LOOKBACK_SECONDS = 300`, `MISMATCH_LOOKAHEAD_AFTER_EXPIRY_SECONDS = 7200`, `MISMATCH_AMOUNT_TOLERANCE_MINOR = 1 * MINOR_FACTOR` (1.00 USDT)
- Produces: `select_mismatch_candidate(invoice: dict, candidates: list[dict]) -> dict | None`
  - `invoice` keys: `created_at`, `expires_at`, `base_minor`, `exact_minor` (ints)
  - candidate keys: `id`, `amount_minor`, `created_at`, `tx_hash`, `matched` (0/1)
  - Returns best candidate dict or `None`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_deposit_mismatch.py
from delta_backend.deposit_mismatch import select_mismatch_candidate

def test_select_by_base_minor():
    invoice = {"created_at": 1000, "expires_at": 2000, "base_minor": 100_000000, "exact_minor": 100_370000}
    candidates = [
        {"id": 1, "amount_minor": 100_000000, "created_at": 1010, "tx_hash": "0xa", "matched": 0},
    ]
    assert select_mismatch_candidate(invoice, candidates)["id"] == 1

def test_select_within_one_usdt_of_exact():
    invoice = {"created_at": 1000, "expires_at": 2000, "base_minor": 100_000000, "exact_minor": 100_370000}
    candidates = [
        {"id": 2, "amount_minor": 100_370000 - 50, "created_at": 1010, "tx_hash": "0xb", "matched": 0},
    ]
    assert select_mismatch_candidate(invoice, candidates)["id"] == 2

def test_reject_outside_window_and_tolerance():
    invoice = {"created_at": 1000, "expires_at": 2000, "base_minor": 100_000000, "exact_minor": 100_370000}
    far = {"id": 3, "amount_minor": 50_000000, "created_at": 1010, "tx_hash": "0xc", "matched": 0}
    early = {"id": 4, "amount_minor": 100_000000, "created_at": 100, "tx_hash": "0xd", "matched": 0}
    assert select_mismatch_candidate(invoice, [far, early]) is None

def test_prefer_closest_created_at_then_smaller_delta():
    invoice = {"created_at": 1000, "expires_at": 2000, "base_minor": 100_000000, "exact_minor": 100_370000}
    candidates = [
        {"id": 5, "amount_minor": 100_000000, "created_at": 1500, "tx_hash": "0xe", "matched": 0},
        {"id": 6, "amount_minor": 100_000000, "created_at": 1050, "tx_hash": "0xf", "matched": 0},
    ]
    assert select_mismatch_candidate(invoice, candidates)["id"] == 6
```

- [ ] **Step 2: Run tests — expect FAIL (module missing)**

Run: `pytest tests/test_deposit_mismatch.py -v`  
Expected: import / attribute errors

- [ ] **Step 3: Implement `deposit_mismatch.py`**

```python
"""Near-miss heuristics for unmatched treasury transfers vs an invoice."""

MISMATCH_LOOKBACK_SECONDS = 300
MISMATCH_LOOKAHEAD_AFTER_EXPIRY_SECONDS = 7200
MISMATCH_AMOUNT_TOLERANCE_MINOR = 100  # 1.00 USDT


def _in_time_window(invoice: dict, created_at: int) -> bool:
    start = int(invoice["created_at"]) - MISMATCH_LOOKBACK_SECONDS
    end = int(invoice["expires_at"]) + MISMATCH_LOOKAHEAD_AFTER_EXPIRY_SECONDS
    return start <= int(created_at) <= end


def _amount_matches(invoice: dict, amount_minor: int) -> bool:
    amount_minor = int(amount_minor)
    if amount_minor == int(invoice["base_minor"]):
        return True
    return abs(amount_minor - int(invoice["exact_minor"])) <= MISMATCH_AMOUNT_TOLERANCE_MINOR


def select_mismatch_candidate(
    invoice: dict, candidates: list[dict]
) -> dict | None:
    usable: list[dict] = []
    for row in candidates:
        if int(row.get("matched") or 0) != 0:
            continue
        if not _in_time_window(invoice, int(row["created_at"])):
            continue
        if not _amount_matches(invoice, int(row["amount_minor"])):
            continue
        usable.append(row)
    if not usable:
        return None
    created = int(invoice["created_at"])
    exact = int(invoice["exact_minor"])
    usable.sort(
        key=lambda r: (
            abs(int(r["created_at"]) - created),
            abs(int(r["amount_minor"]) - exact),
            int(r["id"]),
        )
    )
    return usable[0]
```

- [ ] **Step 4: Run tests — expect PASS**

Run: `pytest tests/test_deposit_mismatch.py -v`  
Expected: all PASS

- [ ] **Step 5: Commit** (если владелец разрешил commits в сессии)

```bash
git add delta_backend/deposit_mismatch.py tests/test_deposit_mismatch.py
git commit -m "feat: unmatched deposit near-miss heuristic"
```

---

### Task 2: `get_user_invoice` + mismatch fields

**Files:**
- Modify: `delta_backend/repository.py` (`get_user_invoice`, add `find_invoice_mismatch_hint` / wire select)
- Modify: `tests/test_deposit_mismatch.py` (repo integration) **или** `tests/test_promo_deeplink.py` assertions
- Modify: `delta_backend/api.py` only if GET handler maps fields (обычно проброс dict as-is)

**Interfaces:**
- Consumes: `select_mismatch_candidate`
- Produces: `get_user_invoice` return includes `mismatch_hint: bool`, `mismatch: dict | None` with keys `observed_amount`, `expected_amount`, `tx_hash`, `created_at`
- Requires invoice row to expose `created_at` in the SELECT

- [ ] **Step 1: Failing repo test**

```python
async def test_get_user_invoice_mismatch_hint(tmp_path):
    # ensure_user, set_wallet, create_invoice(base=10 USDT)
    # INSERT chain_deposits matched=0 amount=base_minor near now
    # row = await repo.get_user_invoice(user, invoice_id)
    # assert row["mismatch_hint"] is True
    # assert row["mismatch"]["tx_hash"] == ...
    # assert row["credited"] is False
```

Insert unmatched row with SQL via `repo._connection()` under lock, mirroring columns: `chain_id, tx_hash, log_index, block_number, from_address, to_address, amount_atomic, amount_minor, created_at` (`matched` default 0).

- [ ] **Step 2: Run — FAIL (keys missing)**

Run: `pytest tests/test_deposit_mismatch.py::test_get_user_invoice_mismatch_hint -v`

- [ ] **Step 3: Implement**

In `get_user_invoice` SELECT add `invoice.created_at`, `invoice.exact_minor` already present. After building base response (and if not `credited`):

```python
mismatch = await self._invoice_mismatch_hint(
    connection,
    created_at=int(row["created_at"]),
    expires_at=expires_at,
    base_minor=base_minor,
    exact_minor=int(row["exact_minor"]),
)
# attach mismatch_hint / mismatch using minor_to_text for amounts
```

`_invoice_mismatch_hint`: query

```sql
SELECT id, amount_minor, created_at, tx_hash, matched
FROM chain_deposits
WHERE matched = 0
  AND created_at BETWEEN ? AND ?
```

with `start = created_at - 300`, `end = expires_at + 7200`, then `select_mismatch_candidate(...)`.

Always return `mismatch_hint`/`mismatch` keys (False/None when none).

- [ ] **Step 4: PASS tests** including existing `tests/test_promo_deeplink.py` / `test_promo_api.py` GET invoice (добавить assert ключей если нужно)

- [ ] **Step 5: Commit** (по разрешению)

```bash
git commit -m "feat: expose invoice mismatch_hint on status API"
```

---

### Task 3: Mini App `amount_mismatch` UX

**Files:**
- Modify: `frontend/assets/app.js` — `invoiceUiPhase`, `updateInvoiceStatusUi`, `renderInvoice`, i18n
- Modify: `frontend/index.html` — `app.js?v=novera-deposit-recovery-1`

**Interfaces:**
- Consumes: poll payload `mismatch_hint`, `mismatch.{observed_amount,expected_amount}`, `state.data.support_url`

- [ ] **Step 1: i18n keys (ru + en)**

```javascript
invoiceAmountMismatch: 'Перевод найден, но сумма не совпала',
invoiceAmountMismatchDetail: 'Ожидали {expected} USDT, в сети {observed} USDT. Нужна точная сумма с хвостом.',
invoiceAmountMismatchSupport: 'Написать в поддержку',
invoiceExpiredHint: 'Срок заявки истёк. Если перевод уже отправлен — проверьте точную сумму или напишите в поддержку.',
```

- [ ] **Step 2: Phase logic**

In `invoiceUiPhase`: if `invoice.mismatch_hint && !credited` → `'amount_mismatch'` (даже если status expired).

In `applyInvoiceStatusPayload`: copy `mismatch_hint` / `mismatch` from status.

In `renderInvoice` / `updateInvoiceStatusUi`: показать detail + кнопку support (`window.open(support_url)`). Status class `queued` or `failed` for mismatch; для expired без hint — показать `invoiceExpiredHint`.

- [ ] **Step 3: Manual smoke** — создать invoice в UI, убедиться что poll не ломается при `mismatch_hint:false`.

- [ ] **Step 4: Commit** (по разрешению)

```bash
git commit -m "feat: Mini App amount-mismatch invoice state"
```

---

### Task 4: `admin_match_chain_deposit` (money path)

**Files:**
- Modify: `delta_backend/repository.py`
- Create: `tests/test_deposit_recovery.py`

**Interfaces:**
- Produces: `async def admin_match_chain_deposit(self, chain_deposit_id: int, invoice_id: int, *, admin_id: int, reason: str) -> dict`
  - Returns `{deposit_id, invoice_id, chain_deposit_id, principal_minor, bonus_minor, tx_hash, reused: bool}`
  - Raises `RepositoryError` with clear messages for 409/404 mapping

**Rules (encode in tests first):**
1. reason non-empty (strip, max 500)
2. chain_deposit exists, `matched==0`
3. invoice exists, status in (`pending`,`expired`) after TTL normalize; not `paid`; has payout_address; user not blocked
4. principal = `amount_minor` + optional promo bonus via `_reserve_promo_redemption` on **invoice.base_minor** (same as apply_transfer); on skip → principal = amount_minor
5. Mark invoice paid, set tx_hash/paid_at; set chain_deposits matched+invoice_id; insert deposits; audit `deposit_recovery_matched` and `deposit_opened`; notify like apply_transfer if feasible (reuse notification queue helpers in same transaction path)
6. Second call → RepositoryError already matched

- [ ] **Step 1: Failing tests**

```python
async def test_admin_match_uses_on_chain_amount(tmp_path): ...
async def test_admin_match_allows_expired_invoice(tmp_path): ...
async def test_admin_match_rejects_paid_invoice(tmp_path): ...
async def test_admin_match_rejects_double(tmp_path): ...
```

Pattern: create_invoice → expire via SQL `expires_at`/`status` → insert unmatched chain_deposit with **base** amount ≠ exact → `admin_match_chain_deposit` → assert deposit.principal_minor == chain amount (+bonus if any) and chain.matched==1.

- [ ] **Step 2: Run — FAIL**

- [ ] **Step 3: Implement `admin_match_chain_deposit`**

Скопировать/адаптировать блок открытия депозита из `apply_transfer` (после нахождения invoice), но:
- invoice загружается по id (не по exact_minor);
- разрешить status pending/expired;
- не искать другой invoice по сумме.

Также: `async def list_unmatched_chain_deposits(self, *, limit: int = 50) -> list[dict]`

```sql
SELECT * FROM chain_deposits WHERE matched = 0 ORDER BY id DESC LIMIT ?
```

Serialize amounts with `minor_to_text`.

- [ ] **Step 4: PASS**

Run: `pytest tests/test_deposit_recovery.py tests/test_deposit_mismatch.py -v`

- [ ] **Step 5: Commit** (по разрешению)

```bash
git commit -m "feat: admin match unmatched chain deposit to invoice"
```

---

### Task 5: Admin HTTP API

**Files:**
- Modify: `delta_backend/api.py`
- Modify: `tests/test_deposit_recovery.py` (httpx ASGI, mirror `tests/test_promo_api.py` fixture)

**Interfaces:**
- `GET /api/admin/chain-deposits?matched=0&limit=50` → `{ "items": [ ... ] }`
- `POST /api/admin/chain-deposits/{id}/match` body `{ "invoice_id": int, "reason": str }` → match result
- Map `RepositoryError` → 409; missing → 404

Pydantic:

```python
class ChainDepositMatchRequest(BaseModel):
    invoice_id: int
    reason: str

    @field_validator("reason")
    @classmethod
    def _reason(cls, value: str) -> str:
        clean = value.strip()
        if not clean:
            raise ValueError("Reason is required")
        return clean[:500]
```

- [ ] **Step 1: API tests FAIL**
- [ ] **Step 2: Wire routes with `Depends(admin_user)`**
- [ ] **Step 3: PASS**
- [ ] **Step 4: Commit** (по разрешению)

```bash
git commit -m "feat: admin chain-deposit list and match API"
```

---

### Task 6: Admin Mini App UI

**Files:**
- Modify: `frontend/index.html` — tab button + `<section id="admin-unmatched">`
- Modify: `frontend/assets/app.js` — `loadAdminUnmatched`, match prompt, wire `loadAdminTab`
- Cache bump if not already `novera-deposit-recovery-1`

- [ ] **Step 1: HTML** — admin tab `data-admin-tab="unmatched"` рядом с logs

- [ ] **Step 2: JS**

```javascript
async function loadAdminUnmatched(){
  const res = await api('/api/admin/chain-deposits?matched=0&limit=50');
  // render table: id, amount, tx (explorer link from chain.explorer_tx_url + hash), created
  // Match button → prompt invoice_id + reason → POST .../match → reload
}
```

В `loadAdminTab`: `else if(tab==='unmatched') await loadAdminUnmatched();`

- [ ] **Step 3: Commit** (по разрешению)

```bash
git commit -m "feat: admin unmatched deposits UI"
```

---

### Task 7: Verify + deploy

- [ ] **Step 1:** `pytest tests/test_deposit_mismatch.py tests/test_deposit_recovery.py tests/test_promo_deeplink.py tests/test_promo_api.py -q`
- [ ] **Step 2:** Deploy only if owner confirms:  
  `powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\safe_update_remote.ps1 -Mode full`
- [ ] **Step 3:** Smoke: pending invoice poll; admin list unmatched (может быть пусто); no regression `/ready`

---

## Spec coverage checklist

| Spec item | Task |
|-----------|------|
| mismatch API fields + heuristic | 1–2 |
| Mini App amount_mismatch + expiry fallback | 3 |
| Admin list unmatched | 5–6 |
| Admin match pending\|expired, on-chain principal | 4–5 |
| No auto-rematch / no user claim | Global + omitted tasks |
| Promo skip path | 4 |
| Tests listed in spec | 1,2,4,5 |

## Placeholder / consistency self-review

- Имена: `select_mismatch_candidate`, `admin_match_chain_deposit`, `mismatch_hint` — едины по задачам.
- Tolerance = 100 minor = 1 USDT — как в спеке.
- Нет TBD/«similar to Task N» без кода.

---

**Plan complete.** Два варианта исполнения:

1. **Subagent-Driven (рекомендую)** — свежий субагент на задачу, ревью между задачами  
2. **Inline Execution** — этой сессией по `executing-plans` с чекпоинтами  

Какой подход?
