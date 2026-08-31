# AI Commerce OS — Project Handoff Report

_Written as a context dump for handing this project off to a different AI assistant. Paste this whole file into the new assistant's context before asking it to continue work._

---

## 1. What this project is

**AI Commerce OS** is a multi-tenant ecommerce catalog and AI content-generation platform. Sellers manage a product catalog, use AI to generate product descriptions/titles/tags/images, review and approve AI output before it goes live, and publish approved listings to marketplaces (currently a "manual" test marketplace only — real marketplace integrations are a future phase).

Core idea in one sentence: **AI drafts, a human approves, then it becomes real** — nothing AI-generated ever becomes visible/authoritative without an explicit human approval step.

---

## 2. Tech stack

- **Backend**: Python, FastAPI, SQLAlchemy (Postgres), Alembic migrations, LangGraph for AI workflow orchestration, pytest for tests.
- **Frontend**: Next.js (App Router, TypeScript), Vitest + Testing Library for tests.
- **Database**: PostgreSQL, run via `docker-compose.yml` locally.
- **AI providers**: Anthropic (text), OpenAI (images), Gemini (text; image capability stubbed), plus a network-free `MockProvider` used in all tests.
- **No git repo** is currently initialized in this working directory (environment note, not a project decision) — there is no commit history to inspect; everything is judged from the working tree.

Repo layout:
```
backend/app/
  api/v1/        — FastAPI routers (HTTP layer only, no business logic)
  agents/        — LangGraph state graphs + a "runner" that wires providers into them
  ai/providers/  — provider abstraction (AIProvider protocol) + concrete providers
  ai/tools/      — the actual AI operations (analyze, generate description, generate image, ...)
  ai/pricing.py  — flat cost-estimation tables (not a billing system)
  services/      — DB-facing business logic (products, assets, ai_runs, listings, ...)
  models/        — SQLAlchemy ORM models
  schemas/       — Pydantic request/response schemas
  marketplaces/  — marketplace adapter abstraction + the "manual" test adapter
  db/            — engine/session/tenant-scoping helpers
frontend/src/
  app/           — Next.js routes/pages
  components/    — UI (AIStudioPanel, AssetManager, AssetCard, ListingsPanel, ...)
  lib/           — typed API clients (ai-api.ts, products-api.ts, ...)
  types/         — shared TypeScript types mirroring backend schemas
docs/architecture.md — a very early, now-stale architecture stub (predates almost everything below; don't trust it over this document)
```

---

## 3. Strategy / working philosophy (the guardrails)

This has been built incrementally, phase by phase, under a strict set of constraints that the next assistant should keep respecting unless the user explicitly changes them:

- **Do NOT redesign the architecture.** Extend the existing seams (provider protocol, service layer, LangGraph graphs) rather than introducing new patterns.
- **Do NOT add MCP.**
- **Do NOT add background workers / job queues.** Everything runs synchronously in-request today (LangGraph graphs execute inline inside the FastAPI request).
- **Do NOT add billing/subscriptions.** `Plan`/`Subscription`/`UsageTracking` models exist but billing logic is not implemented — cost tracking is observability-only (`AIRun.cost_usd`), not a billing source of truth.
- **Do NOT implement real marketplace OAuth/adapters yet.** Only the `manual` marketplace adapter (deterministic, no real network calls) exists, to prove the full connect → draft → approve → publish → end pipeline.
- **Do NOT add unnecessary dependencies.** E.g. the OpenAI image provider is implemented as a raw `httpx` POST rather than pulling in the full `openai` SDK.
- **Prefer zero schema changes.** Migrations are added only when a change is genuinely structural; several recent features (image prompt visibility, regenerate lineage) were built entirely on existing columns/JSONB metadata to avoid a migration.
- **Safety-first AI**: every AI-generated artifact (description, title, tags, image) is a *draft* until a human explicitly applies/approves it. AI-generated images in particular can **never** auto-approve and **never** auto-become the primary product image — this is enforced at three layers: service-layer guard, a DB `CHECK` constraint, and UI state gating, deliberately redundant ("belt and suspenders").
- **Error handling discipline**: provider failures are mapped to a small closed set of sanitized categories (`provider_not_configured`, `provider_timeout`, `provider_rate_limited`, `provider_error`, `invalid_response`, `capability_not_supported`, `content_policy_violation`, `unknown_error`). Raw provider exceptions/SDK errors are never persisted to the DB or serialized to the client — only the sanitized category, with the real exception kept as `__cause__` for server logs only.
- **Testing discipline**: no test anywhere makes a real network call. All AI/marketplace tests run against `MockProvider` / `ManualMarketplaceAdapter`. Every new feature ships with backend (pytest) and frontend (Vitest) tests in the same pass, including negative/cross-org/security cases, not just happy paths.
- **Multi-tenancy is load-bearing everywhere.** Every query is organization-scoped (`org_scoped()` helper), every route checks membership (`require_member`/`require_admin`/`require_owner` by role rank), and there is explicit test coverage proving org A can never read/mutate org B's data even when IDs are guessed correctly.

