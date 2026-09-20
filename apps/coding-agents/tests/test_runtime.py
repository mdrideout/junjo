import asyncio

import pytest
from pydantic import ValidationError


async def perform(runtime, execution_id, fixture, has_bug):
    first = await runtime.review(execution_id, fixture)
    second = await runtime.complete(first["request_id"], {"has_bug": has_bug, "explanation": "Inspection evidence"})
    result = await runtime.complete(second["request_id"], {"explanation": "Final explanation"})
    return first, second, result


async def test_concurrent_native_workflows_and_isolated_state(runtime, exporter):
    execution = runtime.start(True)
    a, b = await asyncio.gather(
        perform(runtime, execution["execution_id"], "buggy", True),
        perform(runtime, execution["execution_id"], "correct", False),
    )
    result = await runtime.finish(execution["execution_id"])
    assert result["status"] == "completed"
    assert a[2]["workflow_run_id"] != b[2]["workflow_run_id"]
    assert a[2]["state"]["findings"]["has_bug"] is True
    assert b[2]["state"]["findings"]["has_bug"] is False
    spans = exporter.get_finished_spans()
    assert len({s.context.trace_id for s in spans}) == 1
    assert [s.name for s in spans].count("FunctionReview") == 2
    assert [s.name for s in spans].count("InspectFunction") == 2
    assert [s.name for s in spans].count("ExplainCorrection") == 1
    assert [s.name for s in spans].count("ExplainCorrectness") == 1
    assert any("junjo.state" in str(s.attributes) or "store" in str(s.attributes) for s in spans)


async def test_capture_false_suppresses_native_and_integration_spans(runtime, exporter):
    execution = runtime.start(False)
    await perform(runtime, execution["execution_id"], "correct", False)
    await runtime.finish(execution["execution_id"])
    assert exporter.get_finished_spans() == ()


async def test_invalid_output_does_not_advance_and_duplicate_submission_rejected(runtime):
    execution = runtime.start(True)
    step = await runtime.review(execution["execution_id"], "correct")
    with pytest.raises(ValidationError):
        await runtime.complete(step["request_id"], {"has_bug": "false", "explanation": "Bad type"})
    assert not runtime.work[step["request_id"]].submitted
    second = await runtime.complete(step["request_id"], {"has_bug": False, "explanation": "Valid"})
    with pytest.raises(ValueError, match="no longer pending"):
        await runtime.complete(step["request_id"], {"has_bug": False, "explanation": "Duplicate"})
    await runtime.complete(second["request_id"], {"explanation": "Done"})
    await runtime.finish(execution["execution_id"])


async def test_cancel_closes_pending_work_and_rejects_late_results(runtime):
    execution = runtime.start(True)
    step = await runtime.review(execution["execution_id"], "buggy")
    with pytest.raises(ValueError, match="still running"):
        await runtime.finish(execution["execution_id"])
    result = await runtime.finish(execution["execution_id"], cancel=True)
    assert result["status"] == "cancelled"
    assert result["runs"][0]["status"] == "cancelled"
    with pytest.raises(ValueError, match="no longer pending"):
        await runtime.complete(step["request_id"], {"has_bug": True, "explanation": "Late"})
    assert not runtime.work[step["request_id"]].receipt
