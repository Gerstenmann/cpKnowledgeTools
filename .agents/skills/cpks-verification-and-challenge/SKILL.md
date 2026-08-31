---
name: cpks-verification-and-challenge
description: Verify a scoped cpKnowledgeTools change with impact-based checks and separately attributed reviewer evidence. Use for pre-commit verification or an authorized read-only challenge; never alter Golden Truth or acceptance to obtain a pass.
---

# Verification and challenge

Resolve live `CPKS-SPEC-TST`, `DEV-P04`, `CPKS-SPEC-OPS`, relevant architecture,
contracts and actual task authority through the active-artifact workflow in
[the engineering loop](../cpks-engineering-loop/SKILL.md). Read code and nearest
tests; inspect branch/HEAD/index and preserve foreign work.

Use the verified interpreter and [shared assurance CLI](../../../src/cp_knowledge_tools/assurance/README.md).
Select explicit `--path` and `--test` scopes where automatic mapping is insufficient.
For a committed change provide `--base` against the verified comparison commit.
Read-only reviewers must pass `--no-evidence`; return output to the coordinating
parent for authorized persistence. Run tests only when their side effects are
compatible with the assigned sandbox; an unavailable check stays incomplete.

| Class | Evidence required according to actual impact |
| --- | --- |
| Fast | changed code, Ruff, targeted unit/contract tests and structured inputs |
| Regression | full relevant suite, applicable rebuild/idempotence/Golden regression, coverage and typing |
| Supply chain | dependency, tool, skill, plugin, hook or copied-code delta |
| Extended | applicable security, license, provenance, performance, recovery and human review |

The CLI does not implement every row automatically. Read its individual checks,
scope, warnings and incomplete entries. A subset pass is not full acceptance.
Run missing applicable checks explicitly and attach exact commands and results.

Label evidence accurately: `self_check`, `independent_agent_challenge`,
`human_review_required`, `external_tool_finding`. The coordinating parent assigns
one bounded read-only `cpks-reviewer` after implementation, supplying requirements
and raw artifacts. Reuse an existing independent challenge; a reviewer must not
delegate recursively or create an additional reviewer.
Do not supply a desired verdict. The reviewer may inspect and run existing safe
checks, but must not edit production code or expectations. Reverify after fixes.

An agent challenge is not human or organizational independence. Preserve required
human gates and unresolved findings. Never weaken tests, thresholds or acceptance.
Report actual results, input hashes, changed paths, tool versions and evidence
references; do not reuse stale evidence after the code/input state changes.
