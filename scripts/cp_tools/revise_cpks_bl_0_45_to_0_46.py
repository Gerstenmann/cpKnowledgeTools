#!/usr/bin/env python3
"""
Materially revise CPKS-BL@0.45 into CPKS-BL@0.46 based on the cleaned
cp-wiki state of 2026-08-08.

Lifecycle performed:
- CPKS-BL@0.44 remains active and untouched.
- CPKS-BL@0.45 is moved to the local Development archive and changed to:
    status: withdrawn
    evidence_class: historical_evidence
- A new CPKS-BL@0.46 draft is created with:
    status: draft
    evidence_class: verified_current_state
    source_artifact: CPKS-BL@0.45

Material current-state corrections in 0.46:
- evidence_class coverage: all 39 active Managed Artifacts classified
  (38 active_constraint + active Baseline verified_current_state)
- four previously documented duplicate ID/version Development copies removed
- CPKS-SPEC-KM active version corrected to 0.20
- Managed Artifact Validator v3.2 report exists under Generated/Validation
  with 0 errors / 4 warnings / 36 info
- volatile Vault file counts are explicitly recorded only as point-in-time
  scan observations, not as activation invariants

The script preserves existing CU-01..CU-05 review markers. They remain for
Owner review and must be removed only in a later activation step.

Safety:
- --check is default
- --apply writes
- backups are created before mutation
- the post-change validator is run with --strict-exit
- automatic rollback occurs if validation fails
- no Git commit or push
"""

from __future__ import annotations

import argparse
import datetime as dt
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import Any

try:
    import yaml
except ImportError as exc:
    raise SystemExit(
        "PyYAML is required. Run with the cpKnowledgeTools .venv Python."
    ) from exc


DEFAULT_VAULT = Path("/Users/cp/Documents/cp-wiki")
DEFAULT_REPO = Path("/Users/cp/Developer/cpKnowledgeTools")
DEFAULT_BACKUP_ROOT = Path("/Users/cp/Backups/cp-wiki/Remediation")

VALIDATOR_REL = Path(
    "scripts/cp_wiki/validation/validate_cpwiki_managed_artifacts_v3_2.py"
)

SOURCE_REL = Path(
    "Development/cpKnowledgeSystem/Governance/Draft Baselines/"
    "CPKS-BL@0.45 cpKnowledgeSystem Authoritative Baseline.md"
)
ARCHIVE_045_REL = Path(
    "Development/cpKnowledgeSystem/Governance/Draft Baselines/Archive/"
    "CPKS-BL@0.45 cpKnowledgeSystem Authoritative Baseline.md"
)
TARGET_046_REL = Path(
    "Development/cpKnowledgeSystem/Governance/Draft Baselines/"
    "CPKS-BL@0.46 cpKnowledgeSystem Authoritative Baseline.md"
)
ACTIVE_REL = Path(
    "Systems/cpKnowledgeSystem/Governance/System Control/"
    "CPKS-BL cpKnowledgeSystem Authoritative Baseline.md"
)

REPORT_REL = Path(
    "Generated/Validation/"
    "20260808T013257+0200-managed-artifact-validation-v3-2.md"
)

VERIFICATION_DATE = "2026-08-08"
VERIFICATION_TIME = "2026-08-08T01:49+02:00"
PRE_REVISION_MARKDOWN_COUNT = 590
PRE_REVISION_JSON_COUNT = 30

ACTIVE_EVIDENCE = {
    "CPW-WP-001": "active_constraint",
    "GOV-P01": "active_constraint",
    "CPKS-SPEC-ARCH-INT": "active_constraint",
    "CPKS-SPEC-ARCH": "active_constraint",
    "CPKS-SPEC-KM": "active_constraint",
    "CPKS-SPEC-KM-PU": "active_constraint",
    "CPKS-SPEC-KM-VOC": "active_constraint",
    "CPKS-SPEC-MEM": "active_constraint",
    "CPKS-SPEC-KPR": "active_constraint",
    "CPKS-SPEC-VAL": "active_constraint",
    "CPKS-SPEC-SRC": "active_constraint",
    "CPKS-SPEC-SEC": "active_constraint",
    "CPKS-FWK-AIW": "active_constraint",
    "CPKS-FWK-ARCH": "active_constraint",
    "CPKS-DEC-011": "active_constraint",
    "CPKS-DEC-012": "active_constraint",
    "CPKS-DEC-013": "active_constraint",
    "CPKS-DEC-015": "active_constraint",
    "CPKS-DEC-016": "active_constraint",
    "CPKS-DEC-017": "active_constraint",
    "CPKS-DEC-018": "active_constraint",
    "CPKS-DEC-019": "active_constraint",
    "CPKS-DEC-020": "active_constraint",
    "CPKS-DEC-021": "active_constraint",
    "CPKS-DEC-022": "active_constraint",
    "CPKS-DEC-023": "active_constraint",
    "CPKS-DEC-024": "active_constraint",
    "CPKS-DEC-025": "active_constraint",
    "CPKS-DEC-026": "active_constraint",
    "CPKS-DEC-027": "active_constraint",
    "CPKS-POL-GOV-AUTH": "active_constraint",
    "CPKS-SPEC-ART": "active_constraint",
    "CPKS-SPEC-HGI": "active_constraint",
    "CPKS-SPEC-PROC": "active_constraint",
    "CPKS-SPEC-WP": "active_constraint",
    "CPW-SPEC-VLT": "active_constraint",
    "CPKS-BL": "verified_current_state",
    "CPKT-SPEC-ARCH": "active_constraint",
    "CPKS-TPL-KM-PU": "active_constraint",
}

assert len(ACTIVE_EVIDENCE) == 39


class RevisionError(RuntimeError):
    pass


def split_frontmatter(text: str) -> tuple[str, str]:
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        raise RevisionError("Expected YAML frontmatter.")
    for idx in range(1, len(lines)):
        if lines[idx].strip() == "---":
            return "".join(lines[1:idx]), "".join(lines[idx + 1:])
    raise RevisionError("Unclosed YAML frontmatter.")


def parse_frontmatter(text: str) -> dict[str, Any]:
    raw, _ = split_frontmatter(text)
    data = yaml.safe_load(raw) or {}
    if not isinstance(data, dict):
        raise RevisionError("Frontmatter must be a mapping.")
    return data


def set_scalar(text: str, field: str, value: str, *, quote: bool = False) -> str:
    raw, body = split_frontmatter(text)
    rendered = f'"{value}"' if quote else value
    pattern = re.compile(rf"(?m)^{re.escape(field)}:[^\n]*$")
    if not pattern.search(raw):
        raise RevisionError(f"Missing expected frontmatter field: {field}")
    raw = pattern.sub(f"{field}: {rendered}", raw, count=1)
    return f"---\n{raw.rstrip()}\n---\n{body}"


