"""Alternating, sequential baseline/candidate measurements; no builds overlap."""
import json
import os
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[5]
EVIDENCE = Path(__file__).resolve().parents[1]
BASE = Path('/tmp/junjo-composable-stores-1faadb5')
COMMANDS = []


def run(command, *, name, environment=None):
    COMMANDS.append({'name': name, 'argv': command, 'benchmark_environment': environment or {}})
    (EVIDENCE / 'commands.json').write_text(json.dumps(COMMANDS, indent=2) + '\n')
    with (EVIDENCE / f'{name}.log').open('w') as log:
        subprocess.run(command, cwd=REPO, env={**os.environ, **(environment or {})},
                       stdout=log, stderr=subprocess.STDOUT, check=True)
    print(name, 'completed', flush=True)


for case, count, warmup in [('scalar', 30000, 1000), ('workflow', 600, 30)]:
    for round_number in range(1, 4):
        for variant in (['baseline', 'candidate'] if round_number % 2 else ['candidate', 'baseline']):
            source = BASE if variant == 'baseline' else REPO
            name = f'paired-{variant}-{case}-{round_number}'
            run(['docker', 'run', '--rm', '--cpus', '0.5', '--memory', '350m', '--memory-swap', '350m',
                 '-v', f'{source}:/repo:ro', '-v', f'{EVIDENCE}:/evidence',
                 '-e', 'PYTHONPATH=/repo/sdks/python/src', '--entrypoint', 'python',
                 'sha256:07ba1d278698e2c2024ac5f32135a779bfead1246ed3e5dc6e6b46cacc905989',
                 '/repo/sdks/python/benchmarks/store_ownership.py', '--case', case,
                 '--iterations', str(count), '--warmup-iterations', str(warmup), '--size', '128',
                 '--label', name, '--output', f'/evidence/{name}.json'], name=name)

for round_number in range(1, 4):
    for variant in (['baseline', 'candidate'] if round_number % 2 else ['candidate', 'baseline']):
        source = BASE if variant == 'baseline' else REPO
        name = f'paired-studio-{variant}-{round_number}'
        environment = {
            'JUNJO_BENCHMARK_COMPOSE_OVERLAY': str(EVIDENCE / 'reproduce' / f'{variant}.yaml'),
            'JUNJO_BENCHMARK_PROJECT_NAME': 'junjo-composable-compare',
            'JUNJO_STORE_BENCHMARK_FIXTURE': str(source / 'contracts/telemetry/fixtures/agent/producer/tool_invokes_nested_workflow.json'),
        }
        run(['uv', 'run', '--project', 'apps/studio/backend', 'python',
             str(EVIDENCE / 'reproduce/studio_evidence.py'), '--skip-build', '--skip-revocation',
             '--wal-probe-spans', '0', '--exporters', '4', '--exports-per-exporter', '1000',
             '--spans-per-export', '6', '--export-interval-ms', '10', '--query-workers', '2',
             '--implementation-label', variant, '--output', str(EVIDENCE / f'{name}.json')],
            name=name, environment=environment)
