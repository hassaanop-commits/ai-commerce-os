from __future__ import annotations

from app.core.config import settings


def configure_sentry() -> None:
    """Initialize Sentry error tracking -- but only when a DSN is actually
    configured. Unset (the default) means this is a complete no-op:
    sentry_sdk.init() is never called, so local dev without a DSN and the
    full test suite never attempt to init or phone home. Call once at
    process start (app.main, before the FastAPI app is constructed), same
    place/pattern as app.core.logging.configure_logging().
    """
    if not settings.sentry_dsn:
        return

    import sentry_sdk

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.app_env,
        # Error tracking only -- no performance/trace sampling. Omitting
        # traces_sample_rate (rather than setting it to 0) keeps the
        # performance-monitoring instrumentation off entirely instead of
        # just sampling it down to nothing.
        #
        # auto_session_tracking is also turned off, for the same "error
        # tracking only" reason -- it defaults to True (verified against
        # sentry_sdk.consts.Client.__init__) and is a third, separate
        # feature from error capture: release-health session telemetry that
        # gets sent for every process regardless of whether any error ever
        # occurs. Confirmed by direct observation, not assumed: with this
        # left at its default, `import app.main` alone -- with no request
        # made, no exception raised, nothing captured -- still queued 2
        # envelopes that a real HTTP flush to Sentry's ingest endpoint sent
        # at process exit. That's exactly the kind of ambient phone-home
        # this codebase's testing discipline rules out elsewhere ("no test
        # makes a real network call" -- see docs/architecture.md); the full
        # backend test suite imports app.main (and therefore calls this
        # function, with a real DSN, from backend/.env) on every local run.
        auto_session_tracking=False,
        #
        # send_default_pii is left at its explicit False rather than the
        # True shown in Sentry's own onboarding snippet: the SDK's own
        # internal default is already "off" (verified against
        # sentry_sdk.consts.DEFAULT_OPTIONS), and this project has been
        # deliberate everywhere else about what leaves the system --
        # sanitized AI/marketplace error categories, raw provider
        # exceptions kept server-side only (see app/ai/providers/base.py).
        # Sending default PII would mean request headers/cookies and user
        # IPs on every captured event, which is a materially different
        # (and unreviewed) data-sharing decision from "send an error
        # summary" -- not something to opt into by copying a snippet.
        send_default_pii=False,
        # No failed_request_status_codes override here -- deliberately.
        # Checked against the installed SDK rather than assumed
        # (sentry_sdk.integrations.starlette._DEFAULT_FAILED_REQUEST_STATUS_CODES,
        # pinned via requirements.txt): it's already exactly {500..599}, so
        # this app's expected 401/403/404/409/429 responses (bad login,
        # permission denied, not found, conflict, rate limited) are never
        # reported -- only genuine 5xx failures are. That default is what's
        # relied on here, not reproduced, since hand-rebuilding "every int
        # 500-599" inline is one easy off-by-something away from silently
        # disabling reporting entirely (e.g. passing a range object instead
        # of the expanded set of ints -- a set containing one range is not
        # a set containing those ints, and `x in that_set` would then never
        # match anything). If a future SDK upgrade ever changes that
        # default, it changes here too, on purpose, at review time.
        #
        # This setting is also not what protects the sanitized AI/
        # marketplace error path: those (ProviderError, MarketplaceError/
        # ToolExecutionError) are caught well before the HTTP layer --
        # app/ai/tools/_common.py:start_and_call() and the
        # `except MarketplaceError` blocks in app/api/v1/listings.py always
        # turn them into a normal response, never an HTTPException -- so
        # they never reach Sentry's hook at all, regardless of this setting.
    )
