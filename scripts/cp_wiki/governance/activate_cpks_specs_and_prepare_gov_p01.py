#!/usr/bin/env python3
"""
Activate CPKS-SPEC-ART@0.2 and CPKS-SPEC-PROC@0.3, archive their
never-active predecessor drafts, and prepare GOV-P01@0.3 for activation.

Canonical script location:
  /Users/cp/Developer/cpKnowledgeTools/scripts/cp_wiki/governance/
  activate_cpks_specs_and_prepare_gov_p01.py

Default: dry run.
Use --apply to perform the controlled lifecycle changes.

Preconditions:
- latest validator v3.1 report has 0 errors and 0 warnings;
- the owner has confirmed the macOS/Git/Obsidian filename and link test;
- active target files do not already exist.

Effects:
- CPKS-SPEC-ART@0.2 becomes active at:
  Systems/cpKnowledgeSystem/Governance/Specifications/
  CPKS-SPEC-ART Managed Artifact Metadata and Validation Specification.md
- CPKS-SPEC-PROC@0.3 becomes active at:
  Systems/cpKnowledgeSystem/Governance/Specifications/
  CPKS-SPEC-PROC Process Description Specification.md
- CPKS-SPEC-ART@0.1, CPKS-SPEC-PROC@0.1 and @0.2 become withdrawn
  and move to Development/cpKnowledgeSystem/Specifications/Archive/
- GOV-P01@0.3 changes from draft to proposed and remains in its
  Development path pending a separate activation approval.
- no baseline is modified;
- no GOV-P01 activation is performed;
- no Git commit or push is performed.
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
CANONICAL_SCRIPT = (
    TOOLS / "scripts/cp_wiki/governance/activate_cpks_specs_and_prepare_gov_p01.py"
)
RUN_ROOT = Path(
    "/Users/cp/Library/Application Support/cpKnowledgeTools/Runs/cp-wiki/governance"
)
VALIDATION_ROOT = Path(
    "/Users/cp/Library/Application Support/cpKnowledgeTools/Runs/cp-wiki/validation"
)

APPROVED_BY = "Christoph Peters"
APPROVED_AT = "2026-07-27"
EFFECTIVE_FROM = "2026-07-27"

ART_SOURCE_REL = Path(
    "Development/cpKnowledgeSystem/Specifications/"
    "CPKS-SPEC-ART@0.2 Managed Artifact Metadata and Validation Specification.md"
)
PROC_SOURCE_REL = Path(
    "Development/cpKnowledgeSystem/Specifications/"
    "CPKS-SPEC-PROC@0.3 Process Description Specification.md"
)
ART_ACTIVE_REL = Path(
    "Systems/cpKnowledgeSystem/Governance/Specifications/"
    "CPKS-SPEC-ART Managed Artifact Metadata and Validation Specification.md"
)
PROC_ACTIVE_REL = Path(
    "Systems/cpKnowledgeSystem/Governance/Specifications/"
    "CPKS-SPEC-PROC Process Description Specification.md"
)
GOV_REL = Path(
    "Development/cpKnowledgeSystem/Governance/Draft Processes/"
    "GOV-P01@0.3 Governance Artifact Consolidation and Impact Review.md"
)

ARCHIVE_DIR_REL = Path("Development/cpKnowledgeSystem/Specifications/Archive")
PREDECESSORS = {
    Path(
        "Development/cpKnowledgeSystem/Specifications/"
        "CPKS-SPEC-ART@0.1 Managed Artifact Metadata and Validation Specification.md"
    ): ARCHIVE_DIR_REL
    / "CPKS-SPEC-ART@0.1 Managed Artifact Metadata and Validation Specification.md",
    Path(
        "Development/cpKnowledgeSystem/Specifications/"
        "CPKS-SPEC-PROC@0.1 Process Description Specification.md"
    ): ARCHIVE_DIR_REL / "CPKS-SPEC-PROC@0.1 Process Description Specification.md",
    Path(
        "Development/cpKnowledgeSystem/Specifications/"
        "CPKS-SPEC-PROC@0.2 Process Description Specification.md"
    ): ARCHIVE_DIR_REL / "CPKS-SPEC-PROC@0.2 Process Description Specification.md",
}


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


def insert_after_scalar(raw: str, field: str, insertion: str) -> str:
    pattern = re.compile(rf"(?m)^({re.escape(field)}:.*)$")
    if not pattern.search(raw):
        raise ActivationError(f"Anchor field missing: {field}")
    return pattern.sub(r"\1\n" + insertion.rstrip(), raw, count=1)


def remove_scalar(raw: str, field: str) -> str:
    return re.sub(rf"(?m)^{re.escape(field)}:.*\n?", "", raw, count=1)


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


def activate_specification(
    text: str,
    *,
    specification_id: str,
    version: str,
    active_path: Path,
) -> str:
    raw, body = split_frontmatter(text)
    fm = parse_frontmatter(raw)

    if fm.get("document_type") != "specification":
        raise ActivationError("Source is not a specification.")
    if fm.get("specification_id") != specification_id:
        raise ActivationError(f"Expected specification_id {specification_id}.")
    if str(fm.get("version")) != version or fm.get("status") != "draft":
        raise ActivationError(
            f"{specification_id}@{version} is not the expected draft."
        )

    raw = replace_scalar(raw, "status", "active")
    raw = replace_scalar(raw, "revised", APPROVED_AT)
    raw = replace_scalar(raw, "canonical_path", active_path.as_posix())

    for field in ("approved_by", "approved_at", "effective_from"):
        raw = remove_scalar(raw, field)
    raw = insert_after_scalar(
        raw,
        "owner",
        "\n".join(
            [
                f"approved_by: {APPROVED_BY}",
                f'approved_at: "{APPROVED_AT}"',
                f'effective_from: "{EFFECTIVE_FROM}"',
            ]
        ),
    )

    if specification_id == "CPKS-SPEC-ART":
        status_section = f"""## 1. Status

