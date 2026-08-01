# Frontend — Next.js

Next.js 16 (App Router), React 19, TypeScript, Tailwind CSS v4,
[shadcn/ui](https://ui.shadcn.com) built on **Base UI** (`@base-ui/react`) —
not Radix. TanStack Query for server state, Zustand for client/auth state.

> **Note for anyone editing this code**: this stack has real breaking
> changes vs. what most training data / muscle memory assumes. Next 16
> renames `middleware.ts` → `proxy.ts` and uses async `params: Promise<...>`
> in dynamic routes. Base UI uses the `render` prop for polymorphic
> composition (`<DropdownMenuTrigger render={<Button .../>}>`), **never**
> Radix's `asChild` — passing `asChild` silently no-ops and produces a
> nested-`<button>` hydration error. See `AGENTS.md` in this directory and
> `node_modules/@base-ui/react/docs/` / `node_modules/next/dist/docs/`
> before assuming a pattern from an older project applies here.

## Setup

```bash
npm install
cp .env.example .env.local   # NEXT_PUBLIC_API_URL — defaults to http://localhost:8000
npm run dev
```

Requires the backend running (see [`../backend/README.md`](../backend/README.md)
or `cd ../infra && docker compose up -d`).

## Common commands

```bash
npm run dev      # dev server, Turbopack
npm run build    # production build — also type-checks (fails on TS errors)
npm run lint     # eslint
npx tsc --noEmit # type-check only, faster than a full build
```

There is no automated frontend test suite yet (Vitest/Playwright) — see
[`../docs/11-testing.md`](../docs/11-testing.md) for what's covered instead
(manual live-browser verification of every flow) and what a follow-up
would add.

## Structure

```
app/
├── (auth)/            # login, setup — no sidebar/topbar layout
├── (dashboard)/        # everything behind auth — sidebar + topbar layout
│   ├── dashboard/
│   ├── sales/
│   ├── accounting/
│   ├── inventory/
│   └── purchasing/
components/
├── ui/                 # shadcn-generated primitives (button, select, table, ...)
└── layout/             # sidebar, topbar, coming-soon placeholder
features/<module>/api/  # types.ts + client.ts per backend module — thin
                         #   typed wrappers around lib/api-client.ts
lib/
├── api-client.ts        # fetch wrapper: injects JWT + X-Company-Id/X-Branch-Id,
│                         #   parses RFC 7807 error responses
├── i18n/                 # custom AR/EN context, no external library
└── theme.tsx             # light/dark toggle
stores/auth-store.ts       # Zustand + persist — see hasHydrated note below
```

## Two things that will bite you if you don't know them

**Zustand persist rehydration is async.** A direct page load (not a
client-side nav) can render before `localStorage` has been read back into
the store. `auth-store.ts` tracks a `hasHydrated` flag specifically so auth
guards (`app/(dashboard)/layout.tsx`, `app/page.tsx`) can wait for it
instead of redirecting to `/login` on a session that actually exists.

**Base UI's `Select.Value` shows the raw value by default**, not the
matching `SelectItem`'s label — it doesn't look up the label for you. Every
`SelectValue` in this app passes a `children` render function
(`<SelectValue>{(value) => lookupLabel(value)}</SelectValue>`) to display
the right text instead of a UUID. Also watch for `Tabs.Panel` not reliably
hiding inactive tabs once a second one has mounted (see the comment in
`app/(dashboard)/accounting/page.tsx`) — pages with tabs track the active
tab in local state and gate content on it rather than trusting the
library's built-in visibility.