---

## 4. Core data model (what exists today)

- `Organization`, `OrganizationMember`, `Role` (owner/admin/member, rank-based permission checks), `User`, `Session`, `AuthToken` — auth & multi-tenancy.
- `Product` — the catalog item (sku, title, description, price, status, JSONB metadata used for e.g. AI-generated tags).
- `ProductAsset` — an image/video/document attached to a product. Key fields: `source` (`upload` | `ai_generated` | `processed`), `approval_status` (`not_required` | `pending_review` | `approved` | `rejected`), `is_primary`, `ai_run_id` (which AI generation produced it, if any), `derived_from_asset_id` (self-referential — used for regenerated images and, later, processed derivatives).
- `AIRun` — one row per AI provider call (text or image). Tracks `provider`, `model`, `input_tokens`/`output_tokens`, `cost_usd`, `status`, `error_message` (sanitized category only), `metadata` (JSONB — holds things like `workflow_id`, the crafted `image_prompt`, retry counts). This is the audit/history/cost-tracking backbone for all AI activity.
- `Marketplace`, `MarketplaceConnection`, `Listing` — the marketplace/publishing pipeline. `Listing.status`: `draft → approved → publishing → active → error/ended`.
- `AuditLog` — generic audit trail (who did what, when, from what IP) for security-sensitive actions.
- `Plan`, `Subscription`, `UsageTracking` — exist as models for a future billing phase; not wired into any enforcement logic yet.

---

## 5. What's been built, phase by phase