**Aktiv und verbindlich**

`CPKS-SPEC-ART@0.2` wurde am {APPROVED_AT} durch den System-Owner Christoph Peters ausdrücklich freigegeben und gilt ab diesem Datum vaultweit.

Die nie aktivierte Draft-Fassung `CPKS-SPEC-ART@0.1` wird nicht als `superseded` behandelt. Sie wird mit `status: withdrawn` im lokalen Development-Archiv aufbewahrt.

Die Aktivierung stützt sich insbesondere auf:

- Validator v3.1 mit `0` Fehlern und `0` Warnungen,
- erfolgreiche Prüfung aller vorgesehenen Bestands- und Prüfprofile,
- materialisierte und geprüfte Aliasauflösung,
- Unterstützung strukturierter `target_artifact`-Deskriptoren,
- implementiertes Historical-Acknowledgement-Modell,
- erfolgreichen macOS-, Git- und Obsidian-Dateinamen- und Linktest,
- ausdrückliche Owner-Freigabe."""
        body = replace_section(body, "## 1. Status", "## 2. Zweck", status_section)

        activation_section = f"""## 22. Aktivierungsnachweis und Owner-Freigabe

Für die Aktivierung wurden nachgewiesen:

1. die parallele aktive Kopie von `CPKS-DEC-020@1.0` wurde entfernt,
2. getrennte Prüfprofile sind im Validator implementiert,
3. `former_ids` und Aliasauflösung sind implementiert und materialisiert,
4. strukturierte `target_artifact`-Deskriptoren werden unterstützt,
5. das Statusmodell ist mit `CPKS-SPEC-PROC@0.3` harmonisiert,
6. aktive, historische, aktuelle Development- und geschlossene Development-Artefakte wurden erfolgreich geprüft,
7. die Dateinamen-Normalisierung und Obsidian-Linkauflösung wurden auf macOS erfolgreich getestet,
8. die archivierten Vault-Spezifikationen 1.0 und 1.1 wurden als geschlossene Development-Drafts behandelt,
9. das Acknowledgement-Modell wurde in Validator v3.1 implementiert und mit 18 historischen Acknowledgements getestet,
10. der vollständige Draft wurde durch den Owner geprüft,
11. der Owner hat am {APPROVED_AT} die ausdrückliche Aktivierung freigegeben.

Nicht erforderlich war eine rückwirkende Vollmigration jedes alten Preflights oder zurückgezogenen Drafts. Deren Integrität und Provenienz bleiben erhalten."""
        body = replace_section(
            body,
            "## 22. Aktivierungsblocker und Owner Review",
            "## 23. Kurzregel",
            activation_section,
        )

    elif specification_id == "CPKS-SPEC-PROC":
        status_section = f"""## 1. Status

**Aktiv und verbindlich**

`CPKS-SPEC-PROC@0.3` wurde am {APPROVED_AT} durch den System-Owner Christoph Peters ausdrücklich freigegeben und gilt ab diesem Datum vaultweit für kanonische Prozessbeschreibungen.

Die nie aktivierten Draft-Fassungen `CPKS-SPEC-PROC@0.1` und `CPKS-SPEC-PROC@0.2` werden nicht als `superseded` behandelt. Sie werden mit `status: withdrawn` im lokalen Development-Archiv aufbewahrt.

