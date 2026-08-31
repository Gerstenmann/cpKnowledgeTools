---
name: cpks-supply-chain-assurance
description: Produce scoped software inventory, dependency delta and scanner evidence for cpKnowledgeTools research, admission and deeper reviews. Callable from reuse assessment or engineering; findings never automatically accept dependencies.
---

# Supply-chain assurance

Resolve live `DEV-P06`, `CPKS-POL-SW-SUPPLY`, `CPKS-SPEC-SEC`, `CPKS-SPEC-OPS`
and materially relevant architecture through the active-artifact workflow in
[the engineering loop](../cpks-engineering-loop/SKILL.md). Use the existing
[reuse assessment](../software-reuse-assessment/SKILL.md) for candidate comparison,
provenance and reviewed acceptance. This skill grants neither installation nor
license authority.

Use the verified interpreter and [shared assurance core](../../../src/cp_knowledge_tools/assurance/README.md).

| Profile | Scope |
| --- | --- |
| research | static candidate/repository evidence without executing or adopting candidates |
| admission | concrete dependency/tool use, SBOM, vulnerabilities, licenses, provenance and privileges |
| deep-review | relevant skill/plugin/hook/native/copied-code risks and recovery |
| delta | changes from prior bound inventory and the affected acceptance dimensions |

Installed metadata is only an interpreter snapshot. A lock hash does not prove
environment sync. Missing license expressions, unknown provenance and absent
scanners are not clean findings. Determine their materiality under live policy.

Only execute an external scanner after its intended tool use, concrete version,
source/license, privileges and environment have been reviewed. Use fixed argv,
finite time/output budgets, scoped local inputs and no inherited credentials.
Vulnerability-service network access can disclose package names/versions and
needs a resolved egress scope. Never install, update, fix or copy candidates as
an implicit scan side effect. Keep sensitive raw outputs local and out of Git.

Distinguish inventory, no known findings, findings, partial/error and unavailable.
Record versions, hashes, input scope and limitations. Scanner output is
`external_tool_finding`, never `accepted`. Relevant human or licensing gates
remain separate. A nonmaterial unknown is not automatically an adoption veto.
