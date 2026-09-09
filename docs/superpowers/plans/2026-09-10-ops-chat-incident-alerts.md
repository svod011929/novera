# Ops chat incident alerts + test ping — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend ops chat with test ping, first failed payout, unmatched deposit, and safety alert mirrors (admin DMs unchanged).

**Architecture:** Expand `OpsChatNotifier` formatters + send helpers; repository `_schedule_ops_*` after commit (same pattern as deposit/payout); wire `SafetyMonitor` to call `notify_safety`; admin `POST /api/admin/ops-chat/test` waits for delivery; Система UI button.

**Tech Stack:** Python 3.12, aiogram Bot, FastAPI, pytest, existing Mini App admin JS

**Spec:** `docs/superpowers/specs/2026-09-10-ops-chat-incident-alerts-design.md`

## Global Constraints

- First `failed` only (`not was_failed`); skip `admin_test`
- Unmatched: new non-duplicate chain deposit with no invoice match; one alert per insert
- Safety: keep `_send_admin` LMs; additionally mirror `_alert_text` HTML to ops
- Telegram failures never roll back money / safety loop
- Ops target resolve: DB overrides env (existing `get_ops_chat_settings`)
- RU HTML templates exactly as in the spec
- No new notifier class; no Safety-loop ownership of failed/unmatched

## File map

| File | Responsibility |
|------|----------------|
| `delta_backend/services/ops_chat.py` | Formatters + `notify_failed_payout` / `notify_unmatched` / `notify_safety` / `send_test` |
| `tests/test_ops_chat.py` | Formatter + truncate/escape tests |
| `delta_backend/repository.py` | `_schedule_ops_failed_payout`, `_schedule_ops_unmatched`; hooks in `mark_payout_failed` / `apply_transfer` |
| `delta_backend/services/safety.py` | Optional `ops_chat` ref; mirror in `_publish_transitions` |
| `delta_backend/api.py` | Pass ops into SafetyMonitor; `POST /api/admin/ops-chat/test` |
| `frontend/assets/app.js` | Test button + i18n |
| `frontend/index.html` | Cache bust `app.js?v=` |

---

### Task 1: Incident formatters + unit tests

**Files:**
- Modify: `delta_backend/services/ops_chat.py`
- Test: `tests/test_ops_chat.py`

**Interfaces:**
- Produces:
  - `format_failed_payout_ops_html(*, telegram_id, username, first_name, amount_minor, payout_id, kind, subtype, error) -> str`
  - `format_unmatched_ops_html(*, amount_minor, chain_deposit_id, tx_hash, explorer_template=...) -> str`
  - `format_ops_test_html(*, source: str, chat_id: int, topic_id: int | None) -> str`
  - error truncated to ≤200 chars after strip, then `html.escape`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_ops_chat.py`:

```python
from delta_backend.services.ops_chat import (
    format_failed_payout_ops_html,
    format_ops_test_html,
    format_unmatched_ops_html,
)


def test_format_failed_payout_escapes_and_truncates_error() -> None:
    text = format_failed_payout_ops_html(
        telegram_id=7,
        username="bob",
        first_name=None,
        amount_minor=usdt_to_minor("2"),
        payout_id=55,
        kind="daily",
        subtype=None,
        error="<boom>" + ("x" * 300),
    )
    assert "Выплата не прошла" in text
    assert "@bob" in text
    assert "Выплата #55" in text
    assert "<boom>" not in text
    assert "&lt;boom&gt;" in text
    assert len([line for line in text.splitlines() if line.startswith("❗️")][0]) < 220


def test_format_unmatched_includes_explorer() -> None:
    text = format_unmatched_ops_html(
        amount_minor=usdt_to_minor("10"),
        chain_deposit_id=3,
        tx_hash="0xabc",
    )
    assert "Несопоставленный депозит" in text
    assert "Chain deposit #3" in text or "Chain deposit #3" in text.replace(" ", "")
    assert "bscscan.com/tx/0xabc" in text
    assert "админ" not in text.lower()


def test_format_ops_test_html() -> None:
    text = format_ops_test_html(source="database", chat_id=-1001, topic_id=42)
    assert "Ops-чат: тест" in text
    assert "database" in text
    assert "-1001" in text
    assert "42" in text
```

(Use the exact unmatched line from the spec: `📦 Chain deposit #{id}`.)

- [ ] **Step 2: Run tests — expect FAIL**

Run: `python -m pytest tests/test_ops_chat.py::test_format_failed_payout_escapes_and_truncates_error tests/test_ops_chat.py::test_format_unmatched_includes_explorer tests/test_ops_chat.py::test_format_ops_test_html -q`
Expected: FAIL (import / missing functions)

