#!/usr/bin/env python3
"""
Activate GOV-P01@0.3 and update the authoritative baseline to CPKS-BL@0.44.

Canonical script location:
  /Users/cp/Developer/cpKnowledgeTools/scripts/cp_wiki/governance/
  activate_gov_p01_v0_3.py

Default: dry run.
Use --apply to perform the controlled lifecycle transition.

The script:
- requires active CPKS-SPEC-ART@0.2 and CPKS-SPEC-PROC@0.3;
- requires GOV-P01@0.3 with status proposed;
- runs validator v3.1 before the change and requires 0 errors / 0 warnings;
- activates GOV-P01@0.3 under Processes/Governance/;
- creates and activates CPKS-BL@0.44;
- archives CPKS-BL@0.43 as superseded;
- runs validator v3.1 after the change;
- rolls back Vault changes if post-validation has errors or warnings;
- creates recovery files and reports outside the Vault;
- performs no Git commit or push.
"""

from __future__ import annotations

import argparse
import datetime as dt
import difflib
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from typing import Any

try:
    import yaml
except ImportError as exc:
    raise SystemExit(
        "PyYAML is required in the cpKnowledgeTools environment. "
        "Install it with: .venv/bin/python -m pip install PyYAML"
    ) from exc


VAULT = Path("/Users/cp/Documents/cp-wiki")
TOOLS = Path("/Users/cp/Developer/cpKnowledgeTools")
CANONICAL_SCRIPT = TOOLS / "scripts/cp_wiki/governance/activate_gov_p01_v0_3.py"
RUN_ROOT = Path(
    "/Users/cp/Library/Application Support/cpKnowledgeTools/Runs/cp-wiki/governance"
)

OWNER = "Christoph Peters"
ACTIVATION_DATE = "2026-07-27"

GOV_SOURCE_REL = Path(
    "Development/cpKnowledgeSystem/Governance/Draft Processes/"
    "GOV-P01@0.3 Governance Artifact Consolidation and Impact Review.md"
)
GOV_ACTIVE_REL = Path(
    "Processes/Governance/"
    "GOV-P01 Governance Artifact Consolidation and Impact Review.md"
)

BASELINE_ACTIVE_REL = Path(
    "Systems/cpKnowledgeSystem/Governance/System Control/"
    "CPKS-BL cpKnowledgeSystem Authoritative Baseline.md"
)
BASELINE_ARCHIVE_REL = Path(
    "Systems/cpKnowledgeSystem/Governance/Archive/Baselines/"
    "CPKS-BL@0.43 cpKnowledgeSystem Authoritative Baseline.md"
)

ART_ACTIVE_REL = Path(
    "Systems/cpKnowledgeSystem/Governance/Specifications/"
    "CPKS-SPEC-ART Managed Artifact Metadata and Validation Specification.md"
)
PROC_ACTIVE_REL = Path(
    "Systems/cpKnowledgeSystem/Governance/Specifications/"
    "CPKS-SPEC-PROC Process Description Specification.md"
)

VALIDATOR_CANDIDATES = [
    TOOLS / "scripts/cp_wiki/validation/"
    "validate_cpwiki_managed_artifacts_draft_v3_1.py",
    TOOLS / "scripts/cp_wiki/validation/validate_cpwiki_managed_artifacts_v3_1.py",
]


class ActivationError(RuntimeError):
    pass


def assert_canonical_script_location() -> None:
    actual = Path(__file__).resolve()
    expected = CANONICAL_SCRIPT.resolve()
    if actual != expected:
        raise ActivationError(
            "Script is not in its canonical repository location.\n"
            f"Expected: {expected}\n"
            f"Actual:   {actual}"
        )


def split_frontmatter(text: str) -> tuple[str, str]:
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        raise ActivationError("Missing YAML frontmatter.")
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            return "".join(lines[1:index]), "".join(lines[index + 1 :])
    raise ActivationError("Unclosed YAML frontmatter.")


