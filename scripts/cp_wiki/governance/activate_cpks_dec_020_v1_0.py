#!/usr/bin/env python3
"""
Activate CPKS-DEC-020@1.0 and immediately activate CPKS-BL@0.43.

Canonical script location:
  /Users/cp/Developer/cpKnowledgeTools/scripts/cp_wiki/governance/
  activate_cpks_dec_020_v1_0.py

Default: dry run.
Use --apply to write changes.

Reports and recovery copies are written outside the Vault to:
  /Users/cp/Library/Application Support/cpKnowledgeTools/Runs/cp-wiki/governance/

No Git commit or push is performed.
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
    / "scripts/cp_wiki/governance/activate_cpks_dec_020_v1_0.py"
)
RUN_ROOT = Path(
    "/Users/cp/Library/Application Support/"
    "cpKnowledgeTools/Runs/cp-wiki/governance"
)

DEC_REL = Path(
    "Systems/cpKnowledgeSystem/Governance/Decisions/"
    "CPKS-DEC-020 Generated Reports, Execution Records and Script Lifecycle.md"
)
BASELINE_REL = Path(
    "Systems/cpKnowledgeSystem/Governance/System Control/"
    "CPKS-BL cpKnowledgeSystem Authoritative Baseline.md"
)
BASELINE_HISTORY_REL = Path(
    "Systems/cpKnowledgeSystem/Governance/Archive/Baselines/"
    "CPKS-BL@0.42 cpKnowledgeSystem Authoritative Baseline.md"
)

DECISION = '---\ndocument_type: decision_record\ndecision_id: CPKS-DEC-020\ntitle: Generated Reports, Execution Records and Script Lifecycle\nversion: "1.0"\nstatus: active\ndecision_type: tooling_and_information_lifecycle\nauthority_scope: system-wide\nsystem: cpKnowledgeSystem\nowner: Christoph Peters\napproved_by: Christoph Peters\napproved_at: 2026-07-26\neffective_from: 2026-07-26\ncreated: 2026-07-26\nrevised: 2026-07-26\nlanguage: de\ngoverned_by:\n  - CPKS-POL-GOV-AUTH\ndepends_on:\n  - CPKS-DEC-011\n  - CPKS-DEC-012\n  - CPKS-DEC-016\n  - CPKS-DEC-019\naligned_with:\n  - CPKS-BL\n  - CPKS-FWK-AIW\nvalidated_against:\n  - CPKS-POL-GOV-AUTH@1.0\n  - CPKS-BL@0.42\n  - CPKS-FWK-AIW@0.4\n  - CPKS-DEC-011@1.1\n  - CPKS-DEC-012@1.2\n  - CPKS-DEC-016@1.1\n  - CPKS-DEC-019@1.0\nreferences:\n  - CPW-SPEC-VLT@1.2\n  - CPKT-SPEC-ARCH@1.0\ncanonical_path: Systems/cpKnowledgeSystem/Governance/Decisions/CPKS-DEC-020 Generated Reports, Execution Records and Script Lifecycle.md\nsupersedes: []\n---\n\n# CPKS-DEC-020 – Generated Reports, Execution Records and Script Lifecycle\n\n## 1. Status\n\n**Aktiv und verbindlich**\n\nDiese Decision wurde durch den System-Owner ausdrücklich freigegeben und gilt ab dem 26. Juli 2026 systemweit für das `cpKnowledgeSystem`.\n\n## 2. Kontext\n\nIm Verlauf der Governance- und Vault-Entwicklung wurden ausführbare Python-Skripte über einen allgemeinen Download-Ordner bereitgestellt und von dort ausgeführt.\n\nTechnische Migrations- und Validierungsreports wurden unter folgenden Pfaden erzeugt:\n\n```text\n/Users/cp/Backups/cp-wiki/Migration Reports/\n/Users/cp/Backups/cp-wiki/Validation Reports/\n```\n\nDiese Praxis war als vorläufige Trennung vom kanonischen Vault bewusst gewählt. Sie verhindert, dass umfangreiche technische Laufdaten, Recovery-Kopien und temporäre Diffs ungeprüft in Obsidian und Git gelangen.\n\nDie konkrete Ablage unter `Backups/` ist jedoch semantisch falsch:\n\n- ein Report ist kein Backup,\n- ein Validierungslauf ist kein Snapshot,\n- ein Recovery-Artefakt ist nicht automatisch eine dauerhafte Sicherung,\n- ein Download-Ordner ist kein Entwicklungsrepository,\n- ein heruntergeladenes Skript besitzt dort keinen kontrollierten Lifecycle.\n\nZugleich sind unterschiedliche Artefaktfunktionen zu trennen:\n\n1. dauerhaft gepflegter Python-Code,\n2. revisionsrelevante einmalige Skripte,\n3. temporäre Transfer- und Staging-Skripte,\n4. menschlich gepflegte Entwicklungs- und Migrationsnachweise,\n5. reproduzierbare generierte Reports,\n6. technische Lauf-, Diagnose- und Recovery-Daten,\n7. echte Backups und Snapshots.\n\n## 3. Entscheidung\n\n### 3.1 Grundmodell\n\nFür Skripte, Reports und technische Ausführungsartefakte gilt:\n\n```text\nkanonischer ausführbarer Code\n→ cpKnowledgeTools Repository\n\nmenschlich gepflegter Entwicklungs- oder Migrationsnachweis\n→ zuständiger Development-Kontext im cp-wiki\n\nreproduzierbarer, menschenrelevanter Report\n→ Generated im cp-wiki\n\ntechnischer Lauf-, Diagnose- oder Recovery-Bestand\n→ externer cpKnowledgeTools Runtime-Bereich\n\nBackup oder Snapshot\n→ dedizierter Backup-Bereich\n\nallgemeiner Download-Ordner\n→ ausschließlich Transport und Übergabe\n```\n\nDiese Funktionen dürfen nicht dauerhaft in einem gemeinsamen Ordner vermischt werden.\n\n### 3.2 Kanonisches Repository für Python-Code\n\nDas kanonische Repository für Python-Code des `cpKnowledgeSystem` ist:\n\n```text\n/Users/cp/Developer/cpKnowledgeTools/\n```\n\nEs gelten mindestens folgende Zielbereiche:\n\n```text\n/Users/cp/Developer/cpKnowledgeTools/\n├── src/cp_knowledge_tools/\n└── scripts/\n    └── cp_wiki/\n        ├── governance/\n        ├── migrations/\n        └── validation/\n```\n\nDie Funktionen sind:\n\n| Zielbereich | Funktion |\n|---|---|\n| `src/cp_knowledge_tools/` | wiederverwendbare und testbare Produktivlogik |\n| `scripts/cp_wiki/governance/` | ausführbare Governance-Aktivierungs- und Administrationsskripte |\n| `scripts/cp_wiki/migrations/` | einmalige oder migrationsspezifische, revisionsrelevante Skripte |\n| `scripts/cp_wiki/validation/` | Validator-Prototypen und ausführbare Validierungswerkzeuge vor einer möglichen Überführung nach `src` |\n\nEin wiederverwendbarer Validator, Generator, Parser oder Migrationsmechanismus SOLL in das installierbare Paket unter `src/cp_knowledge_tools/` überführt und durch Tests abgesichert werden.\n\nEin einmaliges Skript DARF unter `scripts/` verbleiben, wenn seine Aufbewahrung für Audit, Provenienz, Reproduktion oder Ableitung späterer Werkzeuge sinnvoll ist.\n\n### 3.3 Kein kanonischer Code im Download-Ordner\n\nDer allgemeine Download-Ordner des Macs ist:\n\n- kein Repository,\n- kein kanonischer Skriptpfad,\n- kein Ausführungsstandard,\n- kein langfristiger Aufbewahrungsort,\n- kein revisionssicherer Entwicklungsbereich.\n\nEin über Chat, Browser oder anderes Transfersystem empfangenes Skript MUSS vor der Ausführung in den nach Funktion zuständigen Zielbereich überführt werden.\n\nNeue Anweisungen DÜRFEN NICHT voraussetzen oder empfehlen:\n\n```text\ncd ~/Downloads\npython <script>.py\n./<script>.py\n```\n\nDer physische Download darf technisch als Transport stattfinden. Er begründet keine kanonische Ablage und keine Ausführungsfreigabe.\n\n### 3.4 Verbindliche Ausführungsanweisungen\n\nAnweisungen für Python-Skripte müssen künftig mindestens enthalten:\n\n1. Klassifikation des Skripts,\n2. dauerhaften oder temporären Zielpfad,\n3. absoluten Repository- oder Runtime-Pfad,\n4. verwendeten Python-Interpreter oder die Projektumgebung,\n5. Dry-Run- und Apply-Modus, soweit unterstützt,\n6. erzeugte Reports und deren Zielbereich,\n7. Hinweis auf Commit und Push, sofern diese nicht automatisch erfolgen.\n\nFür Repository-Skripte lautet das Standardmuster:\n\n```bash\ncd "/Users/cp/Developer/cpKnowledgeTools"\n\n.venv/bin/python \\\n  scripts/cp_wiki/<category>/<script_name>.py\n```\n\nFür einen Apply-Lauf:\n\n```bash\ncd "/Users/cp/Developer/cpKnowledgeTools"\n\n.venv/bin/python \\\n  scripts/cp_wiki/<category>/<script_name>.py \\\n  --apply\n```\n\nEin Skript darf einen anderen Interpreter verwenden, wenn dies ausdrücklich dokumentiert und technisch begründet ist.\n\n### 3.5 Menschlich gepflegte Entwicklungsnachweise\n\nMenschlich gepflegte Pläne, Entscheidungen, Reviews und Abschlussnachweise liegen im zuständigen Development-Kontext des Vaults.\n\nBeispiele:\n\n```text\nDevelopment/cpKnowledgeSystem/Governance/\nDevelopment/cpKnowledgeSystem/Work Packages/\nDevelopment/cpKnowledgeTools/Migrations/\nDevelopment/cp-wiki Vault/\n```\n\nDie Wahl des konkreten Development-Kontexts richtet sich nach dem primären Veränderungsgegenstand.\n\nEin menschlich gepflegter Migrationsnachweis beschreibt mindestens bei Bedarf:\n\n- Zweck,\n- Scope,\n- Ausgangszustand,\n- Zielzustand,\n- eingesetztes Skript,\n- betroffene Artefakte,\n- Prüfergebnis,\n- Git-Commit oder Release,\n- offene Folgearbeiten.\n\nDer Development-Nachweis enthält nicht automatisch vollständige technische Laufdaten oder Recovery-Kopien.\n\n### 3.6 Generierte Reports im Vault\n\nAutomatisch erzeugte, reproduzierbare und für Menschen relevante Reports können unter `Generated/` geführt werden.\n\nKanonische Zielbereiche sind insbesondere:\n\n```text\nGenerated/Validation/\nGenerated/Reports/Migrations/\nGenerated/Reports/Governance/\n```\n\nDiese Reports sind:\n\n- automatisch erzeugt,\n- nicht normativ,\n- nicht manuell zu pflegen,\n- keine zweite Source of Truth,\n- aus kanonischen Quellen oder dokumentierten Läufen reproduzierbar.\n\nNicht jeder lokale Testlauf muss in den Vault übernommen werden.\n\nEin Report wird nur in `Generated/` übernommen, wenn er für mindestens einen der folgenden Zwecke benötigt wird:\n\n- menschliches Review,\n- Release-Nachweis,\n- publizierter Validierungsstand,\n- dokumentierte Migration,\n- nachvollziehbarer Governance-Change,\n- dauerhafte Systemdiagnose.\n\nDie Entscheidung über Git-Versionierung oder `.gitignore` erfolgt je Reportklasse.\n\n### 3.7 Externe technische Run-Daten\n\nTechnische Lauf-, Diagnose-, Diff- und Recovery-Daten werden außerhalb des Vaults unter folgendem Root geführt:\n\n```text\n/Users/cp/Library/Application Support/cpKnowledgeTools/Runs/cp-wiki/\n```\n\nZulässige Unterbereiche sind insbesondere:\n\n```text\n/Users/cp/Library/Application Support/cpKnowledgeTools/Runs/cp-wiki/\n├── governance/\n├── migrations/\n└── validation/\n```\n\nJeder konkrete Lauf SOLL ein eigenes zeitgestempeltes Verzeichnis besitzen.\n\nRecovery-Kopien liegen innerhalb des zugehörigen Laufverzeichnisses:\n\n```text\n<run-directory>/recovery/\n```\n\nDer externe Run-Bereich:\n\n- ist keine Source of Truth,\n- ist kein Backup-System,\n- darf bereinigt werden, wenn Aufbewahrungsanforderungen erfüllt sind,\n- darf große oder häufig neu erzeugte Dateien enthalten,\n- wird nicht automatisch in das Git-Repository des Vaults aufgenommen.\n\n### 3.8 Backup-Bereich\n\nDer Backup-Bereich ist echten Sicherungen vorbehalten.\n\nFür `cp-wiki` gilt insbesondere:\n\n```text\n/Users/cp/Backups/cp-wiki/Snapshots/\n```\n\nNeue Migrations-, Validierungs- und Aktivierungsreports DÜRFEN NICHT unter `/Users/cp/Backups/cp-wiki/` erzeugt werden.\n\nEine Recovery-Kopie eines einzelnen technischen Laufs ist ein Run-Artefakt und noch kein Vault-Backup.\n\n### 3.9 Temporäre Transfer- und Staging-Dateien\n\nEine Datei darf während der technischen Übergabe temporär außerhalb des Repositorys liegen.\n\nVor der Ausführung muss sie entweder:\n\n- in den zuständigen Repository-Pfad übernommen werden, oder\n- als ausdrücklich temporäres Run-Artefakt unter dem externen cpKnowledgeTools-Bereich geführt werden.\n\nTemporäre Staging-Dateien ohne langfristigen Wert können nach erfolgreicher Übernahme, Prüfung und Git-Sicherung gelöscht werden.\n\nEin temporäres Platzierungsskript muss nicht dauerhaft archiviert werden, wenn:\n\n1. das Zielartefakt korrekt im Vault vorliegt,\n2. die Änderung durch Git nachvollziehbar ist,\n3. keine wiederverwendbare Logik enthalten ist,\n4. kein Audit- oder Reproduktionsbedarf besteht.\n\n### 3.10 Bestehende externe Reportordner\n\nDie bestehenden Verzeichnisse:\n\n```text\n/Users/cp/Backups/cp-wiki/Migration Reports/\n/Users/cp/Backups/cp-wiki/Validation Reports/\n```\n\ngelten ab Aktivierung dieser Decision als **Legacy-Ablage**.\n\nFür sie gilt:\n\n- keine neuen Reports mehr erzeugen,\n- nicht unkontrolliert löschen,\n- Inhalte zunächst klassifizieren,\n- technische Run-Daten in den externen cpKnowledgeTools-Run-Bereich überführen,\n- dauerhaft relevante generierte Reports nach `Generated/` übernehmen,\n- menschlich gepflegte Nachweise in den zuständigen Development-Kontext überführen,\n- echte Recovery- oder Snapshot-Bestände nach ihrer tatsächlichen Funktion behandeln.\n\nDie physische Migration ist ein gesonderter kontrollierter Umsetzungsschritt.\n\n## 4. Lifecycle von Skripten\n\n### 4.1 Wiederverwendbare Werkzeuge\n\nWiederverwendbare Werkzeuge gehören nach:\n\n```text\nsrc/cp_knowledge_tools/\n```\n\nSie benötigen bei Aufnahme in das Produktpaket:\n\n- definierte API oder CLI,\n- Tests,\n- Fehlerbehandlung,\n- Dokumentation,\n- kontrollierte Abhängigkeiten.\n\n### 4.2 Revisionsrelevante Einmalskripte\n\nRevisionsrelevante Einmalskripte bleiben unter:\n\n```text\nscripts/cp_wiki/governance/\nscripts/cp_wiki/migrations/\n```\n\nSie sollen mindestens besitzen:\n\n- klaren Zweck,\n- feste Preconditions,\n- Dry Run, soweit praktisch,\n- idempotentes oder kontrolliert abbrechendes Verhalten,\n- Reportausgabe,\n- keine automatische Git-Veröffentlichung,\n- nachvollziehbare Zielpfade.\n\n### 4.3 Validator-Prototypen\n\nEin Validator-Prototyp darf zunächst unter:\n\n```text\nscripts/cp_wiki/validation/\n```\n\nliegen.\n\nBei wiederholter Nutzung oder normativer Relevanz muss geprüft werden, ob er nach:\n\n```text\nsrc/cp_knowledge_tools/\n```\n\nüberführt und durch Tests abgesichert wird.\n\n### 4.4 Entbehrliche Transfer-Skripte\n\nReine Transfer-, Platzierungs- oder Einmal-Hilfsskripte dürfen nach erfolgreicher Ausführung und nachvollziehbarem Commit gelöscht werden, sofern kein Audit- oder Reproduktionsbedarf besteht.\n\n## 5. Auswirkungen auf KI- und Assistenzanweisungen\n\nFür ChatGPT, OpenClaw-Agenten und andere KI-Systeme gilt:\n\n1. Der allgemeine Download-Ordner darf nicht als kanonischer Arbeitsbereich angegeben werden.\n2. Vor der Ausgabe eines ausführbaren Skripts muss dessen Lifecycle-Klasse bestimmt werden.\n3. Für jedes Skript muss ein Zielpfad unter `cpKnowledgeTools` oder im externen Run-Bereich genannt werden.\n4. Ausführungsbefehle müssen vom Repository- oder Runtime-Pfad ausgehen.\n5. Wiederverwendbare Logik darf nicht dauerhaft nur als Chat-Anhang oder Einzeldatei bestehen bleiben.\n6. Reports dürfen nicht pauschal unter `Backups/` erzeugt werden.\n7. Menschliche Nachweise, generierte Reports und technische Run-Daten müssen getrennt behandelt werden.\n8. Die Übergabe eines Skripts ist nicht mit seiner kanonischen Ablage oder Freigabe gleichzusetzen.\n\n## 6. Unmittelbare Konsequenzen\n\nNach Aktivierung gilt:\n\n1. Neue Aktivierungs- und Governance-Skripte werden unter `scripts/cp_wiki/governance/` geführt.\n2. Neue Migrationsskripte werden unter `scripts/cp_wiki/migrations/` geführt.\n3. Validator-Prototypen werden unter `scripts/cp_wiki/validation/` geführt.\n4. Wiederverwendbare Logik wird nach `src/cp_knowledge_tools/` überführt.\n5. Neue technische Reports werden unter `Application Support/cpKnowledgeTools/Runs/` erzeugt.\n6. Neue Reports werden nicht mehr unter `/Users/cp/Backups/cp-wiki/` erzeugt.\n7. Der Backup-Bereich bleibt Snapshots und echten Sicherungen vorbehalten.\n8. Künftige Ausführungsanweisungen beziehen sich nicht mehr auf den allgemeinen Download-Ordner.\n9. Bestehende Legacy-Reports und bisherige Skripte werden später kontrolliert klassifiziert und migriert.\n10. Die Vault Specification und die cpKnowledgeTools Architecture Specification werden bei ihrer nächsten Revision an diese Decision angepasst.\n\n## 7. Nicht entschieden\n\nDiese Decision legt noch nicht fest:\n\n- die Aufbewahrungsdauer einzelner Run-Klassen,\n- die konkrete `.gitignore`-Konfiguration,\n- das endgültige CLI-Design der Validatoren,\n- die vollständige Migration aller bisher erzeugten Skripte,\n- die vollständige Migration der beiden Legacy-Reportordner,\n- eine Pflicht, jeden lokalen Testreport dauerhaft zu behalten,\n- die Dateinamenkonvention für jeden künftigen Skripttyp.\n\nDiese Punkte werden bei konkreter Umsetzung spezifiziert.\n\n## 8. Entscheidungssatz\n\n> Ausführbarer Python-Code des `cpKnowledgeSystem` wird dauerhaft im Repository `cpKnowledgeTools` geführt. Wiederverwendbare Logik gehört in das installierbare Paket; revisionsrelevante Governance-, Migrations- und Validierungsskripte liegen unter `scripts/cp_wiki/`. Der allgemeine Download-Ordner ist ausschließlich ein technischer Transportweg und darf weder als kanonischer Skriptpfad noch als standardmäßiger Ausführungsort verwendet werden. Menschlich gepflegte Entwicklungsnachweise liegen im zuständigen `Development`-Kontext des `cp-wiki`; reproduzierbare menschenrelevante Reports liegen unter `Generated`; technische Lauf-, Diagnose- und Recovery-Daten liegen außerhalb des Vaults unter `Application Support/cpKnowledgeTools/Runs/`. Der Backup-Bereich bleibt echten Snapshots und Sicherungen vorbehalten.\n'


class ActivationError(RuntimeError):
    pass


def split_frontmatter(text: str) -> tuple[str, str]:
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        raise ActivationError("Missing YAML frontmatter.")
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            return "".join(lines[1:index]), "".join(lines[index + 1:])
    raise ActivationError("Unclosed YAML frontmatter.")


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
        raise ActivationError(f"Required field missing: {field}")
    return pattern.sub(f"{field}: {value}", frontmatter, count=1)


def list_values(frontmatter: str, field: str) -> list[str]:
    lines = frontmatter.splitlines()
    values: list[str] = []
    active = False
    for line in lines:
        top = re.match(r"^([A-Za-z0-9_]+):(?:\s*(.*))?$", line)
        if top and not line[0].isspace():
            active = top.group(1) == field
            raw = (top.group(2) or "").strip()
            if active and raw and raw not in {"[]", "null", "~"}:
                values.append(raw.strip("\"'"))
            continue
        if active:
            item = re.match(r"^\s*-\s*(.+?)\s*$", line)
            if item:
                values.append(item.group(1).strip().strip("\"'"))
    return values


def add_list_item(frontmatter: str, field: str, value: str) -> str:
    values = list_values(frontmatter, field)
    if value in values:
        return frontmatter

    lines = frontmatter.splitlines(keepends=True)
    start = None
    end = None
    for index, line in enumerate(lines):
        if re.match(rf"^{re.escape(field)}:\s*$", line.rstrip("\n")):
            start = index
            end = index + 1
            while end < len(lines) and (
                lines[end].startswith("  - ")
                or lines[end].strip() == ""
            ):
                if lines[end].strip() == "":
                    break
                end += 1
            break

    if start is None or end is None:
        raise ActivationError(f"List field missing: {field}")

    lines.insert(end, f"  - {value}\n")
    return "".join(lines)


def replace_list_single(
    frontmatter: str,
    field: str,
    expected_old: str,
    new_value: str,
) -> str:
    values = list_values(frontmatter, field)
    if values == [new_value]:
        return frontmatter
    if values != [expected_old]:
        raise ActivationError(
            f"{field} expected {[expected_old]!r}, got {values!r}"
        )

    pattern = re.compile(
        rf"(?m)^({re.escape(field)}:\s*\n)\s*-\s*"
        rf"{re.escape(expected_old)}\s*$"
    )
    if not pattern.search(frontmatter):
        raise ActivationError(f"Could not replace list field: {field}")
    return pattern.sub(
        lambda match: match.group(1) + f"  - {new_value}",
        frontmatter,
        count=1,
    )


def replace_required(text: str, old: str, new: str, label: str) -> str:
    if new in text and old not in text:
        return text
    count = text.count(old)
    if count != 1:
        raise ActivationError(
            f"{label}: expected exactly one occurrence, found {count}."
        )
    return text.replace(old, new, 1)


def insert_before_required(
    text: str,
    marker: str,
    insertion: str,
    label: str,
) -> str:
    if insertion.strip() in text:
        return text
    count = text.count(marker)
    if count != 1:
        raise ActivationError(
            f"{label}: marker expected exactly once, found {count}."
        )
    return text.replace(marker, insertion.rstrip() + "\n\n" + marker, 1)


def read(relative: Path) -> str:
    path = VAULT / relative
    if not path.is_file():
        raise ActivationError(f"Required file missing: {relative}")
    return path.read_text(encoding="utf-8")


def historical_baseline(active_text: str) -> str:
    fm, body = split_frontmatter(active_text)
    fm = replace_scalar(fm, "status", "superseded")
    fm = replace_scalar(
        fm,
        "canonical_path",
        BASELINE_HISTORY_REL.as_posix(),
    )
    return join_frontmatter(fm, body)


def build_baseline_043(active_text: str) -> str:
    fm, body = split_frontmatter(active_text)

    if scalar(fm, "baseline_id") != "CPKS-BL":
        raise ActivationError("Unexpected baseline_id.")
    if scalar(fm, "version") != "0.42":
        raise ActivationError("Expected active baseline version 0.42.")
    if scalar(fm, "status") != "active":
        raise ActivationError("Expected active baseline status.")

    fm = replace_scalar(fm, "version", '"0.43"')
    fm = replace_scalar(fm, "approved_at", "2026-07-26")
    fm = replace_scalar(fm, "effective_from", "2026-07-26")
    fm = replace_scalar(fm, "revised", "2026-07-26")
    fm = add_list_item(fm, "aligned_with", "CPKS-DEC-020")
    fm = add_list_item(fm, "validated_against", "CPKS-DEC-020@1.0")
    fm = replace_list_single(
        fm,
        "supersedes",
        "CPKS-BL@0.41",
        "CPKS-BL@0.42",
    )

    fm = replace_required(
        fm,
        "  - CPKS-BL@0.41\n",
        "  - CPKS-BL@0.42\n",
        "baseline references",
    )

    body = replace_required(
        body,
        "Diese Datei ist die aktive systemweite Authoritative Baseline "
        "`CPKS-BL@0.42`.",
        "Diese Datei ist die aktive systemweite Authoritative Baseline "
        "`CPKS-BL@0.43`.",
        "baseline header version",
    )
    body = replace_required(
        body,
        "Sie ersetzt `CPKS-BL@0.41`.",
        "Sie ersetzt `CPKS-BL@0.42`.",
        "baseline header predecessor",
    )
    body = replace_required(
        body,
        "Diese Baseline bildet den nachgewiesenen Governance-Zustand nach "
        "Aktivierung von `CPKS-POL-GOV-AUTH@1.0`, `CPKS-DEC-015@1.1` "
        "und `CPKS-DEC-016@1.1` ab.",
        "Diese Baseline bildet den nachgewiesenen Governance-Zustand nach "
        "Aktivierung von `CPKS-DEC-020@1.0` ab und führt die bereits "
        "aktiven Governance-Artefakte fort.",
        "baseline header state",
    )

    decision_row = (
        "| `CPKS-DEC-020` | `1.0` | Reportablage, technische "
        "Run-Daten und Lifecycle ausführbarer Skripte |"
    )
    body = insert_before_required(
        body,
        "\n## 10.3 Historische Decision Records",
        decision_row,
        "active decision table",
    )

    body = replace_required(
        body,
        "└── CPKS-BL@0.41 cpKnowledgeSystem Authoritative Baseline.md",
        "├── CPKS-BL@0.41 cpKnowledgeSystem Authoritative Baseline.md\n"
        "└── CPKS-BL@0.42 cpKnowledgeSystem Authoritative Baseline.md",
        "baseline archive inventory",
    )

    decision_status = """## 11.7 CPKS-DEC-020@1.0