- [ ] **Step 3: Implement formatters in `ops_chat.py`**

```python
def _truncate_error(error: str, limit: int = 200) -> str:
    clean = str(error or "").strip().replace("\n", " ")
    if len(clean) <= limit:
        return clean
    return clean[: max(0, limit - 1)] + "…"


def format_failed_payout_ops_html(
    *,
    telegram_id: int,
    username: str | None,
    first_name: str | None,
    amount_minor: int,
    payout_id: int,
    kind: str,
    subtype: str | None = None,
    error: str,
) -> str:
    user_line = format_user_line(
        telegram_id=telegram_id, username=username, first_name=first_name
    )
    amount = html.escape(minor_to_text(int(amount_minor)))
    label = html.escape(payout_kind_label(kind, subtype))
    err = html.escape(_truncate_error(error))
    return "\n".join(
        [
            f"⚠️ <b>Выплата не прошла</b> · {label}",
            f"👤 {user_line} · <code>{int(telegram_id)}</code>",
            f"💰 Сумма: <b>{amount} USDT</b>",
            f"📦 Выплата #{int(payout_id)}",
            f"❗️ {err}",
        ]
    )


def format_unmatched_ops_html(
    *,
    amount_minor: int,
    chain_deposit_id: int,
    tx_hash: str,
    explorer_template: str = "https://bscscan.com/tx/{tx_hash}",
) -> str:
    amount = html.escape(minor_to_text(int(amount_minor)))
    clean_tx = str(tx_hash).strip()
    url = html.escape(explorer_tx_url(explorer_template, clean_tx))
    return "\n".join(
        [
            "❓ <b>Несопоставленный депозит</b>",
            f"💰 Сумма: <b>{amount} USDT</b>",
            f"📦 Chain deposit #{int(chain_deposit_id)}",
            f'🔗 <a href="{url}">Транзакция</a>',
        ]
    )


def format_ops_test_html(
    *, source: str, chat_id: int, topic_id: int | None
) -> str:
    topic = "—" if topic_id is None else str(int(topic_id))
    return "\n".join(
        [
            "🧪 <b>Ops-чат: тест</b>",
            f"Источник: {html.escape(str(source))}",
            f"Chat: <code>{int(chat_id)}</code>",
            f"Topic: <code>{html.escape(topic)}</code>",
        ]
    )
```

- [ ] **Step 4: Run tests — expect PASS**

Run: `python -m pytest tests/test_ops_chat.py -q`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add delta_backend/services/ops_chat.py tests/test_ops_chat.py
git commit -m "feat: ops chat formatters for failed, unmatched, and test"
```

---

### Task 2: Notifier methods (failed / unmatched / safety / send_test)

**Files:**
- Modify: `delta_backend/services/ops_chat.py`

**Interfaces:**
- Consumes: formatters from Task 1; existing `resolve_target` / `_send`
- Produces:
  - `async notify_failed_payout(...) -> None` (fire-and-forget style via `_send`)
  - `async notify_unmatched(...) -> None`
  - `async notify_safety(text: str) -> None` — sends prebuilt HTML as-is via `_send(..., preview=False)`
  - `async send_test() -> dict[str, object]` — **awaits** delivery; returns `{ok, chat_id, topic_id, source, detail?}`

Refactor lightly: extract `_send_to(chat_id, topic_id, text, *, preview) -> None` that raises on Telegram errors after one RetryAfter retry; keep `_send` swallowing errors for fire-and-forget; `send_test` uses raising path.

- [ ] **Step 1: Add methods on `OpsChatNotifier`**

```python
async def notify_failed_payout(self, *, telegram_id, username, first_name,
                               amount_minor, payout_id, kind, subtype=None, error="") -> None:
    text = format_failed_payout_ops_html(...)
    await self._send(text, preview=False)

async def notify_unmatched(self, *, amount_minor, chain_deposit_id, tx_hash) -> None:
    text = format_unmatched_ops_html(
        ..., explorer_template=self.settings.block_explorer_tx_url
    )
    await self._send(text, preview=False)

async def notify_safety(self, text: str) -> None:
    await self._send(str(text), preview=False)

