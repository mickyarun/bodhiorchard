Now I have everything I need. Let me compile the spec.

---

## BUD-001 Tech Spec — Notification Bell Improvement

### Executive Summary

`NotificationBell.vue` currently bypasses `useNotificationStore` entirely, issues its own raw `api` calls, and has no per-item actions, no panel positioning, and a static icon regardless of unread state. This BUD is a single-file rewrite confined to `NotificationBell.vue` that wires the component to the already-implemented store and socket composable, adds per-item mark-as-read, a two-step clear-all confirm, capped badge display, and corrects the panel opening direction.

---

### Architecture Approach

All changes are isolated to `NotificationBell.vue`. The rewrite removes inline `api` calls in favour of `useNotificationStore()` and wires `useNotificationSocket()` for real-time delivery. Bell icon toggling is a ternary on `unreadCount > 0`; badge display is `unreadCount > 99 ? '99+' : unreadCount`. Panel positioning moves from the current unanchored layout to `position: absolute; top: calc(100% + 8px); right: 0` on a `position: relative` wrapper, matching the wireframe. An overlay backdrop (`position: fixed; inset: 0; z-index: 999`) handles outside-click dismissal without a click-outside directive. The two-step clear-all confirm is a single `showClearConfirm = ref<boolean>(false)` that swaps the header action row inline — no store change, no modal. Optimistic mark-as-read and rollback-on-error are handled by the store's existing `markRead` method; the component only watches `store.error` to surface a transient snackbar.

---

### Files to Create or Modify

| Action | Path | Notes |
|--------|------|-------|
| Modify | `examples/taskflow-web/src/components/notifications/NotificationBell.vue` | Full rewrite: consume store + socket composable, add per-item mark-as-read, two-step clear-all, 99+ badge, dynamic icon, correct panel positioning |

---

### Data Model Changes

None.

---

### Design References

- **Wireframe:** `/Users/arunrajkumar/Documents/code/bodhigrove/examples/taskflow-web/.bodhigrove/wireframes/BUD-001/wireframe.html`

| Wireframe screen | Maps to |
|------------------|---------|
| Bell trigger — filled vs outline, badge ≤99 / "99+" | `<button class="bell-btn">` with conditional SVG + `<span class="badge">` |
| Panel — drops below trigger, 380px wide, 480px max-height, scrollable list | `.notif-panel` `position: absolute; top: calc(100% + 8px); right: 0` |
| Unread item — `--color-surface-alt` bg, 3px `--color-accent` left border, bold title | `.notif-item.unread` |
| Per-item actions — ✓ mark-read (unread only), × dismiss (all); opacity-0 by default, revealed on parent hover | `.notif-actions { opacity: 0 }` + `.notif-item:hover .notif-actions { opacity: 1 }` |
| Two-step clear-all — inline confirm row replacing header button | Conditional render on `showClearConfirm` inside `.panel-actions` |
| Error snackbar — `role="alert"`, `aria-live="assertive"`, `--color-danger` styling | Fixed `<div>` bound to `store.error`, auto-dismissed after 3 s |
| Empty state — "You're all caught up" | `v-if="store.items.length === 0 && !store.loading"` |

Design tokens to reference (no hardcoded values): `--color-accent`, `--color-surface`, `--color-surface-alt`, `--color-text`, `--color-text-muted`, `--color-danger`, `--color-success`, `--radius-panel`, `--shadow-panel`. Badge uses `font-size: 11px; font-weight: 700` per the type scale. Action buttons use `border-radius: 6px` per component defaults.

---

### Dependencies & Risks

