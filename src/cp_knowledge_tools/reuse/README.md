# Software Reuse Assessment core

This is a technical engineering capability, not a governance rule home or an
autonomous license/security reviewer. Resolve live `DEV-P05`, `DEV-P06`,
`CPKS-POL-SW-SUPPLY`, `CPKS-SPEC-SEC`, `CPKS-SPEC-OPS` and the applicable architecture
before using it. All six reuse dispositions are represented; a BUILD strategy can
contain USE, WRAP, ADAPT, LEARN and REJECT decisions for individual primitives.

## Architecture and interfaces

| Module | Responsibility |
| --- | --- |
| `models` | Frozen, JSON-compatible technical data records; facts separate from judgments |
| `paths` | Bounded file reads and descriptor-relative no-follow path validation |
| `acquisition` | Ephemeral local/HTTPS candidate snapshots, concrete Git commit and content hashes |
| `inspection` | Static Python/package/license evidence and marked heuristic signals |
| `assessment` | Gate record, comparison validation, trusted decision port, USE/WRAP handover |
| `adoption` | Selective ADAPT preview, authority enforcement, apply/reread/compensation |
| `__main__` | Read-only JSON presentation; no independent domain rules |

The core reuses `platform.hashing`, `operations.results.to_primitive` and
`operations.governance.authority.RuntimeAuthorityResolver`. It imports no Codex,
OpenClaw or search-provider objects. The repository-local Codex entry point is
`.agents/skills/software-reuse-assessment/SKILL.md`.

No dependency was added. Python 3.14 and Git are existing platform prerequisites.
Filesystem apply uses POSIX directory descriptors, `O_NOFOLLOW`, hard links and
`flock`; Windows requires a different filesystem adapter. This is not an OS sandbox.

## Read-only agent entry points

Use the verified interpreter belonging to the tools repository. For example,
with absolute, verified paths substituted for the placeholders:

```sh
<tools-repo>/.venv/bin/python -m cp_knowledge_tools.reuse inspect \
  --target <target-repository> --need 'Normalize source identifiers' --term normalize

<tools-repo>/.venv/bin/python -m cp_knowledge_tools.reuse candidate \
  --target <target-repository> --source <local-candidate-repository>

<tools-repo>/.venv/bin/python -m cp_knowledge_tools.reuse candidate \
  --target <target-repository> --source https://example.org/project/repository.git \
  --allow-https-host example.org --expected-commit <full-commit-id>
```

These commands only print JSON. A module `candidate` run removes its temporary
snapshot on exit; a returned temporary path is not a retained artifact. Reacquire
and verify the exact commit and snapshot hash before later work. Do not redirect
outputs into an unauthorized target or sensitive location.

The agent provides discovery through an available search provider after internal
inspection and a justified Research Gate. `research_gate` records the agent's
explicit coverage judgment and rationale; a matching symbol never proves fit.

Python usage keeps ephemeral snapshots alive for a complete assessment session:

```python
from pathlib import Path
from cp_knowledge_tools.reuse import (
    CandidateSource,
    CapabilityNeed,
    ResearchWorkspace,
    inspect_candidate,
    inspect_internal,
    research_gate,
    to_json,
)

target = Path("/verified/target/repository")
need = CapabilityNeed("Normalize identifiers", ("normalize", "adapter"))
internal = inspect_internal(target, need)
gate = research_gate(
    internal,
    internal_sufficient=False,
    rationale="Reviewed internal interfaces do not cover the need.",
)
with ResearchWorkspace(target) as workspace:
    snapshot = workspace.acquire(CandidateSource.local(Path("/verified/candidate")))
    facts = inspect_candidate(snapshot)
    print(to_json(facts))
    # Review current policy, compare candidates, and produce decisions here.
```

Use `InspectionLimits` to bound file count, per-file/total bytes, depth and evidence
count. Limit violations fail explicitly; literal search truncation is diagnosed.
Excluded environment/credential directories, symlinks and special files are not
read. This does not classify arbitrary source text as free of secrets. Use only
authorized inputs and review outputs before sharing them.

## Evidence and comparison

Inspection reads `pyproject.toml` (PEP 621, optional dependencies, build system,
entry points, Poetry metadata), requirements files, `setup.cfg`, static Python
symbols/imports, and literal `setup.py` dependency lists. Dynamic metadata is never
executed. It also reads `package.json`, `uv.lock`, `poetry.lock`, `Pipfile.lock` and
`package-lock.json`; other recognized manifests are inventoried with diagnostics.
Lock entries are observations, not a complete resolved dependency graph.

