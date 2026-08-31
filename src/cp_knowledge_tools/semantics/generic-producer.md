# Generic semantic producer: technical contract v1

`GenericSemanticCandidateProducer` transforms an admitted backend's untrusted
UTF-8 JSON response into the existing noncanonical `SemanticCandidatePayload`
contracts. There is no model client, credential lookup, retrieval, retry loop,
tool executor, review, canonicalization or publication path in this component.
The tests use a mechanical byte-returning backend, not a language model.

## Host and backend boundary

The trusted host resolves current task authority, source processing permissions,
profile applicability and backend admission. `SemanticTask.rule_basis_refs` records
the implementation's governed contract basis; it does not dynamically resolve
governance or authorize a task. A change in applicable contracts requires review.

Call `prepare_invocation` with captured Sources, matching
`NormalizedSourceRepresentation`s, existing Evidence Addresses and a trusted
Source adapter implementing `resolve`. Each Evidence Address must match its
captured Source, Snapshot, Source Record, raw dependency and text hash, resolve
through that adapter, and occur in a corresponding normalized record or segment. Captures
and representations pass their existing validation contracts. Passage-preserving
normalization is supported; a normalization that removes or rewrites the supplied
passage fails closed. This does not prove semantic entailment.

All limits are explicit positive invocation configuration: response bytes,
candidates, collection items, string characters, JSON nesting depth, total parsed
nodes and aggregate evidence input characters. There is no global scenario limit.
The host bounds task instructions and its own trusted configuration. The backend
must also enforce byte/time/usage limits while receiving its transport; the core's
byte check happens before parsing, after the backend returns bytes.

`prepare_invocation` creates a handle namespace from the invocation reference and
maps handles to authoritative Evidence Addresses. Use a unique invocation reference
per attempt. Only handles and allowlisted passage text cross `BackendRequest`;
raw capture bytes, local source locations, resolvers and Policy Configuration do
not. Source text stays in `evidence[].content`, separate from versioned host task
instructions. A future backend must preserve that separation in its prompt roles
and never execute source instructions or model tool calls automatically.

Before `SemanticBackend.invoke(request)`, the core builds a `PolicyEvaluationInput`
with action `process` and operations `read_content`, `transform`, `classify`,
`derive`, `create`. Subjects include concrete Evidence Addresses and Snapshots;
the effect scope binds input/configuration hashes including backend, processing
zone, task, profiles, actor, parameters and run. Only a current, bound permit or
satisfied conditions decision proceeds. A local fixed-width UTC view avoids the
legacy evaluator's lexical offset comparison; provenance fingerprints both the
original and evaluated configurations. This host-supplied policy context is never
constructed from source/model text. The core cannot verify a backend's claimed
identity, enforce a remote provider's retention, or grant processing authority.

The backend implements `invoke(BackendRequest) -> bytes`. It must implement this
versioned wire contract, translate provider errors/refusals without inventing
candidates, and bound transport resources. The core rejects invalid responses as
`ValueError`, propagates backend errors, and never automatically retries. A future
retry needs a fresh invocation identity, current policy and a bounded budget.

## Closed response representation

The root is an object with exactly these six required fields:

```json
{
  "transport_version": "1",
  "invocation_ref": "the exact request invocation_ref",
  "candidates": [],
  "gaps": [],
  "identity_proposals": [],
  "evidence_assessments": []
}
```

An empty result is valid abstention. No output defaults to a positive assertion.
UTF-8 errors/BOM, trailing JSON, duplicate keys at every depth, nonfinite numbers
(including overflowing exponents), invalid Unicode scalars, unknown fields,
wrong types, invalid local references and exceeded limits reject the whole result.
No candidate is returned or registered until every row and cross-reference passes.

Every candidate has required `kind`, `proposal`, `evidence`. Optional fields are
`time`, `epistemic_context`, `applicability`, `known_conflicts`, `gaps`. Defaults
are empty arrays, absent epistemic classification and empty applicability.
Unknown candidate/semantic/provenance/authority fields are rejected.

`proposal` is a closed projection of the corresponding common dataclass:

| kind | Required fields | Optional fields (default null) |
|---|---|---|
| entity | entity_key, label, entity_class | none |
| claim | claim_key, subject_entity_key, predicate_ref, value | object_entity_label, statement, time_modality, value_qualifier |
| event | event_key, event_type_ref, label, event_time, time_precision, time_modality | none |
| participation | participation_key, entity_key, event_key, role | none |
| relationship | relationship_key, subject_key, predicate_ref, object_key | none |

