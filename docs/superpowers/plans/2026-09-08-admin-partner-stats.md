# Admin Partner Stats Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** In the admin user modal «Партнёрка» tab, show the selected user’s partner summary and each direct partner’s personal + structure turnover (all deposits, tree depth 5, structure excludes self).

**Architecture:** Extend `DeltaRepository.admin_user_detail` to attach `partner_stats` (reuse `team()` stats) and enrich `partners[]` with turnover fields via one recursive CTE rooted at the user. `GET /api/admin/users/{id}` already returns that payload. Update Mini App `renderAdminUserModal` referral panel only.

**Tech Stack:** Python / aiosqlite (`delta_backend`), pytest, vanilla JS Mini App (`frontend/assets/app.js`).

**Spec:** `docs/superpowers/specs/2026-09-08-admin-partner-stats-design.md`

## Global Constraints

- Admin-only; no changes to user Team UI or `/api/team` contract beyond what `team()` already returns.
- Personal turnover = sum of **all** deposit principals for the partner.
- Structure turnover = sum of **all** deposit principals in partner’s downline levels 1–5; **exclude** partner’s own deposits.
- Partner list sorted by `structure_turnover_minor` DESC, then `personal_turnover_minor` DESC; limit 100.
- No new HTTP routes.
- Do not make the repository public or add yield-marketing copy.

## File map

| File | Responsibility |
|------|----------------|
| `delta_backend/repository.py` | Enrich `admin_user_detail` with `partner_stats` + partner turnovers |
| `tests/test_repository.py` | Repository assertions for turnovers / exclusion of self |
| `frontend/assets/app.js` | Render summary + enriched partner rows; navigate on click; i18n |
| `frontend/index.html` or cache-bust only if `app.js` query version exists | Bump `?v=` if present |

---

### Task 1: Repository — failing test for admin partner turnovers

**Files:**
- Modify: `tests/test_repository.py`
- Test: `tests/test_repository.py::test_admin_user_detail_includes_partner_turnovers`

**Interfaces:**
- Consumes: `DeltaRepository.admin_user_detail`, `ensure_user`, `pay_invoice` helper, `set_wallet`
- Produces: Failing test documenting expected `partner_stats` and `partners[]` fields

- [ ] **Step 1: Write the failing test**

Append to `tests/test_repository.py`:

```python
async def test_admin_user_detail_includes_partner_turnovers(tmp_path) -> None:
    business = MiniAppSettings(_env_file=None)
    repository = DeltaRepository(tmp_path / "delta.sqlite3", business)
    await repository.connect()
    try:
        # Tree: leader(10)
        #   ├─ alice(11) personal 100; her L1 bob(12) deposits 40 → alice structure 40
        #   └─ carol(13) personal 25; no downline → structure 0
        await repository.ensure_user(10, "leader", "Leader", "ru")
        await repository.set_wallet(10, WALLET_ONE)
        await repository.ensure_user(11, "alice", "Alice", "ru", referrer_id=10)
        await repository.set_wallet(11, WALLET_TWO)
        await repository.ensure_user(12, "bob", "Bob", "ru", referrer_id=11)
        await repository.set_wallet(12, "0x0000000000000000000000000000000000000003")
        await repository.ensure_user(13, "carol", "Carol", "ru", referrer_id=10)
        await repository.set_wallet(13, "0x0000000000000000000000000000000000000004")

        await pay_invoice(repository, 11, "100", 11)
        await pay_invoice(repository, 12, "40", 12)
        await pay_invoice(repository, 13, "25", 13)

        detail = await repository.admin_user_detail(10)
        assert "partner_stats" in detail
        stats = detail["partner_stats"]
        assert int(stats["team_count"]) >= 2
        assert "earned_minor" in stats
        assert "available_minor" in stats
        assert "line_minor" in stats
        assert "current_level" in stats

        partners = {int(p["telegram_id"]): p for p in detail["partners"]}
        assert set(partners) == {11, 13}

        alice = partners[11]
        assert int(alice["personal_turnover_minor"]) == usdt_to_minor("100")
        assert int(alice["structure_turnover_minor"]) == usdt_to_minor("40")
        assert int(alice["structure_member_count"]) == 1
        # Partner's own deposit must not inflate structure turnover
        assert int(alice["structure_turnover_minor"]) != int(alice["personal_turnover_minor"])

        carol = partners[13]
        assert int(carol["personal_turnover_minor"]) == usdt_to_minor("25")
        assert int(carol["structure_turnover_minor"]) == 0
        assert int(carol["structure_member_count"]) == 0

        ordered_ids = [int(p["telegram_id"]) for p in detail["partners"]]
        assert ordered_ids[0] == 11  # higher structure turnover first
    finally:
        await repository.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run from `GFORT_CURSOR_READY_PROJECT`:

```bash
python -m pytest tests/test_repository.py::test_admin_user_detail_includes_partner_turnovers -v
```

Expected: FAIL (`partner_stats` missing and/or partners lack turnover fields).

- [ ] **Step 3: Commit**

```bash
git add tests/test_repository.py
git commit -m "test: expect admin partner turnover fields on user detail"
```

---

### Task 2: Repository — implement partner_stats + enriched partners

**Files:**
- Modify: `delta_backend/repository.py` (`admin_user_detail`)
- Test: `tests/test_repository.py::test_admin_user_detail_includes_partner_turnovers`

**Interfaces:**
- Consumes: existing `team(user_id)` for summary stats
- Produces: `admin_user_detail` adds:
  - `partner_stats: dict` with keys from `team()["stats"]` needed by UI (`earned_minor`, `today_minor`, `available_minor`, `personal_minor`, `line_minor`, `team_count`, `current_level`, `levels_total`)
  - `partners: list[dict]` each with `telegram_id`, `username`, `first_name`, `created_at`, `personal_turnover_minor`, `structure_turnover_minor`, `structure_member_count`, `deposit_count`

- [ ] **Step 1: Replace the bare partners query inside `admin_user_detail`**

In `delta_backend/repository.py`, inside `admin_user_detail`, replace:

```python
cursor = await connection.execute(
    "SELECT telegram_id, username, first_name, created_at FROM users "
    "WHERE referrer_id = ? ORDER BY created_at DESC LIMIT 100",
    (user_id,),
)
partners = [dict(row) for row in await cursor.fetchall()]
```

with a query that computes personal + structure metrics for direct partners only, for example:

```python
cursor = await connection.execute(
    """
    WITH RECURSIVE tree(root_id, telegram_id, depth) AS (
        SELECT u.telegram_id AS root_id, u.telegram_id, 0
        FROM users AS u
        WHERE u.referrer_id = ?
        UNION ALL
        SELECT tree.root_id, child.telegram_id, tree.depth + 1
        FROM users AS child
        JOIN tree ON child.referrer_id = tree.telegram_id
        WHERE tree.depth < 5
    ),
    personal AS (
        SELECT user_id, COALESCE(SUM(principal_minor), 0) AS personal_turnover_minor,
               COUNT(id) AS deposit_count
        FROM deposits
        GROUP BY user_id
    ),
    structure AS (
        SELECT tree.root_id,
               COALESCE(SUM(CASE WHEN tree.depth > 0 THEN deposits.principal_minor ELSE 0 END), 0)
                 AS structure_turnover_minor,
               COUNT(DISTINCT CASE WHEN tree.depth > 0 THEN tree.telegram_id END)
                 AS structure_member_count
        FROM tree
        LEFT JOIN deposits ON deposits.user_id = tree.telegram_id
        GROUP BY tree.root_id
    )
    SELECT u.telegram_id, u.username, u.first_name, u.created_at,
           COALESCE(personal.personal_turnover_minor, 0) AS personal_turnover_minor,
           COALESCE(personal.deposit_count, 0) AS deposit_count,
           COALESCE(structure.structure_turnover_minor, 0) AS structure_turnover_minor,
           COALESCE(structure.structure_member_count, 0) AS structure_member_count
    FROM users AS u
    LEFT JOIN personal ON personal.user_id = u.telegram_id
    LEFT JOIN structure ON structure.root_id = u.telegram_id
    WHERE u.referrer_id = ?
    ORDER BY structure_turnover_minor DESC, personal_turnover_minor DESC, u.created_at DESC
    LIMIT 100
    """,
    (user_id, user_id),
)
partners = [dict(row) for row in await cursor.fetchall()]
```

Notes:
- `depth = 0` is the direct partner (root of each subtree); structure sums only `depth > 0`.
- Keep the rest of `admin_user_detail` intact.

- [ ] **Step 2: Attach `partner_stats` before return**

After building the existing return dict fields (still inside the method, after locks as needed), call:

```python
team_payload = await self.team(user_id)
team_stats = dict(team_payload.get("stats") or {})
partner_stats = {
    "earned_minor": int(team_stats.get("earned_minor") or 0),
    "today_minor": int(team_stats.get("today_minor") or 0),
    "available_minor": int(team_stats.get("available_minor") or 0),
    "personal_minor": int(team_stats.get("personal_minor") or 0),
    "line_minor": int(team_stats.get("line_minor") or 0),
    "team_count": int(team_stats.get("team_count") or 0),
    "current_level": int(team_stats.get("current_level") or 0),
    "levels_total": int(team_stats.get("levels_total") or 5),
}
```

Add `"partner_stats": partner_stats` to the returned dict (alongside existing `"partners": partners`).

If calling `team()` while holding `_lock` deadlocks, release locks first then call `team()` (it takes the lock itself). Prefer: finish existing locked sections, then `team()`, then return.

- [ ] **Step 3: Run the new test and related admin detail tests**

```bash
python -m pytest tests/test_repository.py::test_admin_user_detail_includes_partner_turnovers tests/test_repository.py::test_admin_referral_controls_are_audited_and_withdrawable -v
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add delta_backend/repository.py tests/test_repository.py
git commit -m "feat: admin user detail partner stats and turnovers"
```

---

### Task 3: Mini App — render summary and partner turnovers

**Files:**
- Modify: `frontend/assets/app.js` (`renderAdminUserModal`, i18n blocks for `ru`/`en` admin strings)
- Optionally bump cache-bust query on `app.js` in `frontend/index.html` if a `?v=` query is already used

**Interfaces:**
- Consumes: `d.partner_stats`, `d.partners[]` fields from Task 2
- Produces: Updated referral tab UI; partner row click → `openAdminUser(id)`

- [ ] **Step 1: Add i18n keys (ru + en at minimum)**

In the admin i18n objects in `frontend/assets/app.js`, add keys such as:

```javascript
partnerStatsTitle: 'Партнёрская сводка', // en: 'Partner summary'
personalTurnover: 'Личный оборот',       // en: 'Personal turnover'
structureTurnover: 'Оборот структуры',   // en: 'Structure turnover'
structureMembers: 'В структуре',         // en: 'In structure'
```

Reuse existing keys where present (`referralIncome`, `todayEarned`, `lineTurnover`, `inTeam`, `levelsUnlocked`, `yourInvestments`, `availableToWithdraw`).

- [ ] **Step 2: Update `partnerRows` and `referralBody` in `renderAdminUserModal`**

Replace the current partnerRows mapping (~line with `partners.slice(0,30)` name-only cards) with:

```javascript
const ps = d.partner_stats || {};
const partnerSummary = `
  <div class="modal-section">
    <h4>${esc(tr('partnerStatsTitle'))}</h4>
    <div class="detail-row"><span>${esc(tr('referralIncome'))}</span><strong class="money">${money(ps.earned_minor)} USDT</strong></div>
    <div class="detail-row"><span>${esc(tr('todayEarned'))}</span><strong class="money">+${money(ps.today_minor)} USDT</strong></div>
    <div class="detail-row"><span>${esc(tr('availableToWithdraw'))}</span><strong class="money">${money(ps.available_minor)} USDT</strong></div>
    <div class="detail-row"><span>${esc(tr('yourInvestments'))}</span><strong class="money">${money(ps.personal_minor)} USDT</strong></div>
    <div class="detail-row"><span>${esc(tr('lineTurnover'))}</span><strong class="money">${money(ps.line_minor)} USDT</strong></div>
    <div class="detail-row"><span>${esc(tr('inTeam'))}</span><strong>${esc(ps.team_count||0)}</strong></div>
    <div class="detail-row"><span>${esc(tr('levelsUnlocked'))}</span><strong>${esc(ps.current_level||0)}/${esc(ps.levels_total||5)}</strong></div>
  </div>`;