Aktiv beschlossen sind:

- `cpKnowledgeTools` als kanonisches Repository für ausführbaren Python-Code,
- `scripts/cp_wiki/governance/`, `migrations/` und `validation/` als
  Skriptbereiche,
- `Generated/` für reproduzierbare menschenrelevante Reports,
- `Application Support/cpKnowledgeTools/Runs/` für technische Lauf-,
  Diagnose- und Recovery-Daten,
- `Backups/cp-wiki/Snapshots/` ausschließlich für echte Sicherungen,
- Ausschluss des allgemeinen Download-Ordners als kanonischer
  Ausführungs- oder Ablageort.

Noch offen sind:

- kontrollierte Migration der bisherigen externen Reportordner,
- Klassifikation und Überführung bisheriger Skripte,
- Aufbewahrungsregeln für technische Run-Klassen,
- Umsetzung in Vault- und cpKnowledgeTools-Spezifikationen."""

    body = insert_before_required(
        body,
        "# 12. Vault Specification",
        decision_status,
        "decision implementation section",
    )

    body = replace_required(
        body,
        "Policy 1.0 und Decisions bis 019 aktiv",
        "Policy 1.0 und Decisions bis 020 aktiv",
        "system status",
    )

    section_20_start = body.find("# 20. Aktivierungsnachweis")
    section_21_start = body.find("# 21. Maschinenlesbare Kurzfassung")
    if section_20_start < 0 or section_21_start < 0:
        raise ActivationError("Baseline activation sections not found.")

    new_section_20 = """# 20. Aktivierungsnachweis

