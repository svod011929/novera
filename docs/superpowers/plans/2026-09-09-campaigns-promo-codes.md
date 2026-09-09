# Campaigns + Promo Codes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship admin-managed promo codes (percent or fixed USDT bonus that boosts deposit principal) plus scheduled campaigns (promo / partner / custom) that send through the existing broadcast delivery pipeline.

**Architecture:** Extend SQLite schema in `DeltaRepository._migrate`; promo attach on invoice + redeem on deposit open under the repository lock; `CampaignService` tick creates `create_broadcast(...)` for due campaigns. Admin Mini App tab «Кампании»; deposit form gets optional promo field. One-shot «Рассылка» unchanged.

**Tech Stack:** Python 3.12 / FastAPI / aiosqlite / aiogram / vanilla Mini App JS / pytest

**Spec:** `docs/superpowers/specs/2026-09-09-campaigns-promo-codes-design.md`

## Global Constraints

- Bonus types: `percent` (stored as **bps**, 1000 = 10%) or `fixed` (USDT **minor** units).
- Bonus computed from invoice **`base_minor`** (not jittered `exact_minor`).
- On deposit open: `principal_minor = transfer.amount_minor + bonus_minor` (keeps jitter in principal; adds bonus).
- Shared code; **1 redemption per user**; global `max_redemptions`; reject if `principal` would exceed configured deposit max.
- Redemption committed only when deposit opens; expired invoice does not consume.
- Campaign schedules: `interval` (hours) or `weekly` (weekdays JSON + `HH:MM` UTC).
- Audience: `all` | `investors` | `partners` via existing `BROADCAST_AUDIENCE_FILTERS`.
- Placeholders in promo campaign text: `{{code}}`, `{{bonus_label}}`.
- Admin-only CRUD; server-side validation only; race-safe redeem under repository lock.
- No unique per-user codes, no promo stacking, no Team UI changes, no public marketing toolkit.

## Locked decisions (from open points)

| Topic | Decision |
|--------|----------|
| Percent storage | Integer **bps** in `bonus_bps` column; `fixed` uses `bonus_fixed_minor` |
| Bonus base | `invoice.base_minor` |
| Principal | `transfer.amount_minor + bonus_minor` |
| Worker | `delta_backend/services/campaigns.py` → `CampaignService` |
| Admin investments | No promo in v1 (chain invoices only) |

## File map

| File | Role |
|------|------|
| `delta_backend/repository.py` | Schema, promo CRUD, invoice promo, redeem on open, campaigns CRUD + due claim |
| `delta_backend/api.py` | User invoice `promo_code`; admin promo/campaign routes; wire CampaignService |
| `delta_backend/services/campaigns.py` | Periodic tick → `create_broadcast` |
| `tests/test_promo_codes.py` | Promo + redeem tests |
| `tests/test_campaigns.py` | Schedule / skip / broadcast creation |
| `frontend/index.html` | Admin tab + deposit promo input |
| `frontend/assets/app.js` | UI + i18n + API calls |

---

### Task 1: Schema + promo CRUD (repository)

**Files:**
- Modify: `delta_backend/repository.py` (`_migrate`, new methods)
- Test: `tests/test_promo_codes.py`

**Interfaces:**
- Produces:
  - `async def admin_create_promo_code(self, *, code: str, bonus_type: str, bonus_bps: int, bonus_fixed_minor: int, max_redemptions: int, min_deposit_minor: int, valid_from: int | None, valid_until: int | None, enabled: bool, created_by: int) -> dict`
  - `async def admin_list_promo_codes(self) -> list[dict]`
  - `async def admin_update_promo_code(self, promo_id: int, **fields) -> dict`
  - `async def get_promo_by_code(self, code: str) -> dict | None`
  - Helper: `def compute_promo_bonus_minor(promo: dict, base_minor: int) -> int`

- [ ] **Step 1: Write failing tests**

Create `tests/test_promo_codes.py`:

