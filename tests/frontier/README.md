# WI-018 bounded versatility preparation

`workshop-versatility@1` is a **frontier**, not a new regression truth for
Minecraft and not an implemented LLM capability. Three synthetic HTML inputs
contain nine paragraphs: equipment handover, check planning and clarification,
in German and English. No translation service or new adapter is involved.

Human-readable Golden: Project `communications-knowledge-pilot`, document key
`golden-workshop-frontier`, **Golden Truth – Werkstattübergabe DE-EN Frontier**.
Machine Expected is `tests/golden/source_to_knowledge/workshop_versatility/`;
input-only fixtures are `tests/fixtures/source_to_knowledge/workshop_versatility/`.
Both form scenario version 1. Source hashes bind Expected to the authored inputs.
Material source/meaning changes need reviewed scenario versioning, never automatic
Golden updates to obtain a pass. `example.*` predicates, labels and roles are
local test concepts, not additions to any Core vocabulary or activated profile.

Use the verified locked project Python, from the repository root:

```sh
<project-python> -m pytest tests/frontier -q
<project-python> -m tests.frontier.workshop_baseline --output artifacts/handovers/WI-018/baseline.json
<project-python> -m ruff check tests/frontier
MYPYPATH=src <project-python> -m mypy --follow-imports=skip tests/frontier
```

The report distinguishes:

| Evidence | Meaning and limit |
|---|---|
| Source boundary GREEN | Actual capture/normalization/Source validation and local synthetic Policy-bound content resolution for all nine fragments |
| Contract vector tests | Sixteen manually authored **assertion vectors** can use the existing Entity, Claim, Event, Participation and Relationship dataclasses; not generated interpretations |
| Identity/Lifecycle tests | Existing ChangeCandidatePipeline rejects preempted decisions and foreign publication authority; unresolved questions survive registration and assessment |
| Oracle negatives | A fixture-specific exact oracle rejects altered test vectors and changed source bytes; not a production entailment checker or untrusted-response decoder |
| `not_executed_missing_capability` | Inspection of actual semantic exports, product Python and configured entry points found no generic LLM producer; zero generated candidates and external requests |
| `requires_reinspection` | Product bytes changed since the bounded absence audit; the old finding cannot silently remain current |

`audit.v1.json` records an inspected code state, not an invented producer registry.
The harness never imports a guessed missing module or builds a fake LLM. It does
not use deliberately empty interpretation rules as proof that language processing
failed. Any product-tree hash update requires actual code reinspection.

The candidate dataclasses have no strict runtime schema validation. Perspective
uses the existing EvidenceDimensions/EvidenceAssessment contract; open identity
questions use SemanticChangeProposal and downstream Lifecycle APIs. The common
logical contracts are sufficient for this checkpoint
(`contract_sufficient_for_checkpoint`); a unified transport/decoder and complete
LLM invocation provenance are technical implementation work, not new semantics.

Existing Core preparation/validation binds older exact KM/KPR versions
(`validation/core/inputs.py`, `profiles.py`, `rules.py`). Regression against those
implementations is **not full current conformance** with live KM@0.22/KPR@0.5.
The next scope must revalidate those bindings and the actual consumed structures.
No product or normative change is made here to conceal that gap.

Runtime isolation is exercised with filesystem-read guards: capture, normalize,
resolution and product inventory cannot read Golden. Expected is used only by
the separate assertion oracle and the audit is read only during reporting.
The harness rejects unexpected keys in the top-level manifest, source records,
bounds and processing metadata, including embedded Expected payloads. This is
the finite test-driver input contract, not a new production Candidate schema.
No future generator exists to test yet; its own input-isolation gate remains
mandatory implementation work. The frozen local synthetic Policy is not provider
permission. Allowlisted future Source/Evidence input still needs the concrete
authorized processing context; Golden, reviews and completion reports are excluded.

Contract-revalidation coverage uses the following existing roles:

| Required dimension | Technical projection and boundary |
|---|---|
| Entities, Claims, Events | Corresponding `Proposed*` types; reported statements, actual/planned time remain distinct |
| Participation | Entity + event + role; planned event does not imply performed attendance |
| Relationship | ProposedRelationship plus the qualified relational Claim; no duplicate evidence gain |
| Evidence | ProposedEvidenceLink key → actual Evidence Address → captured Source/Snapshot |
| Perspective | EvidenceAssessment references the **link key**, not the technical Address ID; EvidenceDimensions retains perspective |
| Qualification | Claim qualifier / applicability condition; no confidence substitution |
| Unknown | KnownGap and empty result with visible gaps; no invented scalar/date |
| Identity | Open questions in SemanticChangeProposal, noncanonical registration, unresolved assessment |
| Producer provenance | Explicit assertion-vector origin; complete model-invocation provenance remains missing |

These are representability and scoped boundary checks. They do not assert that a
single dataclass validates arbitrary model responses against all active contracts.

## Following implementation scope: `work_package_required`

This is a concrete **scope proposal**, not a Work Package, active authority,
provider choice or permission to implement. WI-018 stops after preparation.

1. Resolve current governance and an adequately authorized **active** implementation
   Work Package. Run DEV-P05 Research Gate; if required, resolve DEV-P06 and
   software-supply rules before selecting/integrating any dependency or provider.
2. Implement a generic semantic producer behind the current normalized Source/
   Evidence boundary, consuming authorized DE/EN material without scenario keyword
   rules or Golden. Deterministic and model producers must share Candidate semantics.
   Provider, model, local/cloud, invocation protocol and prompt design remain open.
3. Materialize and validate the untrusted Candidate transport against current KM,
   KPR, SRC, SEC and VAL, including Perspective/Qualification, open identity
   questions, unknowns, evidence roles, time, relational Claim linkage and scoped
   Participation. Revalidate old Core bindings; distinguish a technical update
   from a normative conflict. No private alternate ontology or automatic merge.
4. Preserve real source/snapshot/address lineage. Add grounded rejection of invented
   provenance and unsupported content. Confidence cannot substitute for Evidence.
   Preserve gaps and abstention without declaring missing information false.
5. Record producer/model/provider/version, task/prompt version, toolset, material
   parameters, input refs, policy context, run/correlation ID and timestamp.
   Route accepted proposals through existing registration/identity/policy/review/
   publication responsibilities; no direct Source→LLM→Knowledge shortcut.
6. Enforce processing permission before any call, including local/external zones,
   concrete subjects, consumer, purpose, operations, policy anchors and applicable
   profiles. No credentials, provider requests or cost limits are authorized by
   this preparation. Bound the eventual invocation budget in that WP.
7. Execute this frozen frontier: at most 24 payloads, three open/distinct identity
   cases, four gaps, five repetitions per reviewed frozen configuration. Evaluate
   grounded semantic coverage/precision, unsupported assertions, correct abstention,
   identity safety, schema/provenance and variability. Exact wording/IDs are not
   stochastic criteria. Define scenario-local acceptance/tolerances before runs;
   do not invent global thresholds or fit Golden to model output.
8. Independently challenge machine results and obtain the required Human
   Plausibility review. Evaluate Raw Sources + LLM versus structured Knowledge + LLM
   for the same business questions: what was returned/planned, who participates,
   and what remains unknown about release, cost and ownership? Compare reuse,
   unsupported answers, uncertainty/evidence visibility and actual resource use.

Deliverables: scoped producer and transport/validation integration, current
contract-conformance evidence, reproducible bounded runs and negative tests,
provenance/policy evidence, human review, effectiveness findings and recovery
instructions. Preserve all existing baselines and foreign work. Keep WI-003 state
and acceptance unchanged unless a separate Project-Control action authorizes it.
The final HR-006 path must consider the **completed implementation/evaluation**
gate, not merely WI-018 Done.

Stop on a normative Candidate/Core gap, unresolved authority, unpermitted processing,
unbounded scope, Golden leakage, or canonicalization/authority bypass. No production
Knowledge is mutated during this frontier. Recover by retaining prior baselines,
isolating rejected outputs and reverting only the implementation's scoped changes
under the future Work Package; never overwrite Expected or unrelated work.
