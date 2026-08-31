# Local engineering assurance

This runtime-neutral application package produces technical evidence. It grants
no authority, accepts no dependency, mutates no Vault object and creates no
commit or remote effect. The existing `cpks` entry point retains its earlier
commands and default JSON behavior.

Use the verified project interpreter with explicit absolute roots. For reproducible
verification, `<project-python>` is the `bin/python` in the freshly reconstructed
locked environment, not an implicit fallback to the old `.venv`:

```sh
<project-python> -m cp_knowledge_tools.cli.cpks assurance preflight --repo-root <repo>
<project-python> -m cp_knowledge_tools.cli.cpks assurance verify --repo-root <repo> --profile fast --path src/cp_knowledge_tools/assurance --test tests/assurance
<project-python> -m cp_knowledge_tools.cli.cpks assurance verify --repo-root <repo> --profile regression --path src/cp_knowledge_tools/assurance
<project-python> -m cp_knowledge_tools.cli.cpks assurance supply-chain --repo-root <repo> --profile research
<project-python> -m cp_knowledge_tools.cli.cpks assurance supply-chain --repo-root <repo> --profile delta --previous artifacts/assurance/<prior>.json
<project-python> -m cp_knowledge_tools.cli.cpks drift audit --repo-root <repo> --vault-root <vault> --scope system --rule-id DEV-P05
```

`--path` and `--test` are repeatable repository-relative paths. Directory scopes
expand against tracked/untracked inventory. `--base` includes committed changes
from an explicitly resolved commit/ref, plus current staged/unstaged/untracked
changes. No base means the current working delta. Unknown or escaping paths and
symlinks fail closed. Other people's work is observed, never cleaned or staged.

Outputs default to JSON and a unique private file below `artifacts/assurance/`.
`--format text` shows checks, reasons, findings, blockers and warnings.
`--no-evidence` suppresses persistence for fully read-only audit use. Invalid
arguments/preconditions return structured stderr without a report file.

Exit codes: `0` required technical checks passed; `1` a required check failed;
`2` incomplete required checks or invalid preconditions. A result is always scoped. `passed` is not acceptance,
authority, production readiness or proof of human review. Reports include Git
state, content/index hashes, interpreter/tool versions, checks and evidence kind.
Resolved live rules are recorded only when actually read, not invented from IDs.

Fast runs Ruff, mapped/explicit tests, TOML/JSON/YAML syntax and skill metadata.
Every unmapped Python path is visible. Syntax validation is not domain schema
conformance. Explicit test selection is an operator impact decision; the tool
does not prove that chosen tests cover every requirement. Regression runs the
full tests directory by default, measured branch coverage when installed, and
mypy on selected source files with imports skipped. Missing tools remain
incomplete. No coverage threshold is invented. Review actual suites for rebuild,
idempotence and Golden coverage. Extended exposes unresolved independent/human
and risk-specific review; it cannot self-attest those reviews.

Commands use finite time/output budgets, clean subprocess environments and process
group cleanup. Raw stdout/stderr are not stored in verification reports; rerun
the recorded command for detailed diagnosis. The output monitor is cooperative
and does not impose an OS disk quota. Tests execute trusted repository code and
can create files; the runner is not a sandbox. The host must enforce filesystem,
network and privilege bounds. Changing inputs during a run makes evidence stale.

## Locked project environment

`assurance environment` wraps the admitted uv executable without interpreting
`uv.lock`. The binding and operating conditions are documented in
[`config/assurance/project-environment.md`](../../../config/assurance/project-environment.md).
The sole project lock is `uv.lock`; `.python-version` pins the ordinary GIL
CPython patch. No new runtime dependency or build backend is introduced.

After resolving authority and verifying the existing bootstrap interpreter:

```sh
<verified-python> -m cp_knowledge_tools.cli.cpks assurance environment \
  --repo-root <repo> --mode rebuild \
  --uv <repo>/artifacts/locking/admission/uv-0.12.7/uv \
  --python <absolute-existing-base-cpython> \
  --environment <repo>/artifacts/locking/environments/<new-run> \
  --cache-dir <repo>/artifacts/locking/cache --allow-network
```