def ensure_list_item(text: str, field: str, item: str) -> str:
    """Ensure a scalar item exists in a top-level YAML list, preserving formatting."""
    raw, body = split_frontmatter(text)
    lines = raw.splitlines()

    field_index = None
    for i, line in enumerate(lines):
        if re.match(rf"^{re.escape(field)}\s*:\s*$", line):
            field_index = i
            break

    if field_index is None:
        raise RevisionError(f"Missing expected top-level list field: {field}")

    # Determine the extent of the YAML block belonging to this field.
    end = field_index + 1
    while end < len(lines):
        line = lines[end]
        if line and not line[0].isspace():
            break
        end += 1

    block = lines[field_index + 1:end]

    # Accept standard YAML list indentation such as "- value" or "  - value".
    existing = []
    indent = "  "
    for line in block:
        m = re.match(r"^(\s*)-\s*(.*?)\s*$", line)
        if m:
            indent = m.group(1)
            existing.append(m.group(2))

    if item not in existing:
        lines.insert(end, f"{indent}- {item}")

    new_raw = "\n".join(lines)
    return f"---\n{new_raw.rstrip()}\n---\n{body}"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RevisionError(
            f"{label}: expected exactly one occurrence, found {count}"
        )
    return text.replace(old, new, 1)


def replace_heading_section(
    text: str,
    start_heading: str,
    next_heading: str,
    replacement: str,
) -> str:
    start = text.find(start_heading)
    if start < 0:
        raise RevisionError(f"Section start not found: {start_heading}")
    end = text.find(next_heading, start + len(start_heading))
    if end < 0:
        raise RevisionError(f"Next section not found: {next_heading}")
    return text[:start] + replacement.rstrip() + "\n\n" + text[end:]


def replace_cu_block(text: str, cu_id: str, replacement: str) -> str:
    pattern = re.compile(
        rf"<!-- CONSOLIDATED-UPDATE {re.escape(cu_id)}\b.*?"
        rf"<!-- /CONSOLIDATED-UPDATE {re.escape(cu_id)} -->",
        flags=re.S,
    )
    matches = list(pattern.finditer(text))
    if len(matches) != 1:
        raise RevisionError(
            f"{cu_id}: expected exactly one CU block, found {len(matches)}"
        )
    return pattern.sub(replacement.rstrip(), text, count=1)


def assert_source_preconditions(vault: Path) -> None:
    source = vault / SOURCE_REL
    active = vault / ACTIVE_REL
    report = vault / REPORT_REL

    if not source.is_file():
        raise RevisionError(f"Source draft missing: {SOURCE_REL}")
    if not active.is_file():
        raise RevisionError(f"Active baseline missing: {ACTIVE_REL}")
    if not report.is_file():
        raise RevisionError(
            f"Required published validator report missing: {REPORT_REL}"
        )
    if (vault / TARGET_046_REL).exists():
        raise RevisionError(f"Target already exists: {TARGET_046_REL}")
    if (vault / ARCHIVE_045_REL).exists():
        raise RevisionError(f"Archive target already exists: {ARCHIVE_045_REL}")

    source_fm = parse_frontmatter(source.read_text(encoding="utf-8"))
    expected_source = {
        "document_type": "baseline",
        "baseline_id": "CPKS-BL",
        "version": "0.45",
        "status": "draft",
        "evidence_class": "verified_current_state",
        "source_artifact": "CPKS-BL@0.44",
    }
    for field, expected in expected_source.items():
        actual = source_fm.get(field)
        if str(actual) != expected:
            raise RevisionError(
                f"Source precondition {field}: actual={actual!r}, expected={expected!r}"
            )

    active_fm = parse_frontmatter(active.read_text(encoding="utf-8"))
    expected_active = {
        "document_type": "baseline",
        "baseline_id": "CPKS-BL",
        "version": "0.44",
        "status": "active",
        "evidence_class": "verified_current_state",
    }
    for field, expected in expected_active.items():
        actual = active_fm.get(field)
        if str(actual) != expected:
            raise RevisionError(
                f"Active precondition {field}: actual={actual!r}, expected={expected!r}"
            )


def build_withdrawn_045(source_text: str) -> str:
    text = source_text
    text = set_scalar(text, "status", "withdrawn")
    text = set_scalar(text, "evidence_class", "historical_evidence")
    text = set_scalar(text, "revised", VERIFICATION_DATE)
    text = set_scalar(text, "canonical_path", ARCHIVE_045_REL.as_posix())
    return text


SECTION_3 = f"""# 3. Verifikationsstand, Scope und Abdeckungsgrenzen

## 3.1 Revalidierungsstichtag

```yaml
verification_date: {VERIFICATION_DATE}
verification_time_reference: {VERIFICATION_TIME}
vault_root: /Users/cp/Documents/cp-wiki
access_mode: read_only
pre_revision_markdown_file_count: {PRE_REVISION_MARKDOWN_COUNT}
pre_revision_json_file_count: {PRE_REVISION_JSON_COUNT}
inventory_counts_are_point_in_time_observations: true
```

Die Dateizähler sind ausschließlich stichtagsbezogene Beobachtungen des unmittelbar vor dieser materiellen Revision ausgeführten `vault_info`-Scans. Sie sind keine fortlaufend konstant zu haltende Baseline-Invariante. Spätere Dateiänderungen, insbesondere durch Lifecycle-Schritte oder generierte Reports, ändern nicht rückwirkend die Aussage über diesen Verifikationszeitpunkt.

## 3.2 Geprüfter Scope

Direkt geprüft wurden mindestens:

- `vault_info` des Live-Vaults unmittelbar vor dieser Revision,
- sämtliche über `baseline_id: CPKS-BL` ermittelten konkreten Baseline-Fassungen,
- der globale Frontmatter-Statusbestand für `active`, `draft`, `proposed` und historische Statuswerte,
- der aktive Managed-Artifact-Bestand anhand des aktuellen Status- und Dokumenttypmodells,
- die aktuelle `evidence_class`-Belegung der aktiven Managed Artifacts,
- die aktive `CPKS-SPEC-ART@0.3` vollständig,
- das zuständige Instruction Template `Bestehenden Draft überarbeiten - aktualisiert.md`,
- der aktive Prozess `GOV-P01@0.3`,
- die aktive `CPKT-SPEC-ARCH@1.1`,
- der publizierte Managed-Artifact-Validatorreport `{REPORT_REL.as_posix()}`,
- der aktuelle `Generated/Validation/`-Bestand,
- die zuvor dokumentierte Repository-Readiness-Evidenz, soweit sie in `CPKT-SPEC-ARCH@1.1` als stichtagsbezogener Nachweis geführt wird.

## 3.3 Abdeckungsgrenzen

Nicht behauptet werden:

- eine vollständige inhaltliche Volltextrevalidierung aller Vault-Markdown-Dateien,
- eine vollständige fachliche Revalidierung sämtlicher aktiver Spezifikationsinhalte,
- eine unabhängige Repository-Neuinventur gegenüber dem in `CPKT-SPEC-ARCH@1.1` dokumentierten Readiness-Stand,
- bestandene Python-, Build-, Test-, Runtime- oder Netzwerkprüfungen außerhalb des Managed-Artifact-Validatorlaufs,
- eine über das konfigurierte Validatorinventar hinausgehende pauschale Konformitätsaussage für jede Datei des gesamten Vaults.

Der aktuelle Managed-Artifact-Validatorreport belegt für sein konfiguriertes Inventar 0 blockierende Fehler. Die vier Warnungen und 36 Informationen bleiben sichtbar und werden nicht als Fehlerfreiheit sämtlicher anderer System- oder Inhaltsbereiche umgedeutet.
"""


