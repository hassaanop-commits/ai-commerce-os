# Frontend

Next.js (TypeScript, App Router) client for AI Commerce OS.

## Setup

```
cp .env.local.example .env.local
npm install
npm run dev
```

The backend (`../backend`) must be running at the URL in `NEXT_PUBLIC_API_URL` — `next.config.js`
proxies `/api/v1/*` to it, which is what keeps session/CSRF cookies same-origin in the browser.

## Scripts

```
npm run dev        # start the dev server
npm run build       # production build (includes type checking)
npm run typecheck   # tsc --noEmit only
npm run test         # run the Vitest suite once
```

## Layout

- `src/app/` — routes (App Router)
- `src/components/` — `ui/` (primitives), `auth/`, `dashboard/`, `organizations/`
- `src/hooks/` — `useAuth`, `useOrganization` (context + hook together)
- `src/lib/` — `api-client.ts` (browser, CSRF-aware, proxied), `server-api.ts` (server components, direct backend call + cookie forwarding), `validation.ts`
- `src/types/` — API response shapes
- `src/middleware.ts` — cheap cookie-presence redirect only; the real auth check happens server-side in each protected layout/page via a real `/auth/me` call
