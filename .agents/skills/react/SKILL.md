---
name: react
description: React UI development guide. Use when creating or editing .tsx components, UI flows, layouts, modals, pages, routing, or user-facing controls.
---

# React

## Component Choice

- Prefer existing `src/components` and feature components first.
- Prefer `@lobehub/ui/base-ui` primitives over antd equivalents for new RavenWeb UI.
- Use `@lobehub/ui` higher-level components when base-ui has no match.
- Implement custom UI only when local components do not fit.

## Styling

- Prefer `createStaticStyles` with `cssVar.*`.
- Use runtime `createStyles` + token only for dynamic props or runtime color computation.
- For simple local layout, inline `style` is acceptable if neighboring code does that.
- Design for dark mode and responsive behavior.

## Layout and Navigation

- Use `Flexbox` and `Center` from `@lobehub/ui` for common layout.
- For SPA pages, use `Link` and `useNavigate` from `react-router-dom`, not `next/link`.
- Keep route files thin; put real UI and logic under `src/features/<Domain>/`.

## Data

- Do not call `lambdaClient` directly in components.
- Use service/store/SWR patterns for server data.
- Avoid `useEffect` for ordinary data fetching when a store hook pattern exists.

## User Text

- Use i18n for user-facing strings in projects that already use i18n.
- Error text should say what happened and what the user can do next.
- Avoid vague labels like "OK" when a more specific action exists.

## Modals

- For new RavenWeb imperative modals, prefer `createModal`, `confirmModal`, `ModalHost`, and `useModalContext` from `@lobehub/ui/base-ui`.
- Modal content uses hooks; modal factory options use `i18next.t` where hooks are unavailable.
