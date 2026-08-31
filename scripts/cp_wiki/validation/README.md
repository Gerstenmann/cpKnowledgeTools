# Managed Artifact Validator 3.2.1

The `validate_cpwiki_managed_artifacts_v3_2.py` entry point and report filenames
remain compatible with the 3.2 family. Revision 3.2.1 separates diagnostic
severity from the effect on a specific operation. It does not grant authority,
approve a lifecycle transition or replace live governance resolution.

## Modes

Use the verified project Python environment. Examples run from the repository
root; replace the Vault and report paths with explicit local paths.

```sh
# Report findings without turning them into an operation stop (default).
<project-python> scripts/cp_wiki/validation/validate_cpwiki_managed_artifacts_v3_2.py \
  --vault /path/to/cp-wiki --report-root /path/to/reports

# Check only the specified operation and its explicit affected targets.
<project-python> scripts/cp_wiki/validation/validate_cpwiki_managed_artifacts_v3_2.py \
  --vault /path/to/cp-wiki --report-root /path/to/reports \
  --gate-operation artifact.activate \
  --target 'Systems/cpKnowledgeSystem/Governance/Policies/EXAMPLE Policy.md' \
  --target 'Archive/Systems/EXAMPLE@0.1 Policy.md'

# Explicit global conformance audit, not a default mutation prerequisite.
<project-python> scripts/cp_wiki/validation/validate_cpwiki_managed_artifacts_v3_2.py \
  --vault /path/to/cp-wiki --report-root /path/to/reports --strict-exit
```

Supported gate operations are `artifact.activate`, `artifact.revise` and
`artifact.transition`. They share the same technical check; the operation name
records what the caller is withholding. The validator does not verify the
before/after transition, authority, rollback or semantic change impact.

Targets must be explicit Vault-relative Markdown paths inside the supported
validation profiles. Repeat `--target` for every changed or affected artifact
that remains in the proposed state. Deleted paths and rollback evidence belong
to the caller's transaction checks. Missing or unsupported targets are
`incomplete`, never silently clear. `--gate-operation` requires targets and
cannot be combined with `--strict-exit` or `--self-test`.

The gate considers:

- Confirmed errors and incomplete evidence on the explicit targets, using their
  applicable current or historical validation profile.
- Identity, path and lifecycle integrity of their direct required references.
  An ambiguous alias or exact version, wrong canonical path or missing target
  cannot become clear merely because it lives in a different file.
- Identity collisions involving a target, including duplicates outside its
  normal validation zone.

Warnings and information do not block. Unrelated findings remain in both
reports with `gate_effect: out_of_scope`. An incomplete required check has its
own status; it is not a proven conformance error. Required references without a
supported lifecycle profile also remain incomplete. The gate does not traverse
the entire dependency graph, impose today's dependencies on historical evidence,
or perform semantic, security, privacy or legal review. Callers must identify
the actual affected scope and enforce those separate requirements.

| Exit | Default report | Operation gate | Explicit `--strict-exit` |
| --- | --- | --- | --- |
| 0 | Report completed, including findings | Scoped technical checks clear | Global checks conformant |
| 1 | Not used for findings | Confirmed relevant error blocks this operation | Global conformance errors |
| 2 | Invalid invocation or scan unavailable | Required evidence incomplete, or invocation/scan unavailable | Global evidence incomplete, or invocation/scan unavailable |

When both errors and incomplete checks exist, exit 1 takes precedence; all
incomplete evidence remains in the report. Report mode can return 0 with
`conformance.status: incomplete`. Exit 0 never means mutation authorization.

## Evidence and compatibility

Markdown and JSON retain all unsuppressed diagnostics. JSON adds schema
`cpks.managed-artifact-validation/1`, a separate `conformance` summary and `gate`
decision. Each finding includes `rule_source`, `validation_profile`,
`finding_status`, `gate_effect`, `blocking_operation` and `gate_reason`.
Input fingerprints hash the decoded UTF-8 text; they do not attest an atomic
Vault snapshot. Rules are implemented version pins, not live authority claims.

Resolution searches `Systems`, `Development`, `Templates`, `Processes` and
central `Archive`. Reference-only documents retain limited identity/path checks
rather than receiving a current-artifact profile. Historical references resolve
the exact requested version; the validator neither requires it to be active nor
substitutes an active version. Real archive path drift remains an error.

Versions are checked as YAML strings. Both an unquoted three-part string such as
`1.2.3` and a quoted string followed by a comment are valid; numeric YAML values
remain errors. A unique resolvable legacy alias produces an advisory warning.
Conflicting aliases still produce errors. Incomplete version history is reported
as uncertainty instead of falsely asserting an invalid initial version. A new
draft with a demonstrably invalid start still fails its existing version rule.

Default execution reads the Vault and writes reports only below `--report-root`.
The retained optional `--publish-report` path writes a Vault report and requires
separate caller authority; it is not part of the scoped gate. No automatic
metadata repair, governance change, activation or suppression is performed.

The two baseline lifecycle scripts in this repository now pass their concrete
targets to the operation gate. They retain rollback on exits 1 and 2. Other
clients that explicitly use `--strict-exit` retain global audit behavior and must
not interpret that flag as a universal stop for unrelated local work.