```python
import time
from delta_backend.amounts import usdt_to_minor
from delta_backend.api_settings import MiniAppSettings
from delta_backend.repository import DeltaRepository, RepositoryError


async def test_admin_create_and_list_promo_codes(tmp_path) -> None:
    repo = DeltaRepository(tmp_path / "d.sqlite3", MiniAppSettings(_env_file=None))
    await repo.connect()
    try:
        await repo.ensure_user(1, "admin", "Admin", "ru")
        created = await repo.admin_create_promo_code(
            code=" welcome10 ",
            bonus_type="percent",
            bonus_bps=1000,
            bonus_fixed_minor=0,
            max_redemptions=100,
            min_deposit_minor=0,
            valid_from=None,
            valid_until=None,
            enabled=True,
            created_by=1,
        )
        assert created["code"] == "WELCOME10"
        assert created["bonus_type"] == "percent"
        assert int(created["bonus_bps"]) == 1000
        rows = await repo.admin_list_promo_codes()
        assert any(r["code"] == "WELCOME10" for r in rows)
        with pytest.raises(RepositoryError):
            await repo.admin_create_promo_code(
                code="welcome10",
                bonus_type="percent",
                bonus_bps=500,
                bonus_fixed_minor=0,
                max_redemptions=10,
                min_deposit_minor=0,
                valid_from=None,
                valid_until=None,
                enabled=True,
                created_by=1,
            )
    finally:
        await repo.close()


async def test_compute_promo_bonus_minor() -> None:
    from delta_backend.repository import compute_promo_bonus_minor
    assert compute_promo_bonus_minor({"bonus_type": "percent", "bonus_bps": 1000}, usdt_to_minor("100")) == usdt_to_minor("10")
    assert compute_promo_bonus_minor({"bonus_type": "fixed", "bonus_fixed_minor": usdt_to_minor("5")}, usdt_to_minor("100")) == usdt_to_minor("5")
```

Add `import pytest` at top.

- [ ] **Step 2: Run — expect FAIL**

```bash
python -m pytest tests/test_promo_codes.py -v
```

- [ ] **Step 3: Implement schema + CRUD**

In `_migrate`, after existing alters, create tables:

```sql
CREATE TABLE IF NOT EXISTS promo_codes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  code TEXT NOT NULL UNIQUE,
  bonus_type TEXT NOT NULL CHECK (bonus_type IN ('percent', 'fixed')),
  bonus_bps INTEGER NOT NULL DEFAULT 0 CHECK (bonus_bps >= 0),
  bonus_fixed_minor INTEGER NOT NULL DEFAULT 0 CHECK (bonus_fixed_minor >= 0),
  max_redemptions INTEGER NOT NULL CHECK (max_redemptions >= 1),
  redemption_count INTEGER NOT NULL DEFAULT 0 CHECK (redemption_count >= 0),
  min_deposit_minor INTEGER NOT NULL DEFAULT 0 CHECK (min_deposit_minor >= 0),
  valid_from INTEGER,
  valid_until INTEGER,
  enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
  created_by INTEGER NOT NULL,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS promo_redemptions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  promo_code_id INTEGER NOT NULL REFERENCES promo_codes(id),
  user_id INTEGER NOT NULL,
  deposit_id INTEGER NOT NULL,
  invoice_id INTEGER NOT NULL,
  bonus_minor INTEGER NOT NULL CHECK (bonus_minor > 0),
  created_at INTEGER NOT NULL,
  UNIQUE(promo_code_id, user_id)
);
```

Also migrate columns (ignore duplicate-column errors like existing pattern):

```sql
ALTER TABLE deposit_invoices ADD COLUMN promo_code_id INTEGER;
ALTER TABLE deposits ADD COLUMN bonus_minor INTEGER NOT NULL DEFAULT 0;
ALTER TABLE deposits ADD COLUMN promo_code_id INTEGER;
```

Implement module-level:

```python
def compute_promo_bonus_minor(promo: dict[str, object], base_minor: int) -> int:
    kind = str(promo.get("bonus_type") or "")
    if kind == "percent":
        return (int(base_minor) * int(promo.get("bonus_bps") or 0)) // 10_000
    if kind == "fixed":
        return int(promo.get("bonus_fixed_minor") or 0)
    raise RepositoryError("Invalid promo bonus type")
```

