# Junjo platform monorepo migration record

## Status

Complete as of 2026-07-13.

This file records the durable outcome and evidence of the Junjo platform
consolidation. It is not an operator runbook. The migration, remediation, and
cutover plans were removed after completion so finished instructions do not
remain active implementation context.

The governing decisions are:

- [ADR 0001: Junjo platform monorepo](../adr/0001-junjo-platform-monorepo.md)
- [ADR 0002: Platform licensing and third-party material](../adr/0002-platform-licensing-and-third-party-material.md)

## Final source topology

The `mdrideout/junjo` repository is the sole canonical source for:

- the Python SDK under `sdks/python`;
- Junjo AI Studio under `apps/studio`;
- the Junjo website under `apps/website`;
- shared telemetry contracts under `contracts/telemetry`;
- the supported Studio deployment sources under
  `apps/studio/deployments/minimal` and
  `apps/studio/deployments/vm-caddy`.

Each deployable retains its own dependency graph, lockfile, validation, version,
and release artifact. The monorepo does not create a shared runtime.

The two standalone deployment repositories remain active as generated,
one-way release mirrors:

- `mdrideout/junjo-ai-studio-minimal-build`;
- `mdrideout/junjo-ai-studio-deployment-example`.

They are distribution surfaces, not editable sources of truth.

The superseded source repositories are archived:

- `mdrideout/junjo-website`;
- `mdrideout/junjo-ai-studio`.

## Preserved import provenance

Source histories were imported without squashing. The original Junjo history
remained the destination history; Studio, website, and both deployment
histories were rewritten beneath their canonical subdirectories and merged
with their ancestry intact.

| Component | Prepared source revision | Rewritten import tip | Destination merge | Verified imported tree | Imported path |
| --- | --- | --- | --- | --- | --- |
| Studio | `ccb0031156d077aa4c5264290df15cc22a8f5d46` | `54bde3c8f5a762cf802323f8c2a94b030ddbdc4f` | `137ff9dc19dcc637eecaab41d5c1f857525c6fef` | `26761a0f0665a9c62d77fb2f11a15278007950df` | `apps/studio` |
| Minimal distribution | `631319feaa4c918e919460370ca51862e7774d87` | `981dcd327ae2b09fb31ed1598af76d651da3ba9b` | `dbef8621347f909d7acbb85a320c26fa8e05c18c` | `11b30f46f48a1315b0933c0d502a15a0432947a4` | `apps/studio/deployments/minimal` |
| VM/Caddy distribution | `099e07f45d4b238f6aba63736a2bd8b1f37501e5` | `7baec1c12d07cfaf99367fc943ab16798ff397d6` | `c0ec2c34ffd6f374fe3a75d2a2adfd9f073410cd` | `58ef4217cd158c3a284769c96430a50a7dd653ea` | `apps/studio/deployments/vm-caddy` |
| Website | `9964091f3c77fdbe49b2bc0f4b13450b417b5cb2` | `49a87bc320b036e0723643a765380fdcf4f3bde6` | `df119c0aebaf212c35ef08538c29daf674e677e9` | `5133752d25b7292dbf3aa53201b2eed3d8fac5af` | `apps/website` |

Each imported tree was byte-identical to the corresponding prepared source
tree. The historical rewrite used `git filter-repo` with the applicable
`--to-subdirectory-filter`, followed by a merge with unrelated histories
explicitly allowed. The Studio import also renamed historical tags with
`--tag-rename '':'studio-'`; the deployment histories used their respective
`studio-minimal-` and `studio-deployment-` prefixes. Temporary import remotes
were removed after each merge.

Only reviewed Git-tracked history was imported. Local secrets, environment
files, databases, runtime data, dependency caches, generated documentation, and
other ignored or untracked state were excluded.

Historical tags were namespaced as `studio-v*`, `studio-minimal-v*`, and
`studio-deployment-v*`. New Studio releases use only `studio-v*`; the latter
two namespaces remain historical provenance.