SECTION_4 = """# 4. Baseline-Identität und Lifecycle

## 4.1 Stabile Identität

```yaml
baseline_id: CPKS-BL
former_ids:
  - CPKS-BASELINE
```

## 4.2 Aktive Ausgangsfassung

```yaml
reference: CPKS-BL@0.44
status: active
evidence_class: verified_current_state
actual_path: Systems/cpKnowledgeSystem/Governance/System Control/CPKS-BL cpKnowledgeSystem Authoritative Baseline.md
canonical_path: Systems/cpKnowledgeSystem/Governance/System Control/CPKS-BL cpKnowledgeSystem Authoritative Baseline.md
```

`CPKS-BL@0.44` bleibt durch diese Revision vollständig unverändert aktiv.

## 4.3 Konkrete Fassungen der Artefaktlinie

| Version | Status | Tatsächlicher beziehungsweise vorgesehener Pfad |
|---:|---|---|
| `0.1` | `superseded` | `Systems/cpKnowledgeSystem/Governance/Archive/Baselines/CPKS-BL@0.1 cpKnowledgeSystem Authoritative Baseline.md` |
| `0.2` | `superseded` | `Systems/cpKnowledgeSystem/Governance/Archive/Baselines/CPKS-BL@0.2 cpKnowledgeSystem Authoritative Baseline.md` |
| `0.3` | `superseded` | `Systems/cpKnowledgeSystem/Governance/Archive/Baselines/CPKS-BL@0.3 cpKnowledgeSystem Authoritative Baseline.md` |
| `0.4` | `withdrawn` | `Development/cpKnowledgeSystem/Governance/Draft Baselines/CPKS-BL@0.4 cpKnowledgeSystem Authoritative Baseline.md` |
| `0.41` | `superseded` | `Systems/cpKnowledgeSystem/Governance/Archive/Baselines/CPKS-BL@0.41 cpKnowledgeSystem Authoritative Baseline.md` |
| `0.42` | `superseded` | `Systems/cpKnowledgeSystem/Governance/Archive/Baselines/CPKS-BL@0.42 cpKnowledgeSystem Authoritative Baseline.md` |
| `0.43` | `superseded` | `Systems/cpKnowledgeSystem/Governance/Archive/Baselines/CPKS-BL@0.43 cpKnowledgeSystem Authoritative Baseline.md` |
| `0.44` | `active` | `Systems/cpKnowledgeSystem/Governance/System Control/CPKS-BL cpKnowledgeSystem Authoritative Baseline.md` |
| `0.45` | `withdrawn` | `Development/cpKnowledgeSystem/Governance/Draft Baselines/Archive/CPKS-BL@0.45 cpKnowledgeSystem Authoritative Baseline.md` |
| `0.46` | `draft` | `Development/cpKnowledgeSystem/Governance/Draft Baselines/CPKS-BL@0.46 cpKnowledgeSystem Authoritative Baseline.md` |

`CPKS-BL@0.45` war nie aktiv. Sie wird als unmittelbar vorausgehende Entwicklungsfassung mit `status: withdrawn` und `evidence_class: historical_evidence` erhalten. `CPKS-BL@0.46` ist die materiell aktualisierte aktuelle Folgefassung. `CPKS-BL@0.44` bleibt die genau eine aktive Fassung.

Die neue Version `0.46` liegt numerisch über allen früher verwendeten konkreten Versionen der Linie.
"""


SECTION_7 = f"""# 7. Physischer Vault-Zustand

## 7.1 Stichtagsbezogener Markdown- und JSON-Bestand

Der unmittelbar vor dieser Revision ausgeführte read-only `vault_info`-Scan wies aus:

```yaml
markdown_file_count: {PRE_REVISION_MARKDOWN_COUNT}
json_file_count: {PRE_REVISION_JSON_COUNT}
read_only: true
observation_time: {VERIFICATION_TIME}
```

Diese Zahlen dokumentieren ausschließlich den beobachteten Bestand zu diesem Zeitpunkt. Sie werden nicht als dauerhafte Aktivierungsinvariante behandelt. Die Erstellung, Archivierung oder Generierung weiterer Dateien kann die Zahlen unmittelbar ändern, ohne dadurch andere verifizierte Baseline-Aussagen automatisch materiell zu verändern.

Die in `CPKS-BL@0.44` dokumentierte Zahl von `470` Markdown-Dateien ist damit weiterhin nur ein historischer Scanwert eines früheren Zustands.

## 7.2 Statusbestand

Der aktuelle Frontmatter-Statusscan weist `44` Markdown-Dateien mit `status: active` nach.

Davon sind nach dem Managed-Artifact-Modell aus `CPKS-SPEC-ART@0.3`:

```yaml
active_status_hits: 44
formal_active_managed_artifacts: 39
active_non_managed_profile_or_corpus_manifests: 5
proposed_status_hits: 0
```

Die fünf aktiven Profile beziehungsweise Golden-Corpus-Manifeste werden nicht allein aufgrund ihres Status als Managed Artifacts im Sinn von `CPKS-SPEC-ART@0.3` gezählt.
"""


