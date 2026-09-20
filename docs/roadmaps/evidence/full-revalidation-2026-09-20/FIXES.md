# Follow-up fixes and validation

Implemented after the full revalidation, on 2026-09-20. Intentional example
failures are preserved. No SDK execution code, telemetry contract, Studio
backend, ingestion, frontend, or Store semantics were changed.

## Correct Studio browser URL

The native OpenAI SDK example now supplies `http://localhost:26151` as
`JUNJO_STUDIO_URL`. Its OTLP target is unchanged. An HTTP request to the exact
value read from `.env.example` returned 200, HTML, and the frontend root element.
Existing private `.env` files are not rewritten by this source change.

## One generated contact identity

AI Chat now runs `CreateNameNode` before `CreateBioNode`. The biography Node
requires and passes the stored first and last names into its prompt. Persistence
and the Avatar Subflow keep their existing ownership and behavior.

The existing application integration test now checks that the biography prompt
contains the same full name persisted in the contact. The three standalone
biography evaluation inputs now include names, as the Node requires. The
quality judges and their pass criteria are unchanged. The example README
reflects the new graph order.

All four contact evaluations passed with each live provider: three biography
cases and one complete contact/profile/avatar coherence case, for eight passes
over Gemini and Grok. These successful samples do not guarantee that future
probabilistic output always passes its evaluator.

[Studio evidence](fixed-contact-evidence.json) independently verifies both new
full-Workflow traces:

- Grok: `9c4a0e687f860e9393369a2c04b08b59`, Isabella Martinez.
- Gemini: `2207bcc48670624965eed664d8887fcd`, Kylie Dvorak.
- Name commits at sequence 4; biography commits at sequence 5 and its starting
  state contains the canonical name. Each transition belongs to its actual Node.
- Persisted profile agrees with Workflow state; all span parents are present.
- Application and Avatar Subflow Stores reconstruct successfully and remain
  distinct.

## Declare the working Python patch versions

The constructor failure is in CPython's generic-alias machinery, which attempts
an optional `__orig_class__` assignment and historically failed to catch the
exception raised by frozen, slotted dataclasses. Source comparison establishes
the upstream fix between [3.11.8](https://github.com/python/cpython/blob/v3.11.8/Lib/typing.py)
and [3.11.9](https://github.com/python/cpython/blob/v3.11.9/Lib/typing.py), and
between [3.12.2](https://github.com/python/cpython/blob/v3.12.2/Lib/typing.py)
and [3.12.3](https://github.com/python/cpython/blob/v3.12.3/Lib/typing.py).

The package and example requirements now declare
`>=3.11.9,!=3.12.0,!=3.12.1,!=3.12.2`. This intentionally narrows support to
working patch versions; it does not make the old interpreters work. The
README, quickstart, release policy, changelog, workspace lockfile, repository
support-policy check, and CI agree. CI retains the latest 3.11/3.12 jobs and
adds their minimum supported patch versions.

No compatibility shim, new per-object field, instance dictionary, or runtime
workaround was introduced. Existing definition immutability and memory layout
are unchanged.

The full SDK suite passed on both new minimums, 3.11.9 and 3.12.3, as well as
3.13.13 and 3.14.3: **471 tests per interpreter**. A dry-run installation of the
built wheel under 3.11.6 correctly rejects the interpreter before installation.

## Additional validation

- SDK Ruff, ty, Griffe (1,504 public objects / 231 API pages), wheel and sdist
  builds, and Twine validation passed. Workspace lock check passed.
- AI Chat backend: 89 tests plus source type checking passed.
- Native OpenAI SDK example: 4 tests passed.
- OpenAI Agents example: 6 tests passed.
- Repository invariants and telemetry contract validation passed.
- Root tooling: 148 tests and 72 subtests passed.
- Website clean install, documentation assembly, full `validate` command,
  production build, and documentation parity passed (270 assembled documents).
- `git diff --check` passed.

The example suites were run in separate pytest processes because the two
OpenAI examples both name their test module `test_example.py`. Combining them
under pytest's default import mode caused a collection-name collision; separate
invocations passed without source changes to accommodate the harness.

The base joke workflow and its quality tests were not modified. Its package
metadata alone now matches the SDK's Python requirements. Studio runtime and
UI source were untouched, so the full Studio suite and browser navigation
results from the original revalidation remain the evidence for those unchanged
surfaces. No paid OpenAI call was made; the native OpenAI tests use the real SDK
and instrumentor with deterministic HTTP responses.

Raw command logs remain under `/tmp/junjo-full-revalidation-20260920/fixes-*`.
