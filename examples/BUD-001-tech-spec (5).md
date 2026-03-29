I now have a complete picture of both codebases. Let me compose the tech spec.

---

# BUD-001 — Notification Improvement: Technical Implementation Plan

## Executive Summary

The notification infrastructure is substantially complete. The backend exposes all required CRUD endpoints (`GET`, `PATCH /{id}/read`, `POST /read-all`, `DELETE /{id}`), and the frontend has a working Pinia store with optimistic updates plus three Vue components (`NotificationBell`, `NotificationPanel`, `NotificationItem`). The work is almost entirely **surgical refinement** — the components exist but diverge from the wireframe on UX details: missing filter tabs, a basic error state with no retry, `position: fixed` anchoring, HTML entity icons instead of SVGs, and a few accessibility gaps.

One backend addition is needed: a fast `GET /notifications/unread-count` endpoint and pagination params on the list endpoint.

---

## Architecture Overview

```
App.vue
  └── NotificationBell.vue        ← bell + badge + click-outside
        └── NotificationPanel.vue ← dialog, header, filter tabs, body, footer
              └── NotificationItem.vue ← per-row: dot, text, actions

stores/notifications.ts           ← Pinia store (source of truth)
services/api.ts                   ← Axios client (JWT injection, 401 redirect)

taskflow-api/src/notifications/
  ├── router.py                   ← FastAPI routes
  ├── service.py                  ← business logic
  └── models.py                   ← SQLAlchemy ORM
```

**Key design principle**: The store owns all async state. Components are purely reactive consumers — they call store actions and render from computed refs. Optimistic updates live in the store, not in component local state.

---

## Backend Changes — `taskflow-api`

### 1. Add `GET /notifications/unread-count`

**File**: `src/notifications/router.py`

The frontend needs a fast, low-payload endpoint to initialise the badge on app load without fetching all notification bodies. Currently the store calls `GET /notifications` and derives the count client-side — expensive for users with many notifications.

```python
@router.get("/unread-count")
def unread_count(user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    """Return the count of unread notifications for the badge."""
    count = db.query(Notification).filter(
        Notification.user_id == user["user_id"],
        Notification.is_read.is_(False)
    ).count()
    return {"count": count}
```

> **Route ordering note**: This route MUST be registered before `/{notification_id}/read` — FastAPI matches routes top-to-bottom. "unread-count" as a literal path segment comes before the parametric `{notification_id}`.

**File**: `src/notifications/service.py` — no changes needed; the router calls the DB directly for this count (too simple to warrant a service wrapper).

### 2. Add Pagination to `GET /notifications`

**File**: `src/notifications/router.py` — add `limit` and `offset` query params.

**File**: `src/notifications/service.py` — `list_notifications` currently hard-codes `.limit(50)`. Change signature:

```python
def list_notifications(
    db: Session, user_id: int,
    unread_only: bool = False,
    limit: int = 20,
    offset: int = 0
) -> list[Notification]:
```

The router passes these through. Default page size 20 (first load fast); "Load more" appends the next 20.

### Impact: `list_notifications`

Per CLAUDE.md requirements, running impact before edits:

- `list_notifications` is called only by `router.py:index` (d=1, direct). No other callers in the graph. **LOW risk.**

---

## Frontend Changes — `taskflow-web`

`★ Insight ─────────────────────────────────────`
The current `NotificationPanel` uses `position: fixed` with hard-coded `top: 52px; right: 16px`. This works but breaks if the header height changes and cannot be tested in isolation. The wireframe uses `position: absolute` on the panel relative to the `.notification-bell` container — the bell becomes the positioning parent. This is more composable and lets the component be moved anywhere in the layout.
`─────────────────────────────────────────────────`

### Files to Modify

#### `src/stores/notifications.ts`

**What's missing vs. wireframe behaviour:**
- No `activeFilter` ('all' | 'unread') state
- No `filteredNotifications` computed
- No pagination state (offset, hasMore, isLoadingMore)
- No `loadMore()` action
- `fetchNotifications` is called on every bell open — should be additive on `loadMore`, not replace

