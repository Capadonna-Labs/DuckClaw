# Admin Playground Navigation Design

## Goal

Align DuckClaw Admin navigation with the referenced console pattern: one top hamburger controls the left menu, and Playground exposes a small selector for history and new chat flows.

## Requirements

- The left `Sidebar` must not render the `Ocultar menú` button inside its brand/role header.
- The top hamburger must be available for desktop and mobile:
  - desktop: toggles `sidebarOpen`;
  - mobile: opens the drawer.
- The `Playground` sidebar item must expand to show `Historial` and `Nueva conversación`.
- `Historial` routes to `/playground?view=history` and renders a main content view with recent Playground conversations.
- Conversation rows in that view route to `/playground?conversation=<session_id>`; Playground selects that conversation and clears the transient query parameter.
- `Nueva conversación` routes to `/playground?new=1`; Playground creates a new conversation, selects it, refreshes the active conversation state, and clears the transient query parameter.
- `/playground` must not render the large `ConversationInbox` panel in the content area.

## Architecture

`Topbar` owns the menu toggle control and delegates mobile drawer opening through `onMenuClick`. `Sidebar` remains focused on brand, role, navigation groups, and logout. `NavGroup` gets a narrow special case for the canonical `/playground` item because this is a UX selector over the same feature, not a new route family.

`useActiveConversation` exposes `createConversation` and `selectConversationById` helpers so `PlaygroundPage` can handle query-driven actions without duplicating storage and tenant logic.

## Testing

Static tests cover the intended contracts:

- `Sidebar` no longer contains the inline `Ocultar menú` toggle.
- `Topbar` uses the same hamburger button for desktop sidebar toggling.
- `Sidebar` exposes `Historial` and `Nueva conversación` without embedding the conversation list.
- `PlaygroundPage` consumes `view=history`, `new=1`, and `conversation=<session_id>`.

Manual check after implementation: open `/playground`, click top hamburger to hide/show the left menu, expand `Playground`, click `Historial`, select a recent conversation from the main view, then click `Nueva conversación`.