Normalize code: `code.strip().upper()`. Reject empty, length > 32, invalid type, percent with bps<=0, fixed with fixed_minor<=0, both types mutually exclusive values (other field 0). Duplicate code → `RepositoryError`.

- [ ] **Step 4: Run — expect PASS**

```bash
python -m pytest tests/test_promo_codes.py -v
```

- [ ] **Step 5: Commit**

```bash
git add delta_backend/repository.py tests/test_promo_codes.py
git commit -m "feat: promo code schema and admin CRUD"
```

---

### Task 2: Attach promo on invoice + redeem on deposit open

**Files:**
- Modify: `delta_backend/repository.py` (`create_invoice`, `apply_transfer`)
- Modify: `tests/test_promo_codes.py`
- Reuse: `tests/test_repository.py` `pay_invoice` helper pattern

**Interfaces:**
- Change: `create_invoice(self, user_id, base_minor, idempotency_key=None, promo_code: str | None = None)`
- Returns invoice dict may include `promo_code_id`, `bonus_minor`, `effective_principal_minor`
- On open: write `deposits.bonus_minor`, `deposits.promo_code_id`, `promo_redemptions`, bump `redemption_count`

- [ ] **Step 1: Failing redeem tests**

```python
from delta_backend.models import TransferEvent

WALLET_ONE = "0x0000000000000000000000000000000000000001"
WALLET_TWO = "0x0000000000000000000000000000000000000002"


async def _pay(repo, user_id, amount, log_index, promo_code=None):
    inv = await repo.create_invoice(user_id, usdt_to_minor(amount), promo_code=promo_code)
    exact = int(inv["exact_minor"])
    result = await repo.apply_transfer(
        TransferEvent(
            chain_id=97,
            tx_hash=f"0x{log_index:064x}",
            log_index=log_index,
            block_number=100 + log_index,
            from_address=WALLET_TWO,
            to_address=WALLET_ONE,
            amount_atomic=exact * 10**12,
            amount_minor=exact,
        )
    )
    assert result["matched"] is True
    return int(result["deposit_id"]), inv


async def test_promo_boosts_principal_once_per_user(tmp_path) -> None:
    repo = DeltaRepository(tmp_path / "d.sqlite3", MiniAppSettings(_env_file=None))
    await repo.connect()
    try:
        await repo.ensure_user(10, "u", "U", "ru")
        await repo.set_wallet(10, WALLET_ONE)
        await repo.admin_create_promo_code(
            code="PLUS10",
            bonus_type="percent",
            bonus_bps=1000,
            bonus_fixed_minor=0,
            max_redemptions=50,
            min_deposit_minor=0,
            valid_from=None,
            valid_until=None,
            enabled=True,
            created_by=10,
        )
        deposit_id, inv = await _pay(repo, 10, "100", 1, promo_code="PLUS10")
        bonus = usdt_to_minor("10")
        connection = repo._connection()
        async with repo._lock:
            cur = await connection.execute(
                "SELECT principal_minor, bonus_minor FROM deposits WHERE id = ?",
                (deposit_id,),
            )
            row = dict(await cur.fetchone())
        assert int(row["bonus_minor"]) == bonus
        assert int(row["principal_minor"]) == int(inv["exact_minor"]) + bonus

        await repo.ensure_user(11, "u2", "U2", "ru")
        await repo.set_wallet(11, WALLET_TWO)
        # same user cannot redeem again
        with pytest.raises(RepositoryError):
            await repo.create_invoice(10, usdt_to_minor("50"), promo_code="PLUS10")
    finally:
        await repo.close()


async def test_expired_invoice_does_not_consume_promo(tmp_path) -> None:
    repo = DeltaRepository(tmp_path / "d.sqlite3", MiniAppSettings(_env_file=None))
    await repo.connect()
    try:
        await repo.ensure_user(20, "u", "U", "ru")
        await repo.set_wallet(20, WALLET_ONE)
        await repo.admin_create_promo_code(
            code="ONCE",
            bonus_type="fixed",
            bonus_bps=0,
            bonus_fixed_minor=usdt_to_minor("5"),
            max_redemptions=1,
            min_deposit_minor=0,
            valid_from=None,
            valid_until=None,
            enabled=True,
            created_by=20,
        )
        inv = await repo.create_invoice(20, usdt_to_minor("100"), promo_code="ONCE")
        async with repo.transaction() as connection:
            await connection.execute(
                "UPDATE deposit_invoices SET status='expired', expires_at=? WHERE id=?",
                (int(time.time()) - 10, inv["invoice_id"]),
            )
        # promo still available for new invoice
        inv2 = await repo.create_invoice(20, usdt_to_minor("100"), promo_code="ONCE")
        assert inv2["invoice_id"] != inv["invoice_id"]
    finally:
        await repo.close()
```

