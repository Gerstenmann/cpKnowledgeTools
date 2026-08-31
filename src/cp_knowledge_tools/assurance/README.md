# Local engineering assurance

This runtime-neutral application package produces technical evidence. It grants
no authority, accepts no dependency, mutates no Vault object and creates no
commit or remote effect. The existing `cpks` entry point retains its earlier
commands and default JSON behavior.

Use the verified tools-repository interpreter with explicit absolute roots:

```sh
<repo>/.venv/bin/python -m cp_knowledge_tools.cli.cpks assurance preflight --repo-root <repo>
<repo>/.venv/bin/python -m cp_knowledge_tools.cli.cpks assurance verify --repo-root <repo> --profile fast --path src/cp_knowledge_tools/assurance --test tests/assurance
<repo>/.venv/bin/python -m cp_knowledge_tools.cli.cpks assurance verify --repo-root <repo> --profile regression --path src/cp_knowledge_tools/assurance
<repo>/.venv/bin/python -m cp_knowledge_tools.cli.cpks assurance supply-chain --repo-root <repo> --profile research
<repo>/.venv/bin/python -m cp_knowledge_tools.cli.cpks assurance supply-chain --repo-root <repo> --profile delta --previous artifacts/assurance/<prior>.json
<repo>/.venv/bin/python -m cp_knowledge_tools.cli.cpks drift audit --repo-root <repo> --vault-root <vault> --scope system --rule-id DEV-P05
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

Exit codes: `0` selected checks passed; `1` a check failed; `2` incomplete checks
or invalid preconditions. A result is always scoped. `passed` is not acceptance,
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

Supply research inventories the current interpreter and pyproject; it is not a
resolved dependency graph or SBOM. Admission/deep-review/delta expose outstanding
license, provenance, vulnerability and candidate-health evidence. No installer,
package resolver, auto-fix or license-policy engine is embedded.

Opt-in protocol adapters accept separately admitted absolute executables:

```sh
<repo>/.venv/bin/python -m cp_knowledge_tools.cli.cpks assurance supply-chain --repo-root <repo> --profile admission --tool cyclonedx=/absolute/cyclonedx-py
<repo>/.venv/bin/python -m cp_knowledge_tools.cli.cpks assurance supply-chain --repo-root <repo> --profile admission --tool pip-audit=/absolute/pip-audit --allow-network
<repo>/.venv/bin/python -m cp_knowledge_tools.cli.cpks assurance supply-chain --repo-root <repo> --profile deep-review --tool gitleaks=/absolute/gitleaks
```

These adapters have synthetic protocol tests, not installed-tool acceptance.
No external scanners ship as dependencies in this increment. Pip-audit queries
PyPI with pinned installed names/versions; explicit egress scope is required.
CycloneDX uses `-S`, which can omit `.pth`-contributed packages. Its current
adapter retains count/version/hash rather than a transferable SBOM. Grant needs
an explicit separately generated SBOM and reports its output as uninterpreted
inventory because the installed schema has not been admitted. This is not yet
an end-to-end CycloneDX → Grant stack. Gitleaks output keeps only typed location
fields and rule identifiers; secrets/matches/fragments are excluded. Unknown
shapes, skipped inputs, errors and exit/result mismatches never become clean.

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