SECTION_8 = """# 8. Aktiver Managed-Artifact-Bestand

Die folgende Tabelle bildet die 39 aktuell direkt nachgewiesenen aktiven Managed Artifacts ab. Alle 39 führen inzwischen eine kontrollierte `evidence_class`: 38 aktive normative beziehungsweise steuernde Artefakte führen `active_constraint`; die aktive Authoritative Baseline führt ihrer dokumentbezogenen Current-State-Funktion entsprechend `verified_current_state`.

| Stabile ID | Klasse | Aktive Version | `evidence_class` | Tatsächlicher aktiver Pfad |
|---|---|---:|---|---|
| `CPW-WP-001` | work_package | `0.1` | `active_constraint` | `Development/cpKnowledgeSystem/Work Packages/CPW-WP-001 Konsolidierung und Zerlegung der cp-wiki Vault Specification.md` |
| `GOV-P01` | process | `0.3` | `active_constraint` | `Processes/Governance/GOV-P01 Governance Artifact Consolidation and Impact Review.md` |
| `CPKS-SPEC-ARCH-INT` | specification | `0.1` | `active_constraint` | `Systems/cpKnowledgeSystem/Architecture/Contracts/CPKS-SPEC-ARCH-INT Common Contract Envelope and Error Model Specification.md` |
| `CPKS-SPEC-ARCH` | specification | `0.1` | `active_constraint` | `Systems/cpKnowledgeSystem/Architecture/CPKS-SPEC-ARCH Context and Contract Architecture Specification.md` |
| `CPKS-SPEC-KM` | specification | `0.20` | `active_constraint` | `Systems/cpKnowledgeSystem/Architecture/CPKS-SPEC-KM Core Knowledge Model Specification.md` |
| `CPKS-SPEC-KM-PU` | specification | `0.1` | `active_constraint` | `Systems/cpKnowledgeSystem/Architecture/CPKS-SPEC-KM-PU Knowledge Object Publication Unit Specification.md` |
| `CPKS-SPEC-KM-VOC` | specification | `0.1` | `active_constraint` | `Systems/cpKnowledgeSystem/Architecture/CPKS-SPEC-KM-VOC Core Semantic Vocabulary Specification.md` |
| `CPKS-SPEC-MEM` | specification | `0.2` | `active_constraint` | `Systems/cpKnowledgeSystem/Architecture/Knowledge Delivery and Agent Interaction/CPKS-SPEC-MEM Delivery and Agent Interaction Contract Specification.md` |
| `CPKS-SPEC-KPR` | specification | `0.2` | `active_constraint` | `Systems/cpKnowledgeSystem/Architecture/Knowledge Lifecycle and Curation/CPKS-SPEC-KPR Knowledge Lifecycle and Curation Specification.md` |
| `CPKS-SPEC-VAL` | specification | `0.2` | `active_constraint` | `Systems/cpKnowledgeSystem/Architecture/Profiles/CPKS-SPEC-VAL Profile Contract Specification.md` |
| `CPKS-SPEC-SRC` | specification | `0.2` | `active_constraint` | `Systems/cpKnowledgeSystem/Architecture/Source and Processing/CPKS-SPEC-SRC Source and Evidence Boundary Contract Specification.md` |
| `CPKS-SPEC-SEC` | specification | `0.2` | `active_constraint` | `Systems/cpKnowledgeSystem/Architecture/Trust Policy and Assurance/CPKS-SPEC-SEC Trust, Policy and Assurance Contract Specification.md` |
| `CPKS-FWK-AIW` | framework | `0.4` | `active_constraint` | `Systems/cpKnowledgeSystem/Governance/CPKS-FWK-AIW AI Working Governance Framework.md` |
| `CPKS-FWK-ARCH` | framework | `0.1` | `active_constraint` | `Systems/cpKnowledgeSystem/Governance/CPKS-FWK-ARCH Globaler Architekturanker des cpKnowledgeSystem.md` |
| `CPKS-DEC-011` | decision_record | `1.1` | `active_constraint` | `Systems/cpKnowledgeSystem/Governance/Decisions/CPKS-DEC-011 Ablage der systemweiten Governance-Artefakte.md` |
| `CPKS-DEC-012` | decision_record | `1.2` | `active_constraint` | `Systems/cpKnowledgeSystem/Governance/Decisions/CPKS-DEC-012 Governance Artifact Consolidation and Dependency Management.md` |
| `CPKS-DEC-013` | decision_record | `1.0` | `active_constraint` | `Systems/cpKnowledgeSystem/Governance/Decisions/CPKS-DEC-013 Human Owner Direct Governance Changes and AI Control.md` |
| `CPKS-DEC-015` | decision_record | `1.1` | `active_constraint` | `Systems/cpKnowledgeSystem/Governance/Decisions/CPKS-DEC-015 Impact Metadata for Governance Change Artifacts.md` |
| `CPKS-DEC-016` | decision_record | `1.1` | `active_constraint` | `Systems/cpKnowledgeSystem/Governance/Decisions/CPKS-DEC-016 Vault Archive Placement and Retention Model.md` |
| `CPKS-DEC-017` | decision_record | `1.0` | `active_constraint` | `Systems/cpKnowledgeSystem/Governance/Decisions/CPKS-DEC-017 Kanonischer Prozessbestand, Prozesspakete und maschinelle Prozessermittlung.md` |
| `CPKS-DEC-018` | decision_record | `1.0` | `active_constraint` | `Systems/cpKnowledgeSystem/Governance/Decisions/CPKS-DEC-018 Human Governance Instructions and Mandatory AI Instruction Intake.md` |
| `CPKS-DEC-019` | decision_record | `1.0` | `active_constraint` | `Systems/cpKnowledgeSystem/Governance/Decisions/CPKS-DEC-019 Managed Artifact Naming, Versioning and Lifecycle Placement.md` |
| `CPKS-DEC-020` | decision_record | `1.0` | `active_constraint` | `Systems/cpKnowledgeSystem/Governance/Decisions/CPKS-DEC-020 Generated Reports, Execution Records and Script Lifecycle.md` |
| `CPKS-DEC-021` | decision_record | `0.2` | `active_constraint` | `Systems/cpKnowledgeSystem/Governance/Decisions/CPKS-DEC-021 Initialversion, Versionsfolge und Aktivierung verwalteter Entwicklungsartefakte.md` |
| `CPKS-DEC-022` | decision_record | `0.1` | `active_constraint` | `Systems/cpKnowledgeSystem/Governance/Decisions/CPKS-DEC-022 Reduktion und Zerlegung der cp-wiki Vault Specification.md` |
| `CPKS-DEC-023` | decision_record | `0.1` | `active_constraint` | `Systems/cpKnowledgeSystem/Governance/Decisions/CPKS-DEC-023 Minimale notwendige Ausführung und Ausgabe für Human Governance Instructions.md` |
| `CPKS-DEC-024` | decision_record | `0.2` | `active_constraint` | `Systems/cpKnowledgeSystem/Governance/Decisions/CPKS-DEC-024 Internes Projekt Kommunikations-Wissen verarbeiten und bereitstellen.md` |
| `CPKS-DEC-025` | decision_record | `1.0` | `active_constraint` | `Systems/cpKnowledgeSystem/Governance/Decisions/CPKS-DEC-025 Outside-in-Architekturrahmen und Neubewertung der Spezifikationsgliederung des cpKnowledgeSystem.md` |
| `CPKS-DEC-026` | decision_record | `1.0` | `active_constraint` | `Systems/cpKnowledgeSystem/Governance/Decisions/CPKS-DEC-026 Einführung der evidence_class für Managed Artifacts.md` |
| `CPKS-DEC-027` | decision_record | `1.0` | `active_constraint` | `Systems/cpKnowledgeSystem/Governance/Decisions/CPKS-DEC-027 Begrenzte Freigabe von SHA-256 für Profile und Conformance-Testartefakte.md` |
| `CPKS-POL-GOV-AUTH` | policy | `1.0` | `active_constraint` | `Systems/cpKnowledgeSystem/Governance/Policies/CPKS-POL-GOV-AUTH Governance Artifact Authoring Policy.md` |
| `CPKS-SPEC-ART` | specification | `0.3` | `active_constraint` | `Systems/cpKnowledgeSystem/Governance/Specifications/CPKS-SPEC-ART Managed Artifact Metadata and Validation Specification.md` |
| `CPKS-SPEC-HGI` | specification | `0.2` | `active_constraint` | `Systems/cpKnowledgeSystem/Governance/Specifications/CPKS-SPEC-HGI Human Governance Instruction Specification.md` |
| `CPKS-SPEC-PROC` | specification | `0.3` | `active_constraint` | `Systems/cpKnowledgeSystem/Governance/Specifications/CPKS-SPEC-PROC Process Description Specification.md` |
| `CPKS-SPEC-WP` | specification | `0.1` | `active_constraint` | `Systems/cpKnowledgeSystem/Governance/Specifications/CPKS-SPEC-WP Work Package Specification.md` |
| `CPW-SPEC-VLT` | specification | `0.4` | `active_constraint` | `Systems/cpKnowledgeSystem/Governance/Specifications/CPW-SPEC-VLT cp-wiki Vault Specification.md` |
| `CPKS-BL` | baseline | `0.44` | `verified_current_state` | `Systems/cpKnowledgeSystem/Governance/System Control/CPKS-BL cpKnowledgeSystem Authoritative Baseline.md` |
| `CPKT-SPEC-ARCH` | specification | `1.1` | `active_constraint` | `Systems/cpKnowledgeTools/Architecture/CPKT-SPEC-ARCH cpKnowledgeTools Architecture and Use Case Specification.md` |
| `CPKS-TPL-KM-PU` | template | `0.1` | `active_constraint` | `Templates/Knowledge/CPKS-TPL-KM-PU Knowledge Object Publication Unit Template.md` |
"""


