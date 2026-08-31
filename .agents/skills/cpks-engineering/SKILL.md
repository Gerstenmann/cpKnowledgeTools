---
name: cpks-engineering
description: Compatibility entry for earlier cpks-engineering references. Delegate authorized cpKnowledgeTools engineering to cpks-engineering-loop, including its shared assurance and independent challenge workflow. No additional authority or remote effects.
---

# CPKS Engineering

Compatibility routing: when this name is selected, read and execute
[cpks-engineering-loop](../cpks-engineering-loop/SKILL.md) as the normal entry
point, including its verification and independent challenge steps. The older
detail below is supporting guidance, not a second execution path. Resolve all
rule semantics live; this file does not freeze them.

Use this thin orchestration skill for an authorized repository engineering task.
`DEV-P05` remains the normative process rule home; this file is executable agent
guidance, not a governance copy, approval, policy engine, or runtime component.
Resolve current rules rather than treating this routing as frozen semantics.
Do not add a workflow engine, state machine, registry, or parallel rule model
merely to execute the loop.

```text
GOVERN → UNDERSTAND → INSPECT → RESEARCH when justified → EVALUATE → DECIDE
→ DESIGN → IMPLEMENT → VERIFY → REVIEW → RECORD / MAINTAIN / PROJECT CONTROL ↺
```

## GOVERN

Read the applicable repository `AGENTS.md`. Through the configured read-only
cp-wiki MCP, call `vault_info` → `resolve_governance_bundle` with stable IDs →
require exactly one active artifact and `integrity_ok: true` per required ID →
`read_active_artifact`. Stop affected material work on missing, ambiguous,
inactive, or integrity-invalid authority; report the exact ID and problem.
Never infer active versions from filenames, recency, memory, or generated views.

Start with `CPKS-FWK-AIW` for primary rule-home routing, `CPKS-FWK-ARCH`,
`CPKT-SPEC-ARCH`, `DEV-P05`, and `CPKS-SPEC-OPS`. Load only materially relevant
content and relationships, including the current architecture dependencies:

| Concern | Live rule homes / context |
| --- | --- |
| Business value and verified system state | `CPKS-FWK-BC`, `CPKS-BL`; distinguish intended architecture from implemented state |
| Development-agent authority boundary | `CPKS-DEC-030`, with execution details in `DEV-P05` / `CPKS-SPEC-OPS` |
| Verification and improvement | `CPKS-SPEC-TST`, `DEV-P04` when its triggers apply |
| Required research or third-party changes | `DEV-P06`, `CPKS-POL-SW-SUPPLY`, relevant security and architecture relationships |
| Security, privacy, processing, or privilege boundaries | `CPKS-SPEC-SEC` and its applicable rule homes |
| Named Work Package or specialized domain | Resolve its stable ID and applicable rule homes from live architecture and repository routing |

Apply Project/MVP context when relevant; it does not replace active governance.
Do not scan the whole Vault or preload unrelated contracts as routine preflight.
If this skill or another local instruction disagrees with live governance, use
the active primary rule home; do not invent a reconciliation or new authority.

Identify the actual authority basis: explicit Owner task, applicable active Work
Package, or other verified delegation. Respect its scope, preserve, exclusions,
deliverables, validation, recovery, and gates. A draft Work Package alone grants
no execution authority. The skill itself grants none either.

Verify the actual repository root, shared development/integration line, current
branch, HEAD, working tree, and relevant staged/untracked work. Use that shared
line by default; do not turn `main` into a parallel development line. Isolate
only for a concrete need with a known reintegration boundary under live OPS.
Preserve unrelated work; do not reset, clean, stash, or discard it for convenience.

Determine filesystem, tool, network, data, third-party, and remote-effect limits.
Apply the current `DEV-P05` / OPS execution envelope to the actual task; narrower
instructions prevail. Local repository writes and local commits are distinct
from push, merge, release, deployment, package publication, PR approval, and
external system writes. These effects are outside this local harness and need
separate authority. Write cp-wiki only when the live rule homes and the
concrete resolved authority permit the target mutation; never use technical
write capability or an owner-direct path to grant yourself authority. Keep
secrets out of code, fixtures, logs, and reports.

## UNDERSTAND

Briefly establish `engineering_problem`, `desired_outcome`, `acceptance_criteria`,
`preserve`, `out_of_scope`, and relevant hard constraints, including the business
benefit. Use the task, existing tests, and active contracts to derive acceptance.
Proceed when sufficiently clear; a separate formal acceptance document is not
required merely for ceremony. Escalate only material unresolved acceptance.

## INSPECT

