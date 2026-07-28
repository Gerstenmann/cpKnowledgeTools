#!/usr/bin/env python3
"""
Create GOV-P01@0.3 and withdraw/archive GOV-P01@0.2.

Canonical script location:
  /Users/cp/Developer/cpKnowledgeTools/scripts/cp_wiki/governance/
  revise_gov_p01_to_v0_3.py

Default: dry run.
Use --apply to write changes.

The separate review document
  Development/cpKnowledgeSystem/Governance/Reviews/
  GOV-P01 v0.2 Governance Review.md
is not modified or moved.

Technical run reports and recovery copies are written to:
  /Users/cp/Library/Application Support/
  cpKnowledgeTools/Runs/cp-wiki/governance/

No activation, Git commit or push is performed.
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
    TOOLS
    / "scripts/cp_wiki/governance/revise_gov_p01_to_v0_3.py"
)
RUN_ROOT = Path(
    "/Users/cp/Library/Application Support/"
    "cpKnowledgeTools/Runs/cp-wiki/governance"
)

SOURCE_REL = Path(
    "Development/cpKnowledgeSystem/Governance/Draft Processes/"
    "GOV-P01@0.2 Governance Artifact Consolidation and Impact Review.md"
)
ARCHIVE_REL = Path(
    "Development/cpKnowledgeSystem/Governance/Draft Processes/Archive/"
    "GOV-P01@0.2 Governance Artifact Consolidation and Impact Review.md"
)
TARGET_REL = Path(
    "Development/cpKnowledgeSystem/Governance/Draft Processes/"
    "GOV-P01@0.3 Governance Artifact Consolidation and Impact Review.md"
)

TARGET_CONTENT = '---\ndocument_type: process\nprocess_id: GOV-P01\ntitle: Governance Artifact Consolidation and Impact Review\nversion: "0.3"\nstatus: draft\nprocess_domain: governance\nauthority_scope: system-wide\nsystem: cpKnowledgeSystem\nowner: Christoph Peters\ncreated: 2026-07-26\nrevised: 2026-07-26\nlanguage: de\ngoverned_by:\n  - CPKS-POL-GOV-AUTH\ndepends_on:\n  - CPKS-DEC-012\n  - CPKS-DEC-013\n  - CPKS-DEC-015\n  - CPKS-DEC-016\n  - CPKS-DEC-017\n  - CPKS-DEC-018\n  - CPKS-DEC-019\n  - CPKS-DEC-020\naligned_with:\n  - CPKS-BL\n  - CPKS-FWK-AIW\nimplements_decisions:\n  - CPKS-DEC-012@1.2\n  - CPKS-DEC-013@1.0\n  - CPKS-DEC-015@1.1\n  - CPKS-DEC-016@1.1\n  - CPKS-DEC-017@1.0\n  - CPKS-DEC-018@1.0\n  - CPKS-DEC-019@1.0\nvalidated_against:\n  - CPKS-POL-GOV-AUTH@1.0\n  - CPKS-BL@0.43\n  - CPKS-FWK-AIW@0.4\n  - CPKS-DEC-020@1.0\n  - CPKS-SPEC-ART@0.2\n  - CPKS-SPEC-PROC@0.3\nreferences:\n  - GOV-P01@0.2\ncanonical_path: Development/cpKnowledgeSystem/Governance/Draft Processes/GOV-P01@0.3 Governance Artifact Consolidation and Impact Review.md\nsupersedes: []\n---\n\n# GOV-P01 – Governance Artifact Consolidation and Impact Review\n\n## 1. Zweck\n\nDieser Prozess steuert die Erstellung, Änderung, Prüfung und Aktivierung verwalteter Governance-Artefakte des `cpKnowledgeSystem`.\n\nEr stellt sicher, dass:\n\n- die tatsächliche kanonische Quelle verwendet wird,\n- Autorität und Änderungsscope geklärt sind,\n- bekannte Auswirkungen geprüft werden,\n- Metadaten und Referenzen technisch valide sind,\n- historische Fassungen korrekt behandelt werden,\n- eine Aktivierung nur mit ausdrücklicher Owner-Freigabe erfolgt.\n\nDer Prozess soll Governance-Arbeit kontrollierbar machen, ohne für kleine autorisierte Owner-Änderungen unnötige Bürokratie zu erzeugen.\n\n## 2. Geltungsbereich\n\nDer Prozess gilt insbesondere für:\n\n- Baselines,\n- Decision Records,\n- Policies,\n- Frameworks,\n- Spezifikationen,\n- Prozesse,\n- Work Packages,\n- normative Templates und Manuals,\n- ausdrücklich eingeführte weitere Managed Artifacts.\n\nEr gilt für:\n\n- direkte Änderungen durch den menschlichen System-Owner,\n- KI-gestützte Governance-Änderungen,\n- neue Fassungen bestehender Artefaktlinien,\n- neue Governance-Artefakte,\n- Aktivierung, Rückzug, Supersession und Archivierung.\n\nEr gilt nicht für:\n\n- gewöhnliche Wissensnotizen,\n- unveränderte Rohquellen,\n- rein generierte Reports und Indizes,\n- technische Implementierungsdetails, die ausschließlich im Repository `cpKnowledgeTools` geregelt werden,\n- kleine redaktionelle Korrekturen ohne Änderung der normativen Aussage, sofern Identität, Version, Status und Pfad unverändert bleiben.\n\n## 3. Auslöser\n\nDer Prozess beginnt, wenn mindestens eines der folgenden Ereignisse eintritt:\n\n1. Der Owner beauftragt eine neue oder geänderte Governance-Fassung.\n2. Eine aktive Decision verlangt eine Folgeumsetzung.\n3. Ein Widerspruch oder Validatorfehler in einem aktuellen Managed Artifact wird erkannt.\n4. Eine neue aktive Version kann andere Artefakte beeinflussen.\n5. Ein Draft soll geprüft, zurückgezogen oder aktiviert werden.\n6. Ein bestehendes Artefakt soll verschoben, umbenannt oder archiviert werden.\n7. Eine KI erhält einen governance-relevanten Schreibauftrag.\n\n## 4. Voraussetzungen und Inputs\n\nMindestens erforderlich sind:\n\n| Input oder Voraussetzung | Pflicht |\n|---|---:|\n| eindeutiges Primärziel oder beschriebene neue Artefaktlinie | ja |\n| tatsächliche kanonische Quelldatei, sofern vorhanden | ja |\n| bestätigte Auftragsart | ja |\n| bestätigte Autoritätsgrundlage | ja |\n| bestätigter In-Scope- und Out-of-Scope-Bereich | ja |\n| aktive Policy, relevante Decisions und Baseline | ja |\n| aktueller Validatorbericht bei Metadaten- oder Lifecycle-Arbeit | soweit vorhanden |\n| bekannte Impact-Kandidaten | soweit erkennbar |\n| Aktivierungsbefugnis | nur bei geplanter Aktivierung |\n\nFür ein geplantes, noch nicht vorhandenes Ziel kann ein strukturierter Descriptor verwendet werden:\n\n```yaml\ntarget_artifact:\n  reference: GOV-P01@0.3\n  document_type: process\n  target_status: draft\n  proposed_canonical_path: Development/cpKnowledgeSystem/Governance/Draft Processes/GOV-P01@0.3 Governance Artifact Consolidation and Impact Review.md\n```\n\n## 5. Rollen und Verantwortlichkeiten\n\n| Rolle | Verantwortung |\n|---|---|\n| System-Owner | autorisiert Auftrag, Scope, normative Entscheidungen und Aktivierung |\n| ausführende menschliche Rolle | führt autorisierte Änderungen und Mindestkontrollen durch |\n| AI Change Agent | prüft Quellen, macht Annahmen sichtbar, erstellt Draft oder Patch und hält Stop-Bedingungen ein |\n| Reviewer | prüft Inhalt, Scope, Impact, Metadaten und Lifecycle |\n| Validator beziehungsweise `cpKnowledgeTools` | prüft technische Konformität read-only und erzeugt nicht normative Reports |\n\nEine Person kann mehrere Rollen wahrnehmen. Technische Werkzeuge besitzen keine normative Freigabeautorität.\n\n## 6. Prozessablauf\n\n### 6.1 Pfadauswahl\n\nEs bestehen zwei zulässige Wege.\n\n#### Human Owner Direct Path\n\nDer menschliche System-Owner darf eine Governance-Änderung direkt veranlassen oder selbst durchführen.\n\nEin eigenständiges Preflight-Dokument ist nicht zwingend. Die Mindestkontrollen aus diesem Prozess bleiben erforderlich.\n\n#### AI-Controlled Path\n\nEine KI-gestützte normative Änderung benötigt vor dem Schreiben mindestens:\n\n- verifizierte Quelle,\n- bestätigtes Ziel,\n- bestätigte Autoritätsgrundlage,\n- bestätigten Scope,\n- bekannte Preserve- und Out-of-Scope-Regeln,\n- erkennbare Stop-Bedingungen,\n- einen überprüfbaren Draft, Patch oder Diff.\n\nBei komplexen oder risikoreichen Änderungen wird ein Preflight oder Work Package verwendet. Ein formales Voll-Intake für jeden kleinen Auftrag ist nicht erforderlich.\n\n### 6.2 Gemeinsamer Ablauf\n\n| Schritt | Verantwortliche Rolle | Tätigkeit | Ergebnis oder Kontrolle |\n|---:|---|---|---|\n| 1 | Owner oder ausführende Rolle | Auftragsart, Primärziel und gewünschtes Ergebnis bestimmen. | Ziel und Bearbeitungsart sind eindeutig. |\n| 2 | ausführende Rolle | Tatsächliche Quelldatei, Identität, Version, Status und Pfad verifizieren. | Kanonische Quelle oder dokumentierter Neuanlagefall. |\n| 3 | Owner oder ausführende Rolle | Autoritätsgrundlage, In Scope, Preserve und Out of Scope bestätigen. | Kontrollierter Arbeitsrahmen. |\n| 4 | ausführende Rolle | Passenden Arbeitsweg wählen und erforderliche Nachweise bestimmen. | Owner Direct Path oder AI-Controlled Path. |\n| 5 | ausführende Rolle oder Validator | Ausgehende Beziehungen, frühere IDs, Vorgängerfassungen und bekannte Rückwärtsreferenzen prüfen. | Vorläufiges Impact Set. |\n| 6 | Owner oder Reviewer | Impact Set auf relevante Kandidaten begrenzen oder ergänzen. | Bestätigtes Review- und Follow-up-Set. |\n| 7 | ausführende Rolle | Minimalen Draft, Patch oder Lifecycle-Change erstellen. | Nur autorisierte Änderungen sind enthalten. |\n| 8 | Validator | Aktuelles Prüfprofil anwenden und Fehler, Warnungen und Informationen ausgeben. | Technischer Validierungsbericht. |\n| 9 | ausführende Rolle | Blockierende Fehler beheben; Warnungen nach Relevanz bewerten. | Aktivierungsfähiger oder kontrolliert gestoppter Stand. |\n| 10 | Reviewer oder Owner | Inhalt, Scope, Impact, Referenzen und Lifecycle prüfen. | Freigabe, Korrekturauftrag, Rückzug oder Ablehnung. |\n| 11 | ausführende Rolle | Bei Freigabe Aktivierung beziehungsweise Status- und Pfadübergang durchführen. | Genau eine kanonische Fassung je ID und Version. |\n| 12 | ausführende Rolle | Git-Diff prüfen und erforderliche Folgearbeiten dokumentieren. | Nachvollziehbarer Abschluss ohne automatischen Push. |\n\n### 6.3 Referenzprüfung\n\nDauerhafte Beziehungen verwenden stabile IDs:\n\n```yaml\ngoverned_by:\ndepends_on:\naligned_with:\nrelated_decisions:\n```\n\nKonkrete Nachweise verwenden versionsgebundene Referenzen:\n\n```yaml\nimplements_decisions:\nvalidated_against:\nsupersedes:\n```\n\n`references` darf beide Formen enthalten.\n\nFrühere stabile IDs werden über `former_ids` aufgelöst. Neue oder aktuelle Artefakte dürfen nach abgeschlossener Migration nur die gültige aktuelle ID verwenden.\n\n### 6.4 Impact-Prüfung\n\nDas Impact Set umfasst nur Artefakte, für die eine tatsächliche Auswirkung plausibel ist.\n\nMindestens zu prüfen sind:\n\n- das Primärziel,\n- seine direkten Beziehungen,\n- seine Vorgänger- und Nachfolgerfassungen,\n- aktuelle Artefakte, die das Primärziel referenzieren,\n- die aktive Baseline bei Änderung des systemweiten Zustands,\n- betroffene Validator-, Prozess- oder Vault-Spezifikationen,\n- ausdrücklich benannte `affected_artifacts`.\n\nEin Impact-Kandidat ist keine automatische Folgeänderung.\n\nDas Ergebnis wird eingeteilt in:\n\n```text\nkeine Auswirkung\nnur Referenz\nReview erforderlich\nFolgeänderung erforderlich\nLifecycle-Übergang erforderlich\n```\n\n### 6.5 Lifecycle-Behandlung\n\nFür eine neue aktuelle Draft-Fassung gilt:\n\n```text\nstatus: draft\n→ versionierter Dateiname\n→ zuständiger Development-Kontext\n```\n\nEin nie aktivierter, nicht weiterverfolgter Draft erhält:\n\n```text\nstatus: withdrawn\n→ lokaler Development-Archive- oder History-Bereich\n```\n\nEin `withdrawn` Draft ist nicht `superseded`.\n\nEine zuvor aktive Fassung darf nur dann `superseded` werden, wenn eine aktive Nachfolgefassung existiert und sie konkret referenziert.\n\nAktive Fassungen liegen im typabhängigen aktiven Bereich und verwenden einen nicht versionierten Dateinamen.\n\n### 6.6 Technische Reports und Skripte\n\nAusführbare Governance-, Migrations- und Validierungsskripte werden im Repository `cpKnowledgeTools` geführt.\n\nTechnische Laufberichte und Recovery-Daten folgen `CPKS-DEC-020@1.0`. Sie sind keine kanonischen Governance-Artefakte und werden nicht im Backup-Bereich abgelegt.\n\nDer Prozess führt weder automatisch Git-Commit noch Push aus.\n\n## 7. Entscheidungs- und Stop-Bedingungen\n\n| Bedingung | Aktion |\n|---|---|\n| kanonische Quelle nicht verifiziert | stoppen |\n| Autoritätsgrundlage fehlt oder widerspricht sich | Owner-Entscheidung anfordern |\n| Ziel oder Scope ist mehrdeutig | Schreiben stoppen und Scope klären |\n| KI-Auftrag enthält keine ausreichenden Mindestinformationen | Intake vervollständigen |\n| Validator meldet aktuelle blockierende Fehler | Aktivierung stoppen |\n| mehrere aktive Fassungen derselben ID | Lifecycle bereinigen |\n| gleiche ID und Version existieren mehrfach | Duplikat bereinigen |\n| `canonical_path` stimmt nicht mit dem tatsächlichen Pfad überein | Pfad oder Metadaten korrigieren |\n| eine neue normative Regel wäre erforderlich | gesonderte Owner-Entscheidung oder Decision Record |\n| Folgeänderung liegt außerhalb des bestätigten Scopes | separat dokumentieren, nicht stillschweigend ausführen |\n| ausdrückliche Aktivierungsfreigabe fehlt | Draft nicht aktivieren |\n\nEin Agent darf bei einer Stop-Bedingung nicht eigenmächtig fortfahren.\n\n## 8. Fehler- und Ausnahmebehandlung\n\n| Fehler oder Ausnahme | Behandlung |\n|---|---|\n| Validator ist nicht verfügbar | Mindestkontrollen manuell nachvollziehbar durchführen |\n| historisches Artefakt verwendet frühere ID | über Aliasmodell auflösen; historische Datei nicht automatisch umschreiben |\n| Legacy-Support-Dokument erfüllt heutige Metadatenregeln nicht | als Warnung oder Information behandeln, sofern Integrität und Provenienz erhalten sind |\n| strukturierter Ziel-Descriptor verweist auf noch nicht vorhandene Fassung | als geplantes Ziel behandeln |\n| generierter Report widerspricht kanonischer Datei | kanonische Datei ist maßgeblich; Report neu erzeugen |\n| Archivregel ist unklar | keine eigenmächtige Verschiebung; Owner-Entscheidung |\n| Änderung kann nicht ohne weitere normative Entscheidung abgeschlossen werden | kontrolliert stoppen und offene Entscheidung dokumentieren |\n\n## 9. Outputs und Nachweise\n\n| Output oder Nachweis | Pflicht |\n|---|---:|\n| verifizierte Quelle oder dokumentierter Neuanlagefall | ja |\n| bestätigter Scope | ja |\n| Draft, Patch oder Lifecycle-Änderung | ja |\n| technischer Validierungsbericht | bei Managed-Artifact-Änderungen |\n| Review oder ausdrückliche Owner-Entscheidung | vor Aktivierung |\n| Git-Diff beziehungsweise nachvollziehbare Änderung | ja |\n| Follow-up-Liste | nur bei tatsächlichem Folgeaufwand |\n| Preflight oder Work Package | nur bei komplexem oder risikoreichem KI-Change |\n| generierter dauerhafter Report | nur bei konkretem Bedarf |\n\nEin manuell gepflegtes Document-, Decision- oder Process-Register ist kein Pflichtoutput.\n\n## 10. Abschlusskriterien\n\nDer Prozess ist abgeschlossen, wenn:\n\n- Ziel, Quelle und Scope eindeutig sind,\n- Autorität und Impact geprüft wurden,\n- der Draft oder Lifecycle-Change technisch valide ist,\n- blockierende Fehler behoben oder der Vorgang kontrolliert gestoppt wurde,\n- eine ausdrückliche Owner-Entscheidung vorliegt, sofern eine Aktivierung erfolgt,\n- keine parallele aktive oder konkrete Fassung entstanden ist,\n- Pfad, Dateiname, Status und Referenzen konsistent sind,\n- erforderliche Folgearbeiten knapp dokumentiert wurden,\n- Git-Diff geprüft wurde,\n- Commit und Push bewusst separat ausgeführt oder ausdrücklich zurückgestellt wurden.\n\n## 11. Zugehörige Prozesse und Artefakte\n\n| Beziehung | Artefakt | Zweck |\n|---|---|---|\n| Policy | `CPKS-POL-GOV-AUTH@1.0` | verbindliche Authoring- und Kontrollgrundsätze |\n| Baseline | `CPKS-BL@0.43` | aktueller systemweiter Governance-Zustand |\n| Framework | `CPKS-FWK-AIW@0.4` | Einordnung der Mensch-KI-Zusammenarbeit |\n| Specification | `CPKS-SPEC-ART@0.2` | Metadaten-, Referenz- und Validatorregeln |\n| Specification | `CPKS-SPEC-PROC@0.3` | Aufbau und Konformität von Prozessbeschreibungen |\n| Decision | `CPKS-DEC-012@1.2` | Artefaktkonsolidierung und Dependency Management |\n| Decision | `CPKS-DEC-013@1.0` | Owner Direct Path und AI-Controlled Path |\n| Decision | `CPKS-DEC-015@1.1` | Impact-Metadaten |\n| Decision | `CPKS-DEC-016@1.1` | Archive und History |\n| Decision | `CPKS-DEC-017@1.0` | kanonischer Prozessbestand |\n| Decision | `CPKS-DEC-018@1.0` | Governance Instruction Intake |\n| Decision | `CPKS-DEC-019@1.0` | Naming, Versioning und Lifecycle Placement |\n| Decision | `CPKS-DEC-020@1.0` | Skript-, Report- und Run-Daten-Lifecycle |\n'


class RevisionError(RuntimeError):
    pass


def assert_canonical_script_location() -> None:
    actual = Path(__file__).resolve()
    expected = CANONICAL_SCRIPT.resolve()
    if actual != expected:
        raise RevisionError(
            "Script is not in its canonical repository location.\n"
            f"Expected: {expected}\n"
            f"Actual:   {actual}"
        )


def split_frontmatter(text: str) -> tuple[str, str]:
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        raise RevisionError("Missing YAML frontmatter.")
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            return "".join(lines[1:index]), "".join(lines[index + 1:])
    raise RevisionError("Unclosed YAML frontmatter.")


def join_frontmatter(frontmatter: str, body: str) -> str:
    return "---\n" + frontmatter.rstrip() + "\n---\n" + body.lstrip("\n")


def scalar(frontmatter: str, field: str) -> str | None:
    match = re.search(
        rf"(?m)^{re.escape(field)}:\s*[\"']?([^\n\"']+)[\"']?\s*$",
        frontmatter,
    )
    return match.group(1).strip() if match else None


def replace_scalar(frontmatter: str, field: str, value: str) -> str:
    pattern = re.compile(rf"(?m)^{re.escape(field)}:.*$")
    if not pattern.search(frontmatter):
        raise RevisionError(f"Required field missing: {field}")
    return pattern.sub(f"{field}: {value}", frontmatter, count=1)


def validate_process(
    text: str,
    *,
    version: str,
    status: str,
    canonical_path: str,
) -> None:
    fm, _ = split_frontmatter(text)
    expected = {
        "document_type": "process",
        "process_id": "GOV-P01",
        "version": version,
        "status": status,
        "canonical_path": canonical_path,
    }
    for field, wanted in expected.items():
        actual = scalar(fm, field)
        if actual != wanted:
            raise RevisionError(
                f"{field} expected {wanted!r}, got {actual!r}"
            )


def build_archived_source(source_text: str) -> str:
    fm, body = split_frontmatter(source_text)
    validate_process(
        source_text,
        version="0.2",
        status="draft",
        canonical_path=SOURCE_REL.as_posix(),
    )
    fm = replace_scalar(fm, "status", "withdrawn")
    fm = replace_scalar(fm, "revised", "2026-07-26")
    fm = replace_scalar(
        fm,
        "canonical_path",
        ARCHIVE_REL.as_posix(),
    )
    return join_frontmatter(fm, body)


def diff(before: str, after: str, before_name: str, after_name: str) -> str:
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


def atomic_write(path: Path, content: str, mode: int = 0o644) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".revision.tmp",
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
    validate_process(
        TARGET_CONTENT,
        version="0.3",
        status="draft",
        canonical_path=TARGET_REL.as_posix(),
    )

    source_path = VAULT / SOURCE_REL
    archive_path = VAULT / ARCHIVE_REL
    target_path = VAULT / TARGET_REL

    timestamp = dt.datetime.now().astimezone().strftime("%Y%m%dT%H%M%S%z")
    mode = "apply" if args.apply else "dry-run"
    run_dir = (
        RUN_ROOT / f"{timestamp}-revise-GOV-P01-to-0.3-{mode}"
    )
    run_dir.mkdir(parents=True, exist_ok=False)

    if target_path.exists() and archive_path.exists() and not source_path.exists():
        target_existing = target_path.read_text(encoding="utf-8")
        archive_existing = archive_path.read_text(encoding="utf-8")
        validate_process(
            target_existing,
            version="0.3",
            status="draft",
            canonical_path=TARGET_REL.as_posix(),
        )
        validate_process(
            archive_existing,
            version="0.2",
            status="withdrawn",
            canonical_path=ARCHIVE_REL.as_posix(),
        )
        if target_existing != TARGET_CONTENT:
            raise RevisionError(
                "GOV-P01@0.3 exists with unexpected content."
            )
        report = {
            "mode": mode,
            "state": "already_final",
            "target": TARGET_REL.as_posix(),
            "archived_source": ARCHIVE_REL.as_posix(),
            "review_document_modified": False,
            "activation_performed": False,
            "commit_created": False,
            "push_performed": False,
        }
        (run_dir / "revision-report.json").write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print("Final GOV-P01 revision state already exists.")
        print(f"Run report: {run_dir}")
        return 0

    if not source_path.is_file():
        raise RevisionError(f"Source draft missing: {SOURCE_REL}")
    if archive_path.exists():
        raise RevisionError(f"Archive target already exists: {ARCHIVE_REL}")
    if target_path.exists():
        raise RevisionError(f"Target draft already exists: {TARGET_REL}")

    source_text = source_path.read_text(encoding="utf-8")
    archived_text = build_archived_source(source_text)

    validate_process(
        archived_text,
        version="0.2",
        status="withdrawn",
        canonical_path=ARCHIVE_REL.as_posix(),
    )

    planned_diff = (
        diff(
            source_text,
            "",
            f"a/{SOURCE_REL.as_posix()}",
            "/dev/null",
        )
        + diff(
            "",
            archived_text,
            "/dev/null",
            f"b/{ARCHIVE_REL.as_posix()}",
        )
        + diff(
            "",
            TARGET_CONTENT,
            "/dev/null",
            f"b/{TARGET_REL.as_posix()}",
        )
    )
    (run_dir / "planned-changes.diff").write_text(
        planned_diff,
        encoding="utf-8",
    )

    manifest = {
        "mode": mode,
        "state": "planned" if not args.apply else "applied",
        "source": SOURCE_REL.as_posix(),
        "archived_source": ARCHIVE_REL.as_posix(),
        "target": TARGET_REL.as_posix(),
        "source_sha256": sha256(source_text),
        "archived_sha256": sha256(archived_text),
        "target_sha256": sha256(TARGET_CONTENT),
        "review_document_modified": False,
        "activation_performed": False,
        "commit_created": False,
        "push_performed": False,
    }
    (run_dir / "revision-manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    if not args.apply:
        print("Dry run completed. No Vault files were changed.")
        print(f"Run report: {run_dir}")
        return 0

    recovery_path = run_dir / "recovery" / SOURCE_REL
    recovery_path.parent.mkdir(parents=True, exist_ok=True)
    recovery_path.write_text(source_text, encoding="utf-8")

    source_mode = source_path.stat().st_mode & 0o777
    created: list[Path] = []

    try:
        atomic_write(archive_path, archived_text, source_mode)
        created.append(archive_path)

        atomic_write(target_path, TARGET_CONTENT, source_mode)
        created.append(target_path)

        source_path.unlink()

        validate_process(
            archive_path.read_text(encoding="utf-8"),
            version="0.2",
            status="withdrawn",
            canonical_path=ARCHIVE_REL.as_posix(),
        )
        validate_process(
            target_path.read_text(encoding="utf-8"),
            version="0.3",
            status="draft",
            canonical_path=TARGET_REL.as_posix(),
        )
        if source_path.exists():
            raise RevisionError("Source draft still exists after migration.")

    except Exception:
        if not source_path.exists():
            atomic_write(source_path, source_text, source_mode)
        for path in created:
            path.unlink(missing_ok=True)
        raise

    report = {
        **manifest,
        "state": "applied",
        "recovery_path": str(recovery_path),
    }
    (run_dir / "revision-report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print("GOV-P01@0.3 created as draft.")
    print("GOV-P01@0.2 withdrawn and moved to Draft Processes/Archive.")
    print("The separate Governance Review was not modified.")
    print(f"Run report: {run_dir}")
    print("No activation, Git commit or push was performed.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RevisionError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
