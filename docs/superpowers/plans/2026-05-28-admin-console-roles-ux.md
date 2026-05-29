# Admin Console Roles UX Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the first visual and information-architecture pass for separate `user` and `admin` console experiences without changing secure login/JWT yet.

**Architecture:** Keep the existing Next.js BFF and route structure. Add a small role utility layer so UI decisions are centralized, then make the sidebar role-aware and rename user-facing labels while preserving current paths. Advanced admin screens stay reachable for admins and hidden from users.

**Tech Stack:** Next.js 14 App Router, React, TypeScript, Zustand auth store, Tailwind CSS, existing `adminService` BFF.

---

### Task 1: Role Model Utilities

**Files:**
- Create: `apps/duckclaw-admin/src/lib/roles.ts`
- Modify: `apps/duckclaw-admin/src/types/admin.ts`
- Modify: `apps/duckclaw-admin/src/store/authStore.ts`
- Test: `apps/duckclaw-admin/src/config/adminNav.test.ts`

- [ ] Add `user` as the product role and keep `viewer` as a legacy alias.
- [ ] Centralize helpers: `normalizeAdminRole`, `isAdminRole`, `isUserRole`, `canCreateAgents`.
- [ ] Normalize login API responses so legacy `viewer` becomes `user` in the client state.

### Task 2: Role-Aware Navigation

**Files:**
- Modify: `apps/duckclaw-admin/src/config/adminNav.ts`
- Modify: `apps/duckclaw-admin/src/components/layout/Sidebar.tsx`

- [ ] Add `NavAudience` / role metadata to navigation items.
- [ ] Build a concise `User Console` nav: Inicio, Chat, Mis agentes, Crear agente, Tablero, Historial, Ajustes.
- [ ] Keep an expanded `Admin Console` nav: Operación, Agentes, Datos, Integraciones, Seguridad, Sistema avanzado.
- [ ] Rename `Runtime` to `Runtime overrides` and hide it from users.
- [ ] Add visual role context in the sidebar so users understand which console mode they are in.

### Task 3: User-Friendly Page Labels

**Files:**
- Modify: `apps/duckclaw-admin/src/app/(admin)/overview/page.tsx`
- Modify: `apps/duckclaw-admin/src/app/(admin)/templates/page.tsx`
- Modify: `apps/duckclaw-admin/src/app/(admin)/projects/new/page.tsx`
- Modify: `apps/duckclaw-admin/src/app/(admin)/runtime/page.tsx`

- [ ] Adjust copy based on role without breaking routes.
- [ ] Allow `user` to enter the create-agent wizard.
- [ ] Keep project/team advanced controls admin-only where current BFF write permissions require admin.
- [ ] Add warning copy to `Runtime overrides`.

### Task 4: Verification

**Files:**
- Test: `apps/duckclaw-admin/src/config/adminNav.test.ts`

- [ ] Run the role-navigation test.
- [ ] Run lints on touched files.
- [ ] Run `next build --no-lint` and report any unrelated pre-existing type failures.

## Self Review

- Scope excludes JWT, rate limiting, idempotency and full permission enforcement; those remain later security work.
- The plan keeps current routes stable to avoid breaking deep links.
- Runtime remains accessible for admin and hidden from user.
- The UI refactor is centralized around roles and navigation instead of scattering role checks everywhere.
