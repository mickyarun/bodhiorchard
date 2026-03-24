# Plan: Garden Gamification System ("Garden Seeds")

## Context

The Living Garden dashboard already has houses with interiors, 85+ character models, and presence tracking. The user wants to **gamify** the developer experience: earn currency from work activity (features shipped, bugs fixed, streaks) and spend it on house decorations, avatar unlocks, character gear, and house upgrades. This motivates consistent contributions and makes the garden feel personal.

---

## Currency: "Garden Seeds"

Earned through development activity, spent in a shop. Simple economy — no inflation mechanics, no trading.

### Earning Rules

#### Core Activity

| Event | Seeds | Trigger |
|-------|-------|---------|
| Feature completed (BUD → prod) | +50 × priority multiplier | BUD status transition |
| Bug resolved (medium) | +20 | Bug status → resolved |
| Bug resolved (high) | +30 | Bug status → resolved |
| Bug resolved (critical) | +40 | Bug status → resolved |
| Weekly commit streak (5+ days) | +100 | Daily streak check |
| Zero bugs on a feature | +25 | Feature completion check |
| Daily active (any commit/touch) | +5 | Dashboard load recalc |

#### BUD Priority & Urgency Multiplier

Feature completion seeds are multiplied based on BUD priority/urgency (new fields on BUDDocument):

| Priority | Multiplier |
|----------|------------|
| Low | ×1.0 (base 50) |
| Medium | ×1.5 (75 seeds) |
| High | ×2.0 (100 seeds) |
| Critical | ×2.5 (125 seeds) |

Urgency adds a flat bonus: `urgent` flag = +25 seeds on top.

#### Estimation Accuracy

| Event | Seeds | Trigger |
|-------|-------|---------|
| Met estimated end date (finished ≤ estimate) | +30 | BUD → prod, compare `estimated_end_date` vs `updated_at` |
| Early delivery (finished > 2 days before estimate) | +50 | Same check, stricter threshold |
| Close estimate (within ±1 day of actual) | +15 | Estimation accuracy bonus |

Requires new `estimated_end_date` (Date, nullable) field on BUDDocument.

#### Wellness & Sustainable Pace

These encourage healthy work habits using existing presence data (Slack presence cache) and commit timestamps (SkillProfile.last_touch, git commit dates).

| Event | Seeds | Trigger | Data Source |
|-------|-------|---------|-------------|
| Healthy work day (no activity after 7pm) | +10 | Daily check (next morning) | Git commit timestamps — no commits between 19:00–06:00 |
| Regular break taker (≥1 break/day during work hours) | +5 | Daily check | Presence cache — at least one `on_break` transition during 8am–6pm |
| Consistent start time (within ±30min of avg over 5 days) | +15 | Weekly check | First daily commit timestamp vs rolling average |
| No weekend work (Sat+Sun zero commits) | +20 | Monday morning check | Git commit timestamps |
| Sustainable week (avg ≤ 8hrs active/day, 5 days) | +25 | Weekly check | Presence cache — sum of `active` hours per day |

**Anti-burnout guardrail:** If a user works > 10 hours in a day (presence `active` > 10hrs), they get a ×0.5 penalty on that day's daily_active seeds and a gentle nudge in the wallet UI ("Take care of yourself!"). No negative balance — just reduced earning rate.

#### Tracking Implementation

**New `garden_activity_log` table** (lightweight daily log per user):
- `org_id`, `user_id`, `date` (unique together)
- `first_commit_at` (Time, nullable) — earliest commit timestamp that day
- `last_commit_at` (Time, nullable) — latest commit timestamp that day
- `break_count` (int) — number of `on_break` transitions
- `active_hours` (float) — total hours in `active` presence state
- `had_weekend_commits` (bool)

Populated by `refresh_all_presence()` in presence_cache.py (piggyback on existing poll loop) and by git_analyzer commit scan.

### Spending Categories

| Category | Examples | Price Range |
|----------|----------|-------------|
| House Items | Plants, pet (cat/dog), gaming setup, trophy shelf, aquarium | 25–200 |
| Avatar Unlocks | Witch, Wizard, Elf, Golden Knight | 150–300 |
| Character Gear | Hats, capes, auras, halos | 40–300 |
| House Upgrades | Wall paint, floor material, bay windows | 75–200 |

