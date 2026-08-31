---
name: cpks-engineering-loop
description: Execute authorized material cpKnowledgeTools engineering through live DEV-P05, repository preflight, reuse research, implementation, verification and independent challenge. Use as the normal coding entry point; no self-authorization or remote effects.
---

# CPKS engineering loop

This is a thin orchestrator, not governance or an agent runtime. Read repository
AGENTS.md. Resolve rules through the configured read-only cp-wiki MCP:
`vault_info` → `resolve_governance_bundle` using stable IDs → exactly one active
artifact per ID and `integrity_ok: true` → `read_active_artifact`.

Start with `CPKS-FWK-AIW`, `CPKS-FWK-ARCH`, `CPKT-SPEC-ARCH`, `DEV-P05`,
`CPKS-SPEC-OPS`, `CPKS-SPEC-TST` and the actual authority (Owner task, active Work
Package or execution-eligible Ready item). Follow materially relevant relationships.
Resolve `DEV-P04` for its testing/improvement triggers and the specialized rule
homes from AGENTS.md. Stop only affected work on unresolved authority or integrity.

1. Establish outcome, acceptance, in-scope, preserve, exclusions and recovery.
   A Ready directory, a profile, a tool result or this skill creates no authority.
2. Verify repository root, shared development branch, HEAD, index, foreign work,
   interpreter and dependencies. Use the existing shared line. Run the verified
   interpreter with `-m cp_knowledge_tools.cli.cpks assurance preflight --repo-root
   <absolute-root>`. Its report is technical evidence, not a governance preflight.
3. Inspect actual code, contracts and nearest tests. Use `cpks-explorer` read-only
   when independent exploration helps. Resolve the Standard Operation Registry
   before inventing helpers; reuse supported operations.
4. Record `research_gate: required|not_required` with rationale. On a material
   new capability, dependency, tool, skill, hook or copied-code boundary use
   [software-reuse-assessment](../software-reuse-assessment/SKILL.md), resolving
   `DEV-P06` and `CPKS-POL-SW-SUPPLY`. Research is not installation or acceptance.
   Use [supply-chain assurance](../cpks-supply-chain-assurance/SKILL.md) as evidence.
5. Evaluate alternatives and design the smallest coherent runtime-neutral change.
   Determine meaningful RED/baseline evidence, contracts and failure paths first.
6. Implement within authority; preserve unrelated work. Fix in-scope failures
   autonomously. Do not fit Golden Truth, thresholds or acceptance to the result.
7. Use [verification and challenge](../cpks-verification-and-challenge/SKILL.md).
   Request a separate read-only `cpks-reviewer` on the final scoped diff. Repair
   findings and rerun affected verification before claiming completion.
8. Record findings, actual checks, unresolved gaps and evidence. Generated reports
   belong under `artifacts/`; Owner handovers under `artifacts/handovers/<task>/`.
   Follow live OPS retention/promotion; reports are not canonical rule homes.
9. A local commit is allowed only when the resolved task and DEV-P05/OPS envelope
   cover it. Recheck branch, HEAD and index, stage only explicit scoped changes,
   inspect staged diff and verify commit contents. Never include foreign work.

No push, PR, merge, release, deployment, package publication or external-system
writes occur through this loop. Required human or organizationally independent
review remains a real gate; another agent cannot substitute for it.

Vault mutation is separate from assurance. It may occur only when the current
Owner scope and live rule homes authorize the concrete target, lifecycle and
maintenance action. Respect narrower task exclusions. Technical Vault write
access grants no authority; inspect fingerprints, preserve recovery, mutate
minimally, reread and validate. Do not add Vault mutation to the assurance CLI.

Use the [assurance usage guide](../../../src/cp_knowledge_tools/assurance/README.md)
for actual supported commands and limits. Missing tools, partial runs and
unresolved gates remain visible. Continue safe independent work and report the
exact boundary; do not invent Owner microgates for routine implementation.