CU_02 = f"""<!-- CONSOLIDATED-UPDATE CU-02
source: CPKS-SPEC-ART@0.3; aktueller aktiver Frontmatter-Bestand; {REPORT_REL.as_posix()}
basis: aktualisierter Nachweis der evidence_class-Abdeckung und der operativen Validatorunterstützung
verified_at: {VERIFICATION_TIME}
verification_scope: 39 formale aktive Managed Artifacts; Managed-Artifact-Validator v3.2 mit 191 inventarisierten Dateien -->

Von den 39 direkt nachgewiesenen aktiven Managed Artifacts führen aktuell `38`:

```yaml
evidence_class: active_constraint
```

Die aktive Authoritative Baseline `CPKS-BL@0.44` führt ihrer primären Current-State-Funktion entsprechend:

```yaml
evidence_class: verified_current_state
```

Damit besitzen alle 39 aktiven Managed Artifacts eine kontrollierte `evidence_class`.

Der publizierte Report:

```text
Generated/Validation/20260808T013257+0200-managed-artifact-validation-v3-2.md
```

weist für Managed Artifact Validator v3.2 auf Basis von `CPKS-SPEC-ART@0.3` und `CPKS-SPEC-PROC@0.3` nach:

```yaml
files_inventoried: 191
errors: 0
warnings: 4
info: 36
required_evidence_class_missing_errors: 0
```

Damit sind die in `CPKS-SPEC-ART@0.3` geforderte Validatorunterstützung und die Klassifikation der relevanten aktuellen Managed Artifacts technisch nachgewiesen. Der Report belegt keine pauschale fachliche oder technische Konformität außerhalb seines dokumentierten Scan- und Prüfprofils.

<!-- /CONSOLIDATED-UPDATE CU-02 -->"""


CU_03 = f"""<!-- CONSOLIDATED-UPDATE CU-03
source: aktueller Live-Vault-Bestand; {REPORT_REL.as_posix()}; CPKS-SPEC-ART@0.3 Abschnitt 5.2
basis: Revalidierung der zuvor dokumentierten parallelen ID-/Versionskonflikte nach Hygiene-Bereinigung
verified_at: {VERIFICATION_TIME}
verification_scope: aktuelles Managed-Artifact-Validatorinventar und direkter Baseline-/Artefaktlinienabgleich -->

## 14.1 Bereinigter Duplicate-Stand

Die in `CPKS-BL@0.45` dokumentierten vier parallelen ID-/Versionskonflikte:

- `CPW-SPEC-VLT@0.4`,
- `CPKS-DEC-022@0.1`,
- `CPKS-SPEC-WP@0.1`,
- `CPW-WP-001@0.1`

sind im aktuellen Bestand nicht mehr vorhanden. Die redundanten Development-Fassungen wurden entfernt; die jeweils maßgeblichen aktuellen Fassungen bleiben bestehen.

Der Managed-Artifact-Validator v3.2 meldet aktuell keine Fehler der Klassen:

```text
duplicate_stable_id_and_version
parallel_canonical_version
multiple_active_versions
```

Damit besteht für diese vier Linien kein offener Duplicate-Blocker mehr.

<!-- /CONSOLIDATED-UPDATE CU-03 -->"""


SECTION_17 = f"""# 17. Aktueller Systemstatus

| Bereich | Verifizierter Status | Baseline-Aussage |
|---|---|---|
| cp-wiki | aktiv; Pre-Revision-Scan mit {PRE_REVISION_MARKDOWN_COUNT} Markdown-Dateien und {PRE_REVISION_JSON_COUNT} JSON-Dateien | menschlich kontrollierte kanonische Wissens- und Governance-Schicht; Dateizähler sind stichtagsbezogene Beobachtungen |
| Authoritative Baseline | `CPKS-BL@0.44 active`; `CPKS-BL@0.45 withdrawn`; dieser Draft `CPKS-BL@0.46 draft` | `0.44` bleibt aktiv, `0.46` ist die aktuelle nicht verbindliche Folgefassung |
| Governance Authoring Policy | `CPKS-POL-GOV-AUTH@1.0 active` | aktive Governance-Regelbasis |
| Managed Artifact Specification | `CPKS-SPEC-ART@0.3 active` | aktuelle Metadaten-, Versions-, Evidenz- und Validatorregelbasis |
| Process Description Specification | `CPKS-SPEC-PROC@0.3 active` | aktiver Prozessvertrag |
| Work Package Specification | `CPKS-SPEC-WP@0.1 active` | aktiver Work-Package-Vertrag; keine parallele gleichversionierte Development-Fassung mehr nachgewiesen |
| Human Governance Instruction Specification | `CPKS-SPEC-HGI@0.2 active` | aktive HGI-Regelbasis |
| cp-wiki Vault Specification | `CPW-SPEC-VLT@0.4 active` | aktive Vault-Spezifikation; keine parallele gleichversionierte Development-Fassung mehr nachgewiesen |
| Governance-Prozess | `GOV-P01@0.3 active` | zuständiger Prozess für Governance-Konsolidierung und Impact Review |
| Globaler Architekturanker | `CPKS-FWK-ARCH@0.1 active` | aktiver systemweiter Architekturrahmen |
| Systemarchitektur-Verträge | aktiv | aktive Contract-, Source-, Knowledge-, Lifecycle-, Policy-, Delivery- und Profile-Spezifikationen vorhanden |
| cpKnowledgeTools Architecture | `CPKT-SPEC-ARCH@1.1 active` | aktive component-wide Architektur; vollständiger Vertical Slice im dokumentierten Repo-Stand noch nicht nachgewiesen |
| Managed-Artifact-Validator gegen ART 0.3 | nachgewiesen | Validator v3.2; publizierter Report mit `0 errors`, `4 warnings`, `36 info` |
| `evidence_class`-Abdeckung aktiver Managed Artifacts | vollständig | `39/39` klassifiziert: `38 active_constraint`, `1 verified_current_state` |
| aktuelle `proposed` Managed Artifacts | keine nachgewiesen | globaler `status: proposed`-Scan leer |
"""


