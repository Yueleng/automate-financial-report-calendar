<!-- BEGIN:nextjs-agent-rules -->

## This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` (resolved from this file's directory; in monorepos the `next` package may not be visible from the repo root) before writing any code. Heed deprecation notices.

This block is written and re-added by `next dev` — verify at `node_modules/next/dist/server/lib/generate-agent-files.js`. Removing it from a diff only re-creates the uncommitted change; committing it with your work keeps the tree clean.

<!-- END:nextjs-agent-rules -->

# Financial Reports Calendar — Frontend Agent Guide

This document provides architecture, tech stack, conventions, and operational guidelines for AI coding agents working on the `frontend` application.

---

## 1. Project Overview

The frontend is a single-page interactive application built with **Next.js 16 (App Router)** and **React 19** for tracking corporate earnings reports and subscribing to calendar feeds.

- **Calendar Route (`/calendar`)**: Displays earnings reports using FullCalendar (DayGrid and List views) with interactive event dialogs, ticker filtering chips, an ICS feed export button, and on-demand Alpha Vantage sync with cooldown timers.
- **Watchlist Route (`/watchlist`)**: Provides ticker management (add, delete with confirmation dialog) that dynamically updates tracked companies and triggers backend re-filtering.
- **Root Route (`/`)**: Automatically redirects to `/calendar`.

---

## 2. Tech Stack & Key Dependencies

- **Framework**: Next.js 16.4.2 (App Router, Turbopack, React 19)
- **Language**: TypeScript 5 (`strict` mode enabled, `@/*` aliases mapping to `./src/*`)
- **Package Manager**: `pnpm` (`pnpm@12.6.0`)
- **Styling**: Tailwind CSS v4 (`@tailwindcss/turbopack`, `@import "tailwindcss"`, `tw-animate-css`)
- **UI Components**: shadcn UI (`radix-nova` style, configured in `components.json`) built on Radix UI primitives (`radix-ui`)
- **Icons**: `lucide-react`
- **Calendar**: `@fullcalendar/react` (`@fullcalendar/daygrid`, `@fullcalendar/list`, with `temporal-polyfill`)
- **Data Fetching**: SWR (`swr`) for client-side caching, polling, and optimistic revalidation
- **Notifications**: Sonner (`sonner`) via `<Toaster position="bottom-right" richColors />`
- **Linting & Formatting**:
  - ESLint 9 (`eslint.config.mjs` with `eslint-config-next`)
  - Biome (`@biomejs/biome`, `biome.json`) for code formatting

---

## 3. Directory Structure

```text
frontend/
├── components.json          # shadcn UI CLI configuration
├── next.config.ts           # Next.js configuration (includes /api/* rewrite proxy)
├── package.json             # Dependencies and scripts (pnpm)
├── tsconfig.json            # Path alias @/* -> ./src/*
├── biome.json               # Formatting configuration
├── eslint.config.mjs        # ESLint flat configuration
└── src/
    ├── app/
    │   ├── layout.tsx       # Root layout: font loading, sticky header/nav, Toaster
    │   ├── page.tsx         # Root redirect to /calendar
    │   ├── globals.css      # Tailwind v4 theme, OKLCH colors, FullCalendar dark styles
    │   ├── calendar/
    │   │   └── page.tsx     # Calendar view page (FullCalendar + filters + refresh)
    │   └── watchlist/
    │       └── page.tsx     # Watchlist management page (add/delete companies table)
    ├── components/
    │   ├── earnings-calendar.tsx  # FullCalendar wrapper with custom event rendering
    │   ├── event-dialog.tsx       # Detailed modal for selected earnings event
    │   ├── refresh-button.tsx     # Manual sync trigger with cooldown countdown
    │   ├── symbol-filter.tsx      # Ticker toggle group filter
    │   └── ui/                    # shadcn UI atomic components (button, card, dialog, table...)
    └── lib/
        ├── api.ts           # Typed API client, error wrapper, and endpoint callers
        ├── colors.ts        # Deterministic ticker color hashing & rescheduled styles
        └── utils.ts         # Re-exports `cn` utility for class merging
```

---

## 4. Backend Communication & API Layer

### Proxy Rewriting
- Do **not** hardcode `http://localhost:8000` in browser components.
- In `next.config.ts`, `/api/:path*` is proxied to `process.env.BACKEND_URL || "http://localhost:8000"`.
- All frontend calls must use relative `/api/...` paths.

### API Client (`src/lib/api.ts`)
Always use the helper functions and TypeScript interfaces in `src/lib/api.ts`:
- `fetchReports({ start, end, symbols })`: Fetches earnings events from `/api/reports`.
- `fetchWatchlist()`: Fetches tracked companies from `/api/watchlist`.
- `addWatchlistItem({ symbol, name })`: Adds a ticker to the watchlist.
- `removeWatchlistItem(symbol)`: Deletes a ticker from the watchlist.
- `fetchJobStatus()`: Returns background sync status and cooldowns (`/api/jobs/status`).
- `triggerRefresh()`: Triggers background sync with Alpha Vantage (`/api/jobs/refresh`).
- `getCalendarIcsUrl()`: Returns the subscription ICS endpoint (`/api/calendar.ics`).
- Custom `ApiError` provides structured HTTP status and `detail` message parsing.

---

## 5. State Management & Data Fetching

- Use **SWR** (`useSWR`) for all server-backed state:
  ```tsx
  const { data, error, isLoading, mutate } = useSWR("/api/reports", () => fetchReports());
  ```
- Use `mutate()` to optimistically update or trigger revalidation after mutations (e.g., adding/deleting watchlist items or triggering sync).
- Derive filtered views using `useMemo` (e.g., filtering reports by active tickers in `calendar/page.tsx`).
- For user actions, notify with Sonner:
  ```tsx
  toast.success("Watchlist updated");
  toast.error(err.message);
  ```

---

## 6. Styling & UI Conventions

- **Tailwind CSS v4**: Tokens and CSS variables use OKLCH colors defined in `globals.css`.
- **Dark Mode**: The app runs with dark mode by default (`dark` class on `<html>`).
- **Ticker Colors**:
  - Never hardcode ticker pill colors in components.
  - Use `getSymbolColor(symbol)` from `src/lib/colors.ts`, which uses deterministic hashing (`hashString`) across a curated 10-palette theme.
  - Rescheduled events should apply `RESCHEDULED_STYLE` from `src/lib/colors.ts`.
- **Class Merging**: Use `cn(...)` from `"cn"` or `@/lib/utils` for conditional classes.
- **Components**:
  - Keep atomic primitives in `src/components/ui/` compatible with shadcn (`components.json`).
  - Interactive components using browser APIs, SWR, or React state must include the `"use client"` directive at line 1.

---

## 7. Development & Verification Commands

All commands should be executed from the `frontend/` directory (or using root `make` targets):

```bash
# Start development server with Turbopack (http://localhost:3000)
pnpm dev

# Type check and build production bundle
pnpm run build

# Run ESLint checks
pnpm run lint

# Check code formatting with Biome
pnpm run format:check

# Auto-format codebase with Biome
pnpm run format
```

Before committing any frontend changes:
1. Ensure `pnpm run lint` passes with 0 errors.
2. Run `pnpm run format` to keep styling consistent with Biome rules.
3. Validate with `pnpm run build` if changes involve routing, TypeScript interfaces, or exports.
