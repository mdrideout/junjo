"""Regression tests for fail-closed Studio E2E orchestration."""

import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

ORCHESTRATION_DIRECTORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ORCHESTRATION_DIRECTORY))

import generate_data as orchestration  # noqa: E402


def metadata(*, failed_processes: int = 0) -> dict:
    return {"results": {"failed_processes": failed_processes}}


class GenerateDataMainTests(unittest.TestCase):
    @staticmethod
    def run_main(result: dict) -> int:
        with patch.object(
            orchestration,
            "generate_data",
            new=AsyncMock(return_value=result),
        ):
            return orchestration.main(
                [
                    "--num-services",
                    "1",
                    "--num-cycles",
                    "1",
                    "--concurrency",
                    "1",
                    "--workflows-per-process",
                    "1",
                ]
            )

    def test_successful_children_exit_zero(self) -> None:
        self.assertEqual(self.run_main(metadata()), 0)

    def test_child_failure_exits_nonzero(self) -> None:
        self.assertEqual(self.run_main(metadata(failed_processes=1)), 1)

    def test_load_dimensions_must_be_positive(self) -> None:
        options = (
            "--num-services",
            "--num-cycles",
            "--duration",
            "--concurrency",
            "--workflows-per-process",
        )
        for option in options:
            with self.subTest(option=option), self.assertRaises(SystemExit):
                arguments = ["--num-services", "1", "--num-cycles", "1"]
                index = arguments.index(option) if option in arguments else None
                if index is None:
                    arguments.extend([option, "0"])
                else:
                    arguments[index + 1] = "0"
                orchestration.parse_args(arguments)

    def test_low_resource_default_runs_one_workflow_per_process(self) -> None:
        args = orchestration.parse_args(["--num-services", "1", "--num-cycles", "1"])
        self.assertEqual(args.workflows_per_process, 1)


class RunWorkflowTests(unittest.IsolatedAsyncioTestCase):
    async def test_locked_app_project_is_invoked(self) -> None:
        process = AsyncMock()
        process.returncode = 0
        process.communicate.return_value = (b"workflow completed\n", b"")

        with patch.object(
            orchestration.asyncio,
            "create_subprocess_exec",
            new=AsyncMock(return_value=process),
        ) as create_process:
            result = await orchestration.run_workflow(
                "test-service",
                workflow_num=2,
                config_path="config.yaml",
                workflows_per_process=3,
            )

        self.assertEqual(result.return_code, 0)
        create_process.assert_awaited_once_with(
            "uv",
            "run",
            "--frozen",
            "python",
            "main.py",
            "--config",
            "config.yaml",
            "--service-name",
            "test-service",
            "--num-workflows",
            "3",
            cwd=ORCHESTRATION_DIRECTORY.parent / "app",
            stdout=orchestration.asyncio.subprocess.PIPE,
            stderr=orchestration.asyncio.subprocess.PIPE,
        )


if __name__ == "__main__":
    unittest.main()