The target must not exist. Use its `bin/python` for subsequent regression and
scanners. For the separate offline/frozen rebuild, omit `--allow-network`, add
`--offline-frozen`, and choose another new target. The wrapper always checks
lock freshness first. All uv operations disable Python downloads and managed
Python discovery, sanitize inherited configuration, and verify input hashes.
`--extra dev` selects the current optional development extra.

With `--mode check` and an existing target, only official lock/environment
consistency checks run. Fresh creation cannot be inferred from existing files:
the report marks freshness `incomplete` and returns 2 even when consistency
passes. It never accepts an arbitrary receipt as proof. Rebuild reports record
the actual absent-to-created observation and interpreter/prefix/base/ABI identity.
Generated reports are evidence, not an authority or a durable attestation.

`--mode routine_check` explicitly checks only the existing environment's
consistency, offline, with fresh rebuild `not_applicable`. It does not weaken the
freshness claim of `check` or `rebuild` and never performs a mutating sync.

Isolated setuptools build dependencies and host Python are outside the complete
project artifact-hash lock. A warm-cache offline run is not a hermetic-build
claim. The generated dependencies-only `pylock.toml` export remains ignored,
noncanonical evidence; it is not another committed project lock.

## Unattended routine

`assurance unattended` composes finite offline checks with live governance and
read-only Project Home/Ready/Doing observation. It requires explicit roots and
the selected existing locked interpreter. Its separate report adds `changed`
(exit 0), materiality, protected-input fingerprints and a validated prior-run
hash chain under ignored `artifacts/assurance/scheduled/`.

It never schedules itself, fixes inputs, installs packages, writes the Vault,
processes Work Items or stages/commits. See the
[host operation guide](../../../config/assurance/unattended.md) for the manual
command, daily native scheduling, review delivery, budgets and honest limits of
the native sandbox and observed nonmutation evidence.

## Admitted local scanner stack

Supply `research` inventories the current interpreter and pyproject without
executing scanners; it is not adoption, a resolved dependency graph or an SBOM.
`admission` and `deep-review` require the complete four-tool stack. `delta`
requires prior inventory evidence and runs only explicitly selected scanners.
No installer, package resolver, auto-fix or license-policy engine is embedded.

The reviewed Darwin arm64 stack is CycloneDX Python 7.3.1, pip-audit 2.10.1,
Gitleaks 8.30.1 and Grant 0.6.8. Python scanners run in a separate CPython 3.14.6
Venv, not the project runtime environment. See
`config/assurance/dependency-admission.md` for the use-context decision and
`config/assurance/scanner-admission.json` for exact artifact, executable,
environment, license and upstream evidence. These are repository engineering
records, not policy, a permission grant or a general third-party registry.

The `cpks.scanner-admission/1` manifest has tool-specific records, including a
full timezone-bearing `verified_at`, `accepted_use_context`, `disposition`,
conditions and an assessment reference. It cannot supply executable commands or
environment overrides. The wrappers select fixed module names and arguments.
Before even `--version`, they compare platform and executable SHA-256; Python
tools additionally require the separate Venv, reviewed base interpreter and
installed site-packages hash. They repeat those bindings after execution.
Changed versions, bytes, platform or use context require fresh delta review;
do not automatically rewrite a hash to obtain a pass.

Pass explicit absolute executables. Both Python tool IDs use the same admitted
Venv interpreter; the wrapper adds `-I -B -m` and the fixed module name:

```sh
<project-python> -m cp_knowledge_tools.cli.cpks assurance supply-chain \
  --repo-root <repo> --profile admission \
  --admission-manifest <repo>/config/assurance/scanner-admission.json \
  --tool cyclonedx=<tool-root>/python/bin/python \
  --tool pip-audit=<tool-root>/python/bin/python \
  --tool gitleaks=<tool-root>/gitleaks/gitleaks \
  --tool grant=<tool-root>/grant/grant \
  --allow-network --retain-sbom --timeout 300 --format text
```

The default manifest is the repository path above. Missing or invalid admission
does not execute a tool. No executable is discovered from PATH. Scanner HOME,
XDG locations and working directory are private temporary directories; inherited
credentials and scanner configuration are not forwarded. Monitors bound combined
stdout/stderr to 10 MB (100 KB for version probes) and work/cache to 20 MB,
with a configurable 1–3600 second run limit. These
are cooperative limits, not an OS sandbox or an enforced network allowlist.
The host must enforce privilege, filesystem and egress restrictions.