1. **Product Catalog + Assets** — CRUD for products, asset upload (with real image-content sniffing, not just trusting the declared MIME type), reordering, primary-image selection, deletion with safe re-promotion of the next eligible asset.
2. **AI description / title / tags generation** — a LangGraph graph (`product_content.py`): `analyze → generate_description → generate_title → generate_tags`, each step short-circuiting on failure. Each generated field is a separate "apply" action (`apply-description`, `apply-title`, `apply-tags`) so the user can accept some and reject others independently.
3. **AI image generation** — a separate LangGraph graph (`product_image.py`): `craft_prompt → generate_image`. Two providers are used deliberately (a text provider crafts the image prompt; an image provider renders it), because no single provider does both well in this stack.
4. **Image approval/rejection workflow** — `pending_review → approved/rejected`, one-way one-shot transition, enforced by `InvalidApprovalTransitionError` service guard + a DB `CHECK` for primary-eligibility.
5. **Anthropic provider, Gemini provider** — both implement the same `AIProvider` protocol (`complete()` for text; `generate_image()` for images, where unsupported it raises `capability_not_supported` cleanly rather than crashing).
6. **Per-task model routing** — `app/agents/runner.py` maps "utility" vs "content" tiers to provider-specific model IDs (e.g. Claude Haiku for cheap tasks, Sonnet for customer-facing description text), independently per provider, so switching the active provider never requires touching graph/tool code.
7. **Retry + exponential backoff** — `app/ai/tools/_common.py`: `start_and_call()` wraps every provider call, retries only genuinely transient categories (`provider_timeout`, `provider_rate_limited`, `provider_error`) with capped exponential backoff + jitter, up to `settings.ai_max_retries`. One logical operation = one `AIRun` row regardless of how many attempts it took internally.
8. **AI run tracking/history** — every provider call is durably recorded as an `AIRun` (own DB commit, independent of the caller's transaction) with provider/model/tokens/cost/status, surfaced in the "AI Studio" UI as a history feed.
9. **Marketplace/listing pipeline** — connect a marketplace (currently only `manual`), draft a listing from a product, publish (`create_listing` via `MarketplaceAdapter` protocol), end a listing. Same sanitized-error-category pattern as the AI provider layer (`MarketplaceError`).
10. **AI Studio UI improvements** — `AIStudioPanel.tsx` shows current vs AI-draft content side by side, provider/model/cost per generation, generation history, and (as of this session) multi-variation image review.

### Just-completed phase: **Production-hardening the AI image workflow** (this session)

Audited the existing image pipeline first (it was already quite mature — sanitized errors, retry/backoff, org isolation, and the approval/primary guards were already solid and well-tested), then added the genuinely missing pieces:

- **Multiple image variations in one request** — `POST .../ai/generate-image` now accepts `variations` (1–4). The single-image path still runs through the original, unchanged, well-tested LangGraph graph; `variations > 1` is handled as a thin loop over the *same underlying tool functions* the graph nodes call (craft the prompt once, generate the image N times) — deliberately not a graph redesign. Each variation gets its own `AIRun` and own `ProductAsset`; one variation failing doesn't abort the others; a fully-failed request produces zero fabricated assets.
- **Regenerate** — new endpoint `POST .../ai/assets/{asset_id}/regenerate`. Reuses the *exact* prompt that generated the original image (now stored on the generate-step `AIRun`'s metadata, not just the craft-prompt step's), skips re-crafting, creates a brand-new `AIRun` + `ProductAsset` linked back via `derived_from_asset_id`, leaves the original completely untouched, and requires independent approval (never inherits the original's approval state).
- **Prompt visibility** — `ProductAssetRead` now exposes `image_prompt`, `ai_run_id`, `derived_from_asset_id` (all derived from existing columns/JSONB — **no migration needed**). The UI shows a "View AI prompt" toggle on each asset card.
- **Source visibility** — new `SourceBadge` component distinguishes Uploaded / AI Generated / Processed on every asset card.
- **AI Studio UI** — added a variations selector and a per-variation review grid (each generated image gets its own independent approve/reject state, provider/model/cost line, and partial-failure notice if some variations failed).
- Confirmed the Gemini image-generation seam is already clean (`ProviderError("capability_not_supported", ...)`) — deliberately left unimplemented since a real integration wasn't verified against live API behavior, per the "don't fake it" instruction.
- Added ~25 new backend tests and ~12 new frontend tests covering variations, regeneration, cross-org isolation, partial-failure semantics, and prompt/source exposure. Full validation run: **339 backend tests passing, 108 frontend tests passing, `tsc --noEmit` clean, `next build` clean, `compileall` clean, SQLAlchemy `configure_mappers()` clean.** Zero schema/migration changes were required.

---

## 6. Explicit non-goals / things intentionally NOT done

Keep respecting these unless the user says otherwise:
- No MCP integration.
- No background job workers / task queues (everything is synchronous, in-request).
- No billing/subscription enforcement (models exist, logic doesn't).
- No real marketplace OAuth or real marketplace adapters (Etsy/Shopify/eBay/etc.) — only the deterministic `manual` adapter.
- No real Gemini image generation (clean stub only).
- No "processed" asset pipeline (background removal, upscaling, etc.) — `process_product_asset()` deliberately raises `NotImplementedError` as an interface placeholder.
- No AI content is ever auto-approved or auto-published anywhere in the system.

---

## 7. Suggested next steps (not started, for the next assistant to pick up if asked)

- Wire a real second image provider (once chosen) behind the existing `AIProvider.generate_image` seam — the seam is ready; nothing else should need to change (graph nodes, services, routes, frontend business logic all stay provider-agnostic).
- Consider surfacing *which specific* variation failed and why in the AI Studio UI, not just a success count.
- Real marketplace adapter(s) beyond `manual`, once OAuth/credentials strategy is decided (explicitly out of scope until now).
- Billing/subscription enforcement using the existing `Plan`/`Subscription`/`UsageTracking` models.
- The `docs/architecture.md` file is stale (predates the agents/AI layer entirely) — worth rewriting or replacing with this document at some point.

---

## 8. How to verify the system still works

Backend: `cd backend && .venv\Scripts\python -m pytest -q` (expects a local Postgres test DB at `postgresql+psycopg2://postgres:postgres@localhost:5432/ai_commerce_os_test`; the test DB is created via `Base.metadata.create_all()`, not via Alembic, so `alembic check` against it will always report out-of-date — that's expected, not a real migration gap).
Frontend: `cd frontend && npx vitest run`, `npx tsc --noEmit`, `npx next build`.