def parse_frontmatter(raw: str) -> dict[str, Any]:
    try:
        parsed = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise ActivationError(f"Invalid YAML frontmatter: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ActivationError("Frontmatter must be a YAML mapping.")
    return parsed


def join_frontmatter(raw: str, body: str) -> str:
    return "---\n" + raw.rstrip() + "\n---\n" + body.lstrip("\n")


def replace_scalar(raw: str, field: str, value: str) -> str:
    pattern = re.compile(rf"(?m)^{re.escape(field)}:.*$")
    if not pattern.search(raw):
        raise ActivationError(f"Required scalar field missing: {field}")
    return pattern.sub(f"{field}: {value}", raw, count=1)


def remove_scalar(raw: str, field: str) -> str:
    return re.sub(rf"(?m)^{re.escape(field)}:.*\n?", "", raw, count=1)


def insert_after_scalar(raw: str, field: str, insertion: str) -> str:
    pattern = re.compile(rf"(?m)^({re.escape(field)}:.*)$")
    if not pattern.search(raw):
        raise ActivationError(f"Anchor field missing: {field}")
    return pattern.sub(r"\1\n" + insertion.rstrip(), raw, count=1)


def replace_yaml_list(raw: str, field: str, values: list[str]) -> str:
    lines = raw.splitlines()
    start = None
    end = None

    for index, line in enumerate(lines):
        if re.fullmatch(rf"{re.escape(field)}:\s*", line):
            start = index
            end = index + 1
            while end < len(lines):
                candidate = lines[end]
                if candidate.startswith("  - "):
                    end += 1
                    continue
                if candidate.startswith("  ") and candidate.strip():
                    end += 1
                    continue
                break
            break

    block = [f"{field}:"] + [f"  - {value}" for value in values]

    if start is None:
        raise ActivationError(f"YAML list field missing: {field}")

    return "\n".join(lines[:start] + block + lines[end:]) + "\n"


def list_values(frontmatter: dict[str, Any], field: str) -> list[str]:
    value = frontmatter.get(field)
    if value is None:
        return []
    if not isinstance(value, list):
        raise ActivationError(f"{field} must be a YAML list.")
    return [str(item) for item in value]


def unique(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value not in result:
            result.append(value)
    return result


def replace_section(
    body: str,
    start_heading: str,
    next_heading: str,
    replacement: str,
) -> str:
    start = body.find(start_heading)
    if start < 0:
        raise ActivationError(f"Section start not found: {start_heading}")
    end = body.find(next_heading, start + len(start_heading))
    if end < 0:
        raise ActivationError(f"Next section not found: {next_heading}")
    return body[:start] + replacement.rstrip() + "\n\n" + body[end:]


def replace_tail_section(
    body: str,
    start_heading: str,
    replacement: str,
) -> str:
    start = body.find(start_heading)
    if start < 0:
        raise ActivationError(f"Tail section not found: {start_heading}")
    return body[:start] + replacement.rstrip() + "\n"


def validate_identity(
    text: str,
    *,
    document_type: str,
    identity_field: str,
    identity: str,
    version: str,
    status: str,
    canonical_path: str,
) -> None:
    raw, _ = split_frontmatter(text)
    fm = parse_frontmatter(raw)
    expected = {
        "document_type": document_type,
        identity_field: identity,
        "version": version,
        "status": status,
        "canonical_path": canonical_path,
    }
    for field, wanted in expected.items():
        actual = str(fm.get(field) or "")
        if actual != wanted:
            raise ActivationError(f"{field} expected {wanted!r}, got {actual!r}")


def require_active_specification(
    path: Path,
    specification_id: str,
    version: str,
) -> None:
    if not path.is_file():
        raise ActivationError(f"Active specification missing: {path}")
    raw, _ = split_frontmatter(path.read_text(encoding="utf-8"))
    fm = parse_frontmatter(raw)
    expected = {
        "document_type": "specification",
        "specification_id": specification_id,
        "version": version,
        "status": "active",
        "canonical_path": path.relative_to(VAULT).as_posix(),
    }
    for field, wanted in expected.items():
        actual = str(fm.get(field) or "")
        if actual != wanted:
            raise ActivationError(
                f"{specification_id}: {field} expected {wanted!r}, got {actual!r}"
            )


def build_active_gov(source: str) -> str:
    raw, body = split_frontmatter(source)
    fm = parse_frontmatter(raw)

    expected = {
        "document_type": "process",
        "process_id": "GOV-P01",
        "version": "0.3",
        "status": "proposed",
        "canonical_path": GOV_SOURCE_REL.as_posix(),
    }
    for field, wanted in expected.items():
        actual = str(fm.get(field) or "")
        if actual != wanted:
            raise ActivationError(
                f"GOV-P01 {field} expected {wanted!r}, got {actual!r}"
            )

    raw = replace_scalar(raw, "status", "active")
    raw = replace_scalar(raw, "revised", ACTIVATION_DATE)
    raw = replace_scalar(raw, "canonical_path", GOV_ACTIVE_REL.as_posix())

    for field in ("approved_by", "approved_at", "effective_from"):
        raw = remove_scalar(raw, field)
    raw = insert_after_scalar(
        raw,
        "owner",
        "\n".join(
            [
                f"approved_by: {OWNER}",
                f'approved_at: "{ACTIVATION_DATE}"',
                f'effective_from: "{ACTIVATION_DATE}"',
            ]
        ),
    )

    fm_after = parse_frontmatter(raw)
    validated = [
        value
        for value in list_values(fm_after, "validated_against")
        if value != "CPKS-BL@0.43"
    ]
    validated.append("CPKS-BL@0.44")
    raw = replace_yaml_list(raw, "validated_against", unique(validated))

    active_callout = f"""# GOV-P01 – Governance Artifact Consolidation and Impact Review

> [!IMPORTANT]
> Diese Datei ist der aktive Governance-Prozess `GOV-P01@0.3`.
>
> Freigegeben durch {OWNER} am {ACTIVATION_DATE}; wirksam ab {ACTIVATION_DATE}.
>
> Die nie aktivierte Fassung `GOV-P01@0.2` bleibt als `withdrawn` im Development-Archiv erhalten."""

    h1_end = body.find("\n", body.find("# GOV-P01"))
    if h1_end < 0:
        raise ActivationError("GOV-P01 title heading not found.")
    next_section = body.find("## 1. Zweck", h1_end)
    if next_section < 0:
        raise ActivationError("GOV-P01 section 1 not found.")
    body = active_callout + "\n\n" + body[next_section:]

    body = body.replace(
        "target_artifact:\n"
        "  reference: GOV-P01@0.3\n"
        "  document_type: process\n"
        "  target_status: active\n"
        "  proposed_canonical_path: Processes/Governance/GOV-P01 Governance Artifact Consolidation and Impact Review.md",
        "target_artifact:\n"
        "  reference: CPKS-SPEC-ART@0.3\n"
        "  document_type: specification\n"
        "  target_status: draft\n"
        "  proposed_canonical_path: Development/cpKnowledgeSystem/Specifications/CPKS-SPEC-ART@0.3 Managed Artifact Metadata and Validation Specification.md",
        1,
    )
    body = body.replace(
        "| Baseline | `CPKS-BL@0.43` | aktueller systemweiter Governance-Zustand |",
        "| Baseline | `CPKS-BL@0.44` | aktueller systemweiter Governance-Zustand |",
        1,
    )

    activation_section = f"""## 12. Aktivierungsnachweis

`GOV-P01@0.3` wurde am {ACTIVATION_DATE} durch den System-Owner {OWNER} ausdrücklich freigegeben.

Für die Aktivierung wurden nachgewiesen:

- `CPKS-SPEC-ART@0.2` ist aktiv,
- `CPKS-SPEC-PROC@0.3` ist aktiv,
- Validator v3.1 meldete vor der Aktivierung keine Fehler und keine Warnungen,
- der macOS-, Git- und Obsidian-Dateinamen- und Linktest war erfolgreich,
- der Prozess liegt vollständig nach der aktiven Process Description Specification vor,
- der aktive Zielpfad und die erforderlichen Approval-Metadaten sind gesetzt,
- die Authoritative Baseline wird im selben kontrollierten Schritt auf `CPKS-BL@0.44` aktualisiert,
- `GOV-P01@0.2` bleibt als nie aktivierte, zurückgezogene Fassung historisch erhalten.

Die Aktivierung erzeugt keinen automatischen Git-Commit und keinen Push."""

    if "## 12. Aktivierungsnachweis" not in body:
        body = body.rstrip() + "\n\n" + activation_section + "\n"

    updated = join_frontmatter(raw, body)
    validate_identity(
        updated,
        document_type="process",
        identity_field="process_id",
        identity="GOV-P01",
        version="0.3",
        status="active",
        canonical_path=GOV_ACTIVE_REL.as_posix(),
    )
    return updated


def build_archived_baseline_043(source: str) -> str:
    raw, body = split_frontmatter(source)
    fm = parse_frontmatter(raw)

    expected = {
        "document_type": "baseline",
        "baseline_id": "CPKS-BL",
        "version": "0.43",
        "status": "active",
        "canonical_path": BASELINE_ACTIVE_REL.as_posix(),
    }
    for field, wanted in expected.items():
        actual = str(fm.get(field) or "")
        if actual != wanted:
            raise ActivationError(
                f"Baseline 0.43 {field} expected {wanted!r}, got {actual!r}"
            )

    raw = replace_scalar(raw, "status", "superseded")
    raw = replace_scalar(raw, "revised", ACTIVATION_DATE)
    raw = replace_scalar(
        raw,
        "canonical_path",
        BASELINE_ARCHIVE_REL.as_posix(),
    )

    callout = f"""> [!IMPORTANT]
> Diese Datei ist die historische, `superseded` Fassung `CPKS-BL@0.43`.
>
> Sie wurde am {ACTIVATION_DATE} durch `CPKS-BL@0.44` ersetzt.
>
> Ihr Inhalt dokumentiert den damaligen Systemzustand und wird nicht rückwirkend auf den Stand der Nachfolgefassung umgeschrieben."""

    start = body.find("> [!IMPORTANT]")
    end = body.find("# 1. Zweck")
    if start < 0 or end < 0:
        raise ActivationError("Baseline 0.43 callout boundaries not found.")
    body = body[:start] + callout + "\n\n" + body[end:]

    updated = join_frontmatter(raw, body)
    validate_identity(
        updated,
        document_type="baseline",
        identity_field="baseline_id",
        identity="CPKS-BL",
        version="0.43",
        status="superseded",
        canonical_path=BASELINE_ARCHIVE_REL.as_posix(),
    )
    return updated


def build_active_baseline_044(source: str) -> str:
    raw, body = split_frontmatter(source)
    fm = parse_frontmatter(raw)

    if (
        fm.get("document_type") != "baseline"
        or fm.get("baseline_id") != "CPKS-BL"
        or str(fm.get("version")) != "0.43"
        or fm.get("status") != "active"
    ):
        raise ActivationError("Active baseline is not CPKS-BL@0.43.")

    raw = replace_scalar(raw, "version", '"0.44"')
    raw = replace_scalar(raw, "revised", ACTIVATION_DATE)
    raw = replace_scalar(raw, "approved_at", f'"{ACTIVATION_DATE}"')
    raw = replace_scalar(raw, "effective_from", f'"{ACTIVATION_DATE}"')
    raw = replace_scalar(
        raw,
        "canonical_path",
        BASELINE_ACTIVE_REL.as_posix(),
    )

    raw = replace_yaml_list(raw, "supersedes", ["CPKS-BL@0.43"])

    fm_after = parse_frontmatter(raw)

    aligned = list_values(fm_after, "aligned_with")
    aligned.extend(["CPKS-SPEC-ART", "CPKS-SPEC-PROC", "GOV-P01"])
    raw = replace_yaml_list(raw, "aligned_with", unique(aligned))

    fm_after = parse_frontmatter(raw)
    validated = [
        value
        for value in list_values(fm_after, "validated_against")
        if value
        not in {
            "CPKS-SPEC-PROC@0.1",
            "CPKS-BL@0.43",
        }
    ]
    validated.extend(
        [
            "CPKS-SPEC-ART@0.2",
            "CPKS-SPEC-PROC@0.3",
            "GOV-P01@0.3",
        ]
    )
    raw = replace_yaml_list(raw, "validated_against", unique(validated))

    fm_after = parse_frontmatter(raw)
    references = [
        value
        for value in list_values(fm_after, "references")
        if value != "CPKS-SPEC-PROC@0.1"
    ]
    references.extend(
        [
            "CPKS-BL@0.43",
            "CPKS-SPEC-ART@0.2",
            "CPKS-SPEC-PROC@0.3",
            "GOV-P01@0.3",
        ]
    )
    raw = replace_yaml_list(raw, "references", unique(references))

    callout = f"""> [!IMPORTANT]
> Diese Datei ist die aktive systemweite Authoritative Baseline `CPKS-BL@0.44`.
>
> Sie ersetzt `CPKS-BL@0.43`.
>
> Die Vorgängerversion besitzt den Status `superseded` und wird versioniert unter `Systems/cpKnowledgeSystem/Governance/Archive/Baselines/` aufbewahrt.
>
> Diese Baseline bildet den nachgewiesenen Governance-Zustand nach Aktivierung von `CPKS-SPEC-ART@0.2`, `CPKS-SPEC-PROC@0.3` und `GOV-P01@0.3` ab."""

    start = body.find("> [!IMPORTANT]")
    end = body.find("# 1. Zweck")
    if start < 0 or end < 0:
        raise ActivationError("Baseline callout boundaries not found.")
    body = body[:start] + callout + "\n\n" + body[end:]

    section_9 = """# 9. Managed Artifacts und kompakte IDs

## 9.1 Kanonische Kern-IDs

| Artefakt | Kanonische stabile ID | Aktive Version |
|---|---|---:|
| Authoritative Baseline | `CPKS-BL` | `0.44` |
| Governance Artifact Authoring Policy | `CPKS-POL-GOV-AUTH` | `1.0` |
| AI Working Governance Framework | `CPKS-FWK-AIW` | `0.4` |
| Managed Artifact Metadata and Validation Specification | `CPKS-SPEC-ART` | `0.2` |
| Process Description Specification | `CPKS-SPEC-PROC` | `0.3` |
| Governance Artifact Consolidation and Impact Review | `GOV-P01` | `0.3` |
| Obsidian cp-wiki Vault Specification | `CPW-SPEC-VLT` | kein aktiver Stand |

`CPKS-SPEC-ART@0.2` und `CPKS-SPEC-PROC@0.3` sind aktive, verbindliche Spezifikationen.

## 9.2 Dateibenennung

Aktive Managed Artifacts:

```text
<stable_artifact_id> <title>.md
```

Nicht aktive konkrete Fassungen:

```text
<stable_artifact_id>@<version> <title>.md
```

Version und Status werden im Frontmatter geführt.

## 9.3 Maschinenidentität und Validierung

Die Maschinenidentität beruht mindestens auf:

```text
zulässiger Scanbereich
+
document_type
+
typabhängige stabile ID
+
version
+
status
```

Validator v3.1 implementiert die aktiven Regeln aus `CPKS-SPEC-ART@0.2` und `CPKS-SPEC-PROC@0.3`. Historische Acknowledgements unterdrücken nur konkret bestätigte Warnungen und Informationen; Integritätsfehler bleiben blockierend."""

    section_10 = """# 10. Aktueller Governance- und Prozessstand

## 10.1 Aktive Kernartefakte

| Artefakt | Version | Status | Kanonischer Pfad |
|---|---:|---|---|
| `CPKS-BL` | `0.44` | `active` | `Systems/cpKnowledgeSystem/Governance/System Control/CPKS-BL cpKnowledgeSystem Authoritative Baseline.md` |
| `CPKS-POL-GOV-AUTH` | `1.0` | `active` | `Systems/cpKnowledgeSystem/Governance/Policies/CPKS-POL-GOV-AUTH Governance Artifact Authoring Policy.md` |
| `CPKS-FWK-AIW` | `0.4` | `active` | `Systems/cpKnowledgeSystem/Governance/CPKS-FWK-AIW AI Working Governance Framework.md` |
| `CPKS-SPEC-ART` | `0.2` | `active` | `Systems/cpKnowledgeSystem/Governance/Specifications/CPKS-SPEC-ART Managed Artifact Metadata and Validation Specification.md` |
| `CPKS-SPEC-PROC` | `0.3` | `active` | `Systems/cpKnowledgeSystem/Governance/Specifications/CPKS-SPEC-PROC Process Description Specification.md` |

## 10.2 Aktive Decision Records

| Decision | Version | Gegenstand |
|---|---:|---|
| `CPKS-DEC-011` | `1.1` | Governance-Ablage und Registerprinzip |
| `CPKS-DEC-012` | `1.2` | Governance-Referenzen, Dependency Management und Artefaktermittlung |
| `CPKS-DEC-013` | `1.0` | Human Owner Direct Changes und AI Control |
| `CPKS-DEC-015` | `1.1` | Impact-Metadaten für Governance-Change-Artefakte |
| `CPKS-DEC-016` | `1.1` | Archivierungs-, History- und Aufbewahrungsmodell |
| `CPKS-DEC-017` | `1.0` | kanonischer Prozessbestand und maschinelle Prozessermittlung |
| `CPKS-DEC-018` | `1.0` | Human Governance Instructions und AI Instruction Intake |
| `CPKS-DEC-019` | `1.0` | Managed Artifact Naming, Versioning und Lifecycle Placement |
| `CPKS-DEC-020` | `1.0` | Reportablage, technische Run-Daten und Lifecycle ausführbarer Skripte |

## 10.3 Aktiver Governance-Prozess

```text
Processes/Governance/
GOV-P01 Governance Artifact Consolidation and Impact Review.md
```

```yaml
process_id: GOV-P01
version: "0.3"
status: active
```

`GOV-P01@0.3` ist der erste nach dem aktiven Prozessmodell geführte Governance-Prozess.

## 10.4 Historische Kernartefakte

Die früheren Baselines einschließlich `CPKS-BL@0.43`, frühere Framework- und Policy-Fassungen sowie historische Decisions bleiben in ihren lokalen Archive- und History-Bereichen versionsgebunden auflösbar.

Nie aktivierte Vorgänger-Drafts von `CPKS-SPEC-ART`, `CPKS-SPEC-PROC` und `GOV-P01` werden als `withdrawn` im jeweiligen Development-Archiv geführt."""

    section_11 = """# 11. Umsetzungsstand maßgeblicher Decisions

## 11.1 CPKS-DEC-012@1.2

Umgesetzt sind das hybride Referenzmodell, kompakte Kern-IDs, Aliasauflösung, lifecycle-weite Artefaktermittlung und der Managed-Artifact-Validator.

Offen bleibt die schrittweise Normalisierung weiterer fachlicher und historischer Artefaktklassen, soweit ein konkreter Nutzen besteht.

## 11.2 CPKS-DEC-015@1.1

Die technische Definition und Validierung von `affected_artifacts` ist in `CPKS-SPEC-ART@0.2` und Validator v3.1 umgesetzt. `GOV-P01@0.3` behandelt Impact-Kandidaten verbindlich.

Alte Change-Artefakte werden nicht pauschal rückwirkend modernisiert.

## 11.3 CPKS-DEC-016@1.1

Decision History, lokale Archive, geschlossene Development-Profile und historische Acknowledgements sind umgesetzt.

Eine aktive konsolidierte Vault Specification und weitere spezialisierte Archivierungsprozesse bleiben mögliche Folgearbeiten.

## 11.4 CPKS-DEC-017@1.0

Umgesetzt sind:

- aktive `CPKS-SPEC-PROC@0.3`,
- aktiver `GOV-P01@0.3`,
- maschinenlesbare Prozessidentität,
- aktiver Prozesspfad unter `Processes/Governance/`,
- Lifecycle-Regeln für Drafts, aktive und zurückgezogene Prozessfassungen.

Nicht alle vorhandenen Platzhalter unter `Processes/` sind bereits konforme aktive Prozesse. Sie bleiben außerhalb des Managed-Process-Bestands, bis sie konkret bearbeitet werden.

## 11.5 CPKS-DEC-018@1.0

Die abstrakten Intake- und Kontrollregeln sind in Policy und `GOV-P01@0.3` verankert.

Spezialisierte Templates oder technische Intake-Werkzeuge werden erst bei nachgewiesenem operativem Bedarf eingeführt.

## 11.6 CPKS-DEC-019@1.0

Kern-IDs, Dateinamen, Lifecycle-Zonen, Aliasmodell, Dateinamen-Normalisierung und Validatorunterstützung sind umgesetzt.

## 11.7 CPKS-DEC-020@1.0

Die kanonischen Repository-, Skript- und Runtime-Pfade sind aktiv. Technische Reports und Recovery-Daten liegen außerhalb des Vaults im festgelegten Runtime-Bereich."""

    section_16 = """# 16. Aktuelle Workstreams

## 16.1 CPKS-GOV – Governance und System Control

Prioritäten:

1. Validator v3.1 als operatives Kontrollwerkzeug pflegen.
2. `GOV-P01@0.3` im praktischen Einsatz erproben.
3. Nur bei konkretem Bedarf weitere Governance-Prozesse als Managed Processes einführen.
4. Die Vault Specification auf den aktiven Governance- und Managed-Artifact-Stand konsolidieren.
5. DEC-018-Folgeartefakte nur soweit operational erforderlich entwickeln.

## 16.2 CPWIKI – Vault

Prioritäten:

- Vault Specification konsolidieren,
- präfixfreie Zielstruktur abbilden,
- Managed-Artifact-, Archive-, History- und Acknowledgement-Regeln integrieren,
- physische Altbestände nur bei tatsächlichem Nutzen kontrolliert migrieren.

## 16.3 CPKT – cpKnowledgeTools

Prioritäten:

- Validator v3.1 und zugehörige Tests im Repository konsolidieren,
- tatsächlichen Repository-Stand und Architektur-Draft verifizieren,
- Generatoren und weitere Validatoren nur anhand konkreter Use Cases erweitern.

## 16.4 OCOS – OpenClaw OS

Prioritäten:

- Agentenrollen und Workspaces,
- Least Privilege,
- Context Packaging,
- kontrollierte Tool- und Write-back-Pfade,
- Nutzung der aktiven Governance-Verträge.

## 16.5 CPKS-MEM – Memory und Retrieval

Prioritäten:

- getrennte Knowledge-, Run- und Development-Kontexte,
- Provenienz,
- Sensitivity und Access Policy,
- reproduzierbare Indizes,
- keine konkurrierende Source of Truth."""

    section_17 = """# 17. Aktueller Systemstatus

| Bereich | Status | Baseline-Aussage |
|---|---|---|
| cp-wiki | aktiv, strukturell in Migration | menschlich kontrollierte Source of Truth |
| Governance Authoring Policy | aktiv | `CPKS-POL-GOV-AUTH@1.0` |
| Managed Artifact Specification | aktiv | `CPKS-SPEC-ART@0.2` |
| Process Description Specification | aktiv | `CPKS-SPEC-PROC@0.3` |
| Governance-Prozess | aktiv | `GOV-P01@0.3` |
| Managed Artifact Validation | operativ | Validator v3.1, historische Acknowledgements und getrennte Prüfprofile |
| Vault Specification | Draft | `CPW-SPEC-VLT@1.2` ist nicht aktiv |
| cpKnowledgeTools Run-Kontext | angelegt und genutzt | Run- und Development-Kontext getrennt |
| OpenClaw OS | experimentell bis vorproduktiv | keine unkontrollierte autonome Vault-Pflege |
| AI Instruction Intake | teilweise formalisiert | Mindestkontrollen in Policy und GOV-P01 aktiv |
| automatisches Write-back | nicht freigegeben | nur kontrollierte Änderung mit Prüfung und Befugnis |"""

    section_18 = """# 18. Status der ID-, Metadaten- und Validatorimplementierung

## 18.1 Konsolidierte Kern-IDs

```text
CPKS-POL-GOVERNANCE-AUTHORING → CPKS-POL-GOV-AUTH
CPKS-FWK-AI-WORKING           → CPKS-FWK-AIW
CPKS-BASELINE                 → CPKS-BL
CPWIKI-VAULT-SPEC             → CPW-SPEC-VLT
CPKS-SPEC-PROCESS-DESCRIPTION → CPKS-SPEC-PROC
```

Die Aliasabbildung wird aus verteilten `former_ids` reproduzierbar erzeugt.

## 18.2 Aktive technische Regelbasis

```yaml
metadata_specification:
  id: CPKS-SPEC-ART
  version: "0.2"
  status: active

process_specification:
  id: CPKS-SPEC-PROC
  version: "0.3"
  status: active

managed_artifact_validator:
  version: "3.1"
  status: operational
  last_activation_gate:
    errors: 0
    warnings: 0

governance_process:
  id: GOV-P01
  version: "0.3"
  status: active
```

## 18.3 Migrationsstand

```yaml
core_id_migration: completed
core_frontmatter_migration: completed
alias_model: operational
historical_acknowledgement_model: operational
broader_managed_artifact_normalization: on_demand
```

Eine Warnungsfreiheit historischer Bestände wird nicht durch rückwirkende Vollmigration erzwungen. Bereits geprüfte Legacy-Diagnosen können kontrolliert bestätigt werden; Integritätsfehler bleiben sichtbar."""

    section_20 = f"""# 20. Aktivierungsnachweis

`CPKS-BL@0.44` und `GOV-P01@0.3` wurden am {ACTIVATION_DATE} durch den Owner {OWNER} ausdrücklich freigegeben.

Für die gemeinsame Aktivierung wurden bestätigt:

- [x] `CPKS-SPEC-ART@0.2` ist aktiv
- [x] `CPKS-SPEC-PROC@0.3` ist aktiv
- [x] `GOV-P01@0.3` lag als vollständiger Proposal-Draft vor
- [x] Validator v3.1 meldete vor der Aktivierung 0 Fehler und 0 Warnungen
- [x] macOS-, Git- und Obsidian-Dateinamen- und Linktest erfolgreich
- [x] aktiver Prozesspfad festgelegt
- [x] Approval-Metadaten gesetzt
- [x] `CPKS-BL@0.43` wird als `superseded` archiviert
- [x] `CPKS-BL@0.44` bildet den neuen autoritativen Zustand ab
- [x] Post-Activation-Validierung ist Bestandteil des Aktivierungsskripts
- [x] Commit und Push bleiben getrennte nachgelagerte Handlungen"""

    section_21 = """# 21. Maschinenlesbare Kurzfassung

```yaml
system:
  id: CPKS
  name: cpKnowledgeSystem
  role: overarching_knowledge_and_agent_system

primary_components:
  cp_wiki:
    role: canonical_human_knowledge_and_governance
    path: /Users/cp/Documents/cp-wiki/
  cpKnowledgeTools:
    role: python_toolset
    path: /Users/cp/Developer/cpKnowledgeTools/
    distribution: cp-knowledge-tools
    import_package: cp_knowledge_tools
  OpenClaw_OS:
    role: agent_runtime_and_orchestration

governance:
  baseline:
    active_version: "0.44"
    supersedes: CPKS-BL@0.43
  policy:
    id: CPKS-POL-GOV-AUTH
    version: "1.0"
    status: active
  framework:
    id: CPKS-FWK-AIW
    version: "0.4"
    status: active
  managed_artifact_specification:
    id: CPKS-SPEC-ART
    version: "0.2"
    status: active
  process_description_specification:
    id: CPKS-SPEC-PROC
    version: "0.3"
    status: active
  governance_process:
    id: GOV-P01
    version: "0.3"
    status: active

validation:
  managed_artifact_validator_version: "3.1"
  status: operational
  historical_acknowledgements: supported
  current_artifact_errors_blocking: true

artifact_execution:
  canonical_repository: /Users/cp/Developer/cpKnowledgeTools/
  script_root: /Users/cp/Developer/cpKnowledgeTools/scripts/cp_wiki/
  runtime_root: /Users/cp/Library/Application Support/cpKnowledgeTools/Runs/cp-wiki/
  backup_root: /Users/cp/Backups/cp-wiki/Snapshots/
  downloads_canonical: false

source_of_truth:
  canonical_human_source: cp-wiki
  chat_history_authoritative: false
  model_memory_authoritative: false
  runtime_memory_authoritative: false
```"""

    section_22 = """# 22. Kurzform

> `cpKnowledgeSystem` ist das übergeordnete Wissens- und Agentensystem. `cp-wiki` bleibt die menschlich kontrollierte Source of Truth; `cpKnowledgeTools` stellt die kontrollierten technischen Werkzeuge bereit. `CPKS-SPEC-ART@0.2` und `CPKS-SPEC-PROC@0.3` sind aktive Spezifikationen. Validator v3.1 implementiert die Managed-Artifact-Prüfung mit getrennten Profilen, Aliasauflösung und Historical Acknowledgements. `GOV-P01@0.3` ist der aktive Prozess für Governance Artifact Consolidation and Impact Review. Nicht jeder historische oder unstrukturierte Bestand wird rückwirkend modernisiert; maßgeblich sind aktuelle Konformität, lifecycle-weite Integrität und ein praktisch arbeitsfähiges cpKnowledgeSystem."""

    body = replace_section(body, "# 9. Managed Artifacts", "# 10.", section_9)
    body = replace_section(body, "# 10.", "# 11.", section_10)
    body = replace_section(body, "# 11.", "# 12.", section_11)
    body = replace_section(body, "# 16.", "# 17.", section_16)
    body = replace_section(body, "# 17.", "# 18.", section_17)
    body = replace_section(body, "# 18.", "# 19.", section_18)
    body = replace_section(body, "# 20.", "# 21.", section_20)
    body = replace_section(body, "# 21.", "# 22.", section_21)
    body = replace_tail_section(body, "# 22.", section_22)

    updated = join_frontmatter(raw, body)
    validate_identity(
        updated,
        document_type="baseline",
        identity_field="baseline_id",
        identity="CPKS-BL",
        version="0.44",
        status="active",
        canonical_path=BASELINE_ACTIVE_REL.as_posix(),
    )
    return updated


def find_validator() -> Path:
    for candidate in VALIDATOR_CANDIDATES:
        if candidate.is_file():
            return candidate
    raise ActivationError(
        "Validator v3.1 was not found in the canonical validation script area."
    )


def read_validator_report(report_root: Path) -> tuple[Path, dict[str, Any]]:
    reports = sorted(
        report_root.rglob("validation-report-v3-1.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not reports:
        raise ActivationError(f"Validator report not found below: {report_root}")
    path = reports[0]
    return path, json.loads(path.read_text(encoding="utf-8"))


def run_validator(
    validator: Path,
    report_root: Path,
) -> tuple[Path, dict[str, Any]]:
    report_root.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [
            sys.executable,
            str(validator),
            "--vault",
            str(VAULT),
            "--report-root",
            str(report_root),
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    (report_root / "validator-console-output.txt").write_text(
        result.stdout,
        encoding="utf-8",
    )
    if result.returncode not in {0, 1}:
        raise ActivationError(
            "Validator execution failed. See validator-console-output.txt."
        )

    report_path, report = read_validator_report(report_root)
    summary = report.get("summary") or {}
    errors = int(summary.get("error", 0))
    warnings = int(summary.get("warning", 0))
    if errors or warnings:
        raise ActivationError(
            "Validator is not activation-clean: "
            f"errors={errors}, warnings={warnings}. "
            f"Report: {report_path}"
        )
    return report_path, report


def unified_diff(
    before: str,
    after: str,
    before_name: str,
    after_name: str,
) -> str:
    return "".join(
        difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=before_name,
            tofile=after_name,
        )
    )


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def atomic_write(path: Path, content: str, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".gov-p01-activation.tmp",
        dir=path.parent,
    )
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temp_path, mode)
        os.replace(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    assert_canonical_script_location()

    require_active_specification(
        VAULT / ART_ACTIVE_REL,
        "CPKS-SPEC-ART",
        "0.2",
    )
    require_active_specification(
        VAULT / PROC_ACTIVE_REL,
        "CPKS-SPEC-PROC",
        "0.3",
    )

    gov_source = VAULT / GOV_SOURCE_REL
    gov_active = VAULT / GOV_ACTIVE_REL
    baseline_active = VAULT / BASELINE_ACTIVE_REL
    baseline_archive = VAULT / BASELINE_ARCHIVE_REL

    if not gov_source.is_file():
        raise ActivationError(f"GOV-P01 proposal missing: {gov_source}")
    if gov_active.exists():
        raise ActivationError(f"Active GOV-P01 target already exists: {gov_active}")
    if not baseline_active.is_file():
        raise ActivationError(f"Active baseline missing: {baseline_active}")
    if baseline_archive.exists():
        raise ActivationError(
            f"Baseline archive target already exists: {baseline_archive}"
        )

    validator = find_validator()

    timestamp = dt.datetime.now().astimezone().strftime("%Y%m%dT%H%M%S%z")
    mode = "apply" if args.apply else "dry-run"
    run_dir = RUN_ROOT / f"{timestamp}-activate-GOV-P01-0.3-{mode}"
    run_dir.mkdir(parents=True, exist_ok=False)

    pre_report_path, pre_report = run_validator(
        validator,
        run_dir / "pre-validation",
    )

    gov_before = gov_source.read_text(encoding="utf-8")
    baseline_before = baseline_active.read_text(encoding="utf-8")

    gov_after = build_active_gov(gov_before)
    baseline_043_archived = build_archived_baseline_043(baseline_before)
    baseline_044_active = build_active_baseline_044(baseline_before)

    planned_diff = "".join(
        [
            unified_diff(
                gov_before,
                "",
                f"a/{GOV_SOURCE_REL.as_posix()}",
                "/dev/null",
            ),
            unified_diff(
                "",
                gov_after,
                "/dev/null",
                f"b/{GOV_ACTIVE_REL.as_posix()}",
            ),
            unified_diff(
                baseline_before,
                baseline_044_active,
                f"a/{BASELINE_ACTIVE_REL.as_posix()}",
                f"b/{BASELINE_ACTIVE_REL.as_posix()}",
            ),
            unified_diff(
                "",
                baseline_043_archived,
                "/dev/null",
                f"b/{BASELINE_ARCHIVE_REL.as_posix()}",
            ),
        ]
    )
    (run_dir / "planned-changes.diff").write_text(
        planned_diff,
        encoding="utf-8",
    )

    manifest = {
        "mode": mode,
        "owner_approval": {
            "approved_by": OWNER,
            "approved_at": ACTIVATION_DATE,
            "effective_from": ACTIVATION_DATE,
            "instruction": "Aktiviere GOV-P01@0.3",
        },
        "pre_validation_report": str(pre_report_path),
        "pre_validation_summary": pre_report.get("summary", {}),
        "activate_process": {
            "id": "GOV-P01",
            "version": "0.3",
            "source": GOV_SOURCE_REL.as_posix(),
            "target": GOV_ACTIVE_REL.as_posix(),
            "sha256": sha256(gov_after),
        },
        "activate_baseline": {
            "id": "CPKS-BL",
            "version": "0.44",
            "path": BASELINE_ACTIVE_REL.as_posix(),
            "supersedes": "CPKS-BL@0.43",
            "sha256": sha256(baseline_044_active),
        },
        "archive_baseline": {
            "id": "CPKS-BL",
            "version": "0.43",
            "target": BASELINE_ARCHIVE_REL.as_posix(),
            "sha256": sha256(baseline_043_archived),
        },
        "specifications_modified": False,
        "validator_modified": False,
        "commit_created": False,
        "push_performed": False,
    }
    (run_dir / "activation-manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    if not args.apply:
        print("Dry run completed. No Vault files were changed.")
        print(f"Pre-validation report: {pre_report_path}")
        print(f"Run report: {run_dir}")
        return 0

    recovery_root = run_dir / "recovery"
    recovery_gov = recovery_root / GOV_SOURCE_REL
    recovery_baseline = recovery_root / BASELINE_ACTIVE_REL
    recovery_gov.parent.mkdir(parents=True, exist_ok=True)
    recovery_baseline.parent.mkdir(parents=True, exist_ok=True)
    recovery_gov.write_text(gov_before, encoding="utf-8")
    recovery_baseline.write_text(baseline_before, encoding="utf-8")

    gov_mode = gov_source.stat().st_mode & 0o777
    baseline_mode = baseline_active.stat().st_mode & 0o777

    created: list[Path] = []

    try:
        atomic_write(gov_active, gov_after, gov_mode)
        created.append(gov_active)

        atomic_write(
            baseline_archive,
            baseline_043_archived,
            baseline_mode,
        )
        created.append(baseline_archive)

        atomic_write(
            baseline_active,
            baseline_044_active,
            baseline_mode,
        )

        gov_source.unlink()

        validate_identity(
            gov_active.read_text(encoding="utf-8"),
            document_type="process",
            identity_field="process_id",
            identity="GOV-P01",
            version="0.3",
            status="active",
            canonical_path=GOV_ACTIVE_REL.as_posix(),
        )
        validate_identity(
            baseline_active.read_text(encoding="utf-8"),
            document_type="baseline",
            identity_field="baseline_id",
            identity="CPKS-BL",
            version="0.44",
            status="active",
            canonical_path=BASELINE_ACTIVE_REL.as_posix(),
        )
        validate_identity(
            baseline_archive.read_text(encoding="utf-8"),
            document_type="baseline",
            identity_field="baseline_id",
            identity="CPKS-BL",
            version="0.43",
            status="superseded",
            canonical_path=BASELINE_ARCHIVE_REL.as_posix(),
        )

        post_report_path, post_report = run_validator(
            validator,
            run_dir / "post-validation",
        )

    except Exception:
        for path in reversed(created):
            path.unlink(missing_ok=True)
        atomic_write(gov_source, gov_before, gov_mode)
        atomic_write(baseline_active, baseline_before, baseline_mode)
        raise

    report = {
        **manifest,
        "mode": "apply",
        "state": "applied",
        "post_validation_report": str(post_report_path),
        "post_validation_summary": post_report.get("summary", {}),
        "recovery_root": str(recovery_root),
    }
    (run_dir / "activation-report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print("GOV-P01@0.3 activated.")
    print("CPKS-BL@0.44 activated.")
    print("CPKS-BL@0.43 archived as superseded.")
    print(f"Post-validation report: {post_report_path}")
    print(f"Run report: {run_dir}")
    print("No Git commit or push was performed.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ActivationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
