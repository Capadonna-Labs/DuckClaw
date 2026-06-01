# Admin Playground Navigation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move left-menu visibility to the top hamburger and make Playground open a history/new-conversation selector.

**Architecture:** `Topbar` becomes the single menu visibility control. `Sidebar` removes the inline panel toggle and renders a scoped `Playground` submenu. `useActiveConversation` owns new-chat creation so `PlaygroundPage` can consume `/playground?new=1` without duplicating tenant storage logic.

**Tech Stack:** Next.js App Router, React client components, Zustand layout store, pytest static contract tests.

---

## File Structure

- Modify `tests/test_admin_playground_ui_static.py`: add static regression tests for sidebar/topbar/playground contracts.
- Modify `apps/duckclaw-admin/src/components/layout/Topbar.tsx`: make hamburger visible on all breakpoints and toggle desktop sidebar.
- Modify `apps/duckclaw-admin/src/components/layout/Sidebar.tsx`: remove inline `PanelToggleButton`, add Playground submenu rows.
- Modify `apps/duckclaw-admin/src/components/chat/useActiveConversation.ts`: expose `createConversation`.
- Modify `apps/duckclaw-admin/src/app/(admin)/playground/page.tsx`: handle `?new=1`, create/select conversation, clear query.

### Task 1: Static Contract Tests

- [ ] **Step 1: Add failing tests**

Add tests asserting:

```python
def test_sidebar_removes_inline_hide_menu_button_and_adds_playground_selector() -> None:
    sidebar = Path("apps/duckclaw-admin/src/components/layout/Sidebar.tsx").read_text(encoding="utf-8")

    assert 'openLabel="Ocultar menú"' not in sidebar
    assert "Historial" in sidebar
    assert "Nueva conversación" in sidebar
    assert "/playground?new=1" in sidebar


def test_topbar_hamburger_toggles_desktop_sidebar() -> None:
    topbar = Path("apps/duckclaw-admin/src/components/layout/Topbar.tsx").read_text(encoding="utf-8")

    assert "toggleSidebar" in topbar
    assert "lg:hidden" not in topbar
    assert "sidebarOpen ? 'Ocultar menú lateral' : 'Mostrar menú lateral'" in topbar


def test_playground_new_query_creates_new_conversation() -> None:
    page = Path("apps/duckclaw-admin/src/app/(admin)/playground/page.tsx").read_text(encoding="utf-8")
    hook = Path("apps/duckclaw-admin/src/components/chat/useActiveConversation.ts").read_text(encoding="utf-8")

    assert "createConversation" in hook
    assert "searchParams.get('new')" in page
    assert "conv.createConversation()" in page
    assert "router.replace('/playground'" in page
```

- [ ] **Step 2: Run tests to verify red**

Run: `uv run pytest tests/test_admin_playground_ui_static.py -q`

Expected: FAIL on the new static assertions because the current UI still renders the inline hide button and lacks `?new=1` handling.

### Task 2: Menu Toggle and Playground Selector

- [ ] **Step 1: Implement minimal UI changes**

Change `Topbar.tsx` to import `toggleSidebar`, render the hamburger without `lg:hidden`, and route click by breakpoint via CSS-independent handlers.

Change `Sidebar.tsx` to remove `PanelToggleButton` imports/usages and render a special `PlaygroundNavSelector` for the `/playground` item with two links:

```tsx
<Link href="/playground">Historial</Link>
<Link href="/playground?new=1">Nueva conversación</Link>
```

- [ ] **Step 2: Run static tests**

Run: `uv run pytest tests/test_admin_playground_ui_static.py -q`

Expected: remaining failure only for `createConversation` / query handling if UI task is complete.

### Task 3: New Conversation Query Flow

- [ ] **Step 1: Expose hook helper**

Add `createConversation` to `useActiveConversation`; it calls `adminService.createConversation({ section }, tid)`, then `selectConversation`.

- [ ] **Step 2: Consume `?new=1`**

In `PlaygroundPage`, import `useRouter`, detect `searchParams.get('new') === '1'`, call `conv.createConversation()`, `conv.bumpRefresh()`, then `router.replace('/playground', { scroll: false })`.

- [ ] **Step 3: Run static tests**

Run: `uv run pytest tests/test_admin_playground_ui_static.py -q`

Expected: PASS.

### Task 4: Lint and Final Verification

- [ ] **Step 1: Check edited files with IDE diagnostics**

Run Cursor lints on edited TSX/TS files.

- [ ] **Step 2: Run focused tests**

Run: `uv run pytest tests/test_admin_playground_ui_static.py -q`

Expected: PASS.

---

## Self-Review

- Spec coverage: top hamburger, removed inline sidebar toggle, Playground selector, and `?new=1` flow are mapped to tasks.
- Placeholder scan: no TODO/TBD placeholders.
- Type consistency: `createConversation` is introduced in hook before page consumes it.
