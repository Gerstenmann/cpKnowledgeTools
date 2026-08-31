# Reproducible project environment

`pyproject.toml` declares dependency intent; the committed `uv.lock` is the only
project resolution source. `.python-version` selects CPython **3.14.6**, with the
ordinary GIL build. Locking and successful checks do not grant dependency,
security, license or governance acceptance. Resolve the live `DEV-P05`, `DEV-P06`,
`CPKS-POL-SW-SUPPLY`, `CPKS-SPEC-OPS` and applicable architecture/testing rule homes.

## Development-tool admission

The 2026-08-31 Owner instruction authorizes this bounded local increment.
Disposition: **WRAP uv 0.12.7, accepted with the operating conditions below** as
a separate local development executable, not a runtime dependency or scanner.
The technical binding is [development-tools.json](development-tools.json).
It does not install software, evaluate policy or authorize an operation.

The official [0.12.7 release](https://github.com/astral-sh/uv/releases/tag/0.12.7)
is stable and immutable, published 2026-08-27. Source commit:
`61291a8ca5477a9ca653f14d2ac5665587c263fa`. The tool is licensed
**MIT OR Apache-2.0** ([Cargo.toml](https://github.com/astral-sh/uv/blob/0.12.7/Cargo.toml),
[MIT](https://github.com/astral-sh/uv/blob/0.12.7/LICENSE-MIT),
[Apache](https://github.com/astral-sh/uv/blob/0.12.7/LICENSE-APACHE)). Retain these
notices with the local binary. This admission does not authorize redistribution
of a modified tool or decide the project's outbound license.

The admitted macOS arm64 archive is `uv-aarch64-apple-darwin.tar.gz`
(16,611,578 bytes), SHA-256
`127ebdda7ad953cdf198e964b570ea5771b85467ea93eb7cb6d6f8e6f55408f3`.
The extracted `uv` executable (36,498,144 bytes) has SHA-256
`55936a60bff5de7ac04facb72f9e6fd0ffd9661063480224c3ab321c3f10caff`.
`gh attestation verify <archive> --repo astral-sh/uv --format json` succeeded;
the verified SLSA statement binds this archive digest to the source commit and
`.github/workflows/release.yml`, invocation
`https://github.com/astral-sh/uv/actions/runs/33117010175/attempts/1`.
Artifact provenance is not proof of safety or a reproduced Rust build.

The six published upstream security advisories were inspected on 2026-08-31:
GHSA-4gg8-gxpx-9rph (<0.11.15), GHSA-pjjw-68hj-v9mw (<=0.11.5),
GHSA-pqhf-p39g-3x64 (<=0.9.5), GHSA-w476-p2h3-79g9 (<=0.9.4),
GHSA-7j9j-68r2-f35q (<=0.8.21), GHSA-8qf3-x8v5-2pj8 (<0.8.5).
None of those published ranges includes 0.12.7. This was not an exhaustive audit
of uv's Rust dependency closure or a guarantee against unknown vulnerabilities.

Operating conditions:

- Use the exact verified executable by absolute path, privately extracted under
  ignored `artifacts/locking/admission/uv-0.12.7/`; only `uv` is used, not `uvx`.
  No global install, PATH/profile modification, installer shell script, sudo,
  self-update, tool install, provider credentials or automatic Python download.
- uv can access registries, download archives, create/remove environment files,
  maintain caches and execute build backends. The assurance wrapper exposes only
  fixed checks and an explicitly requested fresh local sync. Network is opt-in;
  offline is the default. It sanitizes inherited configuration and credentials.
- Use an explicitly verified existing system CPython matching the pin. Missing
  Python fails visibly; provision a new Python distribution in a separate scope.
- Never use an existing `.venv` or scanner environment as a fresh target. Rebuild
  only into an absent child of `artifacts/locking/environments/`. Keep the separate
  cache under `artifacts/locking/cache/`. Preserve failed outputs for diagnosis.
- `--no-build` excludes new third-party source builds; it still allows the
  reviewed editable first-party setuptools build and cached built wheels. Keep
  an admission/rebuild cache separate from unrelated caches and inspect inputs.
- Review deliberate dependency or tool updates before use. Archive authenticity,
  license and platform admission must be renewed for a replacement tool artifact.

## Why uv

| Alternative | Decision |
| --- | --- |
| Current pip without lock | Does not preserve a transitive resolution. `pip freeze` inventories an environment; it is not a resolver lock. |
| pip `pylock.toml` | PEP 751 is final, but official pip 26.2 still marks `pip lock` experimental and guarantees only the current Python/platform. No established project-sync advantage for this increment. |
| uv Project Lock | Universal resolution, markers and artifact hashes; stable lock freshness and sync checks; CPython 3.14/macOS arm64 supported; works with existing setuptools and dev extra. Chosen. |
| Poetry/PDM or custom resolver | No demonstrated benefit justifying another migration or a new resolver to maintain. |

The acquired uv source checkout is read-only research evidence, not copied code.
The reuse core retains its aggregate fixture/vendor license observations; it does
not interpret Cargo's complete licensing graph. The scoped native-tool admission
above resolves the tool's license from root primary sources. No positive adoption
of the entire checkout or modified acceptance guard is claimed.

Primary contracts: [PEP 751](https://peps.python.org/pep-0751/),
[pip lock](https://github.com/pypa/pip/blob/26.2/src/pip/_internal/commands/lock.py),
[uv locking/sync](https://github.com/astral-sh/uv/blob/0.12.7/docs/concepts/projects/sync.md),
[Python discovery](https://github.com/astral-sh/uv/blob/0.12.7/docs/concepts/python-versions.md),
[project configuration](https://github.com/astral-sh/uv/blob/0.12.7/docs/concepts/projects/config.md),
[export](https://github.com/astral-sh/uv/blob/0.12.7/docs/concepts/projects/export.md).

## Workflow

Initial-lock delta assessment (2026-08-31): the existing 61-distribution environment
and the installed 54-distribution runtime/dev result were compared using the
official PEP-751 export and installed metadata. **39 versions remain unchanged,
15 change, seven old distributions are absent**. No dependency constraint changed.

| Scope | Reviewed version changes |
| --- | --- |
| Direct runtime | MCP 1.28.0 → 1.29.1 (MIT) |
| Direct development | Ruff 0.16.0 → 0.16.5 (MIT) |
| Runtime transitive | click 8.4.2 → 8.5.0 (BSD-3-Clause), idna 3.18 → 3.19 (BSD-3-Clause), pydantic 2.13.4 → 2.13.5 and pydantic-core 2.46.4 → 2.46.5 (MIT), pydantic-settings 2.14.2 → 2.15.0 (MIT), python-dotenv 1.2.2 → 1.2.3 (BSD-3-Clause), soupsieve 2.9.1 → 2.9.2 (MIT), sse-starlette 3.4.6 → 3.4.8, starlette 1.3.1 → 1.6.0, uvicorn 0.51.0 → 0.52.4 (all BSD-3-Clause), typing-inspection 0.4.2 → 0.4.4 (MIT) |
| Development transitive | packaging 26.2 → 26.3 (Apache-2.0 OR BSD-2-Clause), Pygments 2.20.0 → 2.21.0 (BSD-2-Clause) |

Disposition: accepted with existing local-use conditions, exact wheel/hash
binding, successful fresh regression and contextual scanner review. The material
Settings case-sensitivity/ForwardRef changes, Pydantic union/serialization changes
and MCP Settings/schema initialization were reviewed against official release
sources and covered by the full model/MCP regression. New HTTP/WebSocket transports,
Uvicorn's experimental zttp mode and settings-debug output are not enabled.
This does not expand transport or production authority.

httpcore2, httpx2, opentelemetry-api, truststore, pip, setuptools and wheel were
present in the old environment but are not in the current runtime/dev closure.
setuptools/wheel remain **separate build requirements**; their actual build-version
deltas are assessed below. Windows-only colorama 0.4.6 and pywin32 312 appear in
the universal lock but were not installed here; another host still needs its own
artifact/compatibility admission. The existing PDF chain is unchanged.

The historical cryptography advisory already ceased to match after the earlier
PDF admission upgraded cryptography to 50.0.1; this is not a locking remediation.
A repeat scan of the old environment still reports MCP/PIP advisories; the new
environment reports no known pip-audit findings. MCP 1.29.1 lies outside the
reported version range, and the repository does not use that advisory's deprecated
`websocket_server`. Upgrade alone is not a universal WebSocket mitigation (its
security settings are opt-in). pip is absent from the new environment, which is
a scope removal, not proof of remediation of the old pip installation.

Both old and new inventories retain four Grant license-identifier gaps:
cp-knowledge-tools, pathspec, pypdfium2 and sortedcontainers. The fourth comes from
the already-admitted PDF chain, not this lock. Existing contextual evidence resolves
pathspec (MPL-2.0), sortedcontainers (Apache-2.0) and the pypdfium2/PDFium notices;
the project's outbound license remains outside this scope. Gitleaks still reports
the same public license-file hash in scanner-admission.json as a contextual false
positive. No scanner rule or finding was suppressed.

Use `cpks assurance environment --help` for the fixed interface. Supply absolute
repository, admitted uv, existing Python, environment and cache paths. Run the
command from an already verified project interpreter; after rebuild, use the
reported fresh `bin/python` directly for verification and scanners. There is no
automatic activation or fallback to the old `.venv`.

Normal check delegates to `uv lock --check` and `uv sync --locked --check
--extra dev`, with `--offline`, `--no-config`, `--no-python-downloads` and
`--no-managed-python`. It does not create a freshness claim: only an observed
absent-to-created rebuild proves that. A check-only report therefore exposes
unobserved freshness separately from lock/environment consistency.

An authorized rebuild uses `--mode rebuild --allow-network` and an absent target.
The separate warm-cache test uses another absent target and `--offline-frozen`.
Even that flow first checks lock freshness: `--frozen` alone does **not** check it.
Neither flow intentionally rewrites `pyproject.toml`, the Python pin or lock;
input hashes are checked before and after execution.

Development dependencies remain `[project.optional-dependencies].dev`, selected
by **`--extra dev`**, not `--dev`. No migration to groups or `uv_build` occurred.
When dependency intent changes, deliberately run the admitted uv `lock` command
with the same safe Python/config/cache settings, inspect the version/marker delta,
review material dependencies, and rebuild/verify before committing the new lock.
Normal sync never silently updates the lock. Future CI and scheduled work can
consume this same source contract; none is introduced here.

`config/assurance/scanner-requirements.txt` binds the **separate scanner tools**.
The PDF requirements file preserves prior platform-specific admission evidence.
The legacy `requirements-template-generator.txt` is an unpinned helper bootstrap,
not a project resolution source. Do not maintain any of these as a second project
lock or use them to override `uv.lock` for regular project verification.

## Reproducibility and exit limits

The universal lock carries platform/Python alternatives, but this tool binding and
fresh rebuild are admitted/tested on macOS arm64 only. Another host needs its own
reviewed uv artifact and the existing exact CPython patch/ABI. Native wheels in
the PDF chain limit actual platform availability; a marker in a lock is not proof
that every host can install or execute it.

The existing `setuptools>=68`/`wheel` isolated editable-build requirements are not
a complete hash-bound backend lock. Keep the observed backend/cache versions in
generated evidence. No constraint/backend migration is hidden in this increment.

The initial rebuild additionally resolved **setuptools 83.0.0 → 84.0.0** and
**standalone wheel 0.47.0 → 0.48.0**, both MIT, outside the runtime/dev closure.
Their official PyPI wheel hashes were independently checked:
setuptools `51a52592b3b99e102b609654876bd65f19f999935166d1352678931132b0c670`,
wheel `3217dcc807155e45db462d7ef2431f5ddda0d7273b700d05a67b271ceb1287ab`.
Disposition: **accepted with conditions for this local editable build**; retain
the exact evidence, verify build/import/regression success, do not use converters
on untrusted archives, and review backend deltas on future rebuilds. `--locked`
does not bind future isolated-backend updates.

The [setuptools delta](https://github.com/pypa/setuptools/compare/v83.0.0...v84.0.0)
changes compiler/distutils APIs, with no identified PEP-660 semantic change in
`build_meta.py`/`editable_wheel.py`; this project declares no compiled extension.
The installed project WHEEL explicitly records `Generator: setuptools (84.0.0)`.
The [wheel delta](https://github.com/pypa/wheel/compare/0.47.0...0.48.0) changes
pack/tags/convert commands, not `wheelfile.py`. Cache presence proves availability
of standalone wheel 0.48.0, not its exact imported module path in the removed
temporary build environment.

wheel 0.48.0 addresses **GHSA-vgq5-9859-3mmw** in `wheel convert`. setuptools 84
still bundles wheel **0.46.3** and packaging **26.0**, as setuptools 83 already did.
That embedded converter remains a separate residual finding; the standalone
upgrade does not repair it. No converter call is identified in this repository's
editable-build path. This is a scoped exposure disposition, not universal
remediation or a complete backend-transitive security audit. Project pip-audit
does not cover the isolated backend or uv's native dependencies.

Python itself, OS libraries and build tooling remain prerequisites. An offline
warm-cache run is not a fully hermetic build; uv's `--offline` is not an OS sandbox
for a build backend. Report any separately enforced network restriction accurately.

The stable uv exporter provides the PEP-751 exit path. Export with `--locked
--offline --extra dev --no-emit-project --format pylock.toml` to ignored artifacts
and validate with the existing `packaging.pylock.Pylock.from_dict` API. This is a
**dependencies-only, noncanonical export**: excluding the editable root avoids
misinterpreting its relative source path under `artifacts/`. The repository remains
the project's source contract. Do not commit the export or use experimental
pylock installation as the primary workflow.

Removing the local tool/environment/cache directories reverses their installation;
no global state was required. Replacing uv requires reviewing another consumer of
the exported standard lock or deliberately generating a replacement project lock.
Generated inventories, attestations, test reports and handovers remain under
ignored `artifacts/locking/` and `artifacts/assurance/`; they are not authority.
