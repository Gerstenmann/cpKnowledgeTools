---
name: cpks-current-state-drift-audit
description: Audit current cpKnowledgeTools and cp-wiki evidence read-only for drift between repository, active rules, baseline, project context and handovers. Produce findings and proposed dispositions, never canonical updates or Ready transitions.
---

# Current-state drift audit

Resolve `CPKS-FWK-AIW`, `CPKS-FWK-ARCH`, `CPKT-SPEC-ARCH`, `CPKS-BL` and
`CPKS-SPEC-OPS` live through `vault_info`, stable-ID bundle resolution, unique
active/integrity checks and `read_active_artifact`. Add only relevant rule homes.

Run `cpks drift audit --no-evidence` using the verified interpreter and explicit repository and
Vault roots; see [supported commands](../../../src/cp_knowledge_tools/assurance/README.md).
Use a previous evidence file for temporal comparison. Treat earlier reports as
historical observations, never authority. Without prior evidence report a snapshot.
Return JSON/text to the parent or user. A coordinating parent may separately
persist it within its authorized output scope; do not escalate a read-only audit
merely to write an evidence file.

The deterministic audit resolves active artifacts and compares repository/rule
fingerprints; it does not reconcile prose. Independently compare the actual active
baseline statements, research catalogue, Project Home, Roadmap, Ready items and
handover evidence with direct repository observations. Do not infer absent
capability from old prose, or working capability from a file's mere existence.
Historical HEADs and `validated_against` references need not match today's state.

For each proven deviation report subject, information class, responsible rule or
update home, observed/claimed state, evidence references, severity/operational
impact and recommended disposition. Distinguish temporal change, expected lag,
missing evidence and actual contradiction. Do not fabricate a global all-clear.

All inputs remain unchanged. No baseline/catalogue maintenance, Vault writes,
Ready promotion, authority supplementation or acceptance change. Route proposed
repairs to separately authorized engineering/maintenance or Project Control.