`CPKS-BL@0.43` wurde am 26. Juli 2026 durch den Owner Christoph Peters ausdrücklich freigegeben.

Die Aktivierung erfolgt unmittelbar nach `CPKS-DEC-020@1.0` und bildet diesen Zustand ab.

Für die Aktivierung wurden bestätigt:

- [x] Decision `CPKS-DEC-020@1.0` vollständig erstellt
- [x] Zielstatus `active` ausdrücklich bestätigt
- [x] kanonischer aktiver Decision-Pfad festgelegt
- [x] neue Skript- und Reportablage verbindlich entschieden
- [x] allgemeiner Download-Ordner als Ausführungsstandard ausgeschlossen
- [x] Baseline-Zielversion `0.43` bestätigt
- [x] `supersedes: CPKS-BL@0.42` gesetzt
- [x] Archivziel für `CPKS-BL@0.42` festgelegt
- [x] physische Migration bestehender Legacy-Reports gesondert zurückgestellt
- [x] Commit und Push bleiben getrennte nachgelagerte Handlungen

"""
    body = (
        body[:section_20_start]
        + new_section_20
        + body[section_21_start:]
    )

    body = replace_required(
        body,
        'active_version: "0.42"',
        'active_version: "0.43"',
        "machine baseline version",
    )
    body = replace_required(
        body,
        "supersedes: CPKS-BL@0.41",
        "supersedes: CPKS-BL@0.42",
        "machine baseline predecessor",
    )
    body = insert_before_required(
        body,
        "\n  implementation_status:",
        "    - CPKS-DEC-020@1.0",
        "machine active decision list",
    )
    body = insert_before_required(
        body,
        "\nmanaged_artifacts:",
        "    CPKS-DEC-020: normative_active_migration_pending",
        "machine implementation status",
    )

    execution_block = """artifact_execution:
  canonical_repository: /Users/cp/Developer/cpKnowledgeTools/
  script_root: /Users/cp/Developer/cpKnowledgeTools/scripts/cp_wiki/
  runtime_root: /Users/cp/Library/Application Support/cpKnowledgeTools/Runs/cp-wiki/
  backup_root: /Users/cp/Backups/cp-wiki/Snapshots/
  downloads_canonical: false
