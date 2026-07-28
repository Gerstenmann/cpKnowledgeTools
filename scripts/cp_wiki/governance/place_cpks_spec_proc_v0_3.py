#!/usr/bin/env python3
"""
Place CPKS-SPEC-PROC@0.3 as a draft in cp-wiki.

Canonical script location:
  /Users/cp/Developer/cpKnowledgeTools/scripts/cp_wiki/governance/
  place_cpks_spec_proc_v0_3.py

Default: dry run. Use --apply to create the draft.
No activation, Git commit or push is performed.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile

VAULT = Path("/Users/cp/Documents/cp-wiki")
TOOLS = Path("/Users/cp/Developer/cpKnowledgeTools")
CANONICAL_SCRIPT = TOOLS / "scripts/cp_wiki/governance/place_cpks_spec_proc_v0_3.py"
RUN_ROOT = Path(
    "/Users/cp/Library/Application Support/"
    "cpKnowledgeTools/Runs/cp-wiki/governance"
)
TARGET_REL = Path(
    "Development/cpKnowledgeSystem/Specifications/"
    "CPKS-SPEC-PROC@0.3 Process Description Specification.md"
)
CONTENT = '---\ndocument_type: specification\nspecification_id: CPKS-SPEC-PROC\nformer_ids:\n  - CPKS-SPEC-PROCESS-DESCRIPTION\ntitle: Process Description Specification\nversion: "0.3"\nstatus: draft\nauthority_scope: vault-wide\nsystem: cpKnowledgeSystem\nowner: Christoph Peters\ncreated: 2026-07-23\nrevised: 2026-07-26\nlanguage: de\ngoverned_by:\n  - CPKS-POL-GOV-AUTH\ndepends_on:\n  - CPKS-DEC-012\n  - CPKS-DEC-017\n  - CPKS-DEC-019\naligned_with:\n  - CPKS-BL\n  - CPKS-FWK-AIW\nimplements_decisions:\n  - CPKS-DEC-017@1.0\nvalidated_against:\n  - CPKS-POL-GOV-AUTH@1.0\n  - CPKS-BL@0.43\n  - CPKS-FWK-AIW@0.4\n  - CPKS-SPEC-ART@0.2\nreferences:\n  - CPKS-SPEC-PROC@0.2\ncanonical_path: Development/cpKnowledgeSystem/Specifications/CPKS-SPEC-PROC@0.3 Process Description Specification.md\n---\n\n# CPKS-SPEC-PROC – Process Description Specification\n\n## 1. Status\n\n**Draft zur fachlichen und technischen Prüfung**\n\nDiese Fassung überarbeitet den nie aktivierten Draft `CPKS-SPEC-PROC@0.2`. Sie ersetzt ihn nicht im Sinne einer Supersession, da Version 0.2 nie aktiv war.\n\nVersion 0.3 harmonisiert die Prozessbeschreibung mit:\n\n- `CPKS-POL-GOV-AUTH@1.0`,\n- dem hybriden Referenzmodell,\n- dem Managed-Artifact- und Lifecycle-Modell,\n- `CPKS-SPEC-ART@0.2`,\n- `CPKS-DEC-017@1.0`.\n\n## 2. Zweck\n\nDiese Spezifikation definiert den verbindlichen Aufbau kanonischer Prozessbeschreibungen im `cp-wiki`.\n\nSie konkretisiert insbesondere:\n\n- Prozessidentität,\n- Prozessdomänen,\n- aktive Prozessablage,\n- Prozesspakete,\n- Unterprozesse,\n- wiederverwendbare Prozesse,\n- prozessspezifische Metadaten,\n- verbindliche Dokumentstruktur,\n- Prozessvalidierung.\n\nSie führt kein manuell gepflegtes Process Register ein.\n\n## 3. Verhältnis zu CPKS-SPEC-ART\n\n`CPKS-SPEC-ART` definiert dokumenttypübergreifend:\n\n- Managed-Artifact-Identität,\n- allgemeine Pflichtfelder,\n- ID-, Versions- und Statusformate,\n- Referenzformen,\n- Dateinamen,\n- `canonical_path`,\n- Lifecycle-Zonen,\n- Scanprofile,\n- allgemeine Fehlerklassen.\n\nDiese Spezifikation definiert ergänzend nur die prozessspezifischen Anforderungen.\n\nBei einem Widerspruch gilt:\n\n```text\naktive Policy und Decisions\n→ aktive CPKS-SPEC-ART\n→ aktive CPKS-SPEC-PROC\n→ Prozessartefakt\n```\n\nSolange beide Spezifikationen Drafts sind, muss ein Widerspruch vor einer Aktivierung konsolidiert werden.\n\n## 4. Geltungsbereich\n\nDiese Spezifikation gilt für Dateien mit:\n\n```yaml\ndocument_type: process\n```\n\nSie gilt für alle Prozessdomänen unter:\n\n```text\nProcesses/\n```\n\nSie gilt nicht für:\n\n- `process_support`,\n- allgemeine Checklisten,\n- Templates,\n- Reports,\n- Arbeitsnotizen,\n- Work Packages,\n- Prozessentwürfe ohne eigenständige `process_id`.\n\nBegleitdateien werden nur in Abschnitt 13 geregelt.\n\n## 5. Prozessidentität\n\n### 5.1 Typabhängige Identität\n\nEin Prozess MUSS verwenden:\n\n```yaml\ndocument_type: process\nprocess_id: GOV-P01\n```\n\n`process_id` ist die stabile Identität des Prozesses.\n\nTitel, Dateiname, Ordner und Pfad dürfen geändert werden, ohne die Prozessidentität zu ändern.\n\n### 5.2 Prozess-ID\n\nEine Prozess-ID folgt:\n\n```regex\n^[A-Z][A-Z0-9]*-P[0-9]{2,3}$\n```\n\nBeispiele:\n\n```text\nGOV-P01\nKM-P01\nDEV-P01\nOPS-P01\n```\n\nNicht zulässig:\n\n```text\nP01\nKM-01\nKM-P1\nKM-P01.1\n```\n\nDie Beziehung zu einem übergeordneten Prozess wird nicht in die ID codiert.\n\n### 5.3 Eindeutigkeit\n\nEine `process_id` MUSS vaultweit eindeutig sein.\n\nFür eine Kombination aus `process_id` und `version` darf höchstens eine kanonische Prozessdatei existieren.\n\nFür eine `process_id` darf höchstens eine aktive Fassung existieren.\n\n## 6. Prozessdomäne\n\nJeder Prozess MUSS ein Feld `process_domain` führen.\n\nBeispiele:\n\n| Ordner | `process_domain` | ID-Präfix |\n|---|---|---|\n| `Governance` | `governance` | `GOV` |\n| `Knowledge Management` | `knowledge_management` | `KM` |\n| `Development` | `development` | `DEV` |\n| `Operations` | `operations` | `OPS` |\n| `Customer Management` | `customer_management` | noch festzulegen |\n\n`process_domain` bezeichnet den primären fachlichen Zweck.\n\nEin Prozess mit mehreren Anwendungsbereichen wird nicht kopiert. Zusätzliche Anwendungsbereiche können über `applies_to` dokumentiert werden.\n\nNeue Prozessdomänen und ID-Präfixe dürfen nicht pro Datei improvisiert werden.\n\n## 7. Lifecycle und Ablage\n\n### 7.1 Aktive Prozesse\n\nDer kanonische aktive Prozessbestand liegt rekursiv unter:\n\n```text\nProcesses/\n```\n\nEine Datei unter `Processes/` wird nur dann als aktiver kanonischer Prozess gezählt, wenn sie mindestens besitzt:\n\n```yaml\ndocument_type: process\nstatus: active\n```\n\n`Processes/` enthält keine Drafts oder Proposals.\n\n### 7.2 Nicht aktive Prozessfassungen\n\nNicht aktivierte Prozessfassungen liegen im zuständigen Development-Kontext und verwenden versionierte Dateinamen.\n\nFür Governance-Prozesse gilt:\n\n```text\nDevelopment/cpKnowledgeSystem/Governance/Draft Processes/\n```\n\nDie endgültigen Development-Pfade weiterer Prozessdomänen werden in der Vault Specification oder einer zuständigen Folgefassung festgelegt.\n\n### 7.3 Historische Prozessfassungen\n\nFrühere aktive Prozessfassungen erhalten grundsätzlich `status: superseded` und werden im lokalen Archiv ihrer Prozessdomäne aufbewahrt.\n\nBeispiel:\n\n```text\nProcesses/Governance/Archive/\nGOV-P01@0.9 Governance Artifact Consolidation and Impact Review.md\n```\n\nEin nie aktivierter Draft darf nicht `superseded` werden.\n\n### 7.4 Zurückgezogene Prozess-Drafts\n\nEine nie aktivierte Prozessfassung darf den Status:\n\n```text\nwithdrawn\n```\n\nverwenden, wenn der Owner die Fassung vor Aktivierung zurückzieht.\n\nEin `withdrawn` Prozess-Draft:\n\n- war nie verbindlich,\n- darf nicht `superseded` sein,\n- gehört zum abgeschlossenen Development-Lifecycle,\n- wird im lokalen `Archive/`-Bereich seines Development-Kontexts aufbewahrt,\n- wird mit dem eingeschränkten Profil `closed_development_managed` geprüft.\n\nFür Governance-Prozesse lautet der Zielbereich:\n\n```text\nDevelopment/cpKnowledgeSystem/Governance/Draft Processes/Archive/\n```\n\nFür andere Prozessdomänen wird entsprechend ein lokaler `Archive/`-Bereich im zuständigen Development-Kontext verwendet.\n\nDie Datei behält den versionierten Namen:\n\n```text\n<process_id>@<version> <title>.md\n```\n\n### 7.5 Prozessstatus\n\nFür kanonische Prozessbeschreibungen sind zulässig:\n\n```text\ndraft\nproposed\nactive\nsuperseded\ndeprecated\narchived\nwithdrawn\n```\n\nDabei gilt:\n\n- `withdrawn` nur für nie aktivierte Prozessfassungen,\n- `identified` nicht als Lifecycle-Status,\n- `rejected` nicht als Status der Prozessbeschreibung selbst,\n- `completed` und `cancelled` nicht als Status einer dauerhaft gültigen Prozessbeschreibung.\n\nEin lediglich identifizierter Prozessgegenstand ist noch keine kanonische Prozessbeschreibung. Eine abgelehnte Prozessidee bleibt in ihrem Proposal-, Decision-, Review- oder Work-Package-Kontext dokumentiert.\n\n## 8. Dateinamen und Pfade\n\n### 8.1 Aktive Einzeldatei\n\n```text\nProcesses/<Domain>/<process_id> <title>.md\n```\n\nBeispiel:\n\n```text\nProcesses/Governance/GOV-P01 Governance Artifact Consolidation and Impact Review.md\n```\n\n### 8.2 Nicht aktive Einzeldatei\n\n```text\n<Development Context>/<process_id>@<version> <title>.md\n```\n\n### 8.3 Prozesspaket\n\nEin Prozesspaket verwendet:\n\n```text\nProcesses/<Domain>/<process_id> <title>/\n└── <process_id> <title>.md\n```\n\nOrdnername und Hauptdateiname ohne `.md` müssen übereinstimmen.\n\n### 8.4 `canonical_path`\n\n`canonical_path` muss dem tatsächlichen Pfad entsprechen.\n\nBei Aktivierung, Archivierung oder Umbenennung wird das Feld aktualisiert.\n\n## 9. YAML-Header\n\n### 9.1 Allgemeine Pflichtfelder\n\nJede Prozessbeschreibung MUSS mindestens enthalten:\n\n```yaml\ndocument_type: process\nprocess_id:\ntitle:\nversion:\nstatus:\nprocess_domain:\nowner:\ncreated:\nrevised:\ncanonical_path:\n```\n\nFür aktive Prozesse gelten zusätzlich:\n\n```yaml\napproved_by:\napproved_at:\neffective_from:\n```\n\n### 9.2 Prozessspezifische optionale Felder\n\nZulässige prozessspezifische Felder sind:\n\n```yaml\napplies_to:\nparent_process:\ninvokes_processes:\n```\n\n### 9.3 Referenzform prozessspezifischer Beziehungen\n\n`parent_process` ist eine stabile skalare Prozess-ID ohne Version:\n\n```yaml\nparent_process: KM-P01\n```\n\n`invokes_processes` ist eine Liste stabiler Prozess-IDs ohne Version:\n\n```yaml\ninvokes_processes:\n  - GOV-P05\n```\n\nDiese Felder beschreiben dauerhafte Beziehungen zu Prozesslinien.\n\nKonkrete geprüfte Fassungen werden getrennt in `validated_against` dokumentiert.\n\n### 9.4 Allgemeine Governance-Beziehungen\n\nAllgemeine Beziehungen verwenden das Referenzmodell aus `CPKS-SPEC-ART`.\n\nBeispiel:\n\n```yaml\ngoverned_by:\n  - CPKS-POL-GOV-AUTH\n\ndepends_on:\n  - CPKS-DEC-017\n\nimplements_decisions:\n  - CPKS-DEC-017@1.0\n\nvalidated_against:\n  - CPKS-POL-GOV-AUTH@1.0\n```\n\n## 10. Verbindlicher Dokumentaufbau\n\nEine vollständige Prozessbeschreibung verwendet folgende Hauptabschnitte:\n\n```text\n# <process_id> – <title>\n\n## 1. Zweck\n## 2. Geltungsbereich\n## 3. Auslöser\n## 4. Voraussetzungen und Inputs\n## 5. Rollen und Verantwortlichkeiten\n## 6. Prozessablauf\n## 7. Entscheidungs- und Stop-Bedingungen\n## 8. Fehler- und Ausnahmebehandlung\n## 9. Outputs und Nachweise\n## 10. Abschlusskriterien\n## 11. Zugehörige Prozesse und Artefakte\n```\n\nAlle Hauptabschnitte müssen vorhanden sein.\n\nIst ein Abschnitt im konkreten Prozess fachlich nicht anwendbar, wird eingetragen:\n\n```text\nNicht anwendbar.\n```\n\n## 11. Inhaltliche Anforderungen\n\n### 11.1 Zweck\n\nDer Zweck beschreibt knapp:\n\n- welches Problem der Prozess löst,\n- welches Ergebnis er sicherstellt,\n- warum ein wiederholbarer Prozess erforderlich ist.\n\n### 11.2 Geltungsbereich\n\nDer Geltungsbereich muss eingeschlossene und ausgeschlossene Fälle erkennbar machen.\n\n### 11.3 Auslöser\n\nDer Auslöser muss ein konkretes Ereignis oder eine prüfbare Bedingung sein.\n\nUnpräzise Auslöser wie `bei Bedarf` sind nur zulässig, wenn sie operationalisiert werden.\n\n### 11.4 Voraussetzungen und Inputs\n\nVoraussetzungen und Inputs müssen vor dem ersten Prozessschritt prüfbar sein.\n\n### 11.5 Rollen und Verantwortlichkeiten\n\nOperative Rollen werden unabhängig von konkreten Personennamen beschrieben.\n\nDas Frontmatter-Feld `owner` bezeichnet den Owner des Prozessartefakts und ersetzt nicht die operativen Rollen.\n\n### 11.6 Prozessablauf\n\nDer Ablauf wird als nummerierte Tabelle geführt:\n\n```markdown\n| Schritt | Verantwortliche Rolle | Tätigkeit | Ergebnis oder Kontrolle |\n|---:|---|---|---|\n```\n\nJeder Schritt muss eine ausführende Rolle, eine konkrete Tätigkeit und ein Ergebnis oder einen Kontrollpunkt erkennen lassen.\n\n### 11.7 Entscheidungs- und Stop-Bedingungen\n\nStop-Bedingungen müssen eindeutig sein.\n\nBei Eintritt einer Stop-Bedingung darf eine ausführende Person oder ein Agent nicht ohne autorisierte Entscheidung fortfahren.\n\n### 11.8 Fehler- und Ausnahmebehandlung\n\nErwartbare Fehler erhalten eine geregelte Reaktion und gegebenenfalls eine Eskalation.\n\nNicht abgedeckte Fälle benötigen mindestens eine allgemeine Stop- oder Eskalationsregel.\n\n### 11.9 Outputs und Nachweise\n\nOutputs und Nachweise müssen Ablage oder Empfänger sowie Pflichtstatus erkennen lassen.\n\nGenerierte Reports bleiben nicht normative Ableitungen.\n\n### 11.10 Abschlusskriterien\n\nAbschlusskriterien müssen überprüfbar sein.\n\n### 11.11 Zugehörige Prozesse und Artefakte\n\nDieser Abschnitt verweist nur auf tatsächlich relevante Artefakte und wiederholt deren vollständigen Inhalt nicht.\n\n## 12. Unterprozesse und Wiederverwendung\n\n### 12.1 Unterprozess\n\nEin Unterprozess ist ein eigenständiger Prozess mit:\n\n- eigener `process_id`,\n- eigener Version,\n- eigenem Status,\n- eigener Prozessdatei,\n- stabilem `parent_process`.\n\nHierarchie wird nicht aus Ordnerstruktur oder ID-Nummerierung abgeleitet.\n\n### 12.2 Wiederverwendbarer Prozess\n\nEin von mehreren Prozessen verwendeter Prozess bleibt eigenständig und besitzt kein künstliches `parent_process`.\n\nAufrufende Prozesse verwenden `invokes_processes`.\n\n### 12.3 Zyklusfreiheit\n\n`parent_process` darf keine zyklische Hierarchie erzeugen.\n\n`invokes_processes` darf keinen unendlichen direkten oder indirekten Aufrufzyklus erzeugen, sofern der Prozess keinen ausdrücklich definierten kontrollierten Wiederholungspfad beschreibt.\n\n## 13. Prozesspakete und Begleitdateien\n\n### 13.1 Einzeldatei als Standard\n\nEin Prozess beginnt als Einzeldatei.\n\nEin Prozesspaket wird nur angelegt, wenn mindestens eine prozessspezifische Begleitdatei tatsächlich benötigt wird.\n\n### 13.2 Begleitdatei\n\nEine Markdown-Begleitdatei kann verwenden:\n\n```yaml\ndocument_type: process_support\ntitle:\nbelongs_to_process: KM-P01\n```\n\n`belongs_to_process` ist eine stabile Prozess-ID ohne Version.\n\nEine Begleitdatei:\n\n- ist keine eigenständige Prozessbeschreibung,\n- besitzt keine `process_id`,\n- darf den vollständigen Prozess nicht duplizieren,\n- wird nicht als Prozess in einen Prozessindex aufgenommen.\n\n### 13.3 Eigenständiger Unterprozess\n\nEin Unterprozess ist kein `process_support`. Er verwendet `document_type: process` und die vollständige Prozessstruktur.\n\n## 14. Maschinelle Prozessermittlung\n\n### 14.1 Aktiver Prozessbestand\n\nDas aktive Prozessprofil scannt:\n\n```text\nProcesses/**/*.md\n```\n\nAls aktive Prozesse werden nur Dateien berücksichtigt mit:\n\n```yaml\ndocument_type: process\nstatus: active\n```\n\n### 14.2 Vollständiger Prozess-Lifecycle\n\nFür versionsgebundene Referenzen und Audit-Zwecke werden zusätzlich Development- und lokale Archivbereiche einbezogen.\n\n### 14.3 Hierarchie\n\nDie Prozesshierarchie wird aus:\n\n```text\nprocess_id\nparent_process\ninvokes_processes\n```\n\nermittelt.\n\nSie wird nicht aus Ordnertiefe, alphabetischer Sortierung oder numerischer Nähe abgeleitet.\n\n## 15. Prozessspezifische Validierung\n\nZusätzlich zu `CPKS-SPEC-ART` muss ein Prozessvalidator mindestens erkennen:\n\n### Fehler\n\n```text\nmissing_process_id\ninvalid_process_id\nduplicate_process_id\nmissing_process_domain\nprocess_domain_id_prefix_mismatch\nunresolved_parent_process\ncyclic_process_hierarchy\nunresolved_invoked_process\ncyclic_process_invocation\nprocess_filename_mismatch\nprocess_package_entry_mismatch\nduplicate_process_definition\nunresolved_belongs_to_process\nprocess_support_has_process_id\nmissing_process_section\nactive_process_outside_processes\ninactive_process_in_processes\nprocess_step_without_role\nprocess_step_without_result_or_control\nmissing_completion_criteria\n```\n\n### Warnungen\n\n```text\nunverifiable_trigger\nnon_testable_completion_criteria\nunused_process_package\nunassigned_process_support\nexample_marker_in_active_process\nvery_long_process_step\n```\n\n## 16. Generierter Prozessindex\n\nEin Prozessindex ist kein Pflichtartefakt.\n\nBei nachgewiesenem Bedarf kann ein Index reproduzierbar erzeugt werden, beispielsweise:\n\n```text\nGenerated/Metadata/process-index.jsonl\nGenerated/Reports/Process Overview.md\n```\n\nEin solcher Index ist:\n\n- automatisch erzeugt,\n- nicht normativ,\n- nicht manuell zu pflegen,\n- keine zweite Source of Truth.\n\n## 17. Abgrenzung\n\nDiese Spezifikation definiert nicht:\n\n- fachliche Inhalte einzelner Prozesse,\n- vollständige BPMN-Regeln,\n- eine Diagrammpflicht,\n- eine Pflicht zu Prozesspaketen,\n- die konkrete Python-Implementierung,\n- das Human Governance Instruction Intake,\n- die vollständigen Development-Pfade aller Prozessdomänen.\n\n## 18. Verhältnis zu Version 0.2\n\nVersion 0.3 ergänzt gegenüber dem Draft 0.2 insbesondere:\n\n1. `withdrawn` als zulässigen Status nie aktivierter Prozessfassungen,\n2. die Ablage zurückgezogener Prozess-Drafts im lokalen Development-`Archive/`,\n3. das Prüfprofil `closed_development_managed`,\n4. die Abgrenzung von `rejected`, `completed`, `cancelled` und `identified`,\n5. `former_ids` für die frühere stabile Spezifikations-ID,\n6. Harmonisierung mit `CPKS-SPEC-ART@0.2`,\n7. Validierungsbasis `CPKS-BL@0.43`.\n\n## 19. Aktivierungsblocker\n\nVor Aktivierung müssen mindestens geklärt oder nachgewiesen werden:\n\n1. aktive oder zumindest aktivierungsreife `CPKS-SPEC-ART@0.2` oder Folgefassung,\n2. endgültige Development-Pfade für nicht aktive Prozesse außerhalb der Governance-Domäne,\n3. kontrollierte Liste der Prozessdomänen und ID-Präfixe,\n4. Prüfung des bestehenden Prozessbestands mit Validator v3 gegen diese Spezifikation,\n5. Überarbeitung von `GOV-P01` gegen `CPKS-SPEC-PROC@0.3`,\n6. Owner Review,\n7. ausdrücklicher Aktivierungsauftrag.\n\n## 20. Konformitätsregel\n\nEine Prozessbeschreibung ist konform, wenn:\n\n1. sie die allgemeinen Regeln von `CPKS-SPEC-ART` erfüllt,\n2. `document_type`, `process_id` und `process_domain` gültig sind,\n3. Status und Lifecycle-Zone übereinstimmen,\n4. Dateiname und `canonical_path` korrekt sind,\n5. alle Pflichtabschnitte vorhanden sind,\n6. Rollen, Schritte, Kontrollen und Abschlusskriterien prüfbar sind,\n7. Prozessbeziehungen korrekt und auflösbar sind,\n8. Prozesspakete keine zweite Prozessbeschreibung erzeugen,\n9. die technische Validierung keine Fehler erzeugt.\n\n## 21. Kurzregel\n\n> Der aktive Prozessbestand besteht ausschließlich aus aktiven, maschinenlesbaren Prozessbeschreibungen unter `Processes/`. Jede Prozesslinie besitzt eine stabile `process_id`; dauerhafte Prozessbeziehungen verwenden stabile IDs. Drafts, zurückgezogene Drafts und historische Fassungen liegen außerhalb des aktiven Prozessbestands; `withdrawn` Fassungen werden im lokalen Development-Archiv geführt. Prozessstruktur, Lifecycle und Referenzen müssen sowohl den allgemeinen Managed-Artifact-Regeln als auch den prozessspezifischen Anforderungen entsprechen.\n'


class PlacementError(RuntimeError):
    pass


def assert_location() -> None:
    actual = Path(__file__).resolve()
    expected = CANONICAL_SCRIPT.resolve()
    if actual != expected:
        raise PlacementError(
            "Script is not in its canonical repository location.\n"
            f"Expected: {expected}\nActual:   {actual}"
        )


def split_frontmatter(text: str) -> str:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise PlacementError("Missing YAML frontmatter.")
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            return "\n".join(lines[1:index])
    raise PlacementError("Unclosed YAML frontmatter.")


def scalar(frontmatter: str, field: str) -> str | None:
    match = re.search(
        rf"(?m)^{re.escape(field)}:\s*[\"']?([^\n\"']+)[\"']?\s*$",
        frontmatter,
    )
    return match.group(1).strip() if match else None


def validate(text: str) -> None:
    fm = split_frontmatter(text)
    expected = {
        "document_type": "specification",
        "specification_id": "CPKS-SPEC-PROC",
        "version": "0.3",
        "status": "draft",
        "canonical_path": TARGET_REL.as_posix(),
    }
    for field, wanted in expected.items():
        actual = scalar(fm, field)
        if actual != wanted:
            raise PlacementError(
                f"{field} expected {wanted!r}, got {actual!r}"
            )
    if "  - CPKS-SPEC-PROCESS-DESCRIPTION" not in fm:
        raise PlacementError("former_ids mapping is missing.")
    if "withdrawn" not in text:
        raise PlacementError("withdrawn process status is missing.")


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".placement.tmp", dir=path.parent
    )
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temp_path, 0o644)
        os.replace(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    assert_location()
    validate(CONTENT)
    target = VAULT / TARGET_REL
    timestamp = dt.datetime.now().astimezone().strftime("%Y%m%dT%H%M%S%z")
    mode = "apply" if args.apply else "dry-run"
    run_dir = RUN_ROOT / f"{timestamp}-place-CPKS-SPEC-PROC-0.3-{mode}"
    run_dir.mkdir(parents=True, exist_ok=False)

    if target.exists():
        existing = target.read_text(encoding="utf-8")
        validate(existing)
        if existing != CONTENT:
            raise PlacementError(
                "Target exists with different content. No overwrite performed."
            )
        state = "already_present"
    else:
        state = "planned"

    report = {
        "mode": mode,
        "state": state,
        "artifact": "CPKS-SPEC-PROC@0.3",
        "status": "draft",
        "target": TARGET_REL.as_posix(),
        "sha256": hashlib.sha256(CONTENT.encode("utf-8")).hexdigest(),
        "previous_draft_modified": False,
        "activation_performed": False,
        "commit_created": False,
        "push_performed": False,
    }
    (run_dir / "placement-report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    if not args.apply:
        print("Dry run completed. No Vault files were changed.")
        print(f"Target: {TARGET_REL}")
        print(f"Run report: {run_dir}")
        return 0

    if not target.exists():
        atomic_write(target, CONTENT)
    validate(target.read_text(encoding="utf-8"))
    print("CPKS-SPEC-PROC@0.3 placed and validated as draft.")
    print(f"Target: {target}")
    print(f"Run report: {run_dir}")
    print("CPKS-SPEC-PROC@0.2 was not changed.")
    print("No activation, Git commit or push was performed.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except PlacementError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
