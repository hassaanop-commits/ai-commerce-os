from __future__ import annotations

from decimal import Decimal

from app.services import ai_runs


def test_create_run_starts_pending(db, make_organization):
    org = make_organization()

    run = ai_runs.create_run(db, org.id, run_type="product_content.analyze", provider="mock", model="mock-model")

    assert run.status == "pending"
    assert run.started_at is None
    assert run.completed_at is None
    assert run.input_tokens == 0
    assert run.output_tokens == 0


def test_mark_running_transitions_state(db, make_organization):
    org = make_organization()
    run = ai_runs.create_run(db, org.id, run_type="product_content.analyze", provider="mock", model="mock-model")

    ai_runs.mark_running(db, run)

    assert run.status == "running"
    assert run.started_at is not None


def test_complete_run_records_usage_and_cost(db, make_organization):
    org = make_organization()
    run = ai_runs.create_run(db, org.id, run_type="product_content.analyze", provider="mock", model="mock-model")
    ai_runs.mark_running(db, run)

    ai_runs.complete_run(
        db, run, input_tokens=10, output_tokens=20, cost_usd=Decimal("0.001234"), output_metadata={"analysis": "ok"}
    )

    assert run.status == "succeeded"
    assert run.completed_at is not None
    assert run.input_tokens == 10
    assert run.output_tokens == 20
    assert run.cost_usd == Decimal("0.001234")
    assert run.metadata_["analysis"] == "ok"


def test_fail_run_stores_sanitized_category_only(db, make_organization):
    org = make_organization()
    run = ai_runs.create_run(db, org.id, run_type="product_content.analyze", provider="mock", model="mock-model")
    ai_runs.mark_running(db, run)

    ai_runs.fail_run(db, run, category="provider_timeout", detail="raw provider detail that must not be exposed")

    assert run.status == "failed"
    assert run.error_message == "provider_timeout"
    assert run.completed_at is not None
    # The raw detail is allowed to live in metadata for server-side debugging,
    # but error_message itself -- what a client sees -- is only ever the category.
    assert run.metadata_["error_detail"] == "raw provider detail that must not be exposed"


def test_fail_run_falls_back_to_unknown_error_for_unrecognized_category(db, make_organization):
    org = make_organization()
    run = ai_runs.create_run(db, org.id, run_type="product_content.analyze", provider="mock", model="mock-model")

    ai_runs.fail_run(db, run, category="some_raw_exception_type_never_seen_before")

    assert run.error_message == "unknown_error"


def test_workflow_id_is_stamped_into_metadata(db, make_organization):
    import uuid

    org = make_organization()
    workflow_id = uuid.uuid4()

    run = ai_runs.create_run(
        db, org.id, run_type="product_content.analyze", provider="mock", model="mock-model", workflow_id=workflow_id
    )

    assert run.metadata_["workflow_id"] == str(workflow_id)


def test_get_run_is_organization_scoped(db, make_organization):
    org_a = make_organization()
    org_b = make_organization()
    run = ai_runs.create_run(db, org_a.id, run_type="product_content.analyze", provider="mock", model="mock-model")

    assert ai_runs.get_run(db, org_a.id, run.id).id == run.id

    import pytest

    with pytest.raises(ai_runs.AIRunNotFoundError):
        ai_runs.get_run(db, org_b.id, run.id)
