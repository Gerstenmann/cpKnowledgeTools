#!/usr/bin/env python3
"""
Add the normative historical validation acknowledgement model to
CPKS-SPEC-ART@0.2.

Canonical script location:
  /Users/cp/Developer/cpKnowledgeTools/scripts/cp_wiki/governance/
  update_cpks_spec_art_v0_2_acknowledgement_model.py

Default: dry run.
Use --apply to update the draft in place.

The script:
- keeps CPKS-SPEC-ART at version 0.2 and status draft;
- inserts the normative acknowledgement rules;
- aligns validated_against and references to CPKS-SPEC-PROC@0.3;
- updates the validation error/warning catalogue, conformance rule,
  activation evidence and short rule;
- creates a diff and recovery copy outside the Vault;
- performs no activation, Git commit or push.
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
import sys
import tempfile

VAULT = Path("/Users/cp/Documents/cp-wiki")
TOOLS = Path("/Users/cp/Developer/cpKnowledgeTools")
CANONICAL_SCRIPT = (
    TOOLS / "scripts/cp_wiki/governance/"
    "update_cpks_spec_art_v0_2_acknowledgement_model.py"
)
RUN_ROOT = Path(
    "/Users/cp/Library/Application Support/cpKnowledgeTools/Runs/cp-wiki/governance"
)
TARGET_REL = Path(
    "Development/cpKnowledgeSystem/Specifications/"
    "CPKS-SPEC-ART@0.2 Managed Artifact Metadata and Validation Specification.md"
)

SECTION = '### 17.8 Bestätigte historische Diagnosen\n\nHistorische, abgeschlossene oder ausschließlich als Legacy-Support geführte Dateien können bekannte Validatorbefunde enthalten, deren Unregelmäßigkeit geprüft, zur Kenntnis genommen und ohne weitere Bestandsmigration abgeschlossen wurde.\n\nFür solche Fälle DARF das Frontmatter das Feld `validation_acknowledgement` führen:\n\n```yaml\nvalidation_acknowledgement:\n  disposition: accepted_historical\n  reviewed_by: Christoph Peters\n  reviewed_at: "2026-07-26"\n  source_report_generated_at: "2026-07-26T23:13:34.788366+02:00"\n  accepted_codes:\n    - invalid_reference_form\n    - legacy_artifact_id_resolved\n  rationale: "Historische Metadatenabweichungen wurden geprüft und als abgeschlossen akzeptiert."\n```\n\n#### 17.8.1 Zulässige Prüfprofile\n\n`validation_acknowledgement` ist ausschließlich zulässig für:\n\n```text\nhistorical_managed\nclosed_development_managed\nlegacy_support\n```\n\nDas Feld ist unzulässig für:\n\n```text\ncurrent_managed\ncurrent_development_managed\ncurrent_support\nunmanaged\n```\n\nEin Acknowledgement an einem aktuellen oder aktuellen Development-Artefakt erzeugt den Fehler:\n\n```text\nvalidation_acknowledgement_not_allowed\n```\n\n#### 17.8.2 Pflichtfelder und Datentypen\n\n| Feld | Pflicht | Regel |\n|---|---:|---|\n| `disposition` | ja | ausschließlich `accepted_historical` |\n| `reviewed_by` | ja | nicht leerer Name der prüfenden oder freigebenden Person |\n| `reviewed_at` | ja | ISO-Datum `YYYY-MM-DD` |\n| `accepted_codes` | ja | nicht leere Liste konkret bestätigter Diagnosecodes |\n| `source_report_generated_at` | empfohlen | ISO-8601-Zeitpunkt des zugrunde liegenden Validatorreports |\n| `rationale` | empfohlen | kurze Begründung für die abschließende Akzeptanz |\n\nDoppelte Einträge in `accepted_codes` SOLLEN als Warnung gemeldet werden.\n\n#### 17.8.3 Wirkung\n\nEin gültiges Acknowledgement bewirkt ausschließlich:\n\n- Warnungen und Informationen werden unterdrückt, wenn ihr exakter Diagnosecode in `accepted_codes` steht,\n- die unterdrückten Befunde werden im Validatorreport aggregiert gezählt,\n- die Datei bleibt Bestandteil von Inventarisierung, Referenzauflösung und lifecycle-weiter Integritätsprüfung.\n\nEin Acknowledgement:\n\n- ändert weder Inhalt noch historische Bedeutung des Artefakts,\n- ändert nicht dessen Status, Identität oder Version,\n- erklärt die frühere Metadatenform nicht rückwirkend zur aktuellen Norm,\n- wird nicht automatisch auf andere Dateien oder spätere Versionen übertragen,\n- darf keine unbekannten zukünftigen Diagnosecodes pauschal erfassen.\n\n#### 17.8.4 Nicht unterdrückbare Befunde\n\nEin Acknowledgement DARF niemals eine Diagnose mit `severity: error` unterdrücken.\n\nInsbesondere bleiben immer sichtbar und blockierend:\n\n- ungültiges oder nicht lesbares YAML,\n- fehlende oder widersprüchliche Identität,\n- ungültige Version oder Lifecycle-Statuswerte,\n- falscher `canonical_path`,\n- doppelte Kombination aus stabiler ID und Version,\n- mehrere aktive Fassungen,\n- aktive Artefakte in History- oder Archive-Zonen,\n- unzulässige Acknowledgements,\n- sonstige Fehler, die lifecycle-weite Eindeutigkeit oder Provenienz gefährden.\n\nEin in `accepted_codes` aufgeführter Fehlercode besitzt daher keine unterdrückende Wirkung. Ein Validator KANN den Versuch zusätzlich diagnostizieren.\n\n#### 17.8.5 Erneute Prüfung\n\nWird eine bestätigte historische Datei materiell verändert, in ein aktuelles Prüfprofil überführt oder erneut normativ verwendet, MUSS das Acknowledgement überprüft werden.\n\nNicht mehr zutreffende oder unzureichend begründete Einträge sind zu entfernen oder kontrolliert neu zu bestätigen.\n\nDas bloße Ergänzen eines gültigen Acknowledgements ist eine historische Metadatenpflege und keine materielle Revalidierung des Dokumentinhalts.\n'


class UpdateError(RuntimeError):
    pass


def assert_canonical_script_location() -> None:
    actual = Path(__file__).resolve()
    expected = CANONICAL_SCRIPT.resolve()
    if actual != expected:
        raise UpdateError(
            "Script is not in its canonical repository location.\n"
            f"Expected: {expected}\n"
            f"Actual:   {actual}"
        )


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise UpdateError(f"Expected exactly one anchor for {label}, found {count}.")
    return text.replace(old, new, 1)


def validate_target(text: str) -> None:
    required = {
        "document_type": "specification",
        "specification_id": "CPKS-SPEC-ART",
        "version": "0.2",
        "status": "draft",
        "canonical_path": TARGET_REL.as_posix(),
    }
    for field, wanted in required.items():
        match = re.search(
            rf"(?m)^{re.escape(field)}:\s*[\"']?([^\n\"']+)[\"']?\s*$",
            text,
        )
        actual = match.group(1).strip() if match else None
        if actual != wanted:
            raise UpdateError(f"{field} expected {wanted!r}, got {actual!r}")

    if "### 17.8 Bestätigte historische Diagnosen" not in text:
        raise UpdateError("Normative acknowledgement section is missing.")
    if "validation_acknowledgement_not_allowed" not in text:
        raise UpdateError("Acknowledgement error code is missing.")


def build_updated(source: str) -> str:
    if "### 17.8 Bestätigte historische Diagnosen" in source:
        validate_target(source)
        return source

    updated = source

    updated = replace_once(
        updated,
        "  - CPKS-SPEC-PROC@0.2\n",
        "  - CPKS-SPEC-PROC@0.3\n",
        "validated_against process specification",
    )

    updated = replace_once(
        updated,
        "- das Aliasformat für migrierte stabile IDs wird festgelegt,\n"
        "- technische Reports und Validatorläufe werden mit `CPKS-DEC-020@1.0` harmonisiert.",
        "- das Aliasformat für migrierte stabile IDs wird festgelegt,\n"
        "- ein kontrolliertes Acknowledgement-Modell schließt geprüfte historische Warnungen und Informationen ab, ohne Integritätsfehler zu verbergen,\n"
        "- technische Reports und Validatorläufe werden mit `CPKS-DEC-020@1.0` harmonisiert.",
        "status summary bullet",
    )

    updated = replace_once(
        updated,
        "- Fehler- und Warnungsklassen,\n"
        "- kontrollierte Migration und Aliasbehandlung.",
        "- Fehler- und Warnungsklassen,\n"
        "- kontrollierte Bestätigung abgeschlossener historischer Diagnosen,\n"
        "- kontrollierte Migration und Aliasbehandlung.",
        "purpose bullet",
    )

    updated = replace_once(
        updated,
        "Der Backup-Bereich darf nicht als Standardziel für Validatorreports verwendet werden.\n\n"
        "## 18. Referenzauflösung",
        "Der Backup-Bereich darf nicht als Standardziel für Validatorreports verwendet werden.\n\n"
        + SECTION
        + "\n## 18. Referenzauflösung",
        "section 17.8 insertion",
    )

    updated = replace_once(
        updated,
        "unresolved_supersedes_reference\nparallel_canonical_version\n```",
        "unresolved_supersedes_reference\nparallel_canonical_version\n"
        "validation_acknowledgement_not_allowed\n"
        "invalid_validation_acknowledgement\n"
        "invalid_validation_acknowledgement_disposition\n```",
        "minimum error classes",
    )

    updated = replace_once(
        updated,
        "unknown_controlled_abbreviation\nplanned_target_not_materialized\n```",
        "unknown_controlled_abbreviation\nplanned_target_not_materialized\n"
        "unknown_validation_acknowledgement_field\n"
        "duplicate_validation_acknowledgement_code\n```",
        "minimum warning classes",
    )

    updated = replace_once(
        updated,
        "Ein historisches oder abgeschlossenes Development-Artefakt ist im eingeschränkten Profil konform, wenn seine Identität, Provenienz, Lesbarkeit, Pfadzuordnung und lifecycle-weite Eindeutigkeit erhalten bleiben.\n\n"
        "Eine erfolgreiche technische Validierung ersetzt nicht Owner Review, normative Autoritätsprüfung, Scope-Prüfung oder ausdrückliche Aktivierungsbefugnis.",
        "Ein historisches oder abgeschlossenes Development-Artefakt ist im eingeschränkten Profil konform, wenn seine Identität, Provenienz, Lesbarkeit, Pfadzuordnung und lifecycle-weite Eindeutigkeit erhalten bleiben. Ein gültiges `validation_acknowledgement` darf bereits geprüfte Warnungen und Informationen aus dem laufenden Report ausblenden, verändert aber weder die historische Konformität noch die weiterhin auszuführenden Integritätsprüfungen.\n\n"
        "Eine erfolgreiche technische Validierung ersetzt nicht Owner Review, normative Autoritätsprüfung, Scope-Prüfung oder ausdrückliche Aktivierungsbefugnis.",
        "historical conformance rule",
    )

    updated = replace_once(
        updated,
        "8. kontrollierte Behandlung der archivierten Vault-Spezifikationen 1.0 und 1.1,\n"
        "9. Owner Review des vollständigen Drafts,\n"
        "10. ausdrücklicher Aktivierungsauftrag.",
        "8. kontrollierte Behandlung der archivierten Vault-Spezifikationen 1.0 und 1.1,\n"
        "9. Implementierung und Test des Acknowledgement-Modells in Validator v3.1,\n"
        "10. Owner Review des vollständigen Drafts,\n"
        "11. ausdrücklicher Aktivierungsauftrag.",
        "activation evidence",
    )

    updated = replace_once(
        updated,
        "Frühere stabile IDs werden verteilt über `former_ids` aufgelöst. Geplante Zielartefakte dürfen über einen strukturierten `target_artifact`-Descriptor beschrieben werden. Ein Validator darf Inkonsistenzen erkennen, aber weder historische Provenienz überschreiben noch normative Entscheidungen ergänzen oder Artefakte ohne Autorisierung reparieren und aktivieren.",
        "Frühere stabile IDs werden verteilt über `former_ids` aufgelöst. Geplante Zielartefakte dürfen über einen strukturierten `target_artifact`-Descriptor beschrieben werden. Konkret geprüfte Warnungen und Informationen historischer, geschlossener oder Legacy-Artefakte dürfen über `validation_acknowledgement` abgeschlossen werden; Fehler und lifecycle-weite Integritätsprüfungen bleiben davon unberührt. Ein Validator darf Inkonsistenzen erkennen, aber weder historische Provenienz überschreiben noch normative Entscheidungen ergänzen oder Artefakte ohne Autorisierung reparieren und aktivieren.",
        "short rule",
    )

    validate_target(updated)
    return updated


def unified_diff(before: str, after: str) -> str:
    return "".join(
        difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=f"a/{TARGET_REL.as_posix()}",
            tofile=f"b/{TARGET_REL.as_posix()}",
        )
    )


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def atomic_write(path: Path, content: str, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".acknowledgement-model.tmp",
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

    target = VAULT / TARGET_REL
    if not target.is_file():
        raise UpdateError(f"Target file missing: {TARGET_REL}")

    before = target.read_text(encoding="utf-8")
    after = build_updated(before)
    already_updated = before == after

    timestamp = dt.datetime.now().astimezone().strftime("%Y%m%dT%H%M%S%z")
    mode = "apply" if args.apply else "dry-run"
    run_dir = RUN_ROOT / f"{timestamp}-update-CPKS-SPEC-ART-0.2-acknowledgement-{mode}"
    run_dir.mkdir(parents=True, exist_ok=False)

    (run_dir / "planned-changes.diff").write_text(
        unified_diff(before, after),
        encoding="utf-8",
    )
    (run_dir / "updated-preview.md").write_text(after, encoding="utf-8")
    (run_dir / "update-manifest.json").write_text(
        json.dumps(
            {
                "mode": mode,
                "state": "already_updated" if already_updated else "planned",
                "target": TARGET_REL.as_posix(),
                "before_sha256": sha256(before),
                "after_sha256": sha256(after),
                "version_changed": False,
                "status_changed": False,
                "activation_performed": False,
                "commit_created": False,
                "push_performed": False,
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    if not args.apply:
        print("Dry run completed. No Vault files were changed.")
        print(f"State: {'already_updated' if already_updated else 'planned'}")
        print(f"Run report: {run_dir}")
        return 0

    if already_updated:
        print("CPKS-SPEC-ART@0.2 already contains the acknowledgement model.")
        print(f"Run report: {run_dir}")
        return 0

    recovery = run_dir / "recovery" / TARGET_REL
    recovery.parent.mkdir(parents=True, exist_ok=True)
    recovery.write_text(before, encoding="utf-8")

    mode_bits = target.stat().st_mode & 0o777
    atomic_write(target, after, mode_bits)

    written = target.read_text(encoding="utf-8")
    validate_target(written)
    if written != after:
        atomic_write(target, before, mode_bits)
        raise UpdateError("Post-write byte comparison failed; source restored.")

    (run_dir / "update-report.json").write_text(
        json.dumps(
            {
                "state": "applied",
                "target": TARGET_REL.as_posix(),
                "recovery_path": str(recovery),
                "version": "0.2",
                "status": "draft",
                "activation_performed": False,
                "commit_created": False,
                "push_performed": False,
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    print("Acknowledgement model added to CPKS-SPEC-ART@0.2.")
    print("Version remains 0.2; status remains draft.")
    print(f"Run report: {run_dir}")
    print("No activation, Git commit or push was performed.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except UpdateError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