Die Aktivierung erfolgt gemeinsam mit `CPKS-SPEC-ART@0.2` und stützt sich auf den erfolgreichen Validator-v3.1-Lauf sowie den erfolgreichen macOS-, Git- und Obsidian-Dateinamen- und Linktest."""
        body = replace_section(body, "## 1. Status", "## 2. Zweck", status_section)
        body = body.replace(
            "Solange beide Spezifikationen Drafts sind, muss ein Widerspruch vor einer Aktivierung konsolidiert werden.",
            "Beide Spezifikationen sind aktiv. Bei einem Widerspruch gilt die angegebene Autoritätsreihenfolge; der Konflikt muss kontrolliert durch eine Folgefassung behoben werden.",
            1,
        )

        activation_section = f"""## 19. Aktivierungsnachweis

Für die Aktivierung wurden nachgewiesen:

1. `CPKS-SPEC-ART@0.2` ist gleichzeitig aktivierungsbereit und wird im selben kontrollierten Lifecycle-Schritt aktiviert,
2. für Governance-Prozesse ist der Development- und Archivpfad verbindlich festgelegt,
3. die derzeit verwendeten Prozessdomänen und ID-Präfixe sind in Abschnitt 6 kontrolliert beschrieben,
4. neue Domänen und Präfixe dürfen weiterhin nicht pro Datei improvisiert werden,
5. der bestehende Prozessbestand wurde mit Validator v3.1 geprüft,
6. `GOV-P01@0.3` wurde gegen diese Spezifikation überarbeitet,
7. der macOS-, Git- und Obsidian-Dateinamen- und Linktest war erfolgreich,
8. der Owner hat den vollständigen Draft geprüft,
9. der Owner hat am {APPROVED_AT} die ausdrückliche Aktivierung freigegeben.