- [ ] **Step 2: Run — FAIL**

```bash
python -m pytest tests/test_promo_codes.py::test_promo_boosts_principal_once_per_user tests/test_promo_codes.py::test_expired_invoice_does_not_consume_promo -v
```

- [ ] **Step 3: Implement attach + redeem**

In `create_invoice`:
1. If `promo_code` blank → existing path (`promo_code_id=NULL`).
2. Else load promo by normalized code; validate enabled, time window, `redemption_count < max`, no existing `promo_redemptions` for user, `base_minor >= min_deposit_minor`.
3. `bonus = compute_promo_bonus_minor(...)`; if `bonus <= 0` → error.
4. If `base_minor + bonus > deposit_max_minor` → `RepositoryError("Promo would exceed deposit maximum")`.
5. INSERT invoice with `promo_code_id`.
6. Return also `bonus_minor`, `effective_principal_preview_minor` (= `base_minor + bonus` for UI; actual principal still exact+bonus at pay time).

**Idempotency:** if reused invoice, require same promo binding (or both null); mismatch → error.

In `apply_transfer` after selecting invoice, before INSERT deposits:

```python
bonus_minor = 0
promo_id = invoice["promo_code_id"]
if promo_id is not None:
    # re-validate under same transaction; insert promo_redemptions;
    # UPDATE promo_codes SET redemption_count = redemption_count + 1
    # WHERE id=? AND redemption_count < max_redemptions
    # compute bonus from invoice base_minor
principal = int(transfer.amount_minor) + bonus_minor
# INSERT deposits(..., principal_minor, bonus_minor, promo_code_id)
```

If redeem insert hits UNIQUE or count update rowcount=0 → fail the match path carefully (prefer: leave unmatched only if race; better raise and roll back transaction so transfer can retry — keep inside same transaction so IntegrityError rolls back transfer insert too). Prefer transactional failure that returns unmatched only when invoice invalid; for race on redeem, raise `RepositoryError` after rollback is automatic via transaction context.

- [ ] **Step 4: PASS tests + commit**

```bash
python -m pytest tests/test_promo_codes.py -v
git add delta_backend/repository.py tests/test_promo_codes.py
git commit -m "feat: apply promo bonus to deposit principal on confirm"
```

---

### Task 3: User + admin HTTP API for promos

**Files:**
- Modify: `delta_backend/api.py`
- Test: `tests/test_promo_api.py` (follow `tests/test_broadcast_api.py` / admin auth patterns)

**Interfaces:**
- `InvoiceRequest.promo_code: str | None = None` (max 32)
- `POST /api/deposits/invoice` passes `promo_code` into repository; response includes `bonus_minor`, `bonus_usdt`, `effective_principal_usdt` (preview from base+bonus)
- Admin:
  - `GET /api/admin/promo-codes`
  - `POST /api/admin/promo-codes`
  - `PATCH /api/admin/promo-codes/{id}`

- [ ] **Step 1: Write API tests mirroring existing admin client fixture** (copy auth helper from `tests/test_admin_controls_api.py` or `test_broadcast_api.py`).

Assert non-admin → 403; create percent promo → 200; invoice with promo returns bonus fields; second invoice with same promo for user → 409.

- [ ] **Step 2: Implement routes + models**