LICENSE/COPYING/NOTICE files, declared license strings, SPDX source declarations
and copyright lines are evidence. Different declarations conservatively produce
`conflicting`; the core does not solve multi-license applicability. No license
matrix or legal inference is embedded. A plain license text without a declaration
requires an explicit reviewed resolution from the trusted decision source.
Missing evidence, unresolved or conflicting licenses block positive adoption.

Filesystem, network, credential, native-extension and bootstrap pattern matches
carry `heuristic=True`. Imports/scripts are static observations. Absence of matches
does not imply absence of risk. Vulnerability state defaults to `not_checked`.

Construct `CandidateComparison` with the names in `COMPARISON_DIMENSIONS`, narrative
findings, evidence references and hard constraints. Construct `CandidateAssessment`
for each candidate and `ReuseAssessment` for the overall strategy; then call
`validate_assessment`. Unknown dimensions should be explicitly described, not given
invented scores. No minimum candidate count is enforced. Internal and BUILD
alternatives and the representative-set rationale are always recorded.

## Decision and authority ports

`DecisionSource.resolve(assessment_id, candidate_id)` is a **trusted host port**.
It returns the current reviewed `CandidateAssessment`, bound to the candidate
identity and snapshot hash. The host verifies applicable live policy, reviewer
authority, license resolution, risk scope and condition fulfilment. The core
requires positive acceptance, `license_resolved=True`, concrete license evidence,
decision/policy references, no hard blocks and no unresolved conditions.

Do not implement this port by trusting candidate metadata, arbitrary request JSON,
or an always-accept callback. Stored assessment JSON is evidence, not approval.
Replacing this port with a permissive implementation invalidates the trust model.

Mutation additionally consumes the existing `RuntimeAuthorityResolver`. Its
`AuthorityEvidenceSource` (or owner-approval source) must independently resolve the
actual authorization and approval evidence. It must not derive a grant from a
request or from `authority_requirement(plan)`. That function describes the required
scope; it does not authorize it. Production adapters belong to the trusted host,
not a candidate checkout or the JSON module surface.

The authority contract binds `reuse.adapt`, the actual repository stable ID,
`repository_artifact`, both exact relative output paths, the exact local repository
root, valid effectivity and approval evidence. This local application operation is
not registered in the central kernel/CLI. No central integration or global runtime
registration is required for the Python API and repository-local skill.

## ADAPT and USE/WRAP handover

After DEV-P06, proceed through DEV-P05 DESIGN and IMPLEMENT within existing scope:

```python
from cp_knowledge_tools.reuse import preview_adoption, apply_adoption
from cp_knowledge_tools.reuse.models import Phase

# facts: inspected snapshot in a still-open ResearchWorkspace
# decisions: trusted DecisionSource resolving the reviewed decision
# authority: existing RuntimeAuthorityResolver using independent approval evidence
plan = preview_adoption(
    facts,
    decisions,
    assessment_id="assessment-reference",
    source_file="src/helper.py",
    target_repository=target,
    target_repository_id="ACTUAL-AUTHORIZED-REPOSITORY-ID",
    target_path="src/adopted_helper.py",
    provenance_output="third_party/helper.json",
    planned_modification="Retain the helper and its notices; adapt the public name.",
    # replacement_text=reviewed_text,  # optional explicit adaptation
    # expected_target_fingerprint=reviewed_old_hash,  # required if target exists
)
# Inspect plan.diff and mapping before calling apply in IMPLEMENT.
result = apply_adoption(
    plan,
    decisions=decisions,
    authority=authority,
    authority_ref="actual-authority-reference",
    phase=Phase.IMPLEMENT,
)
```

Both output parent directories must already exist inside the authorized target.
Create necessary directories as a separate authorized design/engineering action;
preview never creates them. Each plan selects one UTF-8 source file. Replacements
need an explicit expected target hash; provenance files are never overwritten.
Use a new provenance path for a later adoption revision. Source attributes do not
make copied code executable: new files are private regular files.