async def send_test(self) -> dict[str, object]:
    env_chat = env_ops_chat_id(self.settings)
    env_topic = env_ops_topic_id(self.settings)
    if self.repository is None:
        cfg = {
            "active": env_chat is not None,
            "chat_id": env_chat,
            "topic_id": env_topic,
            "source": "env" if env_chat is not None else "none",
        }
    else:
        cfg = await self.repository.get_ops_chat_settings(
            env_chat_id=env_chat, env_topic_id=env_topic
        )
    if not cfg.get("active") or cfg.get("chat_id") is None:
        return {
            "ok": False,
            "chat_id": None,
            "topic_id": None,
            "source": cfg.get("source", "none"),
            "detail": "Ops chat is not active",
        }
    chat_id = int(cfg["chat_id"])
    topic_id = None if cfg.get("topic_id") is None else int(cfg["topic_id"])
    text = format_ops_test_html(
        source=str(cfg.get("source") or "none"),
        chat_id=chat_id,
        topic_id=topic_id,
    )
    try:
        await self._send_raising(chat_id, topic_id, text, preview=False)
    except Exception as exc:
        return {
            "ok": False,
            "chat_id": chat_id,
            "topic_id": topic_id,
            "source": cfg.get("source"),
            "detail": type(exc).__name__,
        }
    return {
        "ok": True,
        "chat_id": chat_id,
        "topic_id": topic_id,
        "source": cfg.get("source"),
    }
```

Implement `_send_raising` mirroring `_send` kwargs (`message_thread_id` when topic set) but re-raise after one RetryAfter sleep.

- [ ] **Step 2: Smoke-import**

Run: `python -c "from delta_backend.services.ops_chat import OpsChatNotifier; print('ok')"`
Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add delta_backend/services/ops_chat.py
git commit -m "feat: ops notifier methods for incidents and test ping"
```

---

### Task 3: Repository schedules + hooks (failed + unmatched)

**Files:**
- Modify: `delta_backend/repository.py` (near `_schedule_ops_payout`, `mark_payout_failed`, `apply_transfer`)
- Test: `tests/test_ops_chat.py` (lightweight schedule gate tests with a fake notifier)

**Interfaces:**
- Produces: `_schedule_ops_failed_payout(**kwargs)`, `_schedule_ops_unmatched(**kwargs)` — same `create_task` pattern as deposit
- `mark_payout_failed`: after transaction, if first fail && !admin_test, schedule with user username/first_name (JOIN users in SELECT)
- `apply_transfer`: do **not** `return` early inside the transaction for unmatched; set `ops_unmatched` payload + result, exit `async with`, then schedule, then return

Critical `apply_transfer` reshape (conceptual):

```python
ops_unmatched: dict[str, object] | None = None
unmatched_result: dict[str, object] | None = None
async with self.transaction() as connection:
    ...
    except aiosqlite.IntegrityError:
        return {"duplicate": True, "matched": False}  # still OK: no insert
    ...
    if not invoice or not invoice["payout_address"]:
        await connection.execute(... audit unmatched_deposit ...)
        ops_unmatched = {
            "amount_minor": int(transfer.amount_minor),
            "chain_deposit_id": int(chain_deposit_id),
            "tx_hash": str(transfer.tx_hash),
        }
        unmatched_result = {"duplicate": False, "matched": False}
    else:
        ... existing match path ...
if ops_deposit is not None:
    self._schedule_ops_deposit(**ops_deposit)
if ops_unmatched is not None:
    self._schedule_ops_unmatched(**ops_unmatched)
if matched_result is not None:
    return matched_result
if unmatched_result is not None:
    return unmatched_result
return {"duplicate": False, "matched": False}
```

`mark_payout_failed`:

```python
ops_failed: dict[str, object] | None = None
async with self.transaction() as connection:
    cursor = await connection.execute(
        """
        SELECT payouts.*, users.username, users.first_name
        FROM payouts
        LEFT JOIN users ON users.telegram_id = payouts.user_id
        WHERE payouts.id = ?
        """,
        (payout_id,),
    )
    ...
    if not was_failed and int(payout["admin_test"] or 0) == 0:
        ... existing user notification ...
        ops_failed = {
            "telegram_id": int(payout["user_id"]),
            "username": ...,
            "first_name": ...,
            "amount_minor": int(payout["amount_minor"]),
            "payout_id": int(payout_id),
            "kind": str(payout["kind"] or ""),
            "subtype": None if payout["subtype"] is None else str(payout["subtype"]),
            "error": error[:1000],
        }
if ops_failed is not None:
    self._schedule_ops_failed_payout(**ops_failed)
```

- [ ] **Step 1: Write failing schedule tests**