```python
class PromoCodeCreateRequest(BaseModel):
    code: str = Field(min_length=1, max_length=32)
    bonus_type: Literal["percent", "fixed"]
    bonus_percent: Decimal | None = None  # e.g. 10 for 10% → bps=1000
    bonus_usdt: Decimal | None = None
    max_redemptions: int = Field(ge=1, le=1_000_000)
    min_deposit_usdt: Decimal = Field(default=Decimal("0"), ge=0)
    valid_from: int | None = None
    valid_until: int | None = None
    enabled: bool = True
```

Convert percent → bps: `int(bonus_percent * 100)` only if values are in percent points with 2 decimals max — **use** `int(Decimal(bonus_percent) * 100)` for bps when percent is like `10.00` → 1000 bps.

- [ ] **Step 3: PASS + commit**

```bash
python -m pytest tests/test_promo_api.py tests/test_promo_codes.py -v
git add delta_backend/api.py tests/test_promo_api.py
git commit -m "feat: promo code HTTP API for admin and invoices"
```

---

### Task 4: Campaigns repository + worker

**Files:**
- Modify: `delta_backend/repository.py`
- Create: `delta_backend/services/campaigns.py`
- Test: `tests/test_campaigns.py`

**Interfaces:**
- `admin_create_campaign`, `admin_list_campaigns`, `admin_update_campaign`
- `async def claim_due_campaigns(self, now: int, limit: int = 10) -> list[dict]` — selects enabled where `next_run_at <= now`, then for each updates `last_sent_at`/`next_run_at` in same transaction after building message
- `async def dispatch_campaign(self, campaign_id: int, *, force: bool = False) -> dict` — creates broadcast; returns skip reason or broadcast id
- `CampaignService.run_forever` similar to `BroadcastService` loop (sleep 30–60s)

**Schedule helpers:**

```python
def compute_next_run_at(campaign: dict, after: int) -> int:
    mode = campaign["schedule_mode"]
    if mode == "interval":
        hours = max(1, int(campaign["interval_hours"]))
        return after + hours * 3600
    # weekly: weekdays JSON list of ints 0=Mon .. 6=Sun; time_utc "HH:MM"
    ...
```

Use UTC via `time.gmtime` / `calendar`.

- [ ] **Step 1: Failing tests**

```python
async def test_interval_campaign_creates_broadcast(tmp_path) -> None:
    # create users, campaign interval_hours=24, next_run_at=past
    # call dispatch_campaign / claim+dispatch
    # assert admin_broadcasts has new row with audience and message

async def test_promo_campaign_skips_when_code_exhausted(tmp_path) -> None:
    # max_redemptions=1 already redeemed
    # dispatch → status skipped, no new broadcast
```

- [ ] **Step 2: Implement tables**

```sql
CREATE TABLE IF NOT EXISTS campaigns (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  kind TEXT NOT NULL CHECK (kind IN ('promo', 'partner', 'custom')),
  audience TEXT NOT NULL CHECK (audience IN ('all', 'investors', 'partners')),
  schedule_mode TEXT NOT NULL CHECK (schedule_mode IN ('interval', 'weekly')),
  interval_hours INTEGER NOT NULL DEFAULT 24,
  weekdays_json TEXT NOT NULL DEFAULT '[]',
  time_utc TEXT NOT NULL DEFAULT '12:00',
  message_html TEXT NOT NULL,
  promo_code_id INTEGER REFERENCES promo_codes(id),
  enabled INTEGER NOT NULL DEFAULT 1,
  last_sent_at INTEGER,
  next_run_at INTEGER NOT NULL,
  created_by INTEGER NOT NULL,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);
```

For `kind=promo`, require `promo_code_id`; substitute placeholders before `create_broadcast(actor_id, message, audience)`.

- [ ] **Step 3: CampaignService**

```python
class CampaignService:
    def __init__(self, repository: DeltaRepository) -> None:
        self.repository = repository

    async def tick(self) -> int:
        due = await self.repository.claim_due_campaigns(int(time.time()))
        sent = 0
        for row in due:
            result = await self.repository.dispatch_campaign(int(row["id"]))
            if result.get("broadcast_id"):
                sent += 1
        return sent

    async def run_forever(self) -> None:
        while True:
            try:
                await self.tick()
            except Exception:
                logger.exception("campaign tick failed")
            await asyncio.sleep(45)
```

