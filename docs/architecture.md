# Architecture

This describes the system as it exists today. It is factual, not aspirational — see
[Non-goals](#non-goals) for what is deliberately not built yet.

## Layers

- **frontend/** — Next.js (App Router, TypeScript). Talks to the backend over HTTP via
  `NEXT_PUBLIC_API_URL`. Component tests use Vitest + Testing Library; no test makes a
  real network call (API clients are mocked at the module boundary).
- **backend/** — FastAPI application. Owns all database access and all AI/marketplace
  provider calls. Runs entirely synchronously, in-request — there is no background
  worker or job queue anywhere in this codebase.
- **PostgreSQL** — the system of record (`docker-compose.yml` for local dev). SQLAlchemy
  2.0 ORM (`app/db/`), Alembic migrations (`backend/alembic/`).

```
frontend  -->  backend API (app/api/v1/)  -->  services (app/services/)  -->  PostgreSQL
                                           \->  agents/LangGraph (app/agents/)
                                                 \->  AI providers (app/ai/providers/)
                                           \->  marketplace adapters (app/marketplaces/)
```

## Module boundaries

- `app/api/v1/` — HTTP routing only: auth/permission dependencies, request validation,
  translating service exceptions to HTTP status codes, audit-event recording. No
  business logic lives here.
- `app/services/` — business logic and all database queries. Every organization-owned
  query is built through `org_scoped()` (`app/db/tenant.py`) rather than querying a
  model directly, so the tenant filter can't be left out by mistake.
- `app/models/` — SQLAlchemy ORM models.
- `app/schemas/` — Pydantic request/response schemas (the API's actual public contract).
- `app/agents/` — LangGraph state graphs (`graphs/`) plus a `runner.py` that resolves
  providers/models and invokes a graph per request. Node functions are closures over a
  `db` session and resolved providers (built fresh per invocation by the runner) — the
  state itself (`app/agents/state.py`) stays a plain, JSON-serializable `TypedDict`.
- `app/ai/providers/` — the provider abstraction (below).
- `app/ai/tools/` — the actual AI operations (analyze, generate description/title/tags,
  craft an image prompt, generate an image). Framework-agnostic on purpose: these
  functions know nothing about FastAPI or LangGraph, so a graph node is a thin wrapper
  around one of these, and (per an existing code comment) a future MCP tool wrapper
  could call the same functions unchanged — no MCP integration exists today.
- `app/ai/pricing.py` — flat cost-estimation tables for observability (`AIRun.cost_usd`),
  not a billing system.
- `app/marketplaces/` — the marketplace adapter abstraction (below).
- `app/db/` — engine/session, declarative base, `org_scoped()` tenant-scoping helper.

## Multi-tenancy enforcement

Every request that touches organization-owned data goes through `require_member` /
`require_admin` / `require_owner` (`app/api/deps.py`), which resolve the caller's
`OrganizationMember` row for the `{org_id}` in the URL and check `role.rank` (1=owner,
2=admin, 3=member; lower rank = more privileged). Every service-layer query for
`Product`, `ProductAsset`, `AIRun`, `Listing`, `MarketplaceConnection` is built via
`org_scoped(Model, organization_id)`. A handful of internal service helpers (e.g.
`product_assets._next_position`, `_clear_existing_primary`) filter by `product_id`
alone without re-applying `org_scoped` — this is safe because they're only ever called
after the caller has already resolved that `product_id` through an org-scoped
`get_product`/`get_asset` lookup, never reachable directly from a route. Cross-org
access is covered by tests across every resource (products, assets, AI runs, listings,
marketplace connections).

## AI provider abstraction

```
AIProvider (Protocol, app/ai/providers/base.py)
    .complete(system, prompt, model)       -> CompletionResult
    .generate_image(prompt, model, size)   -> ImageResult
    raises ProviderError(category, message) on failure
        |
        +-- AnthropicProvider   (text only)
        +-- GeminiProvider      (text; generate_image raises
        |                        ProviderError("capability_not_supported", ...) --
        |                        no real Gemini image call is attempted)
        +-- OpenAIImageProvider (generate_image only, plain httpx POST against
        |                        the REST endpoint -- no openai SDK dependency)
        +-- MockProvider        (both, deterministic, network-free, used by every test)
```

`get_default_ai_provider()` / `get_default_image_provider()` (`app/ai/providers/__init__.py`)
are FastAPI dependencies resolved from `settings.ai_default_provider` /
`settings.ai_image_provider` — text and image capabilities can resolve to different
providers, and both seams are overridden with `MockProvider` in every test. Adding a
new provider means implementing this one Protocol; graph nodes, tools, services, and
API routes never know which provider is active.

### Per-task model routing

`app/agents/runner.py` maps two cost tiers — "utility" (analysis, image-prompt
crafting) and "content" (customer-facing description text) — to provider-specific
model IDs (`_UTILITY_MODEL_BY_PROVIDER` / `_CONTENT_MODEL_BY_PROVIDER`), resolved once
per provider name. A model string valid for one provider is meaningless to another, so
this resolution happens in exactly one place; callers below it always take a plain
`model: str`.

### Sanitized error categories

`ProviderError(category, message)` is the only exception any provider raises. `category`
is always one of a small closed set defined in `app/services/ai_runs.py`:

```
provider_not_configured, provider_timeout, provider_rate_limited, provider_error,
invalid_response, capability_not_supported, content_policy_violation, unknown_error
```

Only `category` is ever written to `AIRun.error_message` (`ai_runs.fail_run`, which
falls back to `unknown_error` for anything outside the closed set). The raw underlying
SDK exception is chained via `from exc`/`__cause__` for server-side logging only and is
never persisted or returned to a client. `ai_runs.describe_error_category(category)`
maps each category to a fixed, human-readable sentence (e.g. "AI provider is not
configured.") — also never built from provider-supplied text, so a per-request or
per-variation error message is structurally incapable of reflecting whatever a
provider's exception actually said. `fail_run`'s optional `detail` (stored under
`AIRun.metadata_["error_detail"]`, and so visible via `AIRunRead.metadata`) is always
`str(ProviderError)` — the provider's own developer-authored safe message, per the
`ProviderError` contract — never a raw traceback or SDK error repr. This is a contract
enforced by convention across the three real providers, not by the type system;
`test_metadata_contains_only_safe_keys` and the frontend's own `describeFailure()`
mapping both assume it holds.

### Retry / backoff

`app/ai/tools/_common.py:start_and_call()` wraps every provider call: creates the
`AIRun` row, marks it running, invokes the call, and retries only categories in
`RETRYABLE_ERROR_CATEGORIES` (`provider_timeout`, `provider_rate_limited`,
`provider_error` — genuinely transient conditions) with bounded exponential backoff
plus jitter (`compute_backoff_delay`), up to `settings.ai_max_retries` additional
attempts. Every other category is treated as permanent and fails immediately. One
logical operation always produces exactly one `AIRun` row regardless of how many
internal attempts it took; `attempts`/`retries` counts are recorded in
`AIRun.metadata_` when a retry occurred.

## LangGraph graphs

Two graphs, both built fresh per request by `app/agents/runner.py` (never shared/reused
across requests — providers, `db`, and storage are closed over per invocation):

- **`app/agents/graphs/product_content.py`** — `analyze -> generate_description ->
  generate_title -> generate_tags`, one provider throughout, each step
  short-circuiting to `END` on failure via a conditional edge. Each generated field
  (description/title/tags) is applied to the product independently via its own
  `apply-*` endpoint — nothing is written to the product automatically.
- **`app/agents/graphs/product_image.py`** — `craft_prompt -> generate_image`, using
  two providers deliberately (a text provider crafts the prompt; an image provider
  renders it). This graph handles exactly the single-image case.

### Image variations and regeneration (not graph-level)

Two capabilities were added as a thin layer *around* the existing graph, not by
reshaping it:

- **Variations** (`GenerateImageRequest.variations`, 1-4): `run_product_image_workflow`
  in `runner.py` uses the unchanged graph when `variations <= 1`. For more, it calls
  `generate_image_prompt` once directly (shared prompt) and then loops
  `generate_product_image` N times — each iteration is its own `AIRun` and, on
  success, its own `ProductAsset`. One variation failing doesn't abort the others; a
  fully-failed request produces zero fabricated assets. Every attempt (success or
  failure) is captured as a `VariationOutcome` (index, status, `ai_run_id`, and either
  an `asset_id` or an `error_category`), serialized into
  `GenerateImageResponse.variations` so a caller can see exactly which slot failed and
  why, not just an aggregate count.
- **Regenerate** (`POST .../ai/assets/{asset_id}/regenerate`,
  `run_product_image_regeneration`): reuses the *exact* prompt that produced the
  original image (now stored on the generate-step `AIRun`'s own metadata, not only the
  craft-prompt step's), skips prompt-crafting entirely, and produces a new `AIRun` +
  new `ProductAsset` linked back via `derived_from_asset_id`. The original asset is
  never modified; the new one starts `pending_review` like any other AI-generated
  asset and requires independent approval.

## Marketplace / listing pipeline

```
MarketplaceAdapter (Protocol, app/marketplaces/adapters/base.py)
    .create_listing(connection, payload) -> PublishResult
    .end_listing(connection, external_listing_id)
    raises MarketplaceError(category, message) on failure
        |
        +-- ManualMarketplaceAdapter  (deterministic, network-free -- the only
                                        marketplace adapter that exists today)
```

`Listing.status` transitions: `draft -> approved -> publishing -> active`, or
`-> error` on a publish/retry failure (recoverable via `retry_listing`), or
`active -> ended`. `create_draft` requires the product to already have an approved (or
`not_required`) primary asset (`NoApprovedPrimaryAssetError` otherwise) and the target
`MarketplaceConnection` to be connected. `MarketplaceError` follows the identical
sanitized-category pattern as `ProviderError` — same reasoning, same discipline.

## Data model

- **Auth/tenancy**: `Organization`, `OrganizationMember` (role + `status`), `Role`
  (`owner`/`admin`/`member`, rank 1/2/3), `User`, `Session`, `AuthToken`.
- **`Product`**: catalog item (`sku`, `title`, `description`, `price`, `status`, JSONB
  `metadata_` — used for e.g. AI-generated tags, since there's no dedicated tags
  column).
- **`ProductAsset`**: an image/video/document on a product.
  - `source`: `upload` | `ai_generated` | `processed`.
  - `approval_status`: `not_required` (uploads) | `pending_review` (AI-generated,
    always starts here) | `approved` | `rejected`. `approve_asset`/`reject_asset` are a
    one-way, one-shot transition (`InvalidApprovalTransitionError` otherwise).
  - `is_primary`: at most one true primary per product (partial unique index).
  - `ai_run_id`: the `AIRun` that generated this asset, if any.
  - `derived_from_asset_id`: self-referential — the asset this one was regenerated or
    (in a future phase) processed from.
  - **AI-generated images can never auto-approve or auto-become primary.** Enforced at
    three independent layers, each tested:
    1. Service layer — `update_asset()` raises `AssetNotApprovedError` when setting
       `is_primary=True` on anything not `approved`/`not_required`
       (`app/services/product_assets.py`).
    2. Database — `CHECK` constraint `ck_product_assets_primary_requires_approval`
       (`NOT is_primary OR approval_status IN ('approved','not_required')`) on the
       `product_assets` table (belt-and-suspenders against any future code path that
       forgets the service-layer check).
    3. Frontend — `AssetCard.tsx`'s `canBecomePrimary` gate hides the "Set primary"
       action entirely for a `pending_review`/`rejected` asset.
- **`AIRun`**: one row per provider call (text or image). `run_type`, `provider`,
  `model`, `input_tokens`/`output_tokens`, `cost_usd`, `status`
  (`pending`/`running`/`succeeded`/`failed`), `error_message` (sanitized category
  only), `metadata_` (JSONB — `workflow_id`, crafted `image_prompt`, retry counts,
  `error_detail`). This is the audit/history/cost-tracking backbone for all AI
  activity, surfaced in the AI Studio UI's generation history.
- **`Marketplace`, `MarketplaceConnection`, `Listing`** — see pipeline above.
- **`AuditLog`** — generic security/activity audit trail (actor, org, target,
  metadata, IP) for sensitive actions (approvals, generation, publish, etc.).
- **`Plan`, `Subscription`, `UsageTracking`** — models exist; no service or route
  anywhere reads or enforces them today (see Non-goals).

## Testing discipline

No test anywhere makes a real network call. Every backend test that would otherwise
call an AI provider or marketplace goes through `MockProvider` / `ManualMarketplaceAdapter`
via dependency overrides (`app/ai/providers/get_default_ai_provider` /
`get_default_image_provider`, `app/marketplaces` adapter resolution). `MockProvider`
supports a `"__fail__"` prompt sentinel and a `fail_times`/`fail_category` constructor
for deterministic retry-path testing. Every new capability ships with cross-org,
unauthorized-access, and negative-path tests alongside the happy path, on both backend
(pytest) and frontend (Vitest + Testing Library).

## Non-goals

Explicitly not built. Do not assume these exist without the user asking for them:

- **No MCP integration.** The AI tools layer is written to be framework-agnostic
  (a design comment in `app/ai/tools/product_content.py` notes a future MCP wrapper
  *could* call the same functions unchanged), but no MCP code exists.
- **No background job queue or worker.** No Celery/RQ/arq/Dramatiq/Huey/APScheduler
  dependency anywhere; every LangGraph workflow runs synchronously inside the FastAPI
  request that triggered it.
- **No billing/subscription enforcement.** `Plan`, `Subscription`, `UsageTracking`
  models exist; no code path reads or enforces them. `AIRun.cost_usd` /
  `app/ai/pricing.py` are observability-only estimates, not a billing source of truth.
- **No real marketplace OAuth or adapters beyond `manual`.** `ManualMarketplaceAdapter`
  is deterministic and network-free, proving the full
  connect -> draft -> approve -> publish -> end pipeline without any real marketplace
  account.
- **No real Gemini image generation.** `GeminiProvider.generate_image` cleanly raises
  `ProviderError("capability_not_supported", ...)` rather than attempting a call.
- **No "processed" asset pipeline.** `process_product_asset()`
  (`app/ai/tools/product_images.py`) deliberately raises `NotImplementedError` — the
  `source='processed'` and `derived_from_asset_id` columns exist for this future phase
  but nothing populates them yet.