```python
@pytest.mark.asyncio
async def test_mark_payout_failed_schedules_ops_once(tmp_path, monkeypatch) -> None:
    # setup MiniAppSettings + DeltaRepository + user + queued payout (non-admin_test)
    # attach fake notifier recording notify_failed_payout calls
    # call mark_payout_failed twice with same id
    # assert len(calls) == 1
```

Use existing test helpers from `tests/test_admin_controls_api.py` patterns or create payout via SQL insert matching schema. Keep minimal: insert user + payout row `status='queued'`, `admin_test=0`.

- [ ] **Step 2: Implement schedules + hooks**

- [ ] **Step 3: Run**

Run: `python -m pytest tests/test_ops_chat.py -q`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add delta_backend/repository.py tests/test_ops_chat.py
git commit -m "feat: schedule ops alerts for failed payouts and unmatched deposits"
```

---

### Task 4: SafetyMonitor mirror + lifespan wire

**Files:**
- Modify: `delta_backend/services/safety.py`
- Modify: `delta_backend/api.py` (SafetyMonitor construction)

**Interfaces:**
- `SafetyMonitor.__init__(..., ops_chat: OpsChatNotifier | None = None)`
- In `_publish_transitions`, after each `await self._send_admin(...)`, also:

```python
if self.ops_chat is not None:
    try:
        await self.ops_chat.notify_safety(self._alert_text(code, recovered=...))
    except Exception as exc:
        logger.warning("Ops safety mirror failed: %s", type(exc).__name__)
```

Lifespan:

```python
safety_monitor = SafetyMonitor(
    repository, chain_settings, chain, bot_token,
    safety_runtime, payout_circuit, ops_chat=ops_chat,
)
```

- [ ] **Step 1: Implement optional ops_chat + mirror calls**
- [ ] **Step 2: Wire lifespan**
- [ ] **Step 3: Commit**

```bash
git add delta_backend/services/safety.py delta_backend/api.py
git commit -m "feat: mirror safety alerts into ops chat"
```

---

### Task 5: Admin test API + Система UI

**Files:**
- Modify: `delta_backend/api.py` — `POST /api/admin/ops-chat/test`
- Modify: `frontend/assets/app.js` — button + handler + i18n keys in `OPS_CHAT_I18N`
- Modify: `frontend/index.html` — bump `app.js?v=novera-ops-chat-2`

**API:**

```python
@app.post("/api/admin/ops-chat/test")
async def admin_ops_chat_test(
    request: Request,
    user: AuthenticatedUser = Depends(admin_user),
) -> dict[str, object]:
    await enforce_mutation_limit(request, user, "ops-chat-test")
    ops: OpsChatNotifier | None = getattr(request.app.state, "ops_chat", None)
    if ops is None:
        raise HTTPException(status_code=503, detail="Ops chat notifier unavailable")
    result = await ops.send_test()
    if not result.get("ok"):
        # still 200 with ok=false so UI can toast detail without treating as transport error
        # OR 409 when inactive — prefer 200 + ok field per spec example
        return result
    return result
```

**UI:** next to Save, secondary button `opsChatTest` → `POST /api/admin/ops-chat/test` → toast success/fail from `ok`/`detail`.

- [ ] **Step 1: API endpoint**
- [ ] **Step 2: Frontend button + i18n (ru/en/uk)**
- [ ] **Step 3: Cache bust**
- [ ] **Step 4: Commit**

```bash
git add delta_backend/api.py frontend/assets/app.js frontend/index.html
git commit -m "feat: admin ops chat test ping API and UI"
```

---

### Task 6: Verify + handoff

- [ ] **Step 1: Full ops tests**

Run: `python -m pytest tests/test_ops_chat.py -q`
Expected: PASS

- [ ] **Step 2: Optional deploy** only if owner asks: `scripts/safe_update_remote.ps1 -Mode full`

- [ ] **Step 3: Manual checklist for owner**
  1. Админ → Система → сохранить Chat/Topic → «Отправить тест»
  2. Confirm message in forum topic
  3. (If possible) force unmatched / failed in staging — or wait for production events

---

## Spec coverage checklist

| Spec item | Task |
|-----------|------|
| Test ping API + UI | 5 |
| Failed first-transition | 1–3 |
| Unmatched on insert | 1–3 |
| Safety mirror + keep DMs | 4 |
| Fire-and-forget money path | 2–3 |
| Templates | 1 |
| Truncate error ≤200 | 1 |

## Self-review

- No TBD/placeholder steps
- `apply_transfer` early-return pitfall explicitly fixed in Task 3
- Method names consistent across tasks (`notify_failed_payout`, `notify_unmatched`, `notify_safety`, `send_test`)