"""
    body = insert_before_required(
        body,
        "\nsource_of_truth:",
        execution_block,
        "machine execution block",
    )

    old_short = (
        "> `cpKnowledgeSystem` ist das übergeordnete Wissens- und "
        "Agentensystem."
    )
    if old_short not in body:
        raise ActivationError("Short-form baseline marker not found.")
    body = body.replace(
        old_short,
        "> `cpKnowledgeSystem` ist das übergeordnete Wissens- und "
        "Agentensystem. Ausführbarer Python-Code wird im Repository "
        "`cpKnowledgeTools` geführt; technische Run-Daten liegen unter "
        "`Application Support/cpKnowledgeTools/Runs/`, und der allgemeine "
        "Download-Ordner ist kein kanonischer Ausführungsort.",
        1,
    )

    return join_frontmatter(fm, body)


def validate_decision(text: str) -> None:
    fm, _ = split_frontmatter(text)
    expected = {
        "document_type": "decision_record",
        "decision_id": "CPKS-DEC-020",
        "version": "1.0",
        "status": "active",
        "canonical_path": DEC_REL.as_posix(),
    }
    for field, wanted in expected.items():
        actual = scalar(fm, field)
        if actual != wanted:
            raise ActivationError(
                f"Decision {field} expected {wanted!r}, got {actual!r}"
            )


def validate_baseline(
    text: str,
    *,
    version: str,
    status: str,
    canonical_path: str,
    supersedes: str,
) -> None:
    fm, _ = split_frontmatter(text)
    expected = {
        "document_type": "baseline",
        "baseline_id": "CPKS-BL",
        "version": version,
        "status": status,
        "canonical_path": canonical_path,
    }
    for field, wanted in expected.items():
        actual = scalar(fm, field)
        if actual != wanted:
            raise ActivationError(
                f"Baseline {field} expected {wanted!r}, got {actual!r}"
            )
    if list_values(fm, "supersedes") != [supersedes]:
        raise ActivationError("Unexpected baseline supersedes value.")


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def diff(before: str, after: str, before_name: str, after_name: str) -> str:
    return "".join(
        difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=before_name,
            tofile=after_name,
        )
    )


def atomic_write(path: Path, content: str, mode: int = 0o644) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".activation.tmp",
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


def assert_canonical_script_location() -> None:
    actual = Path(__file__).resolve()
    expected = CANONICAL_SCRIPT.resolve()
    if actual != expected:
        raise ActivationError(
            "Script is not in its canonical repository location.\n"
            f"Expected: {expected}\n"
            f"Actual:   {actual}"
        )


def validate_final_state() -> dict[str, str]:
    decision = read(DEC_REL)
    baseline = read(BASELINE_REL)
    history = read(BASELINE_HISTORY_REL)

    validate_decision(decision)
    validate_baseline(
        baseline,
        version="0.43",
        status="active",
        canonical_path=BASELINE_REL.as_posix(),
        supersedes="CPKS-BL@0.42",
    )
    validate_baseline(
        history,
        version="0.42",
        status="superseded",
        canonical_path=BASELINE_HISTORY_REL.as_posix(),
        supersedes="CPKS-BL@0.41",
    )

    if "CPKS-DEC-020@1.0" not in baseline:
        raise ActivationError("Baseline does not contain DEC-020@1.0.")
    if "downloads_canonical: false" not in baseline:
        raise ActivationError("Baseline lacks downloads rule.")

    return {
        "decision_sha256": sha256(decision),
        "baseline_active_sha256": sha256(baseline),
        "baseline_history_sha256": sha256(history),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    assert_canonical_script_location()
    validate_decision(DECISION)

    timestamp = dt.datetime.now().astimezone().strftime("%Y%m%dT%H%M%S%z")
    mode = "apply" if args.apply else "dry-run"
    run_dir = (
        RUN_ROOT
        / f"{timestamp}-activate-CPKS-DEC-020-and-CPKS-BL-0.43-{mode}"
    )
    run_dir.mkdir(parents=True, exist_ok=False)

    decision_path = VAULT / DEC_REL
    baseline_path = VAULT / BASELINE_REL
    history_path = VAULT / BASELINE_HISTORY_REL

    if decision_path.exists():
        current_decision = decision_path.read_text(encoding="utf-8")
        current_baseline = read(BASELINE_REL)
        fm, _ = split_frontmatter(current_baseline)
        if (
            current_decision == DECISION
            and scalar(fm, "version") == "0.43"
            and scalar(fm, "status") == "active"
        ):
            hashes = validate_final_state()
            (run_dir / "activation-report.json").write_text(
                json.dumps(
                    {
                        "mode": mode,
                        "state": "already_final",
                        "validation": "passed",
                        "hashes": hashes,
                        "commit_created": False,
                        "push_performed": False,
                    },
                    indent=2,
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            print("Final state already exists and passed validation.")
            print(f"Run report: {run_dir}")
            return 0
        raise ActivationError(
            "CPKS-DEC-020 already exists in an unexpected state."
        )

    if history_path.exists():
        raise ActivationError(
            f"Baseline history target already exists: {BASELINE_HISTORY_REL}"
        )

    baseline_before = read(BASELINE_REL)
    baseline_fm, _ = split_frontmatter(baseline_before)
    if not (
        scalar(baseline_fm, "version") == "0.42"
        and scalar(baseline_fm, "status") == "active"
    ):
        raise ActivationError(
            "Expected CPKS-BL@0.42 as active starting state."
        )

    baseline_history = historical_baseline(baseline_before)
    baseline_after = build_baseline_043(baseline_before)

    validate_baseline(
        baseline_history,
        version="0.42",
        status="superseded",
        canonical_path=BASELINE_HISTORY_REL.as_posix(),
        supersedes="CPKS-BL@0.41",
    )
    validate_baseline(
        baseline_after,
        version="0.43",
        status="active",
        canonical_path=BASELINE_REL.as_posix(),
        supersedes="CPKS-BL@0.42",
    )

    planned_diff = (
        diff(
            "",
            DECISION,
            "/dev/null",
            f"b/{DEC_REL.as_posix()}",
        )
        + diff(
            baseline_before,
            baseline_after,
            f"a/{BASELINE_REL.as_posix()}",
            f"b/{BASELINE_REL.as_posix()}",
        )
        + diff(
            "",
            baseline_history,
            "/dev/null",
            f"b/{BASELINE_HISTORY_REL.as_posix()}",
        )
    )
    (run_dir / "planned-changes.diff").write_text(
        planned_diff,
        encoding="utf-8",
    )
    (run_dir / "activation-manifest.json").write_text(
        json.dumps(
            {
                "mode": mode,
                "decision": "CPKS-DEC-020@1.0",
                "baseline": "CPKS-BL@0.43",
                "changes": [
                    {"action": "create", "path": DEC_REL.as_posix()},
                    {
                        "action": "replace",
                        "path": BASELINE_REL.as_posix(),
                    },
                    {
                        "action": "create",
                        "path": BASELINE_HISTORY_REL.as_posix(),
                    },
                ],
                "legacy_report_directories_moved": False,
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
        print(f"Run report: {run_dir}")
        return 0

    recovery_dir = run_dir / "recovery"
    recovery_path = recovery_dir / BASELINE_REL
    recovery_path.parent.mkdir(parents=True, exist_ok=True)
    recovery_path.write_text(baseline_before, encoding="utf-8")

    baseline_mode = baseline_path.stat().st_mode & 0o777
    created: list[Path] = []

    try:
        atomic_write(decision_path, DECISION)
        created.append(decision_path)

        atomic_write(
            history_path,
            baseline_history,
            baseline_mode,
        )
        created.append(history_path)

        atomic_write(
            baseline_path,
            baseline_after,
            baseline_mode,
        )

        hashes = validate_final_state()

    except Exception:
        atomic_write(
            baseline_path,
            baseline_before,
            baseline_mode,
        )
        for path in created:
            path.unlink(missing_ok=True)
        raise

    (run_dir / "activation-report.json").write_text(
        json.dumps(
            {
                "mode": "apply",
                "state": "activated",
                "validation": "passed",
                "decision": "CPKS-DEC-020@1.0",
                "baseline": "CPKS-BL@0.43",
                "recovery_path": str(recovery_dir),
                "hashes": hashes,
                "legacy_report_directories_moved": False,
                "commit_created": False,
                "push_performed": False,
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    print("CPKS-DEC-020@1.0 and CPKS-BL@0.43 activated.")
    print(f"Run report: {run_dir}")
    print("Legacy report directories were not moved.")
    print("No Git commit or push was performed.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ActivationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