SECTION_18 = f"""# 18. Maschinenlesbare Kurzfassung

```yaml
verification:
  date: "{VERIFICATION_DATE}"
  time_reference: "{VERIFICATION_TIME}"
  vault_root: /Users/cp/Documents/cp-wiki
  access: read_only
  pre_revision_markdown_files: {PRE_REVISION_MARKDOWN_COUNT}
  pre_revision_json_files: {PRE_REVISION_JSON_COUNT}
  inventory_counts_are_point_in_time_observations: true
  active_status_hits: 44
  active_managed_artifacts: 39
  active_non_managed_profile_or_corpus_manifests: 5
  current_proposed_hits: 0
  current_art_0_3_validator_report_found: true
  current_art_0_3_validator_report: {REPORT_REL.as_posix()}
  managed_artifact_validator_version: "3.2"
  managed_artifact_validator_errors: 0
  managed_artifact_validator_warnings: 4
  managed_artifact_validator_info: 36
  vault_wide_conformance_claim: false

baseline:
  stable_id: CPKS-BL
  former_ids:
    - CPKS-BASELINE
  active_version: "0.44"
  active_status: active
  active_evidence_class: verified_current_state
  previous_development_draft:
    version: "0.45"
    status: withdrawn
    evidence_class: historical_evidence
    canonical_path: Development/cpKnowledgeSystem/Governance/Draft Baselines/Archive/CPKS-BL@0.45 cpKnowledgeSystem Authoritative Baseline.md
  current_follow_draft:
    version: "0.46"
    status: draft
    evidence_class: verified_current_state
    source_artifact: CPKS-BL@0.45
    canonical_path: Development/cpKnowledgeSystem/Governance/Draft Baselines/CPKS-BL@0.46 cpKnowledgeSystem Authoritative Baseline.md

active_governance:
  policy: CPKS-POL-GOV-AUTH@1.0
  ai_working_framework: CPKS-FWK-AIW@0.4
  architecture_framework: CPKS-FWK-ARCH@0.1
  managed_artifact_specification: CPKS-SPEC-ART@0.3
  hgi_specification: CPKS-SPEC-HGI@0.2
  process_specification: CPKS-SPEC-PROC@0.3
  work_package_specification: CPKS-SPEC-WP@0.1
  vault_specification: CPW-SPEC-VLT@0.4
  governance_process: GOV-P01@0.3

active_decisions:
  - CPKS-DEC-011@1.1
  - CPKS-DEC-012@1.2
  - CPKS-DEC-013@1.0
  - CPKS-DEC-015@1.1
  - CPKS-DEC-016@1.1
  - CPKS-DEC-017@1.0
  - CPKS-DEC-018@1.0
  - CPKS-DEC-019@1.0
  - CPKS-DEC-020@1.0
  - CPKS-DEC-021@0.2
  - CPKS-DEC-022@0.1
  - CPKS-DEC-023@0.1
  - CPKS-DEC-024@0.2
  - CPKS-DEC-025@1.0
  - CPKS-DEC-026@1.0
  - CPKS-DEC-027@1.0

active_system_architecture:
  - CPKS-SPEC-ARCH@0.1
  - CPKS-SPEC-ARCH-INT@0.1
  - CPKS-SPEC-SRC@0.2
  - CPKS-SPEC-KM@0.20
  - CPKS-SPEC-KM-VOC@0.1
  - CPKS-SPEC-KM-PU@0.1
  - CPKS-SPEC-KPR@0.2
  - CPKS-SPEC-SEC@0.2
  - CPKS-SPEC-MEM@0.2
  - CPKS-SPEC-VAL@0.2
  - CPKS-TPL-KM-PU@0.1

evidence_class_coverage:
  active_managed_artifacts: 39
  active_constraint: 38
  verified_current_state: 1
  missing: 0

managed_artifact_integrity:
  duplicate_stable_id_and_version_errors: 0
  parallel_canonical_version_errors: 0
  multiple_active_version_errors: 0

cp_knowledge_tools:
  architecture: CPKT-SPEC-ARCH@1.1
  architecture_status: active
  architecture_evidence_class: active_constraint
  repository_scan_date: "2026-08-07"
  repository_root: /Users/cp/Developer/cpKnowledgeTools
  repository_branch: main
  repository_head: 9f48303a879bbe0257ced6e8049c5664a2eac4dd
  repository_working_tree_clean: true
  repository_file_count: 1497
  full_source_to_knowledge_vertical_slice_implemented: not_verified

open_consolidation_findings:
  cpkt_spec_arch_internal_lifecycle_wording_conflict: true
  hgi_instruction_template_path_inconsistency: true
  validator_warnings_remaining: 4
```
"""


SECTION_19 = """# 19. Review- und Aktivierungsgrenze

Dieser Draft ist als Review-Artefakt verwendbar, aber nicht als Nachweis einer abgeschlossenen Aktivierung.

Vor einer späteren Aktivierung sind mindestens erneut zu prüfen:

1. ob `CPKS-BL@0.44` weiterhin die genau eine aktive Fassung ist,
2. ob `CPKS-BL@0.46` weiterhin die genau eine aktuelle Draft- oder Proposed-Fassung ist,
3. ob der aktuelle Managed-Artifact-Validatorlauf weiterhin keine blockierenden Fehler meldet,
4. ob die vollständige `evidence_class`-Abdeckung der 39 aktiven Managed Artifacts weiterhin besteht,
5. ob alle als aktuell geführten stabilen und versionsgebundenen Referenzen weiterhin auflösbar sind,
6. ob seit diesem Revalidierungsstichtag neue materielle Governance-, Lifecycle- oder Systemzustandsänderungen eingetreten sind,
7. ob alle temporären `CONSOLIDATED-UPDATE`-Markierungen nach Owner-Prüfung aus der freizugebenden Fassung entfernt wurden.

Eine Änderung bloßer stichtagsbezogener Inventarzähler wie der Gesamtzahl von Markdown- oder JSON-Dateien ist für sich allein kein Nachweis einer materiellen Änderung der übrigen Baseline-Aussagen. Maßgeblich ist, ob sich ein in der Baseline geführter Governance-, Lifecycle-, Architektur-, Implementierungs- oder sonstiger materieller Current-State-Befund geändert hat.

Erst ein gesonderter Aktivierungsauftrag darf Lifecycle-, Approval-, Supersession-, Archiv- oder aktive Pfadänderungen ausführen.
"""