---

## Step 1: Backend Models + Migration

**New file:** `backend/app/models/garden.py`

5 tables, all following BaseModel (UUID PK, TimestampMixin, org_id FK):

### `garden_wallets` — one per user
- `org_id`, `user_id` (unique together)
- `balance` (int, default 0)
- `lifetime_earned`, `lifetime_spent` (int)
- `current_streak_days`, `longest_streak_days` (int)
- `last_active_date` (Date, nullable)
- `wellness_score` (int, default 0) — rolling 7-day wellness points (for UI display)

### `garden_transactions` — immutable ledger
- `org_id`, `user_id`, `amount` (+earn / -spend)
- `tx_type` (String 50): feature_completed, bug_resolved, streak_bonus, daily_active, zero_bugs_bonus, estimation_bonus, priority_bonus, healthy_day, regular_breaks, consistent_start, no_weekend_work, sustainable_week, shop_purchase
- `reference_id` (UUID, nullable) — FK to source (BUD, bug, shop item)
- `description` (String 500)
- Index on `(org_id, user_id, created_at)`

### `garden_activity_log` — daily wellness tracking
- `org_id`, `user_id`, `date` (unique together)
- `first_commit_at` (Time, nullable)
- `last_commit_at` (Time, nullable)
- `break_count` (int, default 0)
- `active_hours` (float, default 0.0)
- `had_weekend_commits` (bool, default false)
- `wellness_credited` (bool, default false) — idempotency flag

### `garden_shop_items` — catalog
- `org_id` (nullable — NULL = global items)
- `category` (String 50): house_item, avatar_unlock, character_gear, house_upgrade
- `item_key` (String 100, unique) — e.g. "plant_fern", "avatar_witch"
- `display_name`, `description`, `price`, `rarity` (common/uncommon/rare/legendary)
- `asset_ref` (String 200) — builder method key or GLB filename
- `is_active`, `sort_order`

### `garden_inventory` — user's owned items
- `org_id`, `user_id`, `item_id` (FK shop_items)
- `equipped` (bool) — for gear/avatars
- `placement` (JSON, nullable) — `{x, z, rotation}` for house items
- Unique on `(user_id, item_id)`

**Modify:** `backend/app/models/bud.py` — add 3 new fields to BUDDocument:
- `priority` (String 20, nullable, default "medium") — low / medium / high / critical
- `urgency` (bool, default False) — urgent flag for +25 flat bonus
- `estimated_end_date` (Date, nullable) — target delivery date for estimation accuracy bonus

**Modify:** `backend/app/schemas/bud.py` — add `priority`, `urgency`, `estimated_end_date` to BUDCreate, BUDUpdate, BUDRead

**Migration:** `backend/alembic/versions/s9b0c1d2e3_add_garden_gamification.py`
- Creates all 5 garden tables
- Adds `priority`, `urgency`, `estimated_end_date` columns to `bud_documents`
- Seeds ~30 shop items (12 house items, 7 avatars, 7 gear, 6 house upgrades)

**Modify:** `backend/app/models/__init__.py` — add garden model imports

---

## Step 2: Backend Repository + Schemas

**New file:** `backend/app/repositories/garden.py`

Extends `BaseRepository`. Key methods:
- `get_or_create_wallet(user_id)` — idempotent
- `credit(user_id, amount, tx_type, reference_id, description)` — atomic: insert tx + update balance
- `debit(user_id, amount, tx_type, reference_id, description)` — with `SELECT ... FOR UPDATE` to prevent negative balance
- `list_shop_items(category?)` — catalog query (global + org-specific)
- `get_inventory(user_id)` — user's items
- `add_to_inventory(user_id, item_id)` — purchase record
- `has_item(user_id, item_id)` — ownership check
- `update_placement(inventory_id, placement)` — move furniture
- `toggle_equipped(inventory_id, equipped)` — equip/unequip
- `get_leaderboard(limit=10)` — top earners by lifetime_earned

**New file:** `backend/app/schemas/garden.py`