Fields are nonempty strings except nullable Claim fields and `event_time`;
`value` accepts a finite JSON scalar or null. Keys and reference strings match
`[A-Za-z][A-Za-z0-9_.:-]*`. Candidate keys are unique within the invocation and
remain local proposals, never canonical object IDs. Entity classes, event types
and scalar Claim predicates are identifiers, not a newly imposed global ontology.

Claims require a statement or a structured subject/predicate. Referenced subjects
must be proposed Entities. An object label must resolve unambiguously within the
same response and cannot coexist with a scalar value. Participation references
an Entity and Event. Relationships connect distinct Entity/Event/Claim local keys
using the governed asserted predicates; structural `contains`, `has_evidence`,
`previous_version`, `derived_from`, `references` are not inferred relationships.

Evidence is a nonempty array of exact `{key, handle, role}` objects. Link keys are
unique across the response; handles must belong to the invocation. Roles are
`supports`, `contradicts`, `qualifies`, `reports_statement`, `derivation_input`.
Only the host maps a handle to its actual Evidence Address.

Time objects have exactly `role`, `value`, `precision`, `modality`. Null time
requires precision `unknown`; a supplied time may also have unknown precision.
Event time requires an Event/Participation
context and must agree with an Event proposal's time fields. Calendar meaning is
not inferred or proven. Epistemic context has exactly `status` and
`classification_basis`; statuses follow KM-VOC. `confirmed` without a `supports`
link is rejected; even a supports link does not prove truth. Applicability has
exactly `context_refs` and `conditions` arrays. Context refs are proposed applicability
references, checked for syntax only, not resolved or granted authority by this core.
Known conflicts are text arrays.
Controlled time/participation/predicate sets are explicitly listed in
`candidate_transport.py`; profile extensions are unsupported until implemented.

Gaps (root or candidate) have exactly `gap_code`, `detail`, `evidence_handles`.
Handles are nonempty, distinct and allowlisted. A gap describes an unknown in its
grounding context; it does not assert that the source supports a missing value.
Null, qualification and abstention are retained without coercion to false.

Identity proposals have exactly `left_key`, `right_key`, `rationale`. Both keys
refer to distinct proposed Entities. They become unresolved questions on both
payloads, never a Same-Object decision. Evidence assessments have exactly
`claim_key`, `evidence_link_keys`, `dimensions`, `uncertainty`. Links belong to that
Claim; dimensions contain exactly the existing nine `EvidenceDimensions` fields,
including perspective. The host stamps assessment method, purpose and provenance.

## Result and lifecycle

`GenericSemanticResult` carries common payloads, gaps, Evidence Assessments and
`InvocationProvenance`. Provenance records genuine backend/method/task/instruction
versions, parameters/tools, concrete inputs, policy/profile bindings, processing
zone, run/correlation/invocation, timezone timestamp, and SHA-256 fingerprints of
configuration, input, raw response, accepted result and individual payloads and
assessments. Candidate extraction and deterministic semantic mapping are null;
no fake regex/rule is introduced. Hashes use existing canonical JSON serialization;
raw-response hashing is over exact bytes. Fingerprints detect binding changes,
not authenticity against a malicious trusted host.

`LifecycleCandidateRegistrar.register_semantic` accepts a common payload with its
bound invocation provenance and applicable Evidence Assessments. It creates a
local noncanonical revision, preserves the rich semantic payload, and does not
invent a Finding, prior object or ChangeCandidate. Identical input/idempotency
keys reproduce the same revision. Intake verifies membership in the accepted
payload/assessment hashes. Keep the full result as the correlation bundle for
cross-candidate references and pass every relevant assessment when registering.
The existing Same-Object, review, policy and publication gates remain downstream.
Do not send these rich payloads through the legacy MVP materializer, which has a
narrower entity-relation contract. The existing core validation profile remains
version-pinned to its older KM/KPR basis and is not evidence of current generic
Candidate conformance.

Hermetic tests establish transport, grounding, policy and lifecycle mechanics.
They establish no DE/EN extraction quality, prompt-injection robustness, truth,
release status, price, ownership or model versatility. Golden/Frontier paths are
never runtime inputs. Real model evaluation and human plausibility are later gates.