Die endgültigen Development-Pfade weiterer Prozessdomänen werden erst bei deren konkreter Einführung festgelegt. Dies ist kein Aktivierungsblocker für die gegenwärtig definierte Governance-Prozessdomäne."""
        body = replace_section(
            body,
            "## 19. Aktivierungsblocker",
            "## 20. Konformitätsregel",
            activation_section,
        )

    updated = join_frontmatter(raw, body)
    validate_identity(
        updated,
        document_type="specification",
        identity_field="specification_id",
        identity=specification_id,
        version=version,
        status="active",
        canonical_path=active_path.as_posix(),
    )
    return updated


def withdraw_predecessor(text: str, target_path: Path) -> str:
    raw, body = split_frontmatter(text)
    fm = parse_frontmatter(raw)

    if fm.get("document_type") != "specification":
        raise ActivationError("Predecessor is not a specification.")
    if fm.get("status") == "active":
        raise ActivationError("An active specification cannot be withdrawn.")
    if fm.get("status") not in {"draft", "proposed", "withdrawn"}:
        raise ActivationError(f"Unexpected predecessor status: {fm.get('status')}")

    raw = replace_scalar(raw, "status", "withdrawn")
    raw = replace_scalar(raw, "revised", APPROVED_AT)
    raw = replace_scalar(raw, "canonical_path", target_path.as_posix())

    updated = join_frontmatter(raw, body)
    parsed = parse_frontmatter(split_frontmatter(updated)[0])
    if parsed.get("status") != "withdrawn":
        raise ActivationError("Predecessor withdrawal validation failed.")
    return updated


def prepare_gov_p01(text: str) -> str:
    raw, body = split_frontmatter(text)
    fm = parse_frontmatter(raw)

    expected = {
        "document_type": "process",
        "process_id": "GOV-P01",
        "version": "0.3",
        "status": "draft",
        "canonical_path": GOV_REL.as_posix(),
    }
    for field, wanted in expected.items():
        actual = str(fm.get(field) or "")
        if actual != wanted:
            raise ActivationError(
                f"GOV-P01 field {field} expected {wanted!r}, got {actual!r}"
            )

    raw = replace_scalar(raw, "status", "proposed")
    raw = replace_scalar(raw, "revised", APPROVED_AT)

    body = body.replace(
        "  target_status: draft\n"
        "  proposed_canonical_path: Development/cpKnowledgeSystem/Governance/Draft Processes/GOV-P01@0.3 Governance Artifact Consolidation and Impact Review.md",
        "  target_status: active\n"
        "  proposed_canonical_path: Processes/Governance/GOV-P01 Governance Artifact Consolidation and Impact Review.md",
        1,
    )

    updated = join_frontmatter(raw, body)
    validate_identity(
        updated,
        document_type="process",
        identity_field="process_id",
        identity="GOV-P01",
        version="0.3",
        status="proposed",
        canonical_path=GOV_REL.as_posix(),
    )
    return updated


def latest_successful_v31_report() -> Path:
    candidates = sorted(
        VALIDATION_ROOT.glob(
            "*-managed-artifact-validation-v3-1/validation-report-v3-1.json"
        ),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        raise ActivationError(
            "No validator v3.1 report was found in the canonical runtime root."
        )

    report_path = candidates[0]
    report = json.loads(report_path.read_text(encoding="utf-8"))
    summary = report.get("summary") or {}
    errors = int(summary.get("error", 0))
    warnings = int(summary.get("warning", 0))
    if errors != 0 or warnings != 0:
        raise ActivationError(
            "Latest validator v3.1 report is not activation-clean: "
            f"errors={errors}, warnings={warnings}"
        )
    return report_path


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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    assert_canonical_script_location()
    validation_report = latest_successful_v31_report()

    art_source = VAULT / ART_SOURCE_REL
    proc_source = VAULT / PROC_SOURCE_REL
    gov_path = VAULT / GOV_REL
    art_active = VAULT / ART_ACTIVE_REL
    proc_active = VAULT / PROC_ACTIVE_REL

    for required in [art_source, proc_source, gov_path]:
        if not required.is_file():
            raise ActivationError(f"Required source missing: {required}")

    for target in [art_active, proc_active]:
        if target.exists():
            raise ActivationError(f"Active target already exists: {target}")

    for source_rel, target_rel in PREDECESSORS.items():
        source = VAULT / source_rel
        target = VAULT / target_rel
        if not source.is_file():
            raise ActivationError(f"Predecessor source missing: {source}")
        if target.exists():
            raise ActivationError(f"Predecessor archive target exists: {target}")

    art_before = art_source.read_text(encoding="utf-8")
    proc_before = proc_source.read_text(encoding="utf-8")
    gov_before = gov_path.read_text(encoding="utf-8")

    art_after = activate_specification(
        art_before,
        specification_id="CPKS-SPEC-ART",
        version="0.2",
        active_path=ART_ACTIVE_REL,
    )
    proc_after = activate_specification(
        proc_before,
        specification_id="CPKS-SPEC-PROC",
        version="0.3",
        active_path=PROC_ACTIVE_REL,
    )
    gov_after = prepare_gov_p01(gov_before)

    predecessor_updates: dict[Path, tuple[Path, str, str, int]] = {}
    for source_rel, target_rel in PREDECESSORS.items():
        source = VAULT / source_rel
        target = VAULT / target_rel
        before = source.read_text(encoding="utf-8")
        after = withdraw_predecessor(before, target_rel)
        predecessor_updates[source] = (
            target,
            before,
            after,
            source.stat().st_mode & 0o777,
        )

    timestamp = dt.datetime.now().astimezone().strftime("%Y%m%dT%H%M%S%z")
    mode = "apply" if args.apply else "dry-run"
    run_dir = (
        RUN_ROOT / f"{timestamp}-activate-CPKS-specifications-prepare-GOV-P01-{mode}"
    )
    run_dir.mkdir(parents=True, exist_ok=False)

    diffs = [
        unified_diff(
            art_before,
            "",
            f"a/{ART_SOURCE_REL.as_posix()}",
            "/dev/null",
        ),
        unified_diff(
            "",
            art_after,
            "/dev/null",
            f"b/{ART_ACTIVE_REL.as_posix()}",
        ),
        unified_diff(
            proc_before,
            "",
            f"a/{PROC_SOURCE_REL.as_posix()}",
            "/dev/null",
        ),
        unified_diff(
            "",
            proc_after,
            "/dev/null",
            f"b/{PROC_ACTIVE_REL.as_posix()}",
        ),
        unified_diff(
            gov_before,
            gov_after,
            f"a/{GOV_REL.as_posix()}",
            f"b/{GOV_REL.as_posix()}",
        ),
    ]

    for source, (target, before, after, _mode_bits) in predecessor_updates.items():
        source_rel = source.relative_to(VAULT)
        target_rel = target.relative_to(VAULT)
        diffs.append(
            unified_diff(
                before,
                "",
                f"a/{source_rel.as_posix()}",
                "/dev/null",
            )
        )
        diffs.append(
            unified_diff(
                "",
                after,
                "/dev/null",
                f"b/{target_rel.as_posix()}",
            )
        )

    (run_dir / "planned-changes.diff").write_text(
        "".join(diffs),
        encoding="utf-8",
    )
    manifest = {
        "mode": mode,
        "validation_report": str(validation_report),
        "owner_approval": {
            "approved_by": APPROVED_BY,
            "approved_at": APPROVED_AT,
            "effective_from": EFFECTIVE_FROM,
            "obsidian_link_test_confirmed": True,
        },
        "activate": [
            {
                "id": "CPKS-SPEC-ART",
                "version": "0.2",
                "source": ART_SOURCE_REL.as_posix(),
                "target": ART_ACTIVE_REL.as_posix(),
                "sha256": sha256(art_after),
            },
            {
                "id": "CPKS-SPEC-PROC",
                "version": "0.3",
                "source": PROC_SOURCE_REL.as_posix(),
                "target": PROC_ACTIVE_REL.as_posix(),
                "sha256": sha256(proc_after),
            },
        ],
        "withdraw_and_archive": [
            {
                "source": source.relative_to(VAULT).as_posix(),
                "target": target.relative_to(VAULT).as_posix(),
            }
            for source, (
                target,
                _before,
                _after,
                _mode_bits,
            ) in predecessor_updates.items()
        ],
        "prepare": [
            {
                "id": "GOV-P01",
                "version": "0.3",
                "status": "proposed",
                "path": GOV_REL.as_posix(),
            }
        ],
        "baseline_modified": False,
        "gov_p01_activated": False,
        "commit_created": False,
        "push_performed": False,
    }
    (run_dir / "activation-manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    if not args.apply:
        print("Dry run completed. No Vault files were changed.")
        print(f"Validated against: {validation_report}")
        print(f"Run report: {run_dir}")
        return 0

    recovery_root = run_dir / "recovery"
    operations_created: list[Path] = []
    original_files: dict[Path, tuple[str, int]] = {}

    def remember(path: Path, content: str, mode_bits: int) -> None:
        original_files[path] = (content, mode_bits)
        recovery = recovery_root / path.relative_to(VAULT)
        recovery.parent.mkdir(parents=True, exist_ok=True)
        recovery.write_text(content, encoding="utf-8")

    try:
        art_mode = art_source.stat().st_mode & 0o777
        proc_mode = proc_source.stat().st_mode & 0o777
        gov_mode = gov_path.stat().st_mode & 0o777

        remember(art_source, art_before, art_mode)
        remember(proc_source, proc_before, proc_mode)
        remember(gov_path, gov_before, gov_mode)
        for source, (_target, before, _after, mode_bits) in predecessor_updates.items():
            remember(source, before, mode_bits)

        atomic_write(art_active, art_after, art_mode)
        operations_created.append(art_active)
        atomic_write(proc_active, proc_after, proc_mode)
        operations_created.append(proc_active)

        atomic_write(gov_path, gov_after, gov_mode)

        for source, (target, _before, after, mode_bits) in predecessor_updates.items():
            atomic_write(target, after, mode_bits)
            operations_created.append(target)

        art_source.unlink()
        proc_source.unlink()
        for source in predecessor_updates:
            source.unlink()

        validate_identity(
            art_active.read_text(encoding="utf-8"),
            document_type="specification",
            identity_field="specification_id",
            identity="CPKS-SPEC-ART",
            version="0.2",
            status="active",
            canonical_path=ART_ACTIVE_REL.as_posix(),
        )
        validate_identity(
            proc_active.read_text(encoding="utf-8"),
            document_type="specification",
            identity_field="specification_id",
            identity="CPKS-SPEC-PROC",
            version="0.3",
            status="active",
            canonical_path=PROC_ACTIVE_REL.as_posix(),
        )
        validate_identity(
            gov_path.read_text(encoding="utf-8"),
            document_type="process",
            identity_field="process_id",
            identity="GOV-P01",
            version="0.3",
            status="proposed",
            canonical_path=GOV_REL.as_posix(),
        )

    except Exception:
        for created in reversed(operations_created):
            created.unlink(missing_ok=True)
        for path, (content, mode_bits) in original_files.items():
            atomic_write(path, content, mode_bits)
        raise

    (run_dir / "activation-report.json").write_text(
        json.dumps(
            {
                **manifest,
                "mode": "apply",
                "state": "applied",
                "recovery_root": str(recovery_root),
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    print("CPKS-SPEC-ART@0.2 activated.")
    print("CPKS-SPEC-PROC@0.3 activated.")
    print("Never-active predecessor drafts withdrawn and archived.")
    print("GOV-P01@0.3 prepared with status proposed.")
    print("No baseline or GOV-P01 activation was performed.")
    print(f"Run report: {run_dir}")
    print("No Git commit or push was performed.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ActivationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