SECTION_20 = """# 20. Kurzform

> `CPKS-BL@0.44` bleibt die aktive Authoritative Baseline. Der aktuelle Folge-Draft `CPKS-BL@0.46` konsolidiert den inzwischen bereinigten Managed-Artifact-Zustand: 39 formale aktive Managed Artifacts sind vollständig mit `evidence_class` klassifiziert, die zuvor dokumentierten vier parallelen ID-/Versionskonflikte sind beseitigt, `CPKS-SPEC-KM@0.20` ist die aktive Core-Knowledge-Model-Fassung und Managed Artifact Validator v3.2 weist im publizierten Report `0` Fehler, `4` Warnungen und `36` Informationen aus. Die unmittelbar vorausgehende Draft-Fassung `CPKS-BL@0.45` war nie aktiv und wird als `withdrawn` mit `historical_evidence` erhalten. Stichtagsbezogene Vault-Dateizähler dienen ausschließlich als Scanbeobachtung und nicht als dauerhafte Aktivierungsinvariante. Offene Konsolidierungsbefunde, insbesondere die dokumentinterne Lifecycle-Sprache von `CPKT-SPEC-ARCH@1.1` und die HGI-Template-Pfadinkonsistenz, bleiben sichtbar und werden durch diese Baseline nicht eigenmächtig korrigiert.
"""


def build_new_046(source_text: str) -> str:
    text = source_text

    # Frontmatter identity and provenance.
    text = set_scalar(text, "version", "0.46", quote=True)
    text = set_scalar(text, "created", VERIFICATION_DATE)
    text = set_scalar(text, "revised", VERIFICATION_DATE)
    text = set_scalar(text, "source_artifact", "CPKS-BL@0.45")
    text = set_scalar(text, "canonical_path", TARGET_046_REL.as_posix())

    # Add predecessor draft to references while preserving the existing YAML style.
    text = ensure_list_item(text, "references", "CPKS-BL@0.45")

    # Intro / purpose.
    text = replace_once(
        text,
        "Diese Datei ist der nicht verbindliche Folge-Draft `CPKS-BL@0.45`.",
        "Diese Datei ist der nicht verbindliche Folge-Draft `CPKS-BL@0.46`.",
        "intro version",
    )
    text = replace_once(
        text,
        "Diese Folgefassung konsolidiert den am 7. August 2026 gegen den über den read-only Connector erreichbaren Live-Vault verifizierten aktuellen systemweiten Zustand des `cpKnowledgeSystem`, soweit dieser für die Authoritative Baseline ausreichend belegt ist.",
        "Diese Folgefassung konsolidiert den bis zum 8. August 2026 gegen den über den read-only Connector erreichbaren Live-Vault verifizierten aktuellen systemweiten Zustand des `cpKnowledgeSystem`, einschließlich der inzwischen abgeschlossenen Managed-Artifact-Hygiene, evidence_class-Klassifikation und Validator-v3.2-Revalidierung, soweit dieser Zustand für die Authoritative Baseline ausreichend belegt ist.",
        "purpose verification date",
    )
    text = text.replace(
        "- den aktuellen physischen Markdown-Bestand des Vaults,",
        "- stichtagsbezogene physische Vault-Inventarbeobachtungen,",
    )

    # Whole sections.
    text = replace_heading_section(
        text,
        "# 3. Verifikationsstand, Scope und Abdeckungsgrenzen",
        "# 4. Baseline-Identität und Lifecycle",
        SECTION_3,
    )
    text = replace_heading_section(
        text,
        "# 4. Baseline-Identität und Lifecycle",
        "# 5. Systemidentität und primäre Komponenten",
        SECTION_4,
    )
    text = replace_heading_section(
        text,
        "# 7. Physischer Vault-Zustand",
        "# 8. Aktiver Managed-Artifact-Bestand",
        SECTION_7,
    )
    text = replace_heading_section(
        text,
        "# 8. Aktiver Managed-Artifact-Bestand",
        "# 9. Drift gegenüber `CPKS-BL@0.44`",
        SECTION_8,
    )

    # Historical drift wording about the volatile file count.
    text = text.replace(
        "- die physische Markdown-Zahl `470` ist auf `592` fortgeschritten.",
        "- die in `CPKS-BL@0.44` dokumentierte Markdown-Zahl `470` ist ein historischer Scanwert; neuere stichtagsbezogene `vault_info`-Scans weisen andere Werte aus und werden nicht als dauerhafte Bestandsinvariante interpretiert.",
    )

    # CU-02 and CU-03 now represent the current cleaned state.
    text = replace_cu_block(text, "CU-02", CU_02)
    text = replace_cu_block(text, "CU-03", CU_03)

    # Section 15 explicit cleanup consequences.
    text = text.replace(
        "- Die vier in Abschnitt 14.1 dokumentierten parallelen ID-/Versionskonflikte bleiben offen und werden durch diesen Draft nicht bereinigt.\n- Die aktuelle ART-0.3-Validator- und `evidence_class`-Revalidierung bleibt offen; deshalb wird keine vollständige Konformität behauptet.",
        "- Die vier zuvor dokumentierten parallelen ID-/Versionskonflikte sind bereinigt; der aktuelle Validator weist hierfür keine blockierenden Duplicate- oder Parallelversion-Befunde mehr aus.\n- Die ART-0.3-Validatorunterstützung und die `evidence_class`-Klassifikation der aktiven Managed Artifacts sind technisch nachgewiesen. Die vier verbleibenden Validatorwarnungen bleiben nicht blockierende Review- beziehungsweise Legacy-Befunde.",
    )

    # Baseline history.
    text = text.replace(
        "`CPKS-BL@0.4` wurde nie aktiviert und ist aktuell `withdrawn`. Sein historischer Inhalt ist keine Current-State-Quelle.",
        "`CPKS-BL@0.4` und `CPKS-BL@0.45` wurden nie aktiviert und sind `withdrawn`. `CPKS-BL@0.45` ist die unmittelbar vorausgehende Entwicklungsfassung dieses Drafts und wird mit `evidence_class: historical_evidence` als Provenienz erhalten. Historische Draft-Inhalte sind keine Current-State-Quelle.",
    )

    text = replace_heading_section(
        text,
        "# 17. Aktueller Systemstatus",
        "# 18. Maschinenlesbare Kurzfassung",
        SECTION_17,
    )
    text = replace_heading_section(
        text,
        "# 18. Maschinenlesbare Kurzfassung",
        "# 19. Review- und Aktivierungsgrenze",
        SECTION_18,
    )
    text = replace_heading_section(
        text,
        "# 19. Review- und Aktivierungsgrenze",
        "# 20. Kurzform",
        SECTION_19,
    )
    # Section 20 is the last section.
    start = text.find("# 20. Kurzform")
    if start < 0:
        raise RevisionError("Section 20 not found.")
    text = text[:start] + SECTION_20.rstrip() + "\n"

    # CU markers must remain for later activation.
    for cu in ("CU-01", "CU-02", "CU-03", "CU-04", "CU-05"):
        if text.count(f"<!-- CONSOLIDATED-UPDATE {cu}") != 1:
            raise RevisionError(f"{cu} opening marker not exactly once after revision.")
        if text.count(f"<!-- /CONSOLIDATED-UPDATE {cu} -->") != 1:
            raise RevisionError(f"{cu} closing marker not exactly once after revision.")

    # Known stale blocker assertions must be absent from current 0.46.
    forbidden = [
        "Bei `22` aktiven Managed Artifacts ist im Frontmatter keine `evidence_class` geführt.",
        "kein aktuell nachgewiesener vollständiger ART-0.3-Validatorreport",
        "current_art_0_3_validator_report_found: false",
        "evidence_class_missing_on_active_managed_artifacts: 22",
        "CPKS-SPEC-KM` | specification | `0.2`",
    ]
    for item in forbidden:
        if item in text:
            raise RevisionError(f"Stale current-state assertion remains: {item}")

    return text