Before external research or changes, read the relevant implementation, adjacent
interfaces/patterns, nearest tests, dependency manifests, and internal capabilities.
Keep inspection bounded to the task. Verify the repository interpreter and needed
dependencies before using them; do not assume an activated terminal environment.
Before inventing a helper or one-shot script for a deterministic routine, resolve
the Standard Operation Registry and reuse a tested operation if it supports the
concrete scope. Explain an unsupported-scope deviation; do not expand the kernel
just to perform a simple authorized edit.

A dirty tree alone is not a stop. For uncertain historical internal provenance,
use the live DEV-P05 / OPS bounded-recovery path only when the state is recoverably
preserved, the target follows independently from authority/contracts, scope is
authorized, ownership is safe, and hard constraints hold. Retain the historical
uncertainty and current repair evidence; never invent attribution. If origin may
be third-party/copied code, apply supply-chain rules instead of this recovery path.

## RESEARCH GATE

Explicitly record `research_gate: required` or `research_gate: not_required` with
a short rationale under current DEV-P05 after inspection. Use its actual triggers:
new nontrivial capabilities/infrastructure, open Build-vs-Reuse, third-party
adoption/updates or copied-code paths, and material alternative approaches merit
research; an established internal pattern or sufficient internal capability can
justify `not_required`. Do not research externally on every task or infer coverage
from a matching symbol alone.

- `not_required`: continue to EVALUATE without a research report.
- `required`: read and use the repository-local
  [software-reuse-assessment skill](../software-reuse-assessment/SKILL.md).
  Supply the capability need, verified target repository, architecture/security/
  dependency constraints, internal inspection results, and authorized research/
  network scope. Let that skill run DEV-P06 with its existing capabilities.
  Consume its candidate comparison, dispositions, overall strategy, conditions,
  provenance, and real blockers in EVALUATE / DECIDE / DESIGN.

Do not reproduce DEV-P06, candidate acquisition, license assessment, or adoption
mechanics here. Research is not installation or integration permission. Do not
invent sources or silently skip a required assessment if research is incomplete
or the skill is unavailable; identify the affected boundary. Revisit the gate
if inspection, design, or implementation reveals a materially new need.

## EVALUATE → DECIDE → DESIGN

**EVALUATE:** Compare internal and, when researched, external options against
functional fit, architecture, complexity, security, dependencies, maintenance,
testability, rebuildability, and business value. Keep rationale proportional;
there is no artificial scoring requirement. Preserve assessment conditions and
uncertainties; rejected candidates or an overall BUILD strategy are valid results.

**DECIDE:** Choose the technical approach autonomously within verified architecture,
policy, and scope. Normal engineering trade-offs do not require an Owner microgate.
Escalate a real normative decision, scope expansion, unauthorized architecture
change, or applicable hard constraint. A favorable assessment cannot waive these.

**DESIGN:** Before material implementation, identify the smallest coherent change:
affected boundaries, interfaces, data/error semantics, necessary transaction and
recovery boundaries, tests, and files. Do not add abstractions for formal
completeness. If the approach proves wrong, revise it within scope.

## IMPLEMENT

Implement autonomously within the authorized scope and preserve constraints.
Prefer existing internal capabilities and patterns, deterministic code for
deterministic rules, small explicit interfaces, and synthetic non-sensitive
fixtures. Do not change control-plane files or adjacent product areas merely
because this skill is being used.

Integrate new or updated third-party software only with the current positive
reuse/admission decision for the intended use and satisfied material conditions,
under `CPKS-POL-SW-SUPPLY`. Preserve copied-code provenance. Apply OPS environment,
interpreter, and dependency preflight; never repair by installing into an unknown
environment. Use the existing reuse skill's integration/adoption handover where
applicable, without bypassing its authority or acceptance checks.

## VERIFY — autonomous repair loop

```text
narrow relevant verification
→ failure: classify → diagnose → repair within scope → rerun ↺
→ relevant broader regression → REVIEW
```

For Python changes, typically use the verified repository interpreter from the
verified repository root, substituting actual paths:

```sh
<repo>/.venv/bin/python -m pytest <relevant-tests>
<repo>/.venv/bin/python -m ruff check <changed-python-paths>
```

Start with the narrowest meaningful checks, then broaden by actual impact.
For Markdown-only skill changes, discover and inspect the available local skill
validator, validate the changed skill, check composition/behavior, and run
`git diff --check`; do not run a full Python suite by habit. Invoke DEV-P04 when
its live triggers apply, without turning optional records into gates.

Classify failure as an in-scope defect, environment/test issue, unrelated existing
finding, or genuine contract/authority exception. Diagnose and fix repairable
failures without interrupting the Owner, then rerun affected checks. Investigate
flakiness or irreproducibility rather than reporting green. Re-enter DESIGN or
earlier phases when needed; do not accumulate patches around a wrong approach.