Unmerged branches from the former Studio repository remain readable in its
archive but are not canonical source. In particular,
`feat/node-exceptions-dashboard` ended at
`6d3171c1c41270ad5baa92ad361179bf60942118`; destination
[issue 13](https://github.com/mdrideout/junjo/issues/13) records the review
boundary for any product ideas recovered from that work.

## Licensing and UI outcome

All current Junjo-authored source and independently published components use
Apache License 2.0. Component manifests, image labels, notices, deployment
archives, and release validation enforce that decision.

The current Studio frontend contains no Catalyst component tree, compatibility
surface, or fallback. Junjo-owned semantic components use Base UI's
MIT-licensed interaction primitives and Tailwind CSS. The Tailwind UI/Plus
license holder confirmed legitimate historical purchase and Studio end-product
use, so imported historical Catalyst commits remain preserved under the terms
that applied to them. ADR 0002 owns the complete decision.

## Release and control-plane outcome

Repository workflows are path-scoped and release authority is tag-routed:

- `sdk-python-v*` publishes only the Python SDK;
- `studio-v*` publishes synchronized Studio images, deployment archives, and
  generated mirrors;
- website and Python documentation builds deploy independently through
  Cloudflare Pages.

Production credentials are scoped to their owning GitHub environments. PyPI
uses OIDC trusted publishing and has no GitHub API token. Studio distribution
publication uses the least-privilege `junjo-studio-dist-pub` GitHub App. Docker
Hub autobuilds are disabled, and stable semantic-version and full source-SHA
tags are immutable for all three Studio image repositories.

GitHub Actions are pinned to full commit SHAs. Production environments admit
only their corresponding release-tag patterns. Pull requests and ordinary
`master` changes are not blocked on production publication workflows.

The consolidation and remediation landed through
[pull request 12](https://github.com/mdrideout/junjo/pull/12) at merge commit
`02f34073ceb40963e716498cf2caaaddafa2db28`, from final head
`3f8e5b32f52257e62044f178d197c359974407e8`. The final
[Platform Gate run](https://github.com/mdrideout/junjo/actions/runs/29264365485)
and [Gitleaks run](https://github.com/mdrideout/junjo/actions/runs/29264364485)
both passed before merge.

## Production verification

### Junjo AI Studio

- Release: [`studio-v0.81.5`](https://github.com/mdrideout/junjo/releases/tag/studio-v0.81.5)
- Source commit: `a8bfb232a70f9a5deb43ddd0e80311f009fa3dcf`
- Successful publication workflow:
  [run 29281312535](https://github.com/mdrideout/junjo/actions/runs/29281312535)
- Published images:
  `mdrideout/junjo-ai-studio-backend`,
  `mdrideout/junjo-ai-studio-frontend`, and
  `mdrideout/junjo-ai-studio-ingestion`
- The immutable
  [`RELEASE_EVIDENCE.json`](https://github.com/mdrideout/junjo/releases/download/studio-v0.81.5/RELEASE_EVIDENCE.json)
  asset, SHA-256
  `62f7a9e011c690babcdad76648838b15746f9433cdc5a24f35645e6202ac6e8a`,
  binds exact image digests, source revisions, deployment archives, export
  manifests, and mirror manifests.
- Both generated deployment mirrors were published and validated from the
  canonical monorepo sources. Their release commits are
  `5053b7893ddecdcd4afe145206f555a46c1af959` for the minimal mirror and
  `6d4eaa69777525e5e5ad1c8e617d43fca3f3a300` for the VM/Caddy mirror.

### Python SDK

- Release: [`sdk-python-v0.64.0`](https://github.com/mdrideout/junjo/releases/tag/sdk-python-v0.64.0)
- Source commit: `78351def55ca5ceb9c7d634a92c5b81be06f7323`
- Successful OIDC publication workflow:
  [run 29301441971](https://github.com/mdrideout/junjo/actions/runs/29301441971)
- PyPI: [`junjo 0.64.0`](https://pypi.org/project/junjo/0.64.0/)
- Published artifacts:
  - `junjo-0.64.0-py3-none-any.whl`, SHA-256
    `60b84f017ee1a8e4b259bcbdbb10583281af4474da8cd4923b1ddd3bcae2cb33`;
  - `junjo-0.64.0.tar.gz`, SHA-256
    `4fe0963193125d7d95c396e2022cdf0fedff11437dfbbb641429bd71e936d103`.
- Supported Python: 3.11 and newer; repository development version: 3.13
- Historical Sphinx documentation deployment:
  [python-api.junjo.ai](https://python-api.junjo.ai/), verified serving version
  `0.64.0` before the unified-documentation cutover

The sole PyPI trusted publisher is:

- owner: `mdrideout`;
- repository: `junjo`;
- workflow: `python-publish.yml`;
- environment: `pypi`.

The obsolete `publish.yml` publisher was removed.

### Website

- Canonical source: `apps/website`
- Production domain: [junjo.ai](https://junjo.ai/)
- Restored-site commit: `d81fe0b3013310c7ec962c478c6790a0e487ba72`
- At the time of this consolidation record, Cloudflare Pages built directly
  from `mdrideout/junjo` on `master`. The 2026-07-15 amendment to ADR 0009
  supersedes that publishing path: GitHub Actions now owns the exact validated
  direct-upload artifact. Automatic production and preview deployments are
  disabled on both Cloudflare Pages projects.

The restored site preserves the original Starlight homepage and documentation
content. The temporary migration redesign, gradients, replacement copy, and
custom 404 are not part of the current site.

## Validation evidence

The completed platform passed:

- repository layout, release-policy, license, secret-boundary, and
  release-evidence validation;
- strict Gitleaks scans of reachable history and the current tree;
- Actionlint and workflow security validation;
- Python SDK Ruff, pytest, ty, warning-free Sphinx, telemetry-contract,
  package-build, and Twine checks;
- Python compatibility tests on 3.11, 3.12, 3.13, and 3.14;
- Studio backend, ingestion, frontend, protobuf, REST-contract, Compose,
  Docker-image, deployment, and end-to-end telemetry validation;
- deterministic export and generated-mirror equivalence checks for both Studio
  distributions;
- website locked install, Astro checks, production build, internal-link
  validation, and production dependency audit;
- clean public installation of `junjo==0.64.0` from PyPI;
- live custom-domain verification for the website and Python documentation.

## Completion consequence

There is no remaining source-consolidation or external-cutover prerequisite for
Agent work. Future architecture and implementation should use the ownership
boundaries in ADR 0001, the licensing boundary in ADR 0002, and current code as
the source of truth.
