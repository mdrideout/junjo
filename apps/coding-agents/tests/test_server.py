from unittest.mock import Mock

import httpx

from junjo_coding_agents.codex_telemetry import CodexTelemetry
from junjo_coding_agents.server import create_app


async def test_stateless_mcp_requests_preserve_execution_until_process_shutdown(runtime):
    provider = Mock()
    app = create_app(runtime, CodexTelemetry(runtime), provider)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://localhost:26156",
            headers={"Accept": "application/json, text/event-stream"},
        ) as client:

            async def call(name, arguments):
                response = await client.post(
                    "/mcp",
                    json={
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "tools/call",
                        "params": {"name": name, "arguments": arguments},
                    },
                )
                response.raise_for_status()
                body = response.json()["result"]
                assert not body.get("isError"), body
                return body["structuredContent"]

            started = await call("start_execution", {"capture": False})
            step = await call("start_review", {"execution_id": started["execution_id"], "fixture": "correct"})
            assert step["status"] == "work"
            second = await call(
                "complete_step",
                {"request_id": step["request_id"], "result": {"has_bug": False, "explanation": "Correct"}},
            )
            assert second["status"] == "work"
            provider.shutdown.assert_not_called()
            assert runtime.executions[started["execution_id"]].status == "running"
    provider.shutdown.assert_called_once()
    assert runtime.executions[started["execution_id"]].status == "cancelled"