Wire in `api.py` lifespan next to BroadcastService:

```python
campaign_service = CampaignService(repository)
asyncio.create_task(campaign_service.run_forever(), name="campaigns")
```

- [ ] **Step 4: PASS + commit**

```bash
python -m pytest tests/test_campaigns.py -v
git add delta_backend/repository.py delta_backend/services/campaigns.py delta_backend/api.py tests/test_campaigns.py
git commit -m "feat: scheduled campaigns worker and repository"
```

---

### Task 5: Admin campaigns HTTP API

**Files:**
- Modify: `delta_backend/api.py`
- Test: `tests/test_campaigns_api.py`

**Routes:**
- `GET /api/admin/campaigns`
- `POST /api/admin/campaigns`
- `PATCH /api/admin/campaigns/{id}`
- `POST /api/admin/campaigns/{id}/run` → `dispatch_campaign(..., force=True)`

Request model includes `kind`, `audience`, `schedule_mode`, `interval_hours`, `weekdays`, `time_utc`, `message_html`, `promo_code_id`, `enabled`.

Sanitize message with existing broadcast HTML sanitizer used by create_broadcast.

- [ ] **Step 1–4:** TDD create/list/patch/run; non-admin 403; commit

```bash
git commit -m "feat: admin campaigns HTTP API"
```

---

### Task 6: Mini App — deposit promo field + admin «Кампании» tab

**Files:**
- Modify: `frontend/index.html`
- Modify: `frontend/assets/app.js`
- Bump `app.js?v=` cache string

**Deposit UX**
- Add input `#depositPromoCode` near amount on deposit view.
- On create invoice POST body include `promo_code` if non-empty.
- Show toast/preview from response `bonus_usdt` / `effective_principal_usdt` when present.
- i18n ru/en at minimum: `promoCode`, `promoApplied`, `promoInvalid`.

**Admin UX**
- New tab button `data-admin-tab="campaigns"` label «Кампании».
- Section `#admin-campaigns` with two panels: promo list/form + campaign list/form (reuse panel/form-card patterns from broadcasts).
- Load via `GET /api/admin/promo-codes` and `GET /api/admin/campaigns`.
- Create promo / toggle enabled; create campaign / toggle / run now.

Keep one-shot broadcasts tab intact.

- [ ] **Step 1:** Implement HTML + JS (no automated browser test required).
- [ ] **Step 2:** Manual checklist in commit message body optional.
- [ ] **Step 3: Commit**

```bash
git add frontend/index.html frontend/assets/app.js
git commit -m "feat: Mini App promo field and admin campaigns tab"
```

---

### Task 7: Verification

- [ ] **Step 1: Run focused suites**

```bash
python -m pytest tests/test_promo_codes.py tests/test_promo_api.py tests/test_campaigns.py tests/test_campaigns_api.py tests/test_broadcast_api.py tests/test_repository.py::test_deposit_and_referral_payouts_are_idempotent -v --tb=short
```

Expected: all PASS.

- [ ] **Step 2: Spec coverage self-check**

| Spec item | Task |
|-----------|------|
| Promo percent/fixed → principal | 2 |
| 1/user + global limit | 2 |
| Bonus from base_minor | 2 |
| Reject over max deposit | 2 |
| Campaigns interval/weekly | 4 |
| Promo placeholders + skip exhausted | 4 |
| Admin UI + deposit field | 6 |
| Existing broadcasts still work | 7 |

- [ ] **Step 3: Commit only if test-only fixes remain**

---

## Spec coverage checklist

- Unified campaigns module — Tasks 4–6  
- Promo CRUD + deposit bonus into principal — Tasks 1–3, 6  
- Flexible schedule — Task 4  
- Reuse broadcast delivery — Task 4 (`create_broadcast`)  
- Non-goals respected — no per-user codes, no Team changes  

## Placeholder scan

None intentional. Implementers must use the SQL/API shapes above; adapt only for existing lock/`transaction()` style in `repository.py`.
