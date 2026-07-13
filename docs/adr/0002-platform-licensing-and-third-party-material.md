# ADR 0002: Platform licensing and third-party material

- Status: Accepted
- Date: 2026-07-13
- Owners: Junjo platform

## Context

Junjo publishes multiple independently built artifacts from one source
repository. Junjo-authored SDK, Studio, website, contract, documentation, and
deployment source is intended to use Apache License 2.0. The repository and its
artifacts also contain or depend on third-party material whose authors did not
license it under Apache-2.0.

The imported Studio history includes source derived from Tailwind Plus
Catalyst. Catalyst is distributed under the Tailwind Plus license, not
Apache-2.0. Placing that source beneath Junjo's Apache license does not relicense
it. Studio needs direct control over its visual language and future
customization, so retaining Catalyst as the current component foundation is
also the wrong product boundary.

Ordinary package dependencies present the same general distinction: Junjo may
combine compatible third-party software with Apache-2.0 software, but must not
describe the third-party software as Junjo-authored or Apache-2.0 unless its
license says so.

## Decision

Apache License 2.0 applies to current Junjo-authored source, documentation,
contracts, examples, and deployment definitions. It does not supersede the
license of third-party material.

Every independently published Junjo artifact must:

- identify Junjo-authored material as Apache-2.0;
- preserve the license and notice required by bundled third-party material;
- include a component-owned third-party notice when a build incorporates
  third-party source into the distributed artifact;
- use SPDX and OCI metadata that describes Junjo-authored artifacts without
  claiming ownership of their dependencies;
- fail repository validation when required license or notice metadata is
  absent.

For Studio container artifacts, the repository makes the evidence boundary
explicit:

- every production image carries Junjo's Apache-2.0 license and the Studio
  third-party notice;
- the frontend image carries a committed inventory generated from the exact
  package-lock production closure;
- the statically linked Rust ingestion image carries a committed inventory
  generated from Cargo's normal dependency closure for both published Linux
  targets;
- the backend image carries its resolved production lock, while installed
  Python distribution metadata remains in the virtual environment;
- each inventory is cryptographically bound to its committed lock and checked
  against an explicit set of license expressions reviewed for the artifact;
- manual metadata corrections require exact package identity, source evidence,
  and an evidence-file hash.

These inventories provide deterministic review inputs. They do not prove that
all copyright notices or license-specific redistribution obligations have been
satisfied and are not a substitute for release approval. Artifact license
review remains an explicit production cutover gate.

Studio will replace the current Catalyst-derived component tree with an
independently authored Junjo UI layer built on the standalone Base UI project's
MIT-licensed interaction primitives. Tailwind CSS remains the styling engine.
The replacement must be designed from Junjo's product requirements and must not
copy or adapt Catalyst source, component APIs, class recipes, or visual assets.

The entire current `components/catalyst` tree is removed. No compatibility
surface, deprecated component alias, or fallback implementation is retained.
Future Studio releases contain the Junjo replacement and the applicable Base UI
MIT notice.

Historical commits remain historical provenance. Their Catalyst-derived
material remains governed by the Tailwind Plus terms that applied to that
material; the repository Apache license does not relicense it. The source
repository records that boundary explicitly. If Junjo cannot verify the right
to continue distributing the historical material as part of the Studio end
product, the affected history and tags must be rewritten and all migration
tree, commit, and tag evidence recomputed before cutover.

## Component notice ownership

- `apps/studio/THIRD_PARTY_NOTICES.md` owns notices for third-party source
  incorporated into Studio's published frontend and images.
- `apps/studio/licenses/` owns Studio's generated production dependency
  inventories and the small, human-reviewed artifact license policy.
- Language package managers retain the resolved dependency graph. The artifact
  inventories select and describe the portion distributed in Studio's static
  frontend and statically linked Rust binary.
- Deployment exports include the Studio notice when they redistribute a Studio
  artifact that requires it.
- Root documentation references component notice owners rather than duplicating
  their full contents.

## Validation

Repository validation checks:

- complete Apache-2.0 license text at every independently published Junjo
  component root;
- SPDX license metadata in package manifests;
- OCI license and source labels in Junjo-authored images;
- Studio's third-party notice in every source or release surface that requires
  it;
- the Studio production image copy contract and exact lock-bound dependency
  inventories;
- the Cargo inventory against Cargo metadata for both published Linux targets;
- installed evidence for any manual frontend license-metadata override;
- absence of production frontend source maps, which are not part of the Studio
  distribution contract;
- absence of Catalyst current-source files and dependencies after replacement;
- absence of obsolete claims that every historical or third-party byte is
  Apache-2.0.

License validation is an artifact check, not a conclusion inferred solely from
the root `LICENSE` file.

## Consequences

Junjo has one clear license for its own work without making false claims about
dependencies. Studio gains full control over its UI foundation and can evolve
appearance and composition independently from its interaction primitives.

The repository must maintain third-party notices and inventories as
dependencies and build contents change. New license expressions cannot enter a
production inventory without an explicit policy change and review. Historical
Catalyst provenance and current artifact-license approval remain explicit
cutover gates; neither is implied by a green mechanical inventory check.

## Rejected alternatives

- Relabel Catalyst as Apache-2.0: rejected because Junjo does not own that
  license grant.
- Replace only Catalyst's Headless UI imports: rejected because derivative
  markup, APIs, class recipes, and assets would remain Catalyst material.
- Keep a compatibility copy under a Junjo directory: rejected because it
  preserves the same ownership and licensing problem.
- Remove Tailwind CSS: rejected because Tailwind CSS is MIT-licensed styling
  machinery and is not the source-licensing problem.
- Claim that the root Apache license covers every dependency: rejected because
  third-party licenses remain effective.
