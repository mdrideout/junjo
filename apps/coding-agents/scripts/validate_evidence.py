"""Check exported artifacts from the two-native-worker live proof.

This does not create evidence or perform reasoning. Capture the bridge's
/evidence/{execution_id} response after Codex exits and flushes its telemetry.
"""

import argparse
import json
from pathlib import Path


def validate(evidence: dict, spans: list[dict]) -> dict:
    assert evidence["capture"] and evidence["status"] == "completed", evidence
    runs = evidence["runs"]
    assert len(runs) == 2 and all(r["status"] == "completed" for r in runs)
    assert len({r["workflow_run_id"] for r in runs}) == 2
    assert {r["state"]["findings"]["has_bug"] for r in runs} == {True, False}
    work = evidence["work"]
    assert len(work) == 4 and all(w["submitted"] and w["model_spans"] > 0 for w in work), work

    roots = [s for s in spans if s["attributes"].get("coding_agent.execution.id") == evidence["execution_id"]]
    assert len(roots) == 1 and roots[0]["attributes"]["coding_agent.outcome"] == "completed"
    root = roots[0]
    spans = [s for s in spans if s["context"]["trace_id"] == root["context"]["trace_id"]]
    by_id = {s["context"]["span_id"]: s for s in spans}
    workflows = [s for s in spans if s["name"] == "FunctionReview"]
    assert len(workflows) == 2
    for workflow in workflows:
        worker = by_id[workflow["parent_id"]]
        assert worker["name"] == "Codex worker" and worker["parent_id"] == root["context"]["span_id"]
    models = [s for s in spans if s["name"] == "Codex model request"]
    assert {s["attributes"]["coding_agent.request.id"] for s in models} == {w["request_id"] for w in work}
    assert len({s["attributes"]["coding_agent.session.id"] for s in models}) == 2
    for model in models:
        assert model["links"] and "junjo.span_type" not in model["attributes"]
        assert model["attributes"]["coding_agent.source.operation"] == "responses_websocket.stream_request"
        node = by_id[model["parent_id"]]
        assert node["name"] in {"InspectFunction", "ExplainCorrection", "ExplainCorrectness"}
    assert {s["name"] for s in spans} >= {"ExplainCorrection", "ExplainCorrectness"}
    return {
        "execution_id": evidence["execution_id"],
        "trace_id": root["context"]["trace_id"].removeprefix("0x"),
        "workflow_runs": len(workflows),
        "accepted_steps": len(work),
        "model_spans": len(models),
        "native_worker_sessions": sorted({s["attributes"]["coding_agent.session.id"] for s in models}),
        "host_versions": sorted({s["attributes"]["coding_agent.host.version"] for s in models}),
        "span_count": len(spans),
        "result": "passed",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-file", required=True, type=Path)
    parser.add_argument("--spans-file", required=True, type=Path)
    args = parser.parse_args()
    evidence = json.loads(args.evidence_file.read_text())
    spans = [json.loads(line) for line in args.spans_file.read_text().splitlines()]
    print(json.dumps(validate(evidence, spans), indent=2))


if __name__ == "__main__":
    main()