Never fit Expected Results, Golden Truth, or acceptance to the implementation
just to pass, weaken checks, or delete stable regression coverage. A regression
requiring an unauthorized business/normative expectation change is an exception.
Do not use global strict/full validation as a default gate or let unrelated
pre-existing lint/validator/test findings alone block this change. Report what
actually ran and its result; unavailable or failed checks are not passes.

## REVIEW → re-entry

Review the complete scoped diff against the task and acceptance, architecture,
dependencies, complexity, security/privacy/supply-chain exposure, error/recovery
paths, meaningful test evidence, scope drift, and preservation of others' work.
Look for simplification. A self-review does not replace an independently required
or human review under active rules.

Route findings back without an Owner gate merely for re-entry:

| Finding | Return to |
| --- | --- |
| Misunderstood outcome or acceptance | UNDERSTAND |
| Missed existing capability | INSPECT |
| Open Build-vs-Reuse | RESEARCH GATE, then reuse skill when required |
| Wrong approach | DESIGN, revisiting DECIDE / EVALUATE when necessary |
| Implementation defect | IMPLEMENT, then VERIFY again |

## RECORD / MAINTAIN / PROJECT CONTROL → completion

Keep only durable, relevant evidence in its proper home: significant design
choices, reuse/dependency/copied-code provenance when relevant, actual verification,
remaining findings, and the local commit reference. Do not create a document for
every iteration. If useful, place a non-canonical handover under
`artifacts/handovers/<task-id>/`; apply active OPS classification, retention, and
promotion rules. Generated handovers are not automatically Git artifacts or governance.
cp-wiki mutation is permitted only under resolved Vault-write authority and
the applicable MAINTAIN / PROJECT CONTROL envelope.

When the live DEV-P05 / OPS envelope and actual task allow `local_commit`, complete
it without another Owner microgate. Recheck root, shared integration line, branch,
HEAD, working tree/index, commit scope, and required verification. Stage only
explicit scoped paths/hunks; preserve unrelated staged work without including it.
Review the intended staged diff, commit locally, then verify commit contents and
remaining tree state. An unsafe commit boundary is an exception, not permission
to absorb foreign changes. Do not push or merge as part of local completion.

End with a concise structured summary:

- Outcome and changed files.
- Research Gate and rationale; reuse decision/conditions if assessed.
- Tests/checks actually run and results; overall completion state.
- Local commit ID if created, otherwise the actual reason.
- Remaining genuine findings, blockers/exceptions, and directly required work.
- Relevant resolved stable IDs briefly, and remote effects not performed.

## Exception policy

Apply management by exception under the live rule homes: maximum trustworthy
progress per unit of human attention. Stop the affected action, preserve state,
and identify the specific missing authority, evidence, or decision; continue safe
independent in-scope work. Do not claim completion while required work is blocked.

Real exceptions include materially unresolved authority/scope or unsafe repository
state; actual competing/ongoing work at risk; preserve not achievable; missing
material acceptance; a new normative decision or unauthorized architecture/scope
change; license/copied-code/security/supply-chain hard constraints or required
third-party provenance unavailable; a stable regression only solvable by an
unauthorized expectation change; required review authority unavailable; applicable
resource/tool boundaries exhausted; an unsafe scoped commit; or required external
effects lacking separate authorization. Explain the active rule and concrete
boundary when an Owner decision is necessary.

Not automatic stops: a dirty tree; uncertain historical internal provenance when
bounded recovery applies; repairable test/implementation failures; in-scope review
findings or revisable designs; unrelated existing validator/lint/test findings;
missing optional failure records; non-material open supply-chain assurance points;
a rejected research candidate; or BUILD as the best overall research strategy.
Keep such evidence visible without inventing a Human gate or hiding a hard block.

## RECORD / MAINTAIN / PROJECT CONTROL

### RECORD
Persist engineering evidence and local results. Local commits require resolved engineering authority; push/merge/release/deployment remain separate.

### MAINTAIN
Use the live Vault as writable canonical workspace only when the active governance and concrete authority make the target state derivable. Resolve rules/target/scope, verify fingerprints, preserve recovery evidence, apply the smallest mutation, reread and validate. Stop for genuinely new normative decisions, authority expansion, unresolved policy/security/privacy/legal choices or scope expansion.

### PROJECT CONTROL
When the Project Home grants standing `ai_autonomy_level: bounded_execute`, consume its tolerances as execution boundary. Keep Work Items flowing, update project-control records, execute linked DEV-P05 work and perform authorized local Vault maintenance until a Human-Gate trigger occurs.

```text
local full-vault read/write capability != authority
standing bounded_execute + tolerances + no human-gate trigger = autonomous bounded project flow
```
