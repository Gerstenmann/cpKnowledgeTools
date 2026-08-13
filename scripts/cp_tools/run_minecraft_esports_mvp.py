#!/usr/bin/env python3
# ruff: noqa: E501
"""Run the synthetic Minecraft Esports Source-to-Knowledge MVP reference case.

The production pipeline consumes only the three HTML sources plus the explicit
reference interpretation configuration in this script. It does NOT read
EXPECTED.md, scenario.v1.json, or the cp-wiki Golden-Truth-Matrix.

The final result.json is a test-harness projection created after the generic
pipeline has completed.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from cp_knowledge_tools.delivery import (  # noqa: E402
    EvidenceResolutionRequest,
    EvidenceResolver,
    ExperienceRetrievalRequest,
    ExperienceRetriever,
    KnowledgeRetriever,
    RetrievalRenderer,
    RetrievalRequest,
)
from cp_knowledge_tools.derived import (  # noqa: E402
    DerivedRetrievalBuilder,
    ExperienceContinuationPlan,
    ExperienceGapPlan,
    ExperiencePhasePlan,
    ExperienceProjectionBuilder,
    ExperienceProjectionPlan,
    ExperienceReuseContext,
    ExperienceSemanticSelector,
    ExperienceThreadPlan,
)
from cp_knowledge_tools.platform.hashing import canonical_json_hash  # noqa: E402
from cp_knowledge_tools.policy import (  # noqa: E402
    PolicyConfiguration,
    PolicyEvaluationInput,
    PolicyEvaluator,
    PolicyRule,
    PolicySubject,
    ProfileApplicability,
    ProfileReferenceResolution,
)
from cp_knowledge_tools.publication import (  # noqa: E402
    PublicationApplicability,
    PublicationAssemblyPlan,
    PublicationInterpretationProvenance,
    PublicationPolicyAnchor,
    PublicationPolicyBinding,
    PublicationRepresentation,
    PublicationRepresentationItem,
    PublicationRepresentationSection,
    PublicationSemanticReference,
    PublicationUnitAssembler,
    load_publication_manifest,
)
from cp_knowledge_tools.semantics import (  # noqa: E402
    RuleBasedSemanticInterpreter,
    SemanticStateMaterializer,
)
from cp_knowledge_tools.sources.adapters.local_html import (  # noqa: E402
    LocalHtmlAdapter,
)

SOURCE_BINDINGS = {
    "proposal": REPO_ROOT / "tests/fixtures/source_to_knowledge/minecraft_esports/html/01-program-proposal.html",
    "response": REPO_ROOT / "tests/fixtures/source_to_knowledge/minecraft_esports/html/02-school-response.html",
    "status": REPO_ROOT / "tests/fixtures/source_to_knowledge/minecraft_esports/html/03-pilot-status.html",
}

ORGANIZATIONAL_PROFILE_REF = "cpks.profile.organizational-context@0.1"
GOLDEN_AS_OF = "2024-09-06T15:30:00+02:00"

# These are deterministic extraction/interpretation rules for the synthetic
# reference case. They are implementation configuration, not Golden Truth.
EVIDENCE_RULES = {
    "entity_roster_proposal": ("proposal", ["From", "To", "Cc", "Date", "Subject"]),
    "entity_roster_status": ("status", ["From", "To", "Cc", "Date", "Subject"]),
    "pilot_description": ("proposal", ["propose a small", "concept would combine"]),
    "workshop_proposal": ("proposal", ["concept workshop could take place"]),
    "workshop_confirmed": ("status", ["Concept workshop", "Confirmed for"]),
    "training_initial": ("proposal", ["Internal team training could start"]),
    "training_current": ("status", ["Team training", "Starts on"]),
    "capacity_initial": ("proposal", ["I estimate that around", "might be interested"]),
    "capacity_current": ("status", ["Capacity", "pilot is limited to"]),
    "adviser_open": ("response", ["club advisers", "school year"]),
    "adviser_confirmed": ("status", ["School adviser", "coordinate the pilot"]),
    "scope_open": ("response", ["first pilot should be", "classroom activities"]),
    "scope_afterschool": ("status", ["Initial scope", "first pilot is"]),
    "academic_deferred": ("status", ["Classroom integration", "pilot has been evaluated"]),
    "competition_later": ("proposal", ["Only after an internal pilot", "explore regional"]),
    "competition_not_approved": ("status", ["External competition", "at this stage"]),
    "previous_success": ("response", ["detailed proposal", "after-school Minecraft club"]),
    "general_benefits": ("proposal", ["reports and examples", "concrete learning objectives"]),
    "budget_abstract": ("status", ["public-facing description", "participant communications"]),
    "budget_exact": ("status", ["initial pilot has", "participant communications"]),
    "chris_codelab_proposal": ("proposal", ["From", "Chris Berger, CodeLab Rhine-Main"]),
    "chris_codelab_status": ("status", ["To", "Chris Berger, CodeLab Rhine-Main"]),
    "vera_school_proposal": ("proposal", ["To", "Vera Anders, Rhein-Main International School"]),
    "vera_school_status": ("status", ["From", "Vera Anders, Rhein-Main International School"]),
    "chris_school_services": ("proposal", ["coding and robotics activities at the school for several years", "teach two Minecraft coding courses"]),
    "chris_school_services_reported": ("response", ["You mentioned that you teach at the school"]),
    "pilot_proposal_action": ("proposal", ["I would like to propose a small Minecraft Education esports pilot."]),
    "pilot_decision_confirmation": ("status", ["We completed our internal discussion", "confirm a limited first pilot"]),
    "pilot_decision_table": ("status", ["Confirmed pilot decisions", "Confirmed status"]),
    "status_communication_envelope": ("status", ["From", "To", "Cc", "Date", "Confirmed scope for Minecraft Education pilot"]),
}

RULES = {
    "entities": [
        {"rule_key": "school", "entity_class": "organization", "evidence_keys": ["entity_roster_proposal"], "extraction": {"evidence_key": "entity_roster_proposal", "pattern": r"To Vera Anders, (?P<value>.*?) Cc", "parser": "entity_mention"}},
        {"rule_key": "provider", "entity_class": "organization", "evidence_keys": ["entity_roster_proposal"], "extraction": {"evidence_key": "entity_roster_proposal", "pattern": r"From Chris Berger, (?P<value>.*?) To", "parser": "entity_mention"}},
        {"rule_key": "chris", "entity_class": "person", "evidence_keys": ["entity_roster_proposal"], "extraction": {"evidence_key": "entity_roster_proposal", "pattern": r"From (?P<value>.*?), CodeLab Rhine-Main", "parser": "entity_mention"}},
        {"rule_key": "vera", "entity_class": "person", "evidence_keys": ["entity_roster_proposal"], "extraction": {"evidence_key": "entity_roster_proposal", "pattern": r"To (?P<value>.*?), Rhein-Main International School", "parser": "entity_mention"}},
        {"rule_key": "alex", "entity_class": "person", "evidence_keys": ["entity_roster_proposal"], "extraction": {"evidence_key": "entity_roster_proposal", "pattern": r"Cc (?P<value>.*?), Director of Digital Learning", "parser": "entity_mention"}},
        {"rule_key": "james", "entity_class": "person", "evidence_keys": ["entity_roster_status"], "extraction": {"evidence_key": "entity_roster_status", "pattern": r"Cc Alex Bryant; (?P<value>.*?) Date", "parser": "entity_mention"}},
        {"rule_key": "pilot", "entity_class": "pilot_subject", "evidence_keys": ["pilot_description"], "extraction": {"evidence_key": "pilot_description", "pattern": r"propose a small (?P<value>.*?)\. The concept", "parser": "entity_mention"}},
    ],
    "claims": [
        {"rule_key": "workshop_confirmed_date", "subject_entity_key": "pilot", "predicate_ref": "cpkt.test.minecraft.workshop_date", "evidence_keys": ["workshop_proposal", "workshop_confirmed"], "extraction": {"evidence_key": "workshop_confirmed", "pattern": r"Confirmed for (?P<value>\d{1,2} [A-Za-z]+ \d{4})", "parser": "date"}, "epistemic_status": "confirmed", "epistemic_classification_basis": "explicit_confirmed_status_context", "time_modality": "planned", "time_role": "valid_time", "time_precision": "day"},
        {"rule_key": "training_initial_date", "subject_entity_key": "pilot", "predicate_ref": "cpkt.test.minecraft.training_start", "evidence_keys": ["training_initial"], "extraction": {"evidence_key": "training_initial", "pattern": r"start on (?P<value>\d{1,2} [A-Za-z]+ \d{4})", "parser": "date"}, "epistemic_status": "reported", "epistemic_classification_basis": "source_reports_proposed_plan", "time_modality": "planned", "time_role": "valid_time", "time_precision": "day"},
        {"rule_key": "training_current_date", "subject_entity_key": "pilot", "predicate_ref": "cpkt.test.minecraft.training_start", "evidence_keys": ["training_current"], "extraction": {"evidence_key": "training_current", "pattern": r"Starts on (?P<value>\d{1,2} [A-Za-z]+ \d{4})", "parser": "date"}, "epistemic_status": "confirmed", "epistemic_classification_basis": "explicit_confirmed_status_context", "time_modality": "planned", "time_role": "valid_time", "time_precision": "day"},
        {"rule_key": "capacity_initial_estimate", "subject_entity_key": "pilot", "predicate_ref": "cpkt.test.minecraft.capacity", "evidence_keys": ["capacity_initial"], "extraction": {"evidence_key": "capacity_initial", "pattern": r"around (?P<value>\d+) students", "parser": "integer"}, "value_qualifier": "approximately", "epistemic_status": "reported", "epistemic_classification_basis": "source_reports_estimate"},
        {"rule_key": "capacity_confirmed_maximum", "subject_entity_key": "pilot", "predicate_ref": "cpkt.test.minecraft.capacity", "evidence_keys": ["capacity_current"], "extraction": {"evidence_key": "capacity_current", "pattern": r"limited to (?P<value>\d+) students", "parser": "integer"}, "value_qualifier": "maximum", "epistemic_status": "confirmed", "epistemic_classification_basis": "explicit_confirmed_status_context"},
        {"rule_key": "adviser_not_selected", "subject_entity_key": "pilot", "predicate_ref": "cpkt.test.minecraft.adviser_state", "evidence_keys": ["adviser_open"], "extraction": {"evidence_key": "adviser_open", "pattern": r"(?P<value>not yet been selected)", "parser": "text"}, "semantic_value_map": {"not yet been selected": "not_selected"}, "epistemic_status": "reported", "epistemic_classification_basis": "source_reports_open_state"},
        {"rule_key": "adviser_confirmed_person", "subject_entity_key": "pilot", "predicate_ref": "cpkt.test.minecraft.adviser", "evidence_keys": ["adviser_confirmed"], "extraction": {"evidence_key": "adviser_confirmed", "pattern": r"School adviser (?P<value>[A-Z][A-Za-z'-]+ [A-Z][A-Za-z'-]+) will coordinate", "parser": "entity_mention"}, "object_kind": "entity_mention", "epistemic_status": "confirmed", "epistemic_classification_basis": "explicit_confirmed_status_context"},
        {"rule_key": "scope_open", "subject_entity_key": "pilot", "predicate_ref": "cpkt.test.minecraft.scope_state", "evidence_keys": ["scope_open"], "extraction": {"evidence_key": "scope_open", "pattern": r"pilot should be (?P<value>purely extracurricular or also include classroom activities)", "parser": "text"}, "semantic_value_map": {"purely extracurricular or also include classroom activities": "academic_and_or_extracurricular_open"}, "epistemic_status": "reported", "epistemic_classification_basis": "source_reports_unresolved_option"},
        {"rule_key": "scope_afterschool", "subject_entity_key": "pilot", "predicate_ref": "cpkt.test.minecraft.scope", "evidence_keys": ["scope_afterschool"], "extraction": {"evidence_key": "scope_afterschool", "pattern": r"first pilot is (?P<value>after-school only)", "parser": "text"}, "epistemic_status": "confirmed", "epistemic_classification_basis": "explicit_confirmed_status_context"},
        {"rule_key": "academic_deferred", "subject_entity_key": "pilot", "predicate_ref": "cpkt.test.minecraft.classroom_integration", "evidence_keys": ["academic_deferred"], "extraction": {"evidence_key": "academic_deferred", "pattern": r"Classroom integration is (?P<value>postponed)", "parser": "text"}, "semantic_value_map": {"postponed": "deferred"}, "epistemic_status": "confirmed", "epistemic_classification_basis": "explicit_confirmed_status_context"},
        {"rule_key": "classroom_integration_dependency", "subject_entity_key": "pilot", "predicate_ref": "cpkt.test.minecraft.classroom_integration_dependency", "evidence_keys": ["academic_deferred"], "extraction": {"evidence_key": "academic_deferred", "pattern": r"Classroom integration is postponed until the (?P<value>pilot has been evaluated)", "parser": "text"}, "semantic_value_map": {"pilot has been evaluated": "requires_pilot_evaluation"}, "epistemic_status": "confirmed", "epistemic_classification_basis": "explicit_confirmed_dependency_statement"},
        {"rule_key": "competition_later_possible", "subject_entity_key": "pilot", "predicate_ref": "cpkt.test.minecraft.external_competition_future", "evidence_keys": ["competition_later", "competition_not_approved"], "extraction": {"evidence_key": "competition_later", "pattern": r"(?P<value>after an internal pilot), explore", "parser": "text", "ignore_case": True}, "semantic_value_map": {"after an internal pilot": "possible_later_phase"}, "epistemic_status": "reported", "epistemic_classification_basis": "source_reports_conditional_future_option"},
        {"rule_key": "competition_not_approved", "subject_entity_key": "pilot", "predicate_ref": "cpkt.test.minecraft.external_competition_approval", "evidence_keys": ["competition_not_approved"], "extraction": {"evidence_key": "competition_not_approved", "pattern": r"(?P<value>No external competition is approved at this stage)", "parser": "text"}, "semantic_value_map": {"No external competition is approved at this stage": "not_approved"}, "epistemic_status": "confirmed", "epistemic_classification_basis": "explicit_confirmed_status_context"},
        {"rule_key": "competition_decision_dependency", "subject_entity_key": "pilot", "predicate_ref": "cpkt.test.minecraft.external_competition_decision_dependency", "evidence_keys": ["competition_not_approved"], "extraction": {"evidence_key": "competition_not_approved", "pattern": r"A later decision will (?P<value>depend on the internal pilot evaluation)", "parser": "text"}, "semantic_value_map": {"depend on the internal pilot evaluation": "depends_on_internal_pilot_evaluation"}, "epistemic_status": "confirmed", "epistemic_classification_basis": "explicit_confirmed_dependency_statement"},
        {"rule_key": "previous_success_reported", "subject_entity_key": "school", "predicate_ref": "cpkt.test.minecraft.previous_use_success", "evidence_keys": ["previous_success"], "extraction": {"evidence_key": "previous_success", "pattern": r"(?P<value>used Minecraft successfully in some classes)", "parser": "text"}, "semantic_value_map": {"used Minecraft successfully in some classes": "previous_minecraft_use_described_as_successful"}, "epistemic_status": "reported", "epistemic_classification_basis": "source_reports_previous_use"},
        {"rule_key": "budget_approved", "subject_entity_key": "pilot", "predicate_ref": "cpkt.test.minecraft.internal_budget_status", "evidence_keys": ["budget_abstract"], "extraction": {"evidence_key": "budget_abstract", "pattern": r"(?P<value>approved internal budget)", "parser": "text"}, "epistemic_status": "confirmed", "epistemic_classification_basis": "explicit_approved_status_statement"},
    ],
    "relationships": [
        {"rule_key": "chris_codelab_affiliated", "subject_key": "chris", "predicate_ref": "cpks.vocab.profile.organizational-context.relationship_predicate.affiliated_with", "object_key": "provider", "evidence_keys": ["chris_codelab_proposal", "chris_codelab_status"], "extraction": {"evidence_key": "chris_codelab_proposal", "pattern": r"From (?P<value>Chris Berger, CodeLab Rhine-Main)", "parser": "text"}, "epistemic_status": "confirmed", "epistemic_classification_basis": "consistent_person_organization_assignment_across_two_sources", "profile_refs": [ORGANIZATIONAL_PROFILE_REF]},
        {"rule_key": "vera_school_affiliated", "subject_key": "vera", "predicate_ref": "cpks.vocab.profile.organizational-context.relationship_predicate.affiliated_with", "object_key": "school", "evidence_keys": ["vera_school_proposal", "vera_school_status"], "extraction": {"evidence_key": "vera_school_proposal", "pattern": r"To (?P<value>Vera Anders, Rhein-Main International School)", "parser": "text"}, "epistemic_status": "confirmed", "epistemic_classification_basis": "consistent_person_organization_assignment_across_two_sources", "profile_refs": [ORGANIZATIONAL_PROFILE_REF]},
        {"rule_key": "chris_school_provides_services", "subject_key": "chris", "predicate_ref": "cpks.vocab.profile.organizational-context.relationship_predicate.provides_services_at", "object_key": "school", "evidence_keys": ["chris_school_services", "chris_school_services_reported"], "extraction": {"evidence_key": "chris_school_services", "pattern": r"(?P<value>I have been running coding and robotics activities at the school for several years)", "parser": "text"}, "epistemic_status": "reported", "epistemic_classification_basis": "self_report_repeated_as_prior_statement_not_independently_confirmed", "profile_refs": [ORGANIZATIONAL_PROFILE_REF]},
        {"rule_key": "james_pilot_assigned", "subject_key": "james", "predicate_ref": "cpks.vocab.profile.organizational-context.relationship_predicate.assigned_to", "object_key": "pilot", "evidence_keys": ["adviser_confirmed"], "extraction": {"evidence_key": "adviser_confirmed", "pattern": r"(?P<value>James Stone will coordinate the pilot for the school)", "parser": "text"}, "epistemic_status": "confirmed", "epistemic_classification_basis": "explicit_confirmed_adviser_assignment", "profile_refs": [ORGANIZATIONAL_PROFILE_REF]},
        {"rule_key": "james_pilot_responsible", "subject_key": "james", "predicate_ref": "cpks.vocab.profile.organizational-context.relationship_predicate.responsible_for", "object_key": "pilot", "evidence_keys": ["adviser_confirmed"], "extraction": {"evidence_key": "adviser_confirmed", "pattern": r"(?P<value>James Stone will coordinate the pilot for the school)", "parser": "text"}, "epistemic_status": "confirmed", "epistemic_classification_basis": "explicit_confirmed_scoped_coordination_responsibility", "profile_refs": [ORGANIZATIONAL_PROFILE_REF]},
    ],
    "evidence_links": [
        {"rule_key": "workshop_proposal_report", "claim_key": "workshop_confirmed_date", "evidence_key": "workshop_proposal", "role": "reports_statement"},
        {"rule_key": "workshop_confirmed_support", "claim_key": "workshop_confirmed_date", "evidence_key": "workshop_confirmed", "role": "supports"},
        {"rule_key": "training_initial_report", "claim_key": "training_initial_date", "evidence_key": "training_initial", "role": "reports_statement"},
        {"rule_key": "training_current_support", "claim_key": "training_current_date", "evidence_key": "training_current", "role": "supports"},
        {"rule_key": "capacity_initial_report", "claim_key": "capacity_initial_estimate", "evidence_key": "capacity_initial", "role": "reports_statement"},
        {"rule_key": "capacity_current_support", "claim_key": "capacity_confirmed_maximum", "evidence_key": "capacity_current", "role": "supports"},
        {"rule_key": "capacity_current_qualifies_initial", "claim_key": "capacity_initial_estimate", "evidence_key": "capacity_current", "role": "qualifies"},
        {"rule_key": "adviser_open", "claim_key": "adviser_not_selected", "evidence_key": "adviser_open", "role": "reports_statement"},
        {"rule_key": "adviser_confirmed_support", "claim_key": "adviser_confirmed_person", "evidence_key": "adviser_confirmed", "role": "supports"},
        {"rule_key": "scope_open", "claim_key": "scope_open", "evidence_key": "scope_open", "role": "reports_statement"},
        {"rule_key": "scope_afterschool", "claim_key": "scope_afterschool", "evidence_key": "scope_afterschool", "role": "supports"},
        {"rule_key": "academic_deferred", "claim_key": "academic_deferred", "evidence_key": "academic_deferred", "role": "supports"},
        {"rule_key": "competition_later", "claim_key": "competition_later_possible", "evidence_key": "competition_later", "role": "reports_statement"},
        {"rule_key": "competition_qualifies", "claim_key": "competition_later_possible", "evidence_key": "competition_not_approved", "role": "qualifies"},
        {"rule_key": "competition_not_approved", "claim_key": "competition_not_approved", "evidence_key": "competition_not_approved", "role": "supports"},
        {"rule_key": "previous_success", "claim_key": "previous_success_reported", "evidence_key": "previous_success", "role": "reports_statement"},
        {"rule_key": "budget_abstract", "claim_key": "budget_approved", "evidence_key": "budget_abstract", "role": "supports"},
        {"rule_key": "chris_codelab_proposal_report", "subject_key": "chris_codelab_affiliated", "evidence_key": "chris_codelab_proposal", "role": "reports_statement"},
        {"rule_key": "chris_codelab_status_support", "subject_key": "chris_codelab_affiliated", "evidence_key": "chris_codelab_status", "role": "supports"},
        {"rule_key": "vera_school_proposal_report", "subject_key": "vera_school_affiliated", "evidence_key": "vera_school_proposal", "role": "reports_statement"},
        {"rule_key": "vera_school_status_support", "subject_key": "vera_school_affiliated", "evidence_key": "vera_school_status", "role": "supports"},
        {"rule_key": "chris_school_services_report", "subject_key": "chris_school_provides_services", "evidence_key": "chris_school_services", "role": "reports_statement"},
        {"rule_key": "chris_school_services_repeated_report", "subject_key": "chris_school_provides_services", "evidence_key": "chris_school_services_reported", "role": "reports_statement"},
        {"rule_key": "james_pilot_assignment_support", "subject_key": "james_pilot_assigned", "evidence_key": "adviser_confirmed", "role": "supports"},
        {"rule_key": "james_pilot_responsibility_support", "subject_key": "james_pilot_responsible", "evidence_key": "adviser_confirmed", "role": "supports"},
        {"rule_key": "pilot_proposal_event_support", "subject_key": "pilot_proposal", "evidence_key": "pilot_proposal_action", "role": "supports"},
        {"rule_key": "pilot_decision_event_support", "subject_key": "pilot_decision", "evidence_key": "pilot_decision_confirmation", "role": "supports"},
        {"rule_key": "pilot_decision_table_support", "subject_key": "pilot_decision", "evidence_key": "pilot_decision_table", "role": "supports"},
        {"rule_key": "pilot_confirmation_event_support", "subject_key": "pilot_status_confirmation", "evidence_key": "pilot_decision_confirmation", "role": "supports"},
        {"rule_key": "pilot_communication_event_support", "subject_key": "pilot_status_communication", "evidence_key": "status_communication_envelope", "role": "supports"},
        {"rule_key": "proposal_initiator_support", "subject_key": "chris_proposal_initiator", "evidence_key": "pilot_proposal_action", "role": "supports"},
        {"rule_key": "decision_maker_support", "subject_key": "school_decision_maker", "evidence_key": "pilot_decision_confirmation", "role": "supports"},
        {"rule_key": "status_confirmer_support", "subject_key": "school_status_confirmer", "evidence_key": "pilot_decision_confirmation", "role": "supports"},
        {"rule_key": "communication_actor_support", "subject_key": "vera_communication_actor", "evidence_key": "status_communication_envelope", "role": "supports"},
        {"rule_key": "communication_recipient_support", "subject_key": "chris_communication_recipient", "evidence_key": "status_communication_envelope", "role": "supports"},
        {"rule_key": "internal_pilot_organizer_support", "subject_key": "james_internal_pilot_organizer", "evidence_key": "adviser_confirmed", "role": "supports"},
        {"rule_key": "classroom_integration_dependency_support", "claim_key": "classroom_integration_dependency", "evidence_key": "academic_deferred", "role": "supports"},
        {"rule_key": "competition_decision_dependency_support", "claim_key": "competition_decision_dependency", "evidence_key": "competition_not_approved", "role": "supports"},
    ],
    "events": [
        {"rule_key": "concept_workshop", "event_type_ref": "cpkt.test.event_type.concept_workshop", "label": "Concept Workshop", "evidence_keys": ["workshop_proposal", "workshop_confirmed"], "extraction": {"evidence_key": "workshop_confirmed", "pattern": r"Confirmed for (?P<value>\d{1,2} [A-Za-z]+ \d{4})", "parser": "date"}, "time_precision": "day", "time_modality": "planned"},
        {"rule_key": "training_start", "event_type_ref": "cpkt.test.event_type.training_start", "label": "Team training start", "evidence_keys": ["training_current"], "extraction": {"evidence_key": "training_current", "pattern": r"Starts on (?P<value>\d{1,2} [A-Za-z]+ \d{4})", "parser": "date"}, "time_precision": "day", "time_modality": "planned"},
        {"rule_key": "internal_pilot", "event_type_ref": "cpkt.test.event_type.internal_pilot", "label": "Internal pilot", "time_precision": "unknown", "time_modality": "planned", "evidence_keys": ["scope_afterschool"]},
        {"rule_key": "pilot_proposal", "event_type_ref": "cpks.vocab.profile.organizational-context.event_type.proposal", "label": "Pilot proposal", "time_precision": "minute", "time_modality": "actual", "event_time_from_source": True, "evidence_keys": ["pilot_proposal_action"], "profile_refs": [ORGANIZATIONAL_PROFILE_REF]},
        {"rule_key": "pilot_decision", "event_type_ref": "cpks.vocab.profile.organizational-context.event_type.decision", "label": "Pilot decision", "time_precision": "unknown", "time_modality": "actual", "evidence_keys": ["pilot_decision_confirmation", "pilot_decision_table"], "profile_refs": [ORGANIZATIONAL_PROFILE_REF]},
        {"rule_key": "pilot_status_confirmation", "event_type_ref": "cpks.vocab.profile.organizational-context.event_type.confirmation", "label": "Pilot status confirmation", "time_precision": "minute", "time_modality": "actual", "event_time_from_source": True, "evidence_keys": ["pilot_decision_confirmation"], "profile_refs": [ORGANIZATIONAL_PROFILE_REF]},
        {"rule_key": "pilot_status_communication", "event_type_ref": "cpks.vocab.profile.organizational-context.event_type.communication", "label": "Confirmed pilot status communication", "time_precision": "minute", "time_modality": "actual", "event_time_from_source": True, "evidence_keys": ["status_communication_envelope"], "profile_refs": [ORGANIZATIONAL_PROFILE_REF]},
    ],
    "participations": [
        {"rule_key": "chris_proposal_initiator", "entity_key": "chris", "event_key": "pilot_proposal", "role": "initiator", "evidence_keys": ["pilot_proposal_action"], "profile_refs": [ORGANIZATIONAL_PROFILE_REF]},
        {"rule_key": "school_decision_maker", "entity_key": "school", "event_key": "pilot_decision", "role": "cpks.vocab.profile.organizational-context.event_participation_role.decision_maker", "evidence_keys": ["pilot_decision_confirmation", "pilot_decision_table"], "profile_refs": [ORGANIZATIONAL_PROFILE_REF]},
        {"rule_key": "school_status_confirmer", "entity_key": "school", "event_key": "pilot_status_confirmation", "role": "cpks.vocab.profile.organizational-context.event_participation_role.confirmer", "evidence_keys": ["pilot_decision_confirmation"], "profile_refs": [ORGANIZATIONAL_PROFILE_REF]},
        {"rule_key": "vera_communication_actor", "entity_key": "vera", "event_key": "pilot_status_communication", "role": "actor", "evidence_keys": ["status_communication_envelope"], "profile_refs": [ORGANIZATIONAL_PROFILE_REF]},
        {"rule_key": "chris_communication_recipient", "entity_key": "chris", "event_key": "pilot_status_communication", "role": "recipient", "evidence_keys": ["status_communication_envelope"], "profile_refs": [ORGANIZATIONAL_PROFILE_REF]},
        {"rule_key": "james_internal_pilot_organizer", "entity_key": "james", "event_key": "internal_pilot", "role": "organizer", "evidence_keys": ["adviser_confirmed"], "profile_refs": [ORGANIZATIONAL_PROFILE_REF]},
    ],
    "pattern_claims": [
        {"rule_key": "doc01_general_benefits", "evidence_keys": ["general_benefits"], "extraction": {"evidence_key": "general_benefits", "pattern": r"(?P<value>I have seen reports and examples suggesting that .*?\.)", "parser": "text"}, "epistemic_status": "reported", "epistemic_classification_basis": "source_reports_external_examples", "evidence_role": "reports_statement"},
    ],
}

# Scenario-level curation is deliberately downstream of Candidate creation.
# It preserves the MVP state/history/conflict result without pretending that
# extraction itself determines current or preferred state.
CURATION_RULES = {
    "claim_states": {
        "workshop_confirmed_date": {"current": True, "preserved": True},
        "training_initial_date": {"current": False, "preserved": True},
        "training_current_date": {"current": True, "preserved": True},
        "capacity_initial_estimate": {"current": False, "preserved": True},
        "capacity_confirmed_maximum": {"current": True, "preserved": True},
        "adviser_not_selected": {"current": False, "preserved": True},
        "adviser_confirmed_person": {"current": True, "preserved": True},
        "scope_open": {"current": False, "preserved": True},
        "scope_afterschool": {"current": True, "preserved": True},
        "academic_deferred": {"current": True, "preserved": True},
        "classroom_integration_dependency": {"current": True, "preserved": True},
        "competition_later_possible": {"current": True, "preserved": True},
        "competition_not_approved": {"current": True, "preserved": True},
        "competition_decision_dependency": {"current": True, "preserved": True},
        "previous_success_reported": {"current": True, "preserved": True},
        "budget_approved": {"current": True, "preserved": True},
        "chris_codelab_affiliated": {"current": True, "preserved": True},
        "vera_school_affiliated": {"current": True, "preserved": True},
        "chris_school_provides_services": {"current": True, "preserved": True},
        "james_pilot_assigned": {"current": True, "preserved": True},
        "james_pilot_responsible": {"current": True, "preserved": True},
    },
    "conflict_sets": [
        {"rule_key": "training_date", "claim_keys": ["training_initial_date", "training_current_date"], "conflict_dimensions": ["temporal"], "preferred_claim_key": "training_current_date", "preference_context": "current_confirmed_pilot_plan", "rationale": "The confirmed status supersedes the earlier proposed plan while preserving the earlier state."},
        {"rule_key": "capacity", "claim_keys": ["capacity_initial_estimate", "capacity_confirmed_maximum"], "conflict_dimensions": ["factual", "contextual"], "preferred_claim_key": "capacity_confirmed_maximum", "preference_context": "current_confirmed_pilot_capacity", "rationale": "The confirmed maximum qualifies the earlier reported estimate."},
        {"rule_key": "pilot_scope", "claim_keys": ["scope_open", "scope_afterschool", "academic_deferred"], "conflict_dimensions": ["contextual", "temporal"], "preferred_claim_key": "scope_afterschool", "preference_context": "current_confirmed_pilot_scope", "rationale": "The confirmed pilot scope resolves the earlier open scope for the current pilot stage."},
    ],
}

ENTITY_GT = {
    "school": "ENT-RMIS",
    "provider": "ENT-CODELAB",
    "chris": "ENT-CHRIS-BERGER",
    "vera": "ENT-VERA-ANDERS",
    "alex": "ENT-ALEX-BRYANT",
    "james": "ENT-JAMES-STONE",
    "pilot": "ENT-ME-ESPORTS-PILOT",
}
CLAIM_GT = {
    "workshop_confirmed_date": "CLM-WORKSHOP-12SEP",
    "training_initial_date": "CLM-TRAINING-19SEP",
    "training_current_date": "CLM-TRAINING-26SEP",
    "capacity_initial_estimate": "CLM-CAPACITY-ABOUT20",
    "capacity_confirmed_maximum": "CLM-CAPACITY-MAX16",
    "adviser_not_selected": "CLM-ADVISER-NOT-SELECTED",
    "adviser_confirmed_person": "CLM-ADVISER-JAMES-STONE",
    "scope_open": "CLM-SCOPE-OPEN",
    "scope_afterschool": "CLM-SCOPE-AFTERSCHOOL",
    "academic_deferred": "CLM-ACADEMIC-DEFERRED",
    "classroom_integration_dependency": "CLM-CLASSROOM-INTEGRATION-DEPENDS-ON-PILOT-EVALUATION",
    "competition_later_possible": "CLM-EXT-COMP-LATER-POSSIBLE",
    "competition_not_approved": "CLM-EXT-COMP-NOT-APPROVED",
    "competition_decision_dependency": "CLM-EXT-COMP-DECISION-DEPENDS-ON-PILOT-EVALUATION",
    "previous_success_reported": "CLM-PREVIOUS-MC-SUCCESS-REPORTED",
    "budget_approved": "CLM-BUDGET-APPROVED",
    "chris_codelab_affiliated": "CLM-REL-CHRIS-CODELAB-AFFILIATED",
    "vera_school_affiliated": "CLM-REL-VERA-RMIS-AFFILIATED",
    "chris_school_provides_services": "CLM-REL-CHRIS-RMIS-PROVIDES-SERVICES",
    "james_pilot_assigned": "CLM-REL-JAMES-PILOT-ASSIGNED",
    "james_pilot_responsible": "CLM-REL-JAMES-PILOT-RESPONSIBLE",
}
EVIDENCE_GT = {
    "workshop_proposal": "EA-01",
    "workshop_confirmed": "EA-02",
    "training_initial": "EA-03",
    "training_current": "EA-04",
    "capacity_initial": "EA-05",
    "capacity_current": "EA-06",
    "adviser_open": "EA-07",
    "adviser_confirmed": "EA-08",
    "scope_open": "EA-09",
    "scope_afterschool": "EA-10",
    "academic_deferred": "EA-11",
    "competition_later": "EA-12",
    "competition_not_approved": "EA-13",
    "previous_success": "EA-14",
    "budget_abstract": "EA-15",
    "budget_exact": "EA-16-RESTRICTED",
    "chris_codelab_proposal": "EA-17",
    "chris_codelab_status": "EA-18",
    "vera_school_proposal": "EA-19",
    "vera_school_status": "EA-20",
    "chris_school_services": "EA-21",
    "chris_school_services_reported": "EA-22",
    "pilot_proposal_action": "EA-23",
    "pilot_decision_confirmation": "EA-24",
    "pilot_decision_table": "EA-25",
    "status_communication_envelope": "EA-26",
}
EVIDENCE_LINK_GT = {
    "workshop_proposal_report": "EL-01",
    "workshop_confirmed_support": "EL-02",
    "training_initial_report": "EL-03",
    "training_current_support": "EL-04",
    "capacity_initial_report": "EL-05",
    "capacity_current_support": "EL-06",
    "capacity_current_qualifies_initial": "EL-07",
    "adviser_open": "EL-08",
    "adviser_confirmed_support": "EL-09",
    "scope_open": "EL-10",
    "scope_afterschool": "EL-11",
    "academic_deferred": "EL-12",
    "competition_later": "EL-13",
    "competition_qualifies": "EL-14",
    "competition_not_approved": "EL-15",
    "previous_success": "EL-16",
    "budget_abstract": "EL-17",
    "chris_codelab_proposal_report": "EL-18",
    "chris_codelab_status_support": "EL-19",
    "vera_school_proposal_report": "EL-20",
    "vera_school_status_support": "EL-21",
    "chris_school_services_report": "EL-22",
    "chris_school_services_repeated_report": "EL-23",
    "james_pilot_assignment_support": "EL-24",
    "james_pilot_responsibility_support": "EL-25",
    "pilot_proposal_event_support": "EL-26",
    "pilot_decision_event_support": "EL-27",
    "pilot_decision_table_support": "EL-28",
    "pilot_confirmation_event_support": "EL-29",
    "pilot_communication_event_support": "EL-30",
    "proposal_initiator_support": "EL-31",
    "decision_maker_support": "EL-32",
    "status_confirmer_support": "EL-33",
    "communication_actor_support": "EL-34",
    "communication_recipient_support": "EL-35",
    "internal_pilot_organizer_support": "EL-36",
    "classroom_integration_dependency_support": "EL-37",
    "competition_decision_dependency_support": "EL-38",
}
EVENT_GT = {
    "concept_workshop": "EVT-CONCEPT-WORKSHOP",
    "training_start": "EVT-TEAM-TRAINING-START",
    "internal_pilot": "EVT-INTERNAL-PILOT",
    "pilot_proposal": "EVT-PILOT-PROPOSAL",
    "pilot_decision": "EVT-PILOT-DECISION",
    "pilot_status_confirmation": "EVT-PILOT-STATUS-CONFIRMATION",
    "pilot_status_communication": "EVT-PILOT-STATUS-COMMUNICATION",
}
PARTICIPATION_GT = {
    "chris_proposal_initiator": "PART-CHRIS-PROPOSAL-INITIATOR",
    "school_decision_maker": "PART-RMIS-PILOT-DECISION-MAKER",
    "school_status_confirmer": "PART-RMIS-PILOT-CONFIRMER",
    "vera_communication_actor": "PART-VERA-STATUS-COMM-ACTOR",
    "chris_communication_recipient": "PART-CHRIS-STATUS-COMM-RECIPIENT",
    "james_internal_pilot_organizer": "PART-JAMES-INTERNAL-PILOT-ORGANIZER",
}
CONFLICT_GT = {
    "training_date": "CF-TRAINING-DATE",
    "capacity": "CF-CAPACITY",
    "pilot_scope": "CF-PILOT-SCOPE",
}

SOURCE_GT = {"proposal": "DOC-01", "response": "DOC-02", "status": "DOC-03"}

CONSUMER_REF = "CONSUMER-CLAIM-READ-NO-BUDGET-EVIDENCE"
PURPOSE = "retrieve_pilot_status"
POLICY_REF = "CPKT-MVP-POLICY-KNOWLEDGE-DELIVERY"
POLICY_VERSION = "0.1"

# These information needs are scenario configuration. The generic retrieval
# implementation only sees semantic refs, predicates, state selection, and
# event types; it contains no Minecraft or Golden-Case vocabulary.
RETRIEVAL_NEEDS = (
    {
        "query_key": "concept_workshop_date",
        "subject_key": "pilot",
        "claim_predicates": ("cpkt.test.minecraft.workshop_date",),
        "event_types": ("cpkt.test.event_type.concept_workshop",),
        "state_selection": "current",
    },
    {
        "query_key": "team_training_date",
        "subject_key": "pilot",
        "claim_predicates": ("cpkt.test.minecraft.training_start",),
        "event_types": ("cpkt.test.event_type.training_start",),
        "state_selection": "current",
    },
    {
        "query_key": "team_training_history",
        "subject_key": "pilot",
        "claim_predicates": ("cpkt.test.minecraft.training_start",),
        "event_types": (),
        "state_selection": "all",
    },
    {
        "query_key": "pilot_capacity",
        "subject_key": "pilot",
        "claim_predicates": ("cpkt.test.minecraft.capacity",),
        "event_types": (),
        "state_selection": "current",
    },
    {
        "query_key": "pilot_adviser",
        "subject_key": "pilot",
        "claim_predicates": ("cpkt.test.minecraft.adviser",),
        "event_types": (),
        "state_selection": "current",
    },
    {
        "query_key": "pilot_scope",
        "subject_key": "pilot",
        "claim_predicates": (
            "cpkt.test.minecraft.scope",
            "cpkt.test.minecraft.classroom_integration",
        ),
        "event_types": (),
        "state_selection": "current",
    },
    {
        "query_key": "external_competition",
        "subject_key": "pilot",
        "claim_predicates": (
            "cpkt.test.minecraft.external_competition_approval",
            "cpkt.test.minecraft.external_competition_future",
        ),
        "event_types": (),
        "state_selection": "current",
    },
    {
        "query_key": "previous_minecraft_use",
        "subject_key": "school",
        "claim_predicates": ("cpkt.test.minecraft.previous_use_success",),
        "event_types": (),
        "state_selection": "current",
    },
    {
        "query_key": "pilot_budget",
        "subject_key": "pilot",
        "claim_predicates": ("cpkt.test.minecraft.internal_budget_status",),
        "event_types": (),
        "state_selection": "current",
        "protected_evidence_rule_key": "budget_exact",
    },
    {
        "query_key": "chris_organization_affiliation",
        "subject_keys": ("chris",),
        "claim_predicates": ("cpks.vocab.profile.organizational-context.relationship_predicate.affiliated_with",),
        "event_types": (),
        "state_selection": "current",
    },
    {
        "query_key": "vera_organization_affiliation",
        "subject_keys": ("vera",),
        "claim_predicates": ("cpks.vocab.profile.organizational-context.relationship_predicate.affiliated_with",),
        "event_types": (),
        "state_selection": "current",
    },
    {
        "query_key": "chris_services_at_school",
        "subject_keys": ("chris",),
        "claim_predicates": ("cpks.vocab.profile.organizational-context.relationship_predicate.provides_services_at",),
        "event_types": (),
        "state_selection": "current",
    },
    {
        "query_key": "james_pilot_assignment",
        "subject_keys": ("james",),
        "claim_predicates": ("cpks.vocab.profile.organizational-context.relationship_predicate.assigned_to",),
        "event_types": (),
        "state_selection": "current",
    },
    {
        "query_key": "james_pilot_responsibility",
        "subject_keys": ("james",),
        "claim_predicates": ("cpks.vocab.profile.organizational-context.relationship_predicate.responsible_for",),
        "event_types": (),
        "state_selection": "current",
    },
    {
        "query_key": "pilot_proposal_participation",
        "subject_keys": (),
        "claim_predicates": (),
        "event_types": ("cpks.vocab.profile.organizational-context.event_type.proposal",),
        "participation_roles": ("initiator",),
        "state_selection": "current",
    },
    {
        "query_key": "pilot_decision_participation",
        "subject_keys": (),
        "claim_predicates": (),
        "event_types": ("cpks.vocab.profile.organizational-context.event_type.decision",),
        "participation_roles": ("cpks.vocab.profile.organizational-context.event_participation_role.decision_maker",),
        "state_selection": "current",
    },
    {
        "query_key": "pilot_confirmation_participation",
        "subject_keys": (),
        "claim_predicates": (),
        "event_types": ("cpks.vocab.profile.organizational-context.event_type.confirmation",),
        "participation_roles": ("cpks.vocab.profile.organizational-context.event_participation_role.confirmer",),
        "state_selection": "current",
    },
    {
        "query_key": "pilot_communication_participation",
        "subject_keys": (),
        "claim_predicates": (),
        "event_types": ("cpks.vocab.profile.organizational-context.event_type.communication",),
        "participation_roles": ("actor", "recipient"),
        "state_selection": "current",
    },
    {
        "query_key": "internal_pilot_organizer",
        "subject_keys": (),
        "claim_predicates": (),
        "event_types": ("cpkt.test.event_type.internal_pilot",),
        "participation_roles": ("organizer",),
        "state_selection": "current",
    },
    {
        "query_key": "representation_abstention",
        "subject_keys": ("chris", "vera"),
        "claim_predicates": ("cpks.vocab.profile.organizational-context.relationship_predicate.represents",),
        "event_types": (),
        "state_selection": "current",
    },
    {
        "query_key": "employment_abstention",
        "subject_keys": ("chris", "vera", "james"),
        "claim_predicates": ("cpks.vocab.profile.organizational-context.relationship_predicate.employed_by",),
        "event_types": (),
        "state_selection": "current",
    },
)


def _publication_ref(
    subject_type: str,
    stable_id: str,
    *,
    authority_context: str = "Semantic Core",
) -> PublicationSemanticReference:
    return PublicationSemanticReference(
        subject_type=subject_type,
        stable_id=stable_id,
        version="0.1",
        authority_context=authority_context,
    )


def _publication_claim_sentence(claim: dict) -> str:
    sentences = {
        "workshop_12sep": "The concept workshop is planned for 12 September 2024 and is confirmed as the current plan.",
        "training_19sep": "The initial proposal planned team training for 19 September 2024; this historical plan remains preserved.",
        "training_26sep": "The confirmed pilot plan schedules team training for 26 September 2024.",
        "capacity_about20": "The initial proposal estimated approximately 20 interested students.",
        "capacity_max16": "The confirmed pilot capacity is limited to 16 students.",
        "adviser_not_selected": "At the school-response stage, the adviser had not yet been selected.",
        "adviser_james": "James Stone is the confirmed school adviser for the pilot.",
        "scope_open": "The initial academic versus extracurricular scope remained open in the school response.",
        "scope_afterschool": "The confirmed current pilot scope is after-school only.",
        "academic_deferred": "Classroom integration is deferred until after pilot evaluation.",
        "classroom_integration_dependency": "A later classroom-integration decision requires pilot evaluation.",
        "competition_later_possible": "External competition remains a possible later phase.",
        "competition_not_approved": "External competition is not approved at the current pilot stage.",
        "competition_decision_dependency": "A later external-competition decision depends on internal pilot evaluation.",
        "previous_success_reported": "The school reported previous Minecraft use as successful; this remains a reported statement rather than independent confirmation.",
        "budget_approved": "The pilot has an approved internal budget.",
    }
    return sentences.get(
        claim["rule_key"],
        f"{claim['predicate_ref']}: {claim['value']!r}",
    )


def _publication_inputs(
    semantic: dict,
    evidence: dict,
) -> tuple[PublicationAssemblyPlan, PublicationRepresentation]:
    knowledge_object_ref = _publication_ref(
        "knowledge_object", "KO-GT-ME-ESPORTS-PILOT"
    )
    entity_by_key = {item["rule_key"]: item for item in semantic["entities"]}
    restricted_evidence_ref = _publication_ref(
        "evidence_address",
        evidence["budget_exact"].evidence_address_ref,
        authority_context="Source and Evidence",
    )
    policy_refs = (f"{POLICY_REF}@{POLICY_VERSION}",)
    policy_anchors = (
        PublicationPolicyAnchor(
            policy_anchor_id="PA-KO",
            subject_refs=(knowledge_object_ref,),
            policy_refs=policy_refs,
            dimensions=(
                "discoverability",
                "read_access",
                "evidence_resolution",
                "quotation",
                "transformation",
                "external_processing",
                "indexing",
                "memory_eligibility",
                "export",
                "retention",
            ),
            narrative_anchor="ko-policy",
        ),
        PublicationPolicyAnchor(
            policy_anchor_id="PA-RESTRICTED-EVIDENCE",
            subject_refs=(restricted_evidence_ref,),
            policy_refs=policy_refs,
            dimensions=("evidence_resolution", "quotation", "export"),
            narrative_anchor="restricted-evidence-policy",
        ),
    )

    policy_bindings = [
        PublicationPolicyBinding(
            semantic_ref=_publication_ref("claim", item["claim_ref"]),
            policy_anchor_ids=("PA-KO",),
        )
        for item in semantic["claims"]
    ]
    policy_bindings.extend(
        PublicationPolicyBinding(
            semantic_ref=_publication_ref("event", item["event_ref"]),
            policy_anchor_ids=("PA-KO",),
        )
        for item in semantic["events"]
    )
    policy_bindings.extend(
        PublicationPolicyBinding(
            semantic_ref=_publication_ref(
                "event_participation", item["participation_ref"]
            ),
            policy_anchor_ids=("PA-KO",),
        )
        for item in semantic["participations"]
    )
    for item in semantic["evidence_links"]:
        policy_bindings.append(
            PublicationPolicyBinding(
                semantic_ref=_publication_ref(
                    "evidence_link", item["evidence_link_ref"]
                ),
                policy_anchor_ids=(
                    "PA-RESTRICTED-EVIDENCE"
                    if item["evidence_address_ref"]
                    == restricted_evidence_ref.stable_id
                    else "PA-KO",
                ),
            ),
        )

    plan = PublicationAssemblyPlan(
        knowledge_object_id=knowledge_object_ref.stable_id,
        knowledge_object_version=knowledge_object_ref.version,
        title="Minecraft Education esports pilot – synthetic golden case",
        language="en",
        primary_kind="event_summary",
        knowledge_functions=("descriptive", "explanatory"),
        applicability=PublicationApplicability(
            entity_refs=tuple(
                _publication_ref("entity", entity_by_key[key]["entity_ref"])
                for key in ("pilot", "school", "provider")
            ),
            purposes=("source_to_knowledge_core_mvp_test",),
            valid_time=(
                {
                    "role": "valid_time",
                    "value_kind": "instant",
                    "precision": "minute",
                    "modality": "actual",
                    "start": GOLDEN_AS_OF,
                    "end": None,
                    "timezone": "+02:00",
                    "approximate": False,
                    "uncertainty": None,
                    "source_ref": None,
                },
            ),
        ),
        profile_refs=(ORGANIZATIONAL_PROFILE_REF,),
        policy_anchors=policy_anchors,
        policy_bindings=tuple(policy_bindings),
        evidence_link_interpretation_provenance=(
            PublicationInterpretationProvenance(
                producer_ref=_publication_ref(
                    "producer",
                    "CPKT-RULE-INTERPRETER",
                    authority_context="Platform and Integration",
                ),
                method="deterministic_reference_rules",
                produced_at="2026-08-08T00:00:00+02:00",
            )
        ),
    )

    claim_items = tuple(
        PublicationRepresentationItem(
            semantic_ref=_publication_ref("claim", claim["claim_ref"]),
            narrative_anchor=f"claim-{claim['rule_key']}",
            representation_role="primary_statement",
            rendered_text=_publication_claim_sentence(claim),
            heading=claim["rule_key"],
            mapping_id=f"CVM-CLAIM-{claim['rule_key']}",
            material=True,
        )
        for claim in semantic["claims"]
    )
    event_items = tuple(
        PublicationRepresentationItem(
            semantic_ref=_publication_ref("event", event["event_ref"]),
            narrative_anchor=f"event-{event['rule_key']}",
            representation_role="event_note",
            rendered_text=(
                f"Event state: {event['time_modality']}; time: "
                f"{event['event_time'] or 'unknown'}."
            ),
            heading=event["label"],
            mapping_id=f"CVM-EVENT-{event['rule_key']}",
            material=True,
        )
        for event in semantic["events"]
    ) + tuple(
        PublicationRepresentationItem(
            semantic_ref=_publication_ref(
                "event_participation", participation["participation_ref"]
            ),
            narrative_anchor=f"participation-{participation['rule_key']}",
            representation_role="event_note",
            rendered_text=f"Role: {participation['role']}.",
            heading=f"Participation {participation['rule_key']}",
            mapping_id=f"CVM-PART-{participation['rule_key']}",
            material=True,
        )
        for participation in semantic["participations"]
    )
    evidence_items = tuple(
        PublicationRepresentationItem(
            semantic_ref=_publication_ref(
                "evidence_link", link["evidence_link_ref"]
            ),
            narrative_anchor=f"evidence-{link['rule_key']}",
            representation_role="evidence_note",
            rendered_text=(
                f"Evidence role: `{link['role']}`; address remains "
                "version-bound and resolvable."
            ),
            heading=link["rule_key"],
        )
        for link in semantic["evidence_links"]
    )
    conflict_items = tuple(
        PublicationRepresentationItem(
            semantic_ref=_publication_ref(
                "conflict_set", conflict["conflict_set_ref"]
            ),
            narrative_anchor=f"conflict-{conflict['rule_key']}",
            representation_role="conflict_note",
            rendered_text=(
                "Preferred current state is context-bound; prior alternatives "
                f"remain addressable. {conflict['rationale']}"
            ),
            heading=conflict["rule_key"],
            mapping_id=f"CVM-CONFLICT-{conflict['rule_key']}",
            material=True,
        )
        for conflict in semantic["conflict_sets"]
    )
    representation = PublicationRepresentation(
        summary=PublicationRepresentationSection(
            narrative_anchor="ko-summary",
            heading="Summary",
            rendered_text="The school confirmed a limited after-school Minecraft Education esports pilot. Earlier proposal and open states remain evidentially traceable.",
            semantic_ref=knowledge_object_ref,
            representation_role="summary",
            mapping_id="CVM-SUMMARY",
            material=True,
        ),
        applicability=PublicationRepresentationSection(
            narrative_anchor="ko-applicability",
            heading="Applicability",
            rendered_text="Synthetic, non-sensitive Source-to-Knowledge MVP reference case.",
            semantic_ref=knowledge_object_ref,
            representation_role="applicability_note",
            mapping_id="CVM-APPLICABILITY",
            material=True,
        ),
        details=PublicationRepresentationSection(
            narrative_anchor="ko-details",
            heading="Context",
            rendered_text="The dossier preserves proposal, response, confirmed pilot status, temporal progression, uncertainty, and policy boundaries.",
        ),
        claims=PublicationRepresentationSection(
            narrative_anchor="ko-claims",
            heading="Claims",
            items=claim_items,
        ),
        events=PublicationRepresentationSection(
            narrative_anchor="ko-events",
            heading="Events and participations",
            items=event_items,
        ),
        evidence=PublicationRepresentationSection(
            narrative_anchor="ko-evidence",
            heading="Evidence and provenance",
            items=evidence_items,
        ),
        conflicts=PublicationRepresentationSection(
            narrative_anchor="ko-conflicts",
            heading="Conflicts and uncertainty",
            items=conflict_items,
        ),
        policy=PublicationRepresentationSection(
            narrative_anchor="ko-policy",
            heading="Policy and use",
            rendered_text="The abstract budget claim is readable for the test consumer. Resolution of the restricted exact-budget evidence remains denied.",
            semantic_ref=knowledge_object_ref,
            representation_role="policy_note",
            mapping_id="CVM-POLICY",
            material=True,
            items=(
                PublicationRepresentationItem(
                    semantic_ref=restricted_evidence_ref,
                    narrative_anchor="restricted-evidence-policy",
                    representation_role="policy_note",
                    heading="Restricted evidence policy",
                    rendered_text="Restricted source evidence is referenced but its exact monetary amount is intentionally not reproduced here.",
                ),
            ),
        ),
        publication=PublicationRepresentationSection(
            narrative_anchor="ko-publication",
            heading="Review and publication",
            rendered_text="Publication state: `unpublished`. This MVP does not perform canonical Vault publication.",
        ),
        body_language="en",
    )
    return plan, representation


def _experience_projection_plan(semantic: dict) -> ExperienceProjectionPlan:
    claim_refs = {
        item["rule_key"]: item["claim_ref"] for item in semantic["claims"]
    }
    event_refs = {
        item["rule_key"]: item["event_ref"] for item in semantic["events"]
    }
    participation_refs = {
        item["rule_key"]: item["participation_ref"]
        for item in semantic["participations"]
    }
    selector = ExperienceSemanticSelector
    return ExperienceProjectionPlan(
        experience_ref="EXP-GT-ME-ESPORTS-PILOT-RMIS-2024",
        focus_knowledge_object_ref="KO-GT-ME-ESPORTS-PILOT@0.1",
        as_of=GOLDEN_AS_OF,
        phases=(
            ExperiencePhasePlan(
                "context",
                (
                    selector(
                        "claim",
                        stable_id=claim_refs["chris_codelab_affiliated"],
                    ),
                    selector(
                        "claim",
                        stable_id=claim_refs["vera_school_affiliated"],
                    ),
                    selector(
                        "claim",
                        stable_id=claim_refs["chris_school_provides_services"],
                    ),
                    selector(
                        "claim",
                        stable_id=claim_refs["james_pilot_assigned"],
                    ),
                    selector(
                        "claim",
                        stable_id=claim_refs["james_pilot_responsible"],
                    ),
                ),
            ),
            ExperiencePhasePlan(
                "intent",
                (
                    selector(
                        "event",
                        stable_id=event_refs["pilot_proposal"],
                        event_type_ref="cpks.vocab.profile.organizational-context.event_type.proposal",
                        time_modality="actual",
                    ),
                    selector(
                        "claim",
                        stable_id=claim_refs["training_initial_date"],
                    ),
                    selector(
                        "claim",
                        stable_id=claim_refs["capacity_initial_estimate"],
                    ),
                ),
            ),
            ExperiencePhasePlan(
                "proposal",
                (
                    selector(
                        "event",
                        stable_id=event_refs["pilot_proposal"],
                        event_type_ref="cpks.vocab.profile.organizational-context.event_type.proposal",
                        time_modality="actual",
                    ),
                    selector(
                        "event_participation",
                        stable_id=participation_refs["chris_proposal_initiator"],
                        event_type_ref="cpks.vocab.profile.organizational-context.event_type.proposal",
                        participation_role="initiator",
                        time_modality="actual",
                    ),
                ),
            ),
            ExperiencePhasePlan(
                "decision",
                (
                    selector(
                        "event",
                        stable_id=event_refs["pilot_decision"],
                        event_type_ref="cpks.vocab.profile.organizational-context.event_type.decision",
                        time_modality="actual",
                    ),
                    selector(
                        "claim",
                        stable_id=claim_refs["scope_afterschool"],
                    ),
                ),
            ),
            ExperiencePhasePlan(
                "scope",
                (
                    selector("claim", stable_id=claim_refs["scope_open"]),
                    selector(
                        "claim",
                        stable_id=claim_refs["scope_afterschool"],
                        claim_predicate_ref="cpkt.test.minecraft.scope",
                        claim_object_value="after-school only",
                    ),
                    selector("claim", stable_id=claim_refs["academic_deferred"]),
                    selector(
                        "claim",
                        stable_id=claim_refs["classroom_integration_dependency"],
                        claim_predicate_ref="cpkt.test.minecraft.classroom_integration_dependency",
                        claim_object_value="requires_pilot_evaluation",
                    ),
                    selector(
                        "claim",
                        stable_id=claim_refs["competition_decision_dependency"],
                        claim_predicate_ref="cpkt.test.minecraft.external_competition_decision_dependency",
                        claim_object_value="depends_on_internal_pilot_evaluation",
                    ),
                ),
            ),
            ExperiencePhasePlan(
                "execution",
                (
                    selector(
                        "event",
                        stable_id=event_refs["internal_pilot"],
                        event_type_ref="cpkt.test.event_type.internal_pilot",
                        time_modality="actual",
                    ),
                ),
                required_for_lesson_learned=True,
            ),
            ExperiencePhasePlan(
                "evaluation",
                (
                    selector(
                        "event",
                        event_type_ref="cpkt.test.event_type.pilot_evaluation",
                        time_modality="actual",
                    ),
                ),
                required_for_lesson_learned=True,
            ),
            ExperiencePhasePlan(
                "outcome",
                (
                    selector(
                        "claim",
                        claim_predicate_ref="cpkt.test.minecraft.pilot_outcome",
                    ),
                ),
                required_for_lesson_learned=True,
            ),
            ExperiencePhasePlan(
                "follow_up",
                (
                    selector(
                        "claim",
                        claim_predicate_ref="cpkt.test.minecraft.classroom_integration_followup",
                    ),
                    selector(
                        "claim",
                        claim_predicate_ref="cpkt.test.minecraft.external_competition_followup",
                    ),
                ),
            ),
        ),
        threads=(
            ExperienceThreadPlan(
                "scope_evaluation",
                (
                    claim_refs["scope_open"],
                    claim_refs["scope_afterschool"],
                    claim_refs["academic_deferred"],
                    claim_refs["classroom_integration_dependency"],
                ),
            ),
            ExperienceThreadPlan(
                "external_competition",
                (
                    claim_refs["competition_later_possible"],
                    claim_refs["competition_not_approved"],
                    claim_refs["competition_decision_dependency"],
                ),
            ),
        ),
        gaps=(
            ExperienceGapPlan(
                "EXP-GAP-PILOT-EXECUTION",
                "Did the internal pilot actually occur?",
                "execution",
                (event_refs["internal_pilot"],),
            ),
            ExperienceGapPlan(
                "EXP-GAP-PILOT-EVALUATION-OCCURRENCE",
                "Was the pilot evaluated?",
                "evaluation",
                (
                    claim_refs["classroom_integration_dependency"],
                    claim_refs["competition_decision_dependency"],
                ),
            ),
            ExperienceGapPlan(
                "EXP-GAP-PILOT-EVALUATION-RESULT",
                "What was the evaluation result?",
                "evaluation",
                (
                    claim_refs["classroom_integration_dependency"],
                    claim_refs["competition_decision_dependency"],
                ),
            ),
            ExperienceGapPlan(
                "EXP-GAP-PILOT-OUTCOME",
                "Was the pilot successful, unsuccessful, or mixed?",
                "outcome",
                (event_refs["internal_pilot"],),
            ),
            ExperienceGapPlan(
                "EXP-GAP-CLASSROOM-INTEGRATION-FOLLOWUP",
                "Was classroom integration later introduced or rejected?",
                "follow_up",
                (
                    claim_refs["academic_deferred"],
                    claim_refs["classroom_integration_dependency"],
                ),
            ),
            ExperienceGapPlan(
                "EXP-GAP-EXTERNAL-COMPETITION-FOLLOWUP",
                "Was external competition later approved or rejected?",
                "follow_up",
                (
                    claim_refs["competition_not_approved"],
                    claim_refs["competition_decision_dependency"],
                ),
            ),
            ExperienceGapPlan(
                "EXP-GAP-PILOT-REPETITION",
                "Was the pilot repeated or institutionalized?",
                "follow_up",
                (event_refs["internal_pilot"],),
            ),
        ),
        reuse_context=ExperienceReuseContext(
            domain_terms=("education", "school", "pilot"),
            topic_terms=(
                "minecraft_education",
                "esports",
                "after_school",
                "classroom_integration",
                "pilot_evaluation",
                "external_competition",
            ),
            purpose_terms=(
                "proposal_planning",
                "similar_experience_retrieval",
                "experience_reuse",
                "lesson_learned_discovery",
            ),
        ),
        continuation=ExperienceContinuationPlan(
            continuation_ref="EXP-CONT-01",
            critical_gap_refs=(
                "EXP-GAP-PILOT-EXECUTION",
                "EXP-GAP-PILOT-EVALUATION-OCCURRENCE",
                "EXP-GAP-PILOT-EVALUATION-RESULT",
                "EXP-GAP-PILOT-OUTCOME",
                "EXP-GAP-CLASSROOM-INTEGRATION-FOLLOWUP",
            ),
            search_after=GOLDEN_AS_OF,
            trigger_purposes=(
                "similar_experience_retrieval",
                "experience_reuse",
                "lesson_learned_discovery",
            ),
        ),
    )


def _policy_configuration(
    knowledge_object: PolicySubject,
    restricted_evidence: PolicySubject,
) -> PolicyConfiguration:
    return PolicyConfiguration(
        policy_ref=POLICY_REF,
        version=POLICY_VERSION,
        status="active",
        rules=(
            PolicyRule(
                policy_rule_ref="CPKT-MVP-RULE-CLAIM-READ",
                actor_or_consumer_ref=CONSUMER_REF,
                purpose=PURPOSE,
                requested_operation="claim_read",
                subject_ref=knowledge_object,
                required_policy_anchor_ids=("PA-KO",),
                effect="permit",
                reason="synthetic_consumer_may_read_claims_in_mvp_publication_unit",
            ),
            PolicyRule(
                policy_rule_ref="CPKT-MVP-RULE-RESTRICTED-EVIDENCE-DENY",
                actor_or_consumer_ref=CONSUMER_REF,
                purpose=PURPOSE,
                requested_operation="evidence_resolution",
                subject_ref=restricted_evidence,
                required_policy_anchor_ids=("PA-RESTRICTED-EVIDENCE",),
                effect="deny",
                reason="synthetic_consumer_may_not_resolve_exact_budget_evidence",
            ),
        ),
    )


def _retrieval_requests(
    semantic: dict,
    knowledge_object: PolicySubject,
) -> list[tuple[dict, RetrievalRequest]]:
    entity_by_key = {item["rule_key"]: item for item in semantic["entities"]}
    return [
        (
            need,
            RetrievalRequest(
                retrieval_request_ref=f"RREQ-{need['query_key'].upper()}",
                consumer_ref=CONSUMER_REF,
                purpose=PURPOSE,
                knowledge_object_ref=knowledge_object,
                semantic_subject_refs=tuple(
                    entity_by_key[key]["entity_ref"]
                    for key in need.get(
                        "subject_keys",
                        (need["subject_key"],) if "subject_key" in need else (),
                    )
                ),
                claim_predicate_refs=need["claim_predicates"],
                event_type_refs=need["event_types"],
                participant_entity_refs=tuple(
                    entity_by_key[key]["entity_ref"]
                    for key in need.get("participant_keys", ())
                ),
                participation_role_refs=need.get("participation_roles", ()),
                profile_refs=(ORGANIZATIONAL_PROFILE_REF,),
                state_selection=need["state_selection"],
            ),
        )
        for need in RETRIEVAL_NEEDS
    ]


def _experience_retrieval_requests(
    knowledge_object: PolicySubject,
) -> list[tuple[dict, ExperienceRetrievalRequest]]:
    needs = (
        {
            "query_key": "experience_summary",
            "query": "experience",
            "experience_ref": "EXP-GT-ME-ESPORTS-PILOT-RMIS-2024",
        },
        {
            "query_key": "final_pilot_scope",
            "query": "thread",
            "thread_ref": "scope_evaluation",
        },
        {
            "query_key": "pilot_evaluation",
            "query": "phases",
            "phase_ref": "evaluation",
        },
        {
            "query_key": "pilot_outcome",
            "query": "phases",
            "phase_ref": "outcome",
        },
        {
            "query_key": "classroom_integration_followup",
            "query": "gaps",
            "gap_ref": "EXP-GAP-CLASSROOM-INTEGRATION-FOLLOWUP",
        },
        {
            "query_key": "external_competition_followup",
            "query": "thread",
            "thread_ref": "external_competition",
        },
        {
            "query_key": "lesson_learned",
            "query": "lesson_learned_eligibility",
        },
        {
            "query_key": "similar_experience",
            "query": "reuse_match",
            "required_terms": (
                "education",
                "school",
                "minecraft_education",
                "esports",
            ),
        },
    )
    return [
        (
            need,
            ExperienceRetrievalRequest(
                retrieval_request_ref=(
                    f"ERREQ-{need['query_key'].upper()}"
                ),
                consumer_ref=CONSUMER_REF,
                purpose=PURPOSE,
                knowledge_object_ref=knowledge_object,
                query=need["query"],
                experience_ref=need.get("experience_ref"),
                phase_ref=need.get("phase_ref"),
                thread_ref=need.get("thread_ref"),
                gap_ref=need.get("gap_ref"),
                required_terms=need.get("required_terms", ()),
            ),
        )
        for need in needs
    ]


def _retrieval_harness_result(
    need: dict,
    retrieval_result,
    rendered: dict,
    actual_claim_to_gt: dict[str, str],
    actual_event_to_gt: dict[str, str],
    actual_participation_to_gt: dict[str, str],
) -> dict:
    structured = retrieval_result.to_dict()
    actual_claim_refs = [
        item["subject_ref"]["stable_id"] for item in structured["claim_items"]
    ]
    evidence_refs = [
        evidence_ref
        for item in (
            *structured["claim_items"],
            *structured["event_items"],
            *structured["participation_items"],
        )
        for evidence_ref in item["evidence_refs"]
    ]
    actual_event_refs = list(
        dict.fromkeys(
            [
                item["subject_ref"]["stable_id"]
                for item in structured["event_items"]
            ]
            + [
                item["event_ref"]["stable_id"]
                for item in structured["participation_items"]
            ]
        )
    )
    actual_participation_refs = [
        item["subject_ref"]["stable_id"]
        for item in structured["participation_items"]
    ]
    return {
        "query_key": need["query_key"],
        "claim_keys": [actual_claim_to_gt[ref] for ref in actual_claim_refs],
        "actual_claim_refs": actual_claim_refs,
        "event_keys": [actual_event_to_gt[ref] for ref in actual_event_refs],
        "event_refs": actual_event_refs,
        "participation_keys": [
            actual_participation_to_gt[ref]
            for ref in actual_participation_refs
        ],
        "participation_refs": actual_participation_refs,
        "evidence_refs": evidence_refs,
        "publication_unit_ref": structured["publication_unit_ref"],
        "projection_ref": structured["projection_ref"],
        "structured_result": structured,
        **rendered,
    }


def _experience_harness_result(
    need: dict,
    retrieval_result,
    actual_semantic_to_gt: dict[str, str],
) -> dict:
    structured = retrieval_result.to_dict()
    for item in structured["items"]:
        if "semantic_refs" in item:
            item["semantic_gt_refs"] = [
                actual_semantic_to_gt[ref] for ref in item["semantic_refs"]
            ]
        if item.get("semantic_basis_refs"):
            item["semantic_basis_gt_refs"] = [
                actual_semantic_to_gt[ref]
                for ref in item["semantic_basis_refs"]
            ]
        for thread in item.get("threads", ()):
            thread["semantic_gt_refs"] = [
                actual_semantic_to_gt[ref]
                for ref in thread["semantic_refs"]
            ]
    return {"query_key": need["query_key"], **structured}


def _experience_harness_projection(
    projection,
    actual_semantic_to_gt: dict[str, str],
    artifact_path: str,
) -> dict:
    value = projection.to_dict()
    for thread in value["threads"]:
        thread["semantic_gt_refs"] = [
            actual_semantic_to_gt[ref] for ref in thread["semantic_refs"]
        ]
    for gap in value["gaps"]:
        gap["semantic_basis_gt_refs"] = [
            actual_semantic_to_gt[ref]
            for ref in gap["semantic_basis_refs"]
        ]
    return {
        **value,
        "projection_count": 1,
        "projection_ref": value["experience_projection_ref"],
        "completeness": value["experience_completeness"],
        "artifact_path": artifact_path,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-root",
        default="artifacts/tests/source_to_knowledge/minecraft_esports",
    )
    args = parser.parse_args()

    output_root = (REPO_ROOT / args.output_root).resolve()
    output_root.mkdir(parents=True, exist_ok=True)

    adapter = LocalHtmlAdapter()
    records_list = adapter.capture_many(SOURCE_BINDINGS.items())
    records = {record.source_key: record for record in records_list}

    evidence = {}
    for rule_key, (source_key, fragments) in EVIDENCE_RULES.items():
        address = adapter.evidence_address(records[source_key], fragments)
        if not adapter.resolve(records[source_key], address):
            raise RuntimeError(f"Evidence Address is not reproducible: {rule_key}")
        evidence[rule_key] = address

    # Materialize immutable test snapshots and normalized Source Records. These
    # are run artifacts, not canonical knowledge and not Repository fixtures.
    source_artifact_root = output_root / "source"
    snapshot_dir = source_artifact_root / "snapshots"
    record_dir = source_artifact_root / "records"
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    record_dir.mkdir(parents=True, exist_ok=True)
    for record in records.values():
        (snapshot_dir / f"{record.snapshot_ref}.html").write_text(
            record.raw_html, encoding="utf-8"
        )
        (record_dir / f"{record.record_ref}.json").write_text(
            json.dumps(
                {
                    "source_key": record.source_key,
                    "source_ref": record.source_ref,
                    "snapshot_ref": record.snapshot_ref,
                    "record_ref": record.record_ref,
                    "source_time": record.source_time,
                    "captured_at": record.captured_at,
                    "media_type": record.media_type,
                    "title": record.title,
                    "raw_sha256": record.raw_sha256,
                    "normalized_text": record.normalized_text,
                },
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
    (source_artifact_root / "evidence_addresses.json").write_text(
        json.dumps(
            [
                {
                    "rule_key": key,
                    "evidence_address_ref": address.evidence_address_ref,
                    "source_ref": address.source_ref,
                    "snapshot_ref": address.snapshot_ref,
                    "record_ref": address.record_ref,
                    "selector": address.selector,
                    "content_hash": address.content_hash,
                    "restricted": address.restricted,
                }
                for key, address in evidence.items()
            ],
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    interpreter = RuleBasedSemanticInterpreter()
    interpretation = interpreter.interpret(records, evidence, RULES)
    candidate_artifact_path = output_root / "semantic/candidate_payloads.json"
    candidate_artifact_path.parent.mkdir(parents=True, exist_ok=True)
    candidate_artifact_path.write_text(
        json.dumps(interpretation.to_dict(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    if interpretation.known_gaps:
        gap_refs = ", ".join(
            gap.interpretation_rule_ref for gap in interpretation.known_gaps
        )
        raise RuntimeError(f"Required MVP semantic extraction gaps: {gap_refs}")
    semantic = SemanticStateMaterializer().materialize(
        interpretation,
        CURATION_RULES,
    )

    pu_path = output_root / "publication/KO-GT-ME-ESPORTS-PILOT@0.1.md"
    publication_plan, publication_representation = _publication_inputs(
        semantic,
        evidence,
    )
    assembler = PublicationUnitAssembler()
    pu_manifest = assembler.assemble(
        semantic,
        plan=publication_plan,
        representation=publication_representation,
        output_path=pu_path,
    )
    if pu_manifest["integrity"]["cross_view_validation"]["status"] != "pass":
        raise RuntimeError("Cross-view validation failed")

    loaded_manifest = load_publication_manifest(pu_path)
    builder = DerivedRetrievalBuilder()
    projection_a = builder.build(loaded_manifest)
    projection_path = output_root / "derived/retrieval_projection.json"
    builder.write(projection_a, projection_path)
    hash_a = canonical_json_hash(projection_a)
    experience_plan = _experience_projection_plan(semantic)
    experience_builder = ExperienceProjectionBuilder()
    experience_projection_a = experience_builder.build(
        loaded_manifest,
        experience_plan,
    )
    experience_projection_path = (
        output_root / "derived/experience_projection.json"
    )
    experience_builder.write(
        experience_projection_a,
        experience_projection_path,
    )
    experience_hash_a = experience_projection_a.semantic_hash

    knowledge_object_subject = PolicySubject(
        subject_type="knowledge_object",
        stable_id=pu_manifest["knowledge_object_id"],
        version=pu_manifest["knowledge_object_version"],
        authority_context="Semantic Core",
    )
    restricted_evidence_subject = PolicySubject(
        subject_type="evidence_address",
        stable_id=evidence["budget_exact"].evidence_address_ref,
        version="0.1",
        authority_context="Source and Evidence",
    )
    policy_configuration = _policy_configuration(
        knowledge_object_subject,
        restricted_evidence_subject,
    )
    evaluator = PolicyEvaluator()
    organizational_profile_resolution = ProfileReferenceResolution(
        concrete_ref=ORGANIZATIONAL_PROFILE_REF,
        artifact_type="profile_manifest",
        lifecycle_status="active",
        applicable=True,
        compatible=True,
    )
    profile_applicability = ProfileApplicability(
        resolution_status="resolved",
        reference_resolutions=(organizational_profile_resolution,),
        required_profile_refs=(ORGANIZATIONAL_PROFILE_REF,),
    )
    claim_read_evaluation = PolicyEvaluationInput(
        policy_evaluation_ref="PEVAL-MVP-CLAIM-READ",
        actor_or_consumer_ref=CONSUMER_REF,
        purpose=PURPOSE,
        requested_operation="claim_read",
        subject_refs=(knowledge_object_subject,),
        policy_config_ref=policy_configuration.concrete_ref,
        processing_zone="local_synthetic_test",
        profile_refs=(ORGANIZATIONAL_PROFILE_REF,),
        profile_applicability=profile_applicability,
        policy_anchor_ids=("PA-KO",),
        requested_at="2026-08-09T00:00:00+02:00",
        context_valid_at="2026-08-09T00:00:00+02:00",
    )
    claim_read_decision = evaluator.evaluate(
        claim_read_evaluation,
        policy_configuration,
    )
    evidence_evaluation = PolicyEvaluationInput(
        policy_evaluation_ref="PEVAL-MVP-RESTRICTED-EVIDENCE",
        actor_or_consumer_ref=CONSUMER_REF,
        purpose=PURPOSE,
        requested_operation="evidence_resolution",
        subject_refs=(restricted_evidence_subject,),
        policy_config_ref=policy_configuration.concrete_ref,
        processing_zone="local_synthetic_test",
        profile_refs=(ORGANIZATIONAL_PROFILE_REF,),
        profile_applicability=profile_applicability,
        policy_anchor_ids=("PA-RESTRICTED-EVIDENCE",),
        requested_at="2026-08-09T00:00:00+02:00",
        context_valid_at="2026-08-09T00:00:00+02:00",
    )
    evidence_decision = evaluator.evaluate(
        evidence_evaluation,
        policy_configuration,
    )

    retrieval_requests = _retrieval_requests(semantic, knowledge_object_subject)
    retriever = KnowledgeRetriever()
    renderer = RetrievalRenderer()
    reference_labels = {
        item["entity_ref"]: item["label"] for item in semantic["entities"]
    }
    retrieval_results_a = [
        retriever.retrieve(projection_a, request, claim_read_decision)
        for _need, request in retrieval_requests
    ]
    rendered_results_a = [
        renderer.render(item, reference_labels=reference_labels)
        for item in retrieval_results_a
    ]
    experience_retrieval_requests = _experience_retrieval_requests(
        knowledge_object_subject
    )
    experience_retriever = ExperienceRetriever()

    def load_experience_projection_a():
        return (experience_projection_a,)

    experience_retrieval_results_a = [
        experience_retriever.retrieve(
            load_experience_projection_a,
            request,
            claim_read_decision,
        )
        for _need, request in experience_retrieval_requests
    ]

    evidence_loader_called = False

    def load_restricted_evidence() -> str:
        nonlocal evidence_loader_called
        evidence_loader_called = True
        return evidence["budget_exact"].text

    evidence_resolution = EvidenceResolver().resolve(
        EvidenceResolutionRequest(
            evidence_resolution_request_ref="ERREQ-MVP-EXACT-BUDGET",
            consumer_ref=CONSUMER_REF,
            purpose=PURPOSE,
            evidence_ref=restricted_evidence_subject,
        ),
        evidence_decision,
        load_restricted_evidence,
    )

    projection_path.unlink()
    experience_projection_path.unlink()
    derived_absent_after_delete = (
        not projection_path.exists()
        and not experience_projection_path.exists()
    )

    loaded_manifest_b = load_publication_manifest(pu_path)
    projection_b = builder.build(loaded_manifest_b)
    builder.write(projection_b, projection_path)
    hash_b = canonical_json_hash(projection_b)
    experience_projection_b = experience_builder.build(
        loaded_manifest_b,
        experience_plan,
    )
    experience_builder.write(
        experience_projection_b,
        experience_projection_path,
    )
    experience_hash_b = experience_projection_b.semantic_hash

    retrieval_results_b = [
        retriever.retrieve(projection_b, request, claim_read_decision)
        for _need, request in retrieval_requests
    ]
    rendered_results_b = [
        renderer.render(item, reference_labels=reference_labels)
        for item in retrieval_results_b
    ]

    def load_experience_projection_b():
        return (experience_projection_b,)

    experience_retrieval_results_b = [
        experience_retriever.retrieve(
            load_experience_projection_b,
            request,
            claim_read_decision,
        )
        for _need, request in experience_retrieval_requests
    ]

    claim_by_key = {item["rule_key"]: item for item in semantic["claims"]}
    actual_claim_to_gt = {
        item["claim_ref"]: CLAIM_GT[item["rule_key"]]
        for item in semantic["claims"]
    }
    actual_event_to_gt = {
        item["event_ref"]: EVENT_GT[item["rule_key"]]
        for item in semantic["events"]
    }
    actual_participation_to_gt = {
        item["participation_ref"]: PARTICIPATION_GT[item["rule_key"]]
        for item in semantic["participations"]
    }
    actual_entity_to_gt = {
        item["entity_ref"]: ENTITY_GT[item["rule_key"]]
        for item in semantic["entities"]
    }
    actual_subject_to_gt = {
        "claim": actual_claim_to_gt,
        "event": actual_event_to_gt,
        "event_participation": actual_participation_to_gt,
    }
    actual_semantic_to_gt = {
        **actual_claim_to_gt,
        **actual_event_to_gt,
        **actual_participation_to_gt,
    }
    retrieval_output = []
    for (need, _request), retrieval_result, rendered in zip(
        retrieval_requests,
        retrieval_results_b,
        rendered_results_b,
        strict=True,
    ):
        if need.get("protected_evidence_rule_key"):
            rendered = {
                **rendered,
                "evidence_resolution": evidence_resolution.status,
            }
        retrieval_output.append(
            _retrieval_harness_result(
                need,
                retrieval_result,
                rendered,
                actual_claim_to_gt,
                actual_event_to_gt,
                actual_participation_to_gt,
            )
        )
    retrieval_equivalent = [
        item.semantic_signature() for item in retrieval_results_a
    ] == [item.semantic_signature() for item in retrieval_results_b]
    rendered_equivalent = rendered_results_a == rendered_results_b
    experience_retrieval_output = [
        _experience_harness_result(
            need,
            retrieval_result,
            actual_semantic_to_gt,
        )
        for (need, _request), retrieval_result in zip(
            experience_retrieval_requests,
            experience_retrieval_results_b,
            strict=True,
        )
    ]
    experience_retrieval_equivalent = [
        item.semantic_signature()
        for item in experience_retrieval_results_a
    ] == [
        item.semantic_signature()
        for item in experience_retrieval_results_b
    ]
    budget_retrieval = next(
        item for item in retrieval_output if item["query_key"] == "pilot_budget"
    )
    artifact_path = (
        pu_path.relative_to(REPO_ROOT)
        if pu_path.is_relative_to(REPO_ROOT)
        else pu_path.relative_to(output_root)
    )
    experience_artifact_path = experience_projection_path.relative_to(
        output_root
    )

    result = {
        "result_format_version": "0.1",
        "scenario_ref": "GT-S2K-MINI-DOSSIER-01",
        "scenario_version": "1.2",
        "golden_as_of": GOLDEN_AS_OF,
        "outcome": "pass",
        "source": {
            "source_count": len(records),
            "snapshot_count": len({record.snapshot_ref for record in records.values()}),
            "record_count": len({record.record_ref for record in records.values()}),
            "all_source_identities_preserved": len({record.source_ref for record in records.values()}) == 3,
            "evidence_addresses": [
                {
                    "gt_id": EVIDENCE_GT.get(key, f"RUN-EVIDENCE-{key.upper()}"),
                    "source_key": SOURCE_GT[address.source_key],
                    "actual_evidence_address_ref": address.evidence_address_ref,
                    "snapshot_ref": address.snapshot_ref,
                    "record_ref": address.record_ref,
                    "selector": address.selector,
                    "content_hash": address.content_hash,
                    "restricted": address.restricted,
                    "resolvable": adapter.resolve(records[address.source_key], address),
                }
                for key, address in evidence.items()
            ],
        },
        "semantic": {
            "candidate_boundary": {
                "artifact_path": str(
                    candidate_artifact_path.relative_to(output_root)
                ),
                "candidate_count": len(interpretation.candidate_payloads),
                "known_gaps": [
                    {
                        "gap_code": gap.gap_code,
                        "interpretation_rule_ref": gap.interpretation_rule_ref,
                        "detail": gap.detail,
                        "evidence_address_refs": gap.evidence_address_refs,
                    }
                    for gap in interpretation.known_gaps
                ],
                "candidate_payloads": [
                    candidate.to_dict()
                    for candidate in interpretation.candidate_payloads
                ],
            },
            "entities": [
                {"gt_id": ENTITY_GT[item["rule_key"]], "actual_entity_ref": item["entity_ref"], "label": item["label"], "class": item["class"]}
                for item in semantic["entities"]
            ],
            "claims": [
                {
                    "gt_id": CLAIM_GT[item["rule_key"]],
                    "actual_claim_ref": item["claim_ref"],
                    "value": ENTITY_GT["james"] if item["rule_key"] == "adviser_confirmed_person" else item["value"],
                    "relationship": item["relationship"],
                    "subject_gt_id": actual_entity_to_gt[item["subject_ref"]],
                    "predicate_ref": item["predicate_ref"],
                    "object_gt_id": actual_entity_to_gt.get(item["object_ref"]),
                    "epistemic_status": item["epistemic_status"],
                    "source_keys": [SOURCE_GT[key] for key in item["source_keys"]],
                    "time_modality": item["time_modality"],
                    "current": item["current"],
                    "preserved": item["preserved"],
                }
                for item in semantic["claims"]
            ],
            "pattern_claims": [
                {
                    **item,
                    "rule_key": "DOC01_GENERAL_BENEFITS_REMAIN_REPORTED",
                    "source_keys": ["DOC-01"],
                }
                for item in semantic["pattern_claims"]
            ],
            "evidence_links": [
                {
                    "gt_id": EVIDENCE_LINK_GT[item["rule_key"]],
                    "subject_type": item["subject_type"],
                    "subject_gt_id": actual_subject_to_gt[item["subject_type"]][item["subject_ref"]],
                    "claim_gt_id": actual_claim_to_gt[item["subject_ref"]] if item["subject_type"] == "claim" else None,
                    "evidence_gt_id": EVIDENCE_GT[next(key for key, address in evidence.items() if address.evidence_address_ref == item["evidence_address_ref"])],
                    "role": item["role"],
                    "actual_evidence_link_ref": item["evidence_link_ref"],
                }
                for item in semantic["evidence_links"]
            ],
            "events": [
                {"gt_id": EVENT_GT[item["rule_key"]], "actual_event_ref": item["event_ref"], "event_type_ref": item["event_type_ref"], "event_time": item["event_time"], "time_precision": item["time_precision"], "time_modality": item["time_modality"], "source_keys": [SOURCE_GT[key] for key in item["source_keys"]]}
                for item in semantic["events"]
            ],
            "participations": [
                {
                    "gt_id": PARTICIPATION_GT[item["rule_key"]],
                    "actual_participation_ref": item["participation_ref"],
                    "event_gt_id": actual_event_to_gt[item["event_ref"]],
                    "entity_gt_id": actual_entity_to_gt[item["entity_ref"]],
                    "role": item["role"],
                }
                for item in semantic["participations"]
            ],
            "conflict_sets": [
                {
                    "gt_id": CONFLICT_GT[item["rule_key"]],
                    "actual_conflict_set_ref": item["conflict_set_ref"],
                    "claim_gt_ids": [CLAIM_GT[next(key for key, claim in claim_by_key.items() if claim["claim_ref"] == ref)] for ref in item["claim_refs"]],
                    "conflict_dimensions": item["conflict_dimensions"],
                    "preferred_claim_gt_id": CLAIM_GT[next(key for key, claim in claim_by_key.items() if claim["claim_ref"] == item["preferred_claim_ref"])],
                }
                for item in semantic["conflict_sets"]
            ],
        },
        "policy": {
            "consumer": CONSUMER_REF,
            "purpose": PURPOSE,
            "policy_configuration_ref": policy_configuration.concrete_ref,
            "claim_read": claim_read_decision.result,
            "claim_read_evaluation": {
                "policy_evaluation_ref": claim_read_evaluation.policy_evaluation_ref,
                "requested_operation": claim_read_evaluation.requested_operation,
                "policy_config_ref": claim_read_evaluation.policy_config_ref,
                "profile_refs": claim_read_evaluation.profile_refs,
                "profile_applicability_status": (
                    claim_read_evaluation.profile_applicability.resolution_status
                ),
                "policy_anchor_ids": claim_read_evaluation.policy_anchor_ids,
                "subject_refs": [
                    {
                        "subject_type": ref.subject_type,
                        "stable_id": ref.stable_id,
                        "version": ref.version,
                        "authority_context": ref.authority_context,
                    }
                    for ref in claim_read_evaluation.subject_refs
                ],
            },
            "claim_read_decision": claim_read_decision.to_dict(),
            "experience_delivery_authorization": "claim_read",
            "restricted_evidence_resolution": evidence_decision.result,
            "evidence_resolution_evaluation": {
                "policy_evaluation_ref": evidence_evaluation.policy_evaluation_ref,
                "requested_operation": evidence_evaluation.requested_operation,
                "policy_config_ref": evidence_evaluation.policy_config_ref,
                "profile_refs": evidence_evaluation.profile_refs,
                "profile_applicability_status": (
                    evidence_evaluation.profile_applicability.resolution_status
                ),
                "policy_anchor_ids": evidence_evaluation.policy_anchor_ids,
                "subject_refs": [
                    {
                        "subject_type": ref.subject_type,
                        "stable_id": ref.stable_id,
                        "version": ref.version,
                        "authority_context": ref.authority_context,
                    }
                    for ref in evidence_evaluation.subject_refs
                ],
            },
            "evidence_resolution_decision": evidence_decision.to_dict(),
            "consumer_visible_output": {
                "claim": budget_retrieval["rendered_answer"],
                "evidence_resolution": evidence_resolution.status,
                "evidence_content": evidence_resolution.content,
            },
            "restricted_evidence_loader_called": evidence_loader_called,
        },
        "publication_unit": {
            "knowledge_object_id": pu_manifest["knowledge_object_id"],
            "knowledge_object_version": pu_manifest["knowledge_object_version"],
            "primary_kind": pu_manifest["primary_kind"],
            "knowledge_functions": pu_manifest["knowledge_functions"],
            "publication_state": pu_manifest["publication"]["publication_state"],
            "canonical_path": pu_manifest["canonical_path"],
            "publication_record_ref": pu_manifest["publication"]["publication_record_ref"],
            "published_at": pu_manifest["publication"]["published_at"],
            "publisher_ref": pu_manifest["publication"]["publisher_ref"],
            "schema_ref": pu_manifest["schema_ref"],
            "semantic_model_ref": pu_manifest["semantic_model_ref"],
            "vocabulary_set_ref": pu_manifest["vocabulary_set_ref"],
            "profile_refs": pu_manifest["profile_refs"],
            "cross_view_validation": pu_manifest["integrity"]["cross_view_validation"]["status"],
            "artifact_path": str(artifact_path),
        },
        "experience": _experience_harness_projection(
            experience_projection_b,
            actual_semantic_to_gt,
            str(experience_artifact_path),
        ),
        "experience_retrieval": experience_retrieval_output,
        "retrieval": retrieval_output,
        "rebuild": {
            "derived_state_deleted": derived_absent_after_delete,
            "rebuild_success": (
                projection_path.is_file()
                and experience_projection_path.is_file()
            ),
            "semantic_equivalent": (
                hash_a == hash_b
                and retrieval_equivalent
                and experience_hash_a == experience_hash_b
                and experience_retrieval_equivalent
            ),
            "projection_hash_before": hash_a,
            "projection_hash_after": hash_b,
            "experience_projection_hash_before": experience_hash_a,
            "experience_projection_hash_after": experience_hash_b,
            "retrieval_result_signatures_before": [
                item.semantic_signature() for item in retrieval_results_a
            ],
            "retrieval_result_signatures_after": [
                item.semantic_signature() for item in retrieval_results_b
            ],
            "experience_retrieval_result_signatures_before": [
                item.semantic_signature()
                for item in experience_retrieval_results_a
            ],
            "experience_retrieval_result_signatures_after": [
                item.semantic_signature()
                for item in experience_retrieval_results_b
            ],
            "preserved": {
                "entity_resolution": rendered_equivalent,
                "claim_identities": projection_a["claim_index"] == projection_b["claim_index"],
                "current_state_preferences": projection_a["conflict_index"] == projection_b["conflict_index"],
                "epistemic_status": projection_a["claim_index"] == projection_b["claim_index"],
                "event_identities": projection_a["event_index"] == projection_b["event_index"],
                "event_times": projection_a["event_index"] == projection_b["event_index"],
                "evidence_link_roles": projection_a["evidence_index"] == projection_b["evidence_index"],
                "conflict_sets": projection_a["conflict_index"] == projection_b["conflict_index"],
                "organizational_relationship_claims": projection_a["claim_index"] == projection_b["claim_index"],
                "relationship_epistemics": projection_a["claim_index"] == projection_b["claim_index"],
                "organizational_action_events": projection_a["event_index"] == projection_b["event_index"],
                "event_participations": projection_a["participation_index"] == projection_b["participation_index"],
                "participation_roles": projection_a["participation_index"] == projection_b["participation_index"],
                "decision_confirmation_communication_separation": projection_a["event_index"] == projection_b["event_index"],
                "profile_refs": projection_a["profile_refs"] == projection_b["profile_refs"] == [ORGANIZATIONAL_PROFILE_REF],
                "experience_ref": experience_projection_a.experience_ref == experience_projection_b.experience_ref,
                "experience_phase_statuses": experience_projection_a.phases == experience_projection_b.phases,
                "experience_threads": experience_projection_a.threads == experience_projection_b.threads,
                "experience_gaps": experience_projection_a.gaps == experience_projection_b.gaps,
                "experience_reuse_context": experience_projection_a.reuse_context == experience_projection_b.reuse_context,
                "experience_continuation_requirement": experience_projection_a.continuation_requirements == experience_projection_b.continuation_requirements,
                "experience_lesson_learned_eligibility": experience_projection_a.lesson_learned_eligibility == experience_projection_b.lesson_learned_eligibility,
                "policy_budget_redaction": "EUR 3,200" not in json.dumps(
                    {
                        "retrieval": retrieval_output,
                        "policy": evidence_resolution.to_dict(),
                    },
                    ensure_ascii=False,
                ),
                "golden_retrieval_results": retrieval_equivalent,
                "golden_experience_retrieval_results": experience_retrieval_equivalent,
            },
        },
    }

    result_path = output_root / "result.json"
    result_path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote MVP result: {result_path}")
    print(f"Wrote Publication Unit: {pu_path}")
    print(f"Wrote Derived Projection: {projection_path}")
    print(f"Wrote Experience Projection: {experience_projection_path}")
    print(f"Delete/Rebuild semantic hash equal: {hash_a == hash_b}")
    print(
        "Delete/Rebuild experience hash equal: "
        f"{experience_hash_a == experience_hash_b}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