**Additions**:

```ts
// New state
const activeFilter = ref<'all' | 'unread'>('all')
const offset = ref(0)
const hasMore = ref(false)
const isLoadingMore = ref(false)

// New computed
const filteredNotifications = computed(() =>
  activeFilter.value === 'unread'
    ? notifications.value.filter(n => !n.is_read)
    : notifications.value
)

// New action
async function loadMore() { ... }  // appends next page

// Modified fetchNotifications — resets offset, replaces list
```

Also add `unreadCount` initialisation via the fast `GET /unread-count` call on app mount (so the badge appears before the panel is ever opened).

**Debounce for rapid mark-as-read**: Wrap the `api.patch` call with a per-notification debounce (or guard with an in-flight set) so rapid double-clicks don't fire duplicate PATCH requests.

#### `src/components/notifications/NotificationBell.vue`

**Gap analysis vs. wireframe:**

| Issue | Current | Wireframe |
|---|---|---|
| Panel open state class | Not applied to bell button | `.bell-btn.active` class when `panelOpen` |
| Badge border cut-out | Missing | `border: 2px solid var(--color-header-bg)` |
| `aria-label` | Always says "N unread" even when 0 | Dynamic: "no unread" vs "N unread" |
| `aria-haspopup` | `"true"` | `"dialog"` (ARIA 1.1 spec) |
| Bell fill | Applied via `.filled` class | Applied via inline `:fill-opacity` on the SVG path |