def validator_command(repo: Path, vault: Path) -> list[str]:
    cmd = [
        str(repo / ".venv/bin/python"),
        str(repo / VALIDATOR_REL),
        "--vault",
        str(vault),
        "--strict-exit",
    ]
    # Publish only when the patched validator supports the option.
    validator_text = (repo / VALIDATOR_REL).read_text(encoding="utf-8")
    if "--publish-report" in validator_text:
        cmd.append("--publish-report")
    return cmd


def run_validator(repo: Path, vault: Path) -> subprocess.CompletedProcess[str]:
    python_exe = repo / ".venv/bin/python"
    validator = repo / VALIDATOR_REL
    if not python_exe.is_file():
        raise RevisionError(f"Python environment not found: {python_exe}")
    if not validator.is_file():
        raise RevisionError(f"Validator not found: {validator}")
    return subprocess.run(
        validator_command(repo, vault),
        cwd=str(repo),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )


def backup(vault: Path, source: Path, backup_dir: Path) -> None:
    dst = backup_dir / "vault_before" / source.relative_to(vault)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, dst)


def rollback(vault: Path, backup_dir: Path) -> None:
    source_backup = backup_dir / "vault_before" / SOURCE_REL
    source = vault / SOURCE_REL

    # Remove created/moved results.
    for rel in (TARGET_046_REL, ARCHIVE_045_REL):
        path = vault / rel
        if path.exists():
            path.unlink()

    source.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_backup, source)


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--apply", action="store_true")
    parser.add_argument("--vault", type=Path, default=DEFAULT_VAULT)
    parser.add_argument("--repo", type=Path, default=DEFAULT_REPO)
    parser.add_argument("--backup-root", type=Path, default=DEFAULT_BACKUP_ROOT)
    args = parser.parse_args()

    if not args.apply:
        args.check = True

    vault = args.vault.expanduser().resolve()
    repo = args.repo.expanduser().resolve()
    if not vault.is_dir():
        raise RevisionError(f"Vault not found: {vault}")
    if not repo.is_dir():
        raise RevisionError(f"Repository not found: {repo}")

    assert_source_preconditions(vault)

    source_path = vault / SOURCE_REL
    source_text = source_path.read_text(encoding="utf-8")
    withdrawn_text = build_withdrawn_045(source_text)
    target_text = build_new_046(source_text)

    # Parse generated frontmatter before any write.
    withdrawn_fm = parse_frontmatter(withdrawn_text)
    target_fm = parse_frontmatter(target_text)

    if withdrawn_fm.get("status") != "withdrawn":
        raise RevisionError("Generated 0.45 is not withdrawn.")
    if withdrawn_fm.get("evidence_class") != "historical_evidence":
        raise RevisionError("Generated 0.45 evidence_class is not historical_evidence.")
    if str(target_fm.get("version")) != "0.46":
        raise RevisionError("Generated target version is not 0.46.")
    if target_fm.get("status") != "draft":
        raise RevisionError("Generated target is not draft.")
    if target_fm.get("evidence_class") != "verified_current_state":
        raise RevisionError("Generated target evidence_class is not verified_current_state.")
    if target_fm.get("source_artifact") != "CPKS-BL@0.45":
        raise RevisionError("Generated target source_artifact is not CPKS-BL@0.45.")

    print("CHECK PASSED.")
    print(f"Active baseline remains: {ACTIVE_REL}")
    print(f"Withdraw 0.45 to:        {ARCHIVE_045_REL}")
    print(f"Create new draft:        {TARGET_046_REL}")
    print("New version:             0.46")
    print("New evidence_class:      verified_current_state")
    print("Preserved CU markers:    CU-01 .. CU-05")
    print(
        "Current-state update:    39/39 active Managed Artifacts classified; "
        "duplicates cleared; validator v3.2 gate 0 errors"
    )

    if args.check:
        print("No Vault files changed.")
        return 0

    timestamp = dt.datetime.now().astimezone().strftime("%Y%m%dT%H%M%S%z")
    backup_dir = (
        args.backup_root.expanduser().resolve()
        / f"{timestamp}-cpks-bl-0.45-to-0.46"
    )
    backup_dir.mkdir(parents=True, exist_ok=False)
    backup(vault, source_path, backup_dir)

    try:
        archive_path = vault / ARCHIVE_045_REL
        target_path = vault / TARGET_046_REL
        archive_path.parent.mkdir(parents=True, exist_ok=True)

        archive_path.write_text(withdrawn_text, encoding="utf-8")
        target_path.write_text(target_text, encoding="utf-8")
        source_path.unlink()

        proc = run_validator(repo, vault)
        (backup_dir / "validator-output.txt").write_text(
            proc.stdout, encoding="utf-8"
        )
        print(proc.stdout, end="" if proc.stdout.endswith("\n") else "\n")
        if proc.returncode != 0:
            raise RevisionError(
                f"Post-revision validator failed with exit code {proc.returncode}."
            )

    except Exception:
        rollback(vault, backup_dir)
        raise

    print()
    print("REVISION APPLIED.")
    print(f"Backup: {backup_dir}")
    print(f"Withdrawn source: {ARCHIVE_045_REL}")
    print(f"Current draft:    {TARGET_046_REL}")
    print("CPKS-BL@0.44 remains active and unchanged.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RevisionError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