- **HTTP verb discrepancy**: `frontend/src/stores/notifications.ts:31` calls `api.post(…/read)` but `examples/taskflow-api/src/notifications/router.py:32` declares `@router.patch`. Confirm the taskflow-web store's own `markRead` implementation uses `PATCH` before integration testing; if it uses `POST`, a one-line store fix is needed (outside the stated "NotificationBell.vue only" scope — flag with the team).
- **Icon set availability**: The wireframe uses Unicode characters for illustration; the component must use whatever icon mechanism taskflow-web already ships (confirm whether inline SVG or a project icon utility is preferred before implementing the bell toggle).
- **Rapid mark-as-read**: The spec allows each click to fire independently with no debounce. Confirm this is acceptable under load; if not, a simple `pendingIds = ref<Set<string>>` guard can prevent duplicate in-flight requests for the same ID.
- **Panel z-index**: Panel (`z-index: 1000`) and backdrop (`z-index: 999`) are above the header (`z-index: 100` per `App.vue`). No conflict expected, but verify against any modal or toast already in the app.

---

### Development Workflow

**Branch:** `bud-001/notification-bell-improvement`

Implementation order: script → template → scoped styles → review.

---

### Implementation TODO

1. [ ] **Script block** — import `useNotificationStore` and `useNotificationSocket`; remove direct `api` import; add `showClearConfirm = ref(false)`; add `badgeLabel = computed(() => unreadCount.value > 99 ? '99+' : unreadCount.value)`; call `useNotificationSocket(currentUserId)` on mount; wire `store.fetchAll()` on mount
2. [ ] **Bell trigger** — conditional SVG icon (filled when `unreadCount > 0`, outline when 0); `<span class="badge" v-if="unreadCount > 0">{{ badgeLabel }}</span>`; wrapper div `position: relative`
3. [ ] **Overlay backdrop + panel positioning** — backdrop `div` (fixed, inset-0, z-999) closes panel on click; panel `position: absolute; top: calc(100% + 8px); right: 0; width: 380px; max-height: 480px; z-index: 1000`
4. [ ] **Panel header** — title "Notifications"; "Mark all read" button calling `store.markAllRead()`; "Clear all" button that sets `showClearConfirm = true`; when `showClearConfirm`, swap to inline confirm row: label "Are you sure?", "Yes, clear" button (calls `store.dismissAll()` then resets flag), "Cancel" button (resets flag)
5. [ ] **Notification list** — `v-for` over `store.items`; `:class="{ unread: !n.isRead && !n.isDismissed }"`; type dot color driven by `n.type` matching the design system notification type dot palette; title (bold + `--color-text` when unread; normal weight + `--color-text-muted` when read); body 2-line clamp; timestamp
6. [ ] **Per-item actions** — mark-read button `v-if="!n.isRead"` calls `store.markRead(n.id)` using `--color-accent` + accent-tinted hover; dismiss button (all items) calls `store.dismiss(n.id)` using `--color-text-muted` default, `--color-danger` on hover; both inside `.notif-actions` hidden by default, revealed on item hover via CSS opacity transition
7. [ ] **Error snackbar** — `v-if="store.error"` fixed snackbar with `role="alert"` and `aria-live="assertive"`; `watch(store.error)` triggers 3-second auto-clear via `setTimeout(() => store.error = '', 3000)`
8. [ ] **Empty state** — `v-if="store.items.length === 0 && !store.loading"` renders per design system empty state: ✓ icon, "You're all caught up" label, `--color-text-muted`, `--color-success` icon colour
9. [ ] **Scoped styles** — all colour/radius/shadow values via CSS custom properties; 0.15s transitions; `<style scoped>` per project convention; no hardcoded hex except Border token `#e5e7eb` (until tokenised)
10. [ ] **Code review checkpoint** — run through Code Review Standards below before opening PR

---

### Code Review Standards

Developers must verify at each phase:

- [ ] Modularity: each function <50 lines, each file <300 lines
- [ ] Security: org-scoped queries, auth on endpoints, no PII leaks, input validation at boundaries
- [ ] Reusability: reuse existing patterns/utilities, no duplicated code
- [ ] No large files: split if >300 lines backend / >250 lines frontend
- [ ] No hacks: no hardcoded values, no TODO/FIXME left behind, no bypassed validations
- [ ] Standards: type hints, docstrings on public functions, lint clean (ruff/eslint)

---