**Changes**:
- Add `:class="{ active: panelOpen }"` to `<button>`
- Add `.badge` style: `border: 2px solid var(--color-header-bg, #1a1a2e)`
- Fix `aria-label` binding to match wireframe's ternary
- Fix `aria-haspopup="dialog"`
- Reset `activeFilter` in store when panel opens (match wireframe's `togglePanel` behaviour)

#### `src/components/notifications/NotificationPanel.vue`

**Gap analysis vs. wireframe:**

| Issue | Current | Wireframe |
|---|---|---|
| Positioning | `position: fixed; top: 52px; right: 16px` | `position: absolute; top: calc(100% + 10px); right: 0` |
| ARIA role | `role="region"` | `role="dialog" aria-modal="true"` |
| Close button | Missing | X icon button in panel header |
| Filter tab bar | Missing | All / Unread · N pill tabs |
| Error state | Plain `<div class="panel-error">` text | Styled block with emoji, message, sub-text, and Retry button |
| Panel animation | None | `@keyframes panel-enter` (opacity + translateY) |
| `aria-live` on body | Missing | `aria-live="polite"` |
| Max height | 480px | 520px |
| Skeleton lines | 2 lines per item | 3 lines (long, medium, short) with staggered delay |
| "Load more" footer | Missing | Footer with "Load more notifications" button |
| Empty state | Unicode ✓ + `<p>` | Styled `.panel-empty` with `.empty-title` + `.empty-sub` |

**Changes** (in priority order):

1. **Positioning** — change to `absolute` anchored to bell container.
2. **Dialog role** — `role="dialog" aria-modal="true"`.
3. **Add close button** — X SVG in panel header alongside "Mark all read".
4. **Add filter tab bar** — two pill buttons bound to `store.activeFilter`; "Unread · N" shows `store.unreadCount`.
5. **Error state redesign** — styled block matching wireframe with Retry button that calls `store.fetchNotifications()`.
6. **Panel animation** — CSS `@keyframes panel-enter`.
7. **Skeleton** — 3 lines (long/medium/short), staggered `animation-delay`.
8. **Load more footer** — shown when `store.hasMore`, calls `store.loadMore()`.
9. **Empty state** — add `.empty-title` / `.empty-sub` structure.

#### `src/components/notifications/NotificationItem.vue`

**Gap analysis vs. wireframe:**

| Issue | Current | Wireframe |
|---|---|---|
| Mark-read icon | HTML entity `&#10003;` | SVG checkmark (`d="M2 9l4 4 8-8"`) |
| Dismiss icon | HTML entity `&times;` | SVG X (`d="M1 1l10 10M11 1L1 11"`) |
| Body tooltip | Missing | `:title="notification.body"` on `.notif-body` |
| `focus-within` actions | Not present | `.notification-item:focus-within .item-actions { opacity: 1 }` |
| Read item border-left | No left border | `border-left: 3px solid transparent` (alignment placeholder) |
| Read title colour | `font-weight: 500` (same) | `font-weight: 400; color: var(--color-text-muted)` |
| Danger hover on delete | Generic hover | `.item-action-btn.danger:hover { background: #fef2f2; color: var(--color-danger) }` |
| Item padding | `12px 16px` | `12px 13px` (13px right matches wireframe) |
| `role="listitem"` | Missing | `role="listitem"` + `aria-label` |
| Keyboard: Enter marks read | Missing | `@keydown.enter="markRead"` |
| Keyboard: Delete dismisses | Missing | `@keydown.delete="dismiss"` |

**Changes**: Replace HTML entities with inline SVGs, add all missing a11y attributes, add focus-within CSS, align padding/colour with wireframe tokens.

---

## Data Model

No schema changes. The existing `Notification` table (`id`, `user_id`, `type`, `title`, `body`, `is_read`, `link`, `created_at`) maps directly to the wireframe's notification item shape.

The `Notification` TypeScript interface in `stores/notifications.ts` needs one field rename alignment: the backend returns `is_read`, the store already uses `is_read` — these are consistent. No migration needed.

---

## API Endpoints — Final State

| Method | Path | Status | Purpose |
|---|---|---|---|
| `GET` | `/notifications` | ✅ Exists — add pagination params | List notifications (paginated) |
| `GET` | `/notifications/unread-count` | 🆕 Add | Fast badge initialisation |
| `PATCH` | `/notifications/{id}/read` | ✅ Exists | Mark single as read |
| `POST` | `/notifications/read-all` | ✅ Exists | Mark all as read |
| `DELETE` | `/notifications/{id}` | ✅ Exists | Delete/dismiss |
| `PUT` | `/notifications/preferences` | ✅ Exists (out of scope for this BUD) | Email/push prefs |

---

## Component Tree (Final)

```
NotificationBell.vue
├── <button.bell-btn [active]>       ← aria-haspopup="dialog", aria-expanded
│     ├── <svg> bell icon            ← fill-opacity 0.15 when unread
│     └── <span.badge>              ← 99+, border cut-out
│
└── NotificationPanel.vue [v-if="panelOpen"]
      ├── .panel-header
      │     ├── "Notifications" title
      │     ├── "Mark all read" btn  [v-if="hasUnread"]
      │     └── Close btn (X svg)
      ├── .filter-bar [role="tablist"]
      │     ├── "All" tab
      │     └── "Unread · N" tab
      ├── .panel-body [aria-live="polite"]
      │     ├── <template loading>   ← 4× skeleton-item (3 lines each)
      │     ├── <template error>     ← role="alert", retry button
      │     ├── <template empty>     ← "You're all caught up"
      │     └── <template items>     ← filteredNotifications
      │           └── NotificationItem.vue ×N
      │                 ├── .type-dot (colour-coded)
      │                 ├── .notif-content
      │                 │     ├── .notif-title (bold if unread)
      │                 │     ├── .notif-body  (:title tooltip, 2-line clamp)
      │                 │     └── <time.notif-time>
      │                 └── .item-actions (reveal on hover/focus-within)
      │                       ├── Mark-as-read btn (SVG ✓) [v-if="!is_read"]
      │                       └── Dismiss btn (SVG ×, danger hover)
      └── .panel-footer [v-if="hasMore"]
            └── "Load more" button
```

---

## Acceptance Criteria Mapping

| AC | Implementation Location |
|---|---|
| Bell icon matches design system | `NotificationBell.vue` — SVG stroke-width 1.75, fill-opacity 0.15 |
| Unread badge count (caps 99+) | `store.badgeLabel` computed |
| Badge accessible aria-label | `NotificationBell.vue` — dynamic label |
| Panel opens/closes, keyboard Escape | `NotificationPanel.vue` `@keydown.escape` → `$emit('close')` |
| Scrollable list, newest first | `service.order_by(created_at.desc())` + panel-body `overflow-y: auto` |
| Read/unread visual diff | `NotificationItem.vue` — bold/muted title, accent left border |
| Mark single as read | `store.markRead()` — optimistic update + PATCH |
| Mark all read (bulk header btn) | `store.markAllRead()` — optimistic + POST |
| Delete/dismiss | `store.deleteNotification()` — optimistic splice + DELETE |
| Empty state | `NotificationPanel.vue` — "You're all caught up" |
| 5xx error with retry | `NotificationPanel.vue` — styled error block + retry |
| 401 silently hidden | `services/api.ts` interceptor — already redirects to /login |
| Long text truncate at 2 lines | `NotificationItem.vue` — `-webkit-line-clamp: 2` + `:title` |
| Load more (99+) | `store.loadMore()` + panel footer button |
| Keyboard navigable | `tabindex="0"` on items, Enter=read, Delete=dismiss, Escape=close |

---

## Risks & Mitigations

| Risk | Mitigation |
|---|---|
| `position: absolute` panel clips out of viewport on small screens | Already handled by `@media (max-width: 440px)` override in wireframe — carry into component styles |
| Rapid mark-as-read fires duplicate PATCHes | Guard with an `inFlight: Set<number>` in the store action |
| Route ordering conflict: `/unread-count` vs `/{notification_id}` | Register `/unread-count` before the parametric route in `router.py` |
| Filter tab "Unread" shows stale count after mark-all-read | `unreadCount` is a computed from reactive `notifications` array — updates automatically |
| Panel open on 401 (user logs out mid-session) | `api.ts` interceptor already redirects; store `error` state remains but panel closes on nav |

---

## Files to Create or Modify

### `taskflow-api`
| Action | File |
|---|---|
| Modify | `src/notifications/router.py` — add `/unread-count` route; add `limit`/`offset` params to `index` |
| Modify | `src/notifications/service.py` — add `limit`/`offset` to `list_notifications` signature |

### `taskflow-web`
| Action | File |
|---|---|
| Modify | `src/stores/notifications.ts` — add filter, pagination, debounce, `fetchUnreadCount` |
| Modify | `src/components/notifications/NotificationBell.vue` — active class, badge border, aria fixes |
| Modify | `src/components/notifications/NotificationPanel.vue` — absolute positioning, dialog role, close btn, filter tabs, error retry, animation, load more |
| Modify | `src/components/notifications/NotificationItem.vue` — SVG icons, tooltip, focus-within, a11y, keyboard handlers |

No new files need to be created. All scaffolding exists.

---

## Development Workflow

**Branch naming**: `bud-001/<description>`

Suggested branch splits (can be one PR or sequential):

```
bud-001/backend-pagination-unread-count   ← API changes only
bud-001/notification-panel-redesign       ← frontend components
```

Or continue on the existing branch: `bud-001/notification-redesign` (already active).

**Implementation order**:
1. Backend: `unread-count` endpoint + pagination params (unblocks frontend badge init)
2. Store: filter, pagination, `fetchUnreadCount`
3. `NotificationItem.vue`: SVG icons, a11y, focus-within (self-contained, no panel deps)
4. `NotificationPanel.vue`: positioning, dialog, filter tabs, error state, load more
5. `NotificationBell.vue`: active class, badge border, aria fixes

`★ Insight ─────────────────────────────────────`
The implementation order matters here: start with the store and `NotificationItem` (pure leaf components with no dependencies on positioning) before tackling `NotificationPanel`. This way each layer is testable in isolation. The store's optimistic update pattern (mutate locally, revert on error) is already well-implemented — the main additions are additive state (filter, pagination) rather than rewrites.
`─────────────────────────────────────────────────`