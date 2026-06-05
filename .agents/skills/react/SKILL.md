---
name: react
description: React UI development guide. Use when creating or editing .tsx components, UI flows, layouts, modals, pages, routing, or user-facing controls.
---

# React

## Component Choice

- Prefer existing `src/components` and feature components first.
- Prefer the project's established UI library / design-system primitives over ad-hoc alternatives (check `AGENTS.md` or neighboring code for which library the repo uses).
- Implement custom UI only when local components and the design system do not fit.

## Styling

- Prefer `createStaticStyles` with `cssVar.*`.
- Use runtime `createStyles` + token only for dynamic props or runtime color computation.
- For simple local layout, inline `style` is acceptable if neighboring code does that.
- Design for dark mode and responsive behavior.

## Layout and Navigation

- Use the design system's layout primitives for common layout instead of hand-rolled flex wrappers.
- Use the router that the project already adopts; match SPA vs framework-router conventions in neighboring code.
- Keep route files thin; put real UI and logic under a feature directory (for example `src/features/<Domain>/`).

## Data

- Do not call the data/RPC client directly in components.
- Use the project's service / store / data-hook patterns for server data.
- Avoid `useEffect` for ordinary data fetching when a store or query hook pattern exists.

## User Text

- Use i18n for user-facing strings in projects that already use i18n.
- Error text should say what happened and what the user can do next.
- Avoid vague labels like "OK" when a more specific action exists.

## Modals

- For imperative modals, prefer the project's established modal factory/host pattern over bespoke one-off modals.
- Modal content uses hooks; for modal factory options where hooks are unavailable, use the project's non-hook i18n accessor.