| Check status | Meaning |
| --- | --- |
| `passed` | The required technical check completed in its recorded scope. |
| `failed` | A required technical condition failed. |
| `incomplete` | Required evidence could not be collected or interpreted. |
| `not_applicable` | The dimension is not selected/applicable in this profile. |
| `external_evidence` | Separately supplied evidence, not automatically verified or accepted. |
| `review_required` | Contextual disposition remains open. |

Each check declares `required`. Required `external_evidence` or
`review_required` cannot produce exit 0. Contextual checks marked
`required: false` do not block technical completion; top-level `review_status`
still exposes review needs. `decision` and scanner `acceptance` stay
`not_evaluated`. An `admission` run can therefore exit 0 with real findings,
while provenance, candidate health, legal and human review remain explicitly
open. The executable's prior scoped admission is separate from acceptance of
the dependencies being scanned. No synthetic positive review evidence is added.

## Scanner contracts and evidence

CycloneDX receives a private snapshot containing only installed distribution
`METADATA` (or legacy `PKG-INFO` serialized as `METADATA`). It never receives
target modules, startup hooks or executable metadata files on PYTHONPATH.
Its `-S` path-discovery child sees only this private metadata directory and
standard-library paths; target `.pth` code is not replayed. The snapshot reflects
the already running parent's distribution view, which may already include
`.pth` contributions. This does not prove a complete environment view. Exact
name/version coverage and metadata bytes are bound and checked for changes.
Snapshot limits are 10,000 distributions, 2 MB per record and 10 MB total.

The real CycloneDX 1.6 JSON output is validated and projected to minimal package
names, versions and license identifiers/expressions. URLs, descriptions, source
paths, properties and free-form license names/text are dropped. This reduces
privacy exposure but leaves such licenses unresolved. The projected SBOM flows
directly to `grant list` in a private temporary file. `--retain-sbom` optionally
persists it as a unique private, noncanonical `artifacts/assurance/*.sbom.json`
with source/tool/input hashes; it conflicts with `--no-evidence`. Existing files
and symlink targets are not overwritten. Nothing automatically enters Git.

Grant 0.6.8 is normalized only for the observed `run.targets[].evaluation`
JSON list shape with `unevaluated` package decisions. Duplicate license rows
are merged per package/version; absent license identifiers remain unresolved.
The package set must match the supplied SBOM. Grant policy results, risk labels
and `grant check` are not used. An explicit absolute `--sbom` overrides Grant's
generated input after the same sanitization; its source hash is recorded
separately. Grant receives only a local file, with file searching disabled.

Pip-audit queries PyPI only with `--allow-network`, using the current installed
public distribution names/versions (excluding the local first-party project),
`--no-deps --disable-pip --strict`, private cache and pinned temporary requirements.
No dependency resolution or installation runs. Evidence records the exact input
hash, service, time, package/version, advisory ID and supplied fix versions.
There is no invented advisory-database revision, severity or exploitability.
An offline admission run leaves this required check incomplete. A no-finding
result means only **no known findings in this scanner/service/run scope**.

Gitleaks scans the current directory tree, not Git history. Explicit exclusions
are `.git`, `.venv`, `artifacts`, `__pycache__`, `.mypy_cache`, `.pytest_cache`
and `.ruff_cache`; symlinks, archives and encoded content are not expanded.
Git-ignored regular files otherwise remain in scope. The directory input is
hashed before/after (20,000 files, 500 MB total, 100 MB per file). Repository
`.gitleaksignore` causes incomplete pending scope review; local configuration
and inline allow comments cannot silently hide findings. Full redaction and a
typed allowlist retain only rule and location fields, never Secret/Match/Fragment.
A no-finding result means only **no findings detected by this configured scanner/run**.

Unknown shapes, skipped/omitted packages, excessive output, timeout, parser
errors and exit/result mismatches never become clean. Raw outputs are discarded;
only sanitized evidence and raw-output hashes survive. Findings require context,
not automatic approval, rejection or remediation.

## Rebuild and explicit real tests

After confirming the same use context and platform, download the exact wheels
into a private wheelhouse using the trusted project pip and official PyPI.
The requirements file pins all 49 wheel dependencies with hashes. No project
dependency or global environment changes:

```sh
<repo>/.venv/bin/python -m pip --isolated download --only-binary=:all: --no-deps \
  --require-hashes --index-url https://pypi.org/simple --dest <wheelhouse> \
  -r <repo>/config/assurance/scanner-requirements.txt
<repo>/.venv/bin/python -m venv --without-pip <tool-root>/python
<repo>/.venv/bin/python -m pip --isolated --python <tool-root>/python/bin/python install \
  --no-index --only-binary=:all: --no-deps --require-hashes --no-compile \
  --find-links <wheelhouse> -r <repo>/config/assurance/scanner-requirements.txt
<tool-root>/python/bin/python -I -B -m pip check
```

Inspect downloaded wheel metadata/licenses, entry points, hooks and native files
before installation, and match them to the admission. `--no-compile` and `-B`
are mandatory: unexpected bytecode/startup files invalidate the environment.
The environment digest covers all installed site-packages bytes except the
relocatable installer `RECORD` files. Hash identity depends on this exact
interpreter/wheel/installation form; it is not a cross-platform promise.

Download native archives only from the exact official URLs in the manifest.
Compare SHA-256 to both the admitted artifact and upstream checksums/digests,
inspect archive members, and extract only each tool executable and its LICENSE
into a private tool directory. Verify executable hashes before running them.
There is no privileged install script, automatic update or source build.
The recorded Grant signature check validates the supplied certificate's key;
Fulcio-chain/Rekor validation is not claimed. A rebuild must not infer stronger
provenance than the actual checks performed.

An ignored `<repo>/artifacts/assurance/scanner-tools` is a suitable local
tool-root. The manifest contains no absolute host installation paths. Removal
of this isolated stack and explicit invocation paths is the replacement path;
retain review evidence according to CPKS-SPEC-OPS, not as canonical authority.

Normal tests retain synthetic protocol coverage and visibly skip real tools.
To opt into actual execution, set all four absolute paths below. A partially
configured or invalid tool/hash fails rather than silently skipping:

```sh
CPKS_SCANNER_PYTHON=<tool-root>/python/bin/python \
CPKS_SCANNER_GITLEAKS=<tool-root>/gitleaks/gitleaks \
CPKS_SCANNER_GRANT=<tool-root>/grant/grant \
CPKS_SCANNER_ADMISSION=<repo>/config/assurance/scanner-admission.json \
CPKS_SCANNER_NETWORK=1 \
<repo>/.venv/bin/python -m pytest tests/assurance/test_real_scanners.py -q -rs
```

Without `CPKS_SCANNER_NETWORK=1`, the real pip-audit test remains explicitly
unexecuted. The offline tests exercise CycloneDX→Grant, harmless target-module
shadowing, Gitleaks clean/synthetic-finding redaction and an unlicensed Grant
package. No real credentials are fixtures. Protocol compatibility, execution,
findings and CPKS acceptance are separate assertions.

Drift audit resolves current active baseline/rule artifacts with the existing
resolver and compares prior evidence when supplied. It reports configuration
and file-presence observations. It does not understand baseline prose, research
catalogues or Ready eligibility automatically. The accompanying skill adds
read-only semantic reconciliation. A historical baseline HEAD or historical
validated-against reference is not automatically a defect.

The Standard Operation Registry was inspected: its seven existing operations
cover governance/artifact/derived/incident work, not this scope. The application
reuses the existing resolver, hashing and serialization without introducing an
authority registry or modifying managed-artifact mutation handlers.

Design/reuse decision: BUILD the small scoped report/impact layer; USE existing
Ruff, pytest, hashing, serialization and governance resolution; USE coverage,
mypy and Hypothesis after the local-development admission documented in
`config/assurance/dependency-admission.md`; WRAP scanner CLIs only when admitted.
No generic workflow engine, agent runtime, scanner implementation or third-party
source copying was introduced. The existing reuse skill remains the assessment
entry point. `config/assurance/ruff.toml` adds selected rule families only when
explicitly invoked on assurance; existing repository rules remain unchanged.

`config/assurance/codex-output.schema.json` is a separate strict agent handover
schema for `codex exec --output-schema`, not the richer CLI report schema.
Neither schema turns agent prose into approval. Generated reports and handovers
are noncanonical and ignored by Git; retain until review/reproduction needs end,
then apply live CPKS-SPEC-OPS retention/promotion rules.
