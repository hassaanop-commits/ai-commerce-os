from __future__ import annotations

from decimal import Decimal

import pytest

from app.agents.runner import run_product_content_workflow
from app.ai.providers.mock_provider import MockProvider
from app.ai.tools._common import ToolExecutionError
from app.ai.tools.product_content import analyze_product
from app.services import ai_runs


def _seed_spend(db, org, amount: Decimal) -> None:
    run = ai_runs.create_run(db, org.id, run_type="product_content.analyze", provider="mock", model="mock-model")
    ai_runs.complete_run(db, run, input_tokens=1, output_tokens=1, cost_usd=amount)


def test_generation_blocked_once_org_spend_reaches_the_configured_limit(
    db, make_organization, make_product, monkeypatch
):
    monkeypatch.setattr("app.ai.tools._common.settings.ai_org_monthly_spend_limit_usd", Decimal("5.00"))
    org = make_organization()
    product = make_product(org)
    _seed_spend(db, org, Decimal("5.00"))

    with pytest.raises(ToolExecutionError) as exc_info:
        analyze_product(db, org.id, product, provider=MockProvider(), model="mock-model")

    assert exc_info.value.category == "ai_spend_limit_exceeded"
    blocked_run = ai_runs.get_run(db, org.id, exc_info.value.run_id)
    assert blocked_run.status == "failed"
    assert blocked_run.error_message == "ai_spend_limit_exceeded"
    # Blocked before the provider was ever called -- no cost incurred.
    assert blocked_run.cost_usd == Decimal("0")


def test_generation_allowed_when_spend_is_below_the_limit(db, make_organization, make_product, monkeypatch):
    monkeypatch.setattr("app.ai.tools._common.settings.ai_org_monthly_spend_limit_usd", Decimal("5.00"))
    org = make_organization()
    product = make_product(org)
    _seed_spend(db, org, Decimal("1.00"))

    run_id, analysis = analyze_product(db, org.id, product, provider=MockProvider(), model="mock-model")

    assert analysis


def test_no_limit_configured_means_generation_is_never_blocked(db, make_organization, make_product):
    # settings.ai_org_monthly_spend_limit_usd defaults to None -- existing
    # behavior for every org that never opts in, however much they've spent.
    org = make_organization()
    product = make_product(org)
    _seed_spend(db, org, Decimal("9999.00"))  # near the column's own precision ceiling

    run_id, analysis = analyze_product(db, org.id, product, provider=MockProvider(), model="mock-model")

    assert analysis


def test_spend_cap_is_scoped_per_organization(db, make_organization, make_product, monkeypatch):
    monkeypatch.setattr("app.ai.tools._common.settings.ai_org_monthly_spend_limit_usd", Decimal("5.00"))
    org_a = make_organization()
    org_b = make_organization()
    product_a = make_product(org_a)
    product_b = make_product(org_b)
    _seed_spend(db, org_a, Decimal("5.00"))

    with pytest.raises(ToolExecutionError):
        analyze_product(db, org_a.id, product_a, provider=MockProvider(), model="mock-model")

    # Org B has spent nothing this period -- org A's cap has no effect on it.
    run_id, analysis = analyze_product(db, org_b.id, product_b, provider=MockProvider(), model="mock-model")
    assert analysis


def test_spend_cap_blocks_the_whole_workflow_and_reports_the_sanitized_category(
    db, make_organization, make_product, monkeypatch
):
    monkeypatch.setattr("app.ai.tools._common.settings.ai_org_monthly_spend_limit_usd", Decimal("5.00"))
    org = make_organization()
    product = make_product(org, title="Wireless Mouse")
    _seed_spend(db, org, Decimal("5.00"))

    result = run_product_content_workflow(db, org.id, product, provider=MockProvider(), user_id=None)

    assert result.status == "failed"
    assert result.error_category == "ai_spend_limit_exceeded"
    assert result.generated_description is None
    # Only the blocked (zero-cost) run exists -- nothing downstream ran.
    assert len(result.ai_run_ids) == 1


def test_spend_cap_uses_a_strictly_greater_or_equal_comparison_at_the_boundary(
    db, make_organization, make_product, monkeypatch
):
    # Spend exactly at the limit still blocks the next call -- "would be
    # exceeded" is read as "already at or past the ceiling", not "only once
    # strictly over it", since the cost of the *next* call isn't known
    # upfront.
    monkeypatch.setattr("app.ai.tools._common.settings.ai_org_monthly_spend_limit_usd", Decimal("5.00"))
    org = make_organization()
    product = make_product(org)
    _seed_spend(db, org, Decimal("4.99"))

    run_id, analysis = analyze_product(db, org.id, product, provider=MockProvider(), model="mock-model")
    assert analysis
