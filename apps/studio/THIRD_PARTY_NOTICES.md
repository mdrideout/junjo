# Junjo AI Studio third-party notices

Junjo-authored Studio source is licensed under Apache-2.0 as described in
`LICENSE`. Third-party software retains its own license. Package manifests and
lockfiles are dependency inputs, not artifact-level license evidence by
themselves.

## Production artifact evidence

Every Studio production image carries this notice and Junjo's Apache-2.0
`LICENSE` in `/usr/share/licenses/junjo-ai-studio/`.

- The frontend image also carries `licenses/frontend-production.json`. It is a
  deterministic inventory of the package-lock production dependency closure
  bundled into the static application.
- The ingestion image also carries `licenses/ingestion-production.json`. It is
  a deterministic inventory of the normal Cargo dependency closure statically
  linked for the published Linux amd64 and arm64 targets.
- The backend image also carries its exact resolved `uv.lock` as
  `backend-production.lock`. Installed Python distributions retain the metadata
  and license files supplied in their wheel metadata inside the production
  virtual environment.

The committed inventories bind each entry to the SHA-256 of its committed lock.
Repository validation fails when the lock, dependency closure, manual license
evidence, reviewed license-expression set, image copy contract, or inventory
changes without a coordinated update. The license expressions are inventory
metadata, not legal approval. A release still requires an explicit artifact
license review of new dependencies, copyright notices, and license obligations.

## Current frontend foundation

### Base UI

Studio uses `@base-ui/react` and `@base-ui/utils` from the standalone Base UI
project: <https://base-ui.com/>.

MIT License

Copyright (c) 2019 Material-UI SAS

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

### Tailwind CSS

Studio uses Tailwind CSS as its styling engine: <https://tailwindcss.com/>.
Tailwind CSS is distinct from the Tailwind Plus Catalyst product discussed
below.

MIT License

Copyright (c) Tailwind Labs, Inc.

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

### Khroma

Studio's Mermaid dependency includes Khroma 2.1.0. Its package metadata omits a
license field, so the artifact license policy pins the SHA-256 of the license
file contained in the exact registry package.

MIT License

Copyright (c) 2019-present Fabio Spampinato, Andrew Maney

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

## External production binary

The ingestion image includes grpc-health-probe 0.4.35 from
<https://github.com/grpc-ecosystem/grpc-health-probe>. It is licensed under
Apache-2.0. The image's Apache-2.0 `LICENSE` contains the applicable license
terms; the upstream release does not publish a separate NOTICE file.

## Historical Tailwind Plus Catalyst material

Historical Studio commits and tags imported before the current Junjo UI
replacement contain source derived from Tailwind Plus Catalyst. That material
is governed by the Tailwind Plus license, not Apache-2.0:
<https://tailwindcss.com/plus/license>.

The current source tree and current frontend build do not contain that
Catalyst-derived component tree. Continued distribution of affected historical
revisions is conditional on verifying the applicable Tailwind Plus
distribution rights before production cutover. If those rights cannot be
verified, the affected history and tags must be rewritten as required by
platform ADR 0002.
