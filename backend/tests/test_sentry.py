from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from app.core import sentry as sentry_module

BACKEND_DIR = Path(__file__).resolve().parents[1]


# ---- configure_sentry() (fast, focused, no subprocess) --------------------------


def test_configure_sentry_is_a_noop_without_a_dsn(monkeypatch):
    monkeypatch.setattr(sentry_module.settings, "sentry_dsn", None)
    called = False

    def fake_init(**kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr("sentry_sdk.init", fake_init)

    sentry_module.configure_sentry()

    assert called is False


def test_configure_sentry_is_a_noop_with_an_empty_dsn(monkeypatch):
    # Mirrors how a real deployment might leave SENTRY_DSN="" set rather
    # than fully unset -- same "feature inactive" behavior either way.
    monkeypatch.setattr(sentry_module.settings, "sentry_dsn", "")
    called = False

    def fake_init(**kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr("sentry_sdk.init", fake_init)

    sentry_module.configure_sentry()

    assert called is False


def test_configure_sentry_initializes_with_the_expected_options_when_a_dsn_is_set(monkeypatch):
    monkeypatch.setattr(sentry_module.settings, "sentry_dsn", "https://abc@o0.ingest.sentry.io/0")
    monkeypatch.setattr(sentry_module.settings, "app_env", "test-env")
    captured: dict = {}

    def fake_init(**kwargs):
        captured.update(kwargs)

    monkeypatch.setattr("sentry_sdk.init", fake_init)

    sentry_module.configure_sentry()

    assert captured["dsn"] == "https://abc@o0.ingest.sentry.io/0"
    assert captured["environment"] == "test-env"
    # Error tracking only -- no performance tracing, and deliberately not
    # copying Sentry's onboarding default of send_default_pii=True.
    assert captured["send_default_pii"] is False
    assert "traces_sample_rate" not in captured


# ---- The app actually boots, both with and without a DSN ------------------------
#
# Run in a genuinely separate process (not just re-importing app.main in this
# already-warm test session, which Python would just serve from its module
# cache) so this is a real test of "does the app's actual startup sequence
# -- Settings() loading, the configure_sentry() call, FastAPI construction --
# succeed end-to-end" in each configuration, the same way it would on a real
# deployment or in CI (which never has a DSN set at all).
#
# Run with cwd set to a directory that has no .env of its own (using
# PYTHONPATH to still make `app` importable), rather than backend/ itself:
# backend/.env is a real, gitignored local file that (for this repo, right
# now) has a real SENTRY_DSN in it, and pydantic-settings' env_file loading
# is resolved relative to cwd -- if this ran from backend/, the "unset"
# case couldn't be produced by clearing the SENTRY_DSN env var, since an
# empty-string env var is ignored by pydantic-settings and falls through to
# whatever backend/.env already has (confirmed empirically, not assumed).
# With no .env reachable at all, the environment dict below is the only
# source of truth for SENTRY_DSN, in both directions.


def _run_app_boot(tmp_path, env_overrides: dict) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env.pop("SENTRY_DSN", None)  # never inherit a real DSN from the host shell
    env["PYTHONPATH"] = str(BACKEND_DIR)
    env.update(env_overrides)
    return subprocess.run(
        [sys.executable, "-c", "import app.main; print('BOOT_OK')"],
        cwd=str(tmp_path),
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_app_boots_without_a_sentry_dsn(tmp_path):
    result = _run_app_boot(tmp_path, env_overrides={})

    assert result.returncode == 0, result.stderr
    assert "BOOT_OK" in result.stdout


def test_app_boots_with_a_sentry_dsn_configured(tmp_path):
    # A syntactically valid but non-real DSN -- sentry_sdk.init() itself
    # never makes a network call (only capturing/flushing an actual event
    # does, and nothing here raises), so this stays exactly as
    # network-free as every other test in this suite.
    result = _run_app_boot(
        tmp_path, env_overrides={"SENTRY_DSN": "https://abcabcabcabcabcabcabcabcabcabc@o0.ingest.sentry.io/0"}
    )

    assert result.returncode == 0, result.stderr
    assert "BOOT_OK" in result.stdout