const partnerRows = partners.length
  ? partners.slice(0, 100).map((p) => `
    <article class="list-card compact-card">
      <button class="admin-user-btn touch-target" type="button" data-partner-id="${esc(p.telegram_id)}">
        <div class="list-card-header">
          <div>
            <strong>${esc(p.first_name||p.username||p.telegram_id)}</strong>
            <small>${p.username?'@'+esc(p.username)+' · ':''}ID ${esc(p.telegram_id)} · ${esc(fmtDate(p.created_at))}</small>
          </div>
        </div>
        <div class="detail-row"><span>${esc(tr('personalTurnover'))}</span><strong class="money">${money(p.personal_turnover_minor)} USDT</strong></div>
        <div class="detail-row"><span>${esc(tr('structureTurnover'))}</span><strong class="money">${money(p.structure_turnover_minor)} USDT</strong></div>
        <div class="detail-row"><span>${esc(tr('structureMembers'))}</span><strong>${esc(p.structure_member_count||0)}</strong></div>
      </button>
    </article>`).join('')
  : `<div class="empty-state compact">${esc(tr('noUserPartners'))}</div>`;
```

Insert `partnerSummary` at the top of `referralBody` (before balance controls). Keep balance/level controls. Keep members list at the bottom using `partnerRows`.

After rendering, bind:

```javascript
$('adminUserDetail').querySelectorAll('[data-partner-id]').forEach((btn) => {
  btn.addEventListener('click', () => {
    state.adminUserTab = 'referral';
    openAdminUser(btn.dataset.partnerId);
  });
});
```

- [ ] **Step 3: Cache bust**

If `frontend/index.html` loads `app.js?v=...`, bump the version string (e.g. `novera-admin-partner-1`).

- [ ] **Step 4: Manual sanity check**

Open Mini App as admin → Users → user with referrals → «Партнёрка»: summary visible; partners show both turnovers; click opens partner.

- [ ] **Step 5: Commit**

```bash
git add frontend/assets/app.js frontend/index.html
git commit -m "feat: show admin partner summary and turnovers in user modal"
```

---

### Task 4: Verification

**Files:** none new

- [ ] **Step 1: Run focused + smoke tests**

```bash
python -m pytest tests/test_repository.py::test_admin_user_detail_includes_partner_turnovers tests/test_admin_controls_api.py -v --tb=short
```

Expected: PASS (admin detail still returns 200; new fields present if asserted).

- [ ] **Step 2: Optional quick API assert in `test_admin_controls_api.py`**

Where `detail = await client.get(f"/api/admin/users/{USER_ID}", ...)` already exists, add:

```python
body = detail.json()
assert "partner_stats" in body
assert "partners" in body
```

Commit if added:

```bash
git add tests/test_admin_controls_api.py
git commit -m "test: admin user detail exposes partner_stats"
```

---

## Spec coverage checklist

| Spec item | Task |
|-----------|------|
| Admin referral tab summary | Task 3 |
| Personal + structure turnovers | Tasks 1–2 |
| Structure excludes self | Task 1 assert + Task 2 CTE `depth > 0` |
| Sort / limit 100 | Task 2 ORDER BY + LIMIT |
| Click partner → open card | Task 3 |
| No new routes / Team UI unchanged | All tasks |
| Tests | Tasks 1, 4 |

## Placeholder scan

None intentional. Implementers must use the SQL/JS above (adapt only for lock-ordering / style consistency with surrounding code).