Pydantic v2 schemas with `from_attributes = True`:
- `WalletRead` — balance, streaks, lifetime stats
- `TransactionRead` — ledger entry
- `ShopItemRead` — catalog item
- `InventoryItemRead` — owned item with placement
- `PurchaseRequest` — `{item_id: UUID}`
- `PlacementUpdate` — `{placement: dict}`
- `EquipRequest` — `{equipped: bool}`

**Modify:** `backend/app/repositories/__init__.py` — add import

---

## Step 3: Backend Earnings Service

**New file:** `backend/app/services/garden_earnings.py`

### Constants
```python
# Core activity
SEEDS_FEATURE_BASE = 50
SEEDS_BUG_MEDIUM = 20
SEEDS_BUG_HIGH = 30
SEEDS_BUG_CRITICAL = 40
SEEDS_STREAK_WEEKLY = 100
SEEDS_ZERO_BUGS_BONUS = 25
SEEDS_DAILY_ACTIVE = 5

# Priority multipliers
PRIORITY_MULTIPLIER = {"low": 1.0, "medium": 1.5, "high": 2.0, "critical": 2.5}
SEEDS_URGENCY_BONUS = 25

# Estimation accuracy
SEEDS_MET_ESTIMATE = 30
SEEDS_EARLY_DELIVERY = 50   # finished > 2 days before estimate
SEEDS_CLOSE_ESTIMATE = 15   # within ±1 day of actual

# Wellness
SEEDS_HEALTHY_DAY = 10       # no commits after 7pm
SEEDS_REGULAR_BREAKS = 5     # ≥1 break during work hours
SEEDS_CONSISTENT_START = 15  # weekly: first commit within ±30min of avg
SEEDS_NO_WEEKEND_WORK = 20   # zero commits on Sat+Sun
SEEDS_SUSTAINABLE_WEEK = 25  # avg ≤ 8hrs active/day over 5 weekdays
```

### Functions

**Core earnings (existing plan):**
- `credit_event(db, org_id, user_id, tx_type, reference_id, description)` — idempotent (checks `reference_id` not already credited)
- `recalculate_streak(db, org_id, user_id)` — compare `last_active_date` vs today, update streak counters, issue streak_bonus at 5+ days
- `calculate_pending_earnings(db, org_id, user_id)` — batch catch-up: scan uncredited features + bugs, issue daily_active

**Feature completion with multiplier:**
- `credit_feature_completed(db, org_id, user_id, bud)` — reads `bud.priority` → applies `PRIORITY_MULTIPLIER`, adds `SEEDS_URGENCY_BONUS` if `bud.urgency`, checks `estimated_end_date` vs `bud.updated_at` for estimation bonuses

**Wellness (new):**
- `record_daily_activity(db, org_id, user_id, commit_times: list[datetime])` — upserts `garden_activity_log` row for today: first/last commit, detects after-hours work
- `credit_daily_wellness(db, org_id, user_id, date)` — called next morning: checks activity_log for healthy_day (no commits after 19:00), regular_breaks (break_count > 0). Idempotent via `wellness_credited` flag.
- `credit_weekly_wellness(db, org_id, user_id)` — called Monday: checks consistent start time (stddev of `first_commit_at` over 5 days ≤ 30min), no weekend work, sustainable week (avg `active_hours` ≤ 8). Updates `wellness_score` on wallet.

### Trigger Points
- **On dashboard load:** `calculate_pending_earnings()` + `credit_daily_wellness()` called per member in `tree_data.py` `_collect_members()` (piggybacks on 5-min TTL cache)
- **On BUD transition to prod:** hook in `feature_lifecycle.py` → `credit_feature_completed()` with priority multiplier + estimation check
- **On bug resolution:** hook wherever bug status changes → `credit_event()` for bug_resolved
- **On presence refresh:** `refresh_all_presence()` in presence_cache.py updates `garden_activity_log.break_count` and `active_hours` as a side-effect
- **Weekly cron (Monday 9am):** `credit_weekly_wellness()` for all active users — consistent start, no weekend work, sustainable week

---

## Step 4: Backend API

