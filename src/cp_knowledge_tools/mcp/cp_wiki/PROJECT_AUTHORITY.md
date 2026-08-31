# Project Home authority sources

`projects.resolve_project_authority(Vault(...), reference, kind="project_home")`
resolves an existing Project Home for PWI authority evaluation. The supported
source kinds are `project_home` and the alias `project`. Both produce canonical
`kind: project_home`; the reference is the exact, unversioned `project_key`.

```yaml
authority_basis:
  - kind: project_home
    reference: communications-knowledge-pilot
```

This is an implementation-local source interface under the active
`CPKS-SPEC-PRJ` and `CPKS-SPEC-PWI`. It adds no Project field, normative authority
class, Runtime Authority Contract, or mutation capability. The existing K1
`RuntimeAuthorityResolver` continues to accept only its independently verified
grant sources. A Project source result cannot be substituted for such a grant.

## Resolution and evidence

The resolver scans the configured Vault's current `Projects/` tree without a
search-result cutoff. It matches `type: project` and `project_key` exactly,
excludes `Archive/`, requires one current Home, and checks active lifecycle,
identity/path, required metadata, date consistency and Project controls. It does
not select the first hit, a similarly named document or the largest version.

Duplicate YAML keys in an authority candidate fail closed, including conflicting
`type` keys. Non-Project records are classified without turning their unrelated
metadata into authority-validation inputs. Unclassifiable/malformed metadata
cannot silently disappear from discovery. Symlinks and nonregular files are
rejected. Reads use the existing descriptor-relative, bounded `RootHandle`;
metadata depth and expanded alias size are also bounded. These checks are not an
OS sandbox, and discovery is not an atomic snapshot against concurrent writers.

The returned JSON contains the actual source path, byte SHA-256, Project version,
Owner, autonomy level, unchanged tolerances/gates, complete frontmatter and body.
`checked_on` records the local calendar date of validation; `created`/`revised`
are checked for consistency, not reinterpreted as approval timestamps.
Resolution rereads the current source on every call; no durable permit is cached.
Fingerprinting uses exactly the bytes read for parsing, including line endings.

## Source resolution is not action approval

A successful result has `source_status: resolved` and **always**:

```json
{"execution_authorized": false, "execution_eligibility": "not_evaluated"}
```

These values mean this source resolver has not issued any execution decision.
The responsible evaluator must separately assess the concrete action/scope,
Project tolerances, AI authority, dependencies, Human Gates, hard constraints,
Work Item control conditions and actual tool/data permissions against the live
sources. The result enumerates these pending checks. Missing autonomy does not
become `bounded_execute`; a successful lookup does not waive a gate. Prose such
as “DEV-P05 execution allowed …” is preserved as evidence, never keyword-matched
into a permit. Resolve again before acting if the inputs may have changed.

The Python `today` argument exists for deterministic checks/tests. The CLI and
MCP use the current date and expose no override or caller-supplied permit/scope.

## CLI and MCP

Both entry points call the same resolver and are read-only:

```sh
.venv/bin/python -m cp_knowledge_tools.cli.cpks project authority resolve \
  communications-knowledge-pilot --vault-root /Users/cp/Documents/cp-wiki
```

CLI exit `0` means source resolution succeeded, **not** that execution is
authorized. Exit `2` reports a blocked lookup with a diagnostic `code`.

The cp-wiki MCP tool is `resolve_project_authority(reference, kind="project_home")`
with explicit read-only/non-destructive annotations. An already-running server
must load the updated repository code before this new tool appears; the CLI
works independently of client tool-catalog refresh. No global Codex settings,
Vault content or running MCP process is changed by installing this code.

## Design and verification

USE existing bounded file reads, strict YAML parsing, hashing and serialization;
BUILD only the Project-specific identity/control checks and thin presentations.
No dependency, external source code or policy engine was adopted. The Research
Gate uses DEV-P05's small established-pattern path. Adding an automatic scope or
policy interpreter requires a separate assessment and authorization.

`tests/mcp/test_project_authority.py` covers source identity, current/historical
separation, revocation/drift, malformed and ambiguous metadata, boundary/resource
failures, absence of implicit grants, and actual CLI/MCP behavior. Existing
Managed-Artifact/Runtime-Authority and source-processing regressions must remain
unchanged. This source resolver is not the full `project_work_item_current`
validator and does not move Work Items.