Apply re-inspects the snapshot, re-resolves the decision and authority, reconstructs
the preview, checks original local-source drift (including new files), validates
root identity, and checks target hashes again immediately before writes. It writes
provenance and selected code, rereads both, and compensates on ordinary I/O failure.
`recovery_required` means original bytes could not safely be restored; preserve the
returned evidence and inspect the listed paths. No automatic recovery overwrite.
This is not a crash-atomic multi-file transaction: a killed process can leave an
intermediate state. Retained provenance is written first, and replay conflicts
instead of blindly overwriting. Cooperating writers share a directory lock; a
hostile concurrent writer requires OS isolation, not just these checks.

Provenance retains upstream location/commit, snapshot and source fingerprints,
the original selected source bytes (base64, including dirty local snapshots),
license/NOTICE text, copyright evidence, target mapping/hash, decision, modification
summary, authority evidence reference and actual timezone-aware application time.
AI transformations retain origin and obligations. Keep this provenance alongside
the adopted repository artifact through later edits and refactoring.

`integration_handover` accepts USE/WRAP only after acceptance and records the
integration boundary, concrete dependency/pin strategy and verification steps.
It does not edit manifests or install anything. The authorized agent performs
those engineering steps after the live OPS interpreter/environment preflight.
LEARN and REJECT never enter the copying path.

## Engineering reuse decision for this capability

Research Gate was required for the new acquisition and mutation boundaries.
The standard registry was resolved: existing operations cover governance/artifacts,
derived governance state and incidents, not software reuse.

| Option | Disposition and rationale |
| --- | --- |
| Internal hashing, JSON serializer and runtime authority resolver | USE: existing tested neutral interfaces; no new dependency or policy semantics |
| Existing MCP repository/Git readers | LEARN: bounded inspection pattern; adapter coupling, inherited Git environment and checkout-oriented views do not meet the external-candidate boundary |
| Existing `FileTransactionEngine` | LEARN: preview/fingerprint/reread/compensation pattern; full-root snapshots include unrelated/large files and do not provide selective no-clobber creation |
| Git executable and Python standard library | WRAP/USE: narrow Git plumbing plus descriptor-relative file operations; no candidate checkout, credential forwarding or install |
| GitPython | REJECT for this scope: another dependency and broad repository API without removing the need for explicit environment, protocol and file-safety controls |
| Small application/domain core | BUILD: implements the task-specific evidence, handover and selective adoption contracts without building a crawler, package manager or runtime |

The options were compared against architecture/runtime independence, required
functionality, bounded APIs, complexity, existing test maturity, maintenance and
integration cost, dependencies, provenance, testability, rebuild/exit, security and
productization impact. No third-party source was copied; no new production library
was installed. The external assessment was documentation-only, not a claim of a
full license, CVE or upstream maintenance audit. Scope limits and existing platform
maintenance remain explicit, rather than a blanket security acceptance.

Primary technical references consulted:
[Git configuration environment](https://git-scm.com/docs/git),
[bare clone and no checkout](https://git-scm.com/docs/git-clone),
[Python descriptor-relative filesystem operations](https://docs.python.org/3/library/os.html),
[GitPython overview](https://gitpython.readthedocs.io/en/stable/intro.html), and
[Codex repository-local skill discovery](https://learn.chatgpt.com/docs/build-skills).
These are technical evidence, not CPKS governance. The installed Codex CLI inspected
during initial packaging was 0.147.0; `.agents/skills` follows the current official
local-discovery convention. If the running task's skill catalog has not refreshed,
restart Codex; no global installation is needed.

## Outputs and validation

Source, tests, this usage guide and the thin skill are repository artifacts.
Generated assessments/previews are noncanonical review artifacts, normally under
the authorized repository's `artifacts/`; handovers belong under
`artifacts/handovers/<task-id>/`. Apply provenance is an enduring repository artifact
because it preserves adopted-code origin. Re-resolve OPS for current placement,
retention and promotion instead of treating these examples as policy.

Run the offline synthetic suite with the verified repository interpreter:

```sh
<tools-repo>/.venv/bin/python -m pytest <tools-repo>/tests/reuse -q
<tools-repo>/.venv/bin/python -m ruff check <tools-repo>/src/cp_knowledge_tools/reuse <tools-repo>/tests/reuse
```

The HTTPS transport path is tested with a local Git-backed transport double; no
test depends on internet access. Real remote TLS/host access is an environment
precondition, not proven by that offline test. Git output/time and extracted content
are bounded; disk/CPU quotas for hostile Git packs remain a host sandbox concern.