**New file:** `backend/app/api/v1/garden.py`

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/garden/wallet` | Current user's wallet |
| GET | `/garden/transactions?limit=20&offset=0` | Paginated history |
| GET | `/garden/shop?category=house_item` | Catalog (filterable) |
| POST | `/garden/purchase` | Buy item (debit + inventory) |
| GET | `/garden/inventory` | User's owned items |
| PUT | `/garden/inventory/{id}/placement` | Move house furniture |
| PUT | `/garden/inventory/{id}/equip` | Toggle gear/avatar equipped |
| GET | `/garden/leaderboard` | Top 10 earners |

**Modify:** `backend/app/api/router.py` — include garden router
**Modify:** `backend/app/schemas/dashboard.py` — add `seed_balance: int = 0`, `streak_days: int = 0` to `MemberActivity`
**Modify:** `backend/app/services/tree_data.py` — populate `seed_balance`/`streak_days` in `_collect_members()`

---

## Step 5: Frontend Types + Store

**New file:** `frontend/src/types/garden.ts`
- Interfaces: `GardenWallet`, `GardenTransaction`, `ShopItem`, `InventoryItem`, `LeaderboardEntry`
- Enums/constants for categories, rarities

**New file:** `frontend/src/stores/garden.ts` (Pinia)
- State: `wallet`, `shopItems`, `inventory`, `transactions`, `leaderboard`
- Actions: `fetchWallet()`, `fetchShop(category?)`, `fetchInventory()`, `purchaseItem(itemId)`, `updatePlacement(id, placement)`, `toggleEquip(id)`, `fetchLeaderboard()`

**Modify:** `frontend/src/types/dashboard.ts` — add `seed_balance?: number`, `streak_days?: number` to `MemberActivity`

---

## Step 6: Frontend Shop UI

**New file:** `frontend/src/views/garden/GardenShopView.vue` (route: `/garden-shop`)
- Tab bar: House Items | Avatars | Gear | Upgrades
- Grid of `ShopItemCard` components
- Wallet balance in header
- Purchase confirmation dialog
- "Owned" badge on purchased items

**New file:** `frontend/src/components/garden/ShopItemCard.vue`
- Preview area, name, description, price
- Rarity chip (common=grey, uncommon=green, rare=blue, legendary=purple)
- Buy button (disabled if insufficient balance or already owned)

**New file:** `frontend/src/components/garden/WalletBadge.vue`
- Seed icon + balance + streak fire icon
- Used in TreeDashboard header and shop header
- Clickable → transaction history popover

**New file:** `frontend/src/components/garden/TransactionHistory.vue`
- Scrollable list: icon, description, +/- amount, timestamp
- Green for earnings, red for spending

**New file:** `frontend/src/components/garden/LeaderboardPanel.vue`
- Top 10 earners: avatar, name, lifetime seeds, streak
- Current user highlighted

**Modify:** `frontend/src/router/index.ts` — add `/garden-shop` route
**Modify:** `frontend/src/views/dashboard/TreeDashboard.vue` — add `<WalletBadge>` in header
**Modify:** `frontend/src/components/tree/HouseDetailPanel.vue` — add seed balance display + "Customize" button linking to shop

---

## Step 7: 3D Integration — House Items

**Modify:** `frontend/src/components/tree/garden/HouseInteriorSystem.ts`

Extend `build()` to accept `inventory?: InventoryItem[]`:

1. After standard furniture, iterate `house_item` inventory items
2. Call item-specific builder per `asset_ref` key
3. Items use preset positions (MVP — no drag-and-drop)

New builder methods (same procedural THREE.js pattern as existing furniture):
- `buildPlantFern()` — pot (cylinder) + leaves (cone clusters)
- `buildPlantCactus()` — pot + green cylinder with ridges
- `buildPetCat()` — small capsule body + triangle ears + tail, curled on floor
- `buildPetDog()` — capsule body + legs + triangle ears, lying near couch
- `buildGamingSetup()` — desk + monitor (emissive) + keyboard + chair
- `buildTrophyShelf()` — wall-mounted shelf + gold/silver/bronze trophy meshes
- `buildAquarium()` — glass box (transparent) with blue water + small fish

House upgrades (wall paint, floor material) override color constants:
- Parse `asset_ref` like `wall_color_0x90CAF9` → extract hex → apply to inner wall material
- Parse `floor_color_0x3E2723` → apply to floor material

---

## Step 8: 3D Integration — Avatar Unlocks + Gear

**Modify:** `frontend/src/components/tree/garden/CharacterSystem.ts`

### Avatar Unlocks
Update `resolveCharacterModel()` signature to accept `equippedAvatar`:
```typescript
export function resolveCharacterModel(
  isAgent: boolean, userId: string,
  preference: string | null,
  equippedAvatar: string | null = null,  // from inventory
): string
```
Equipped avatar takes priority over preference.

### Character Gear
New method `applyCharacterGear(group, gearItems: string[])`:
- **Hats**: mesh (cone/cylinder) at head bone or Y=2.4
- **Capes**: animated plane behind character (sine-wave sway in update loop)
- **Halos**: torus geometry above head (emissive gold)
- **Auras**: particle ring orbiting character (reuse WaterEffect pattern)

Follows same pattern as existing `applyAgentTreatment()`.

**Modify:** `frontend/src/components/tree/garden/GardenScene.ts`
- Pass inventory data through `setData()` → `focusOnHouse()` → `HouseInteriorSystem.build()`
- Pass equipped avatar/gear per member to `CharacterSystem`

---

## Implementation Order

| Phase | Scope | Files |
|-------|-------|-------|
| **1** | Backend models + migration | `models/garden.py`, `models/bud.py`, migration, `models/__init__.py` |
| **2** | Backend repo + schemas | `repositories/garden.py`, `schemas/garden.py`, `schemas/bud.py` |
| **3** | Backend earnings service | `services/garden_earnings.py` |
| **4** | Backend API + dashboard integration | `api/v1/garden.py`, `api/router.py`, `schemas/dashboard.py`, `services/tree_data.py` |
| **5** | Backend wellness hooks | `services/presence_cache.py` (activity_log side-effect), `services/feature_lifecycle.py` (priority multiplier + estimation) |
| **6** | Frontend types + store | `types/garden.ts`, `stores/garden.ts`, `types/dashboard.ts` |
| **7** | Frontend shop UI | `GardenShopView.vue`, `ShopItemCard.vue`, `WalletBadge.vue`, `TransactionHistory.vue`, `LeaderboardPanel.vue`, router |
| **8** | 3D house items | `HouseInteriorSystem.ts` — new builder methods |
| **9** | 3D avatar/gear | `CharacterSystem.ts`, `GardenScene.ts` |

---

## Verification

1. **Migration**: `alembic upgrade head` succeeds, shop items seeded, BUD columns added
2. **Wallet**: `GET /garden/wallet` returns `{balance: 0, streak: 0, wellness_score: 0}` for new user
3. **Feature earnings with multiplier**: Completing a high-priority BUD credits +100 seeds (50 × 2.0); urgent adds +25 more
4. **Estimation bonus**: BUD with `estimated_end_date` met → +30 seeds in transactions
5. **Wellness daily**: User with no commits after 7pm gets +10 healthy_day seeds next day
6. **Wellness weekly**: User with consistent start times gets +15 seeds on Monday
7. **Shop**: `GET /garden/shop` returns seeded catalog, filterable by category
8. **Purchase**: `POST /garden/purchase` deducts balance, adds to inventory, rejects if insufficient
9. **Dashboard**: `MemberActivity` includes `seed_balance` and `streak_days`
10. **Shop UI**: Grid renders, tabs filter, buy flow works, owned items show badge
11. **WalletBadge**: Shows in TreeDashboard header with correct balance
12. **House items**: Purchased plant/pet appears in house interior when focused
13. **Avatar unlock**: Equipped avatar overrides default character model in garden
14. **Gear**: Equipped hat/cape renders on character in garden
15. **Leaderboard**: Shows top 10 by lifetime seeds
16. **Idempotency**: Same feature completion doesn't double-credit; wellness_credited flag prevents double wellness credit
17. **Anti-burnout**: User with > 10hr active day sees reduced daily_active and nudge message
18. **TypeScript**: `npx tsc --noEmit` passes
19. **Ruff**: `ruff check . && ruff format --check .` passes
