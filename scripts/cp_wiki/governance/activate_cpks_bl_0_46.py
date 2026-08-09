#!/usr/bin/env python3
"""
Activate CPKS-BL@0.46 as the Authoritative Baseline.

Governance basis:
- CPKS-SPEC-ART@0.3
- GOV-P01@0.3
- explicit Owner activation authorization for CPKS-BL@0.46

Lifecycle:
- CPKS-BL@0.46: draft -> active, version remains 0.46
- evidence_class remains verified_current_state
- approval/effective metadata are added for 2026-08-08
- supersedes becomes [CPKS-BL@0.44]
- active canonical path becomes Systems/.../System Control/CPKS-BL ...
- CU-01..CU-05 review comments are removed, content inside them is preserved
- lifecycle-only body statements are updated to the activated state
- CPKS-BL@0.44: active -> superseded, evidence_class -> historical_evidence
- CPKS-BL@0.44 is moved to the local Baseline archive
- CPKS-BL@0.45 remains withdrawn and unchanged

The script does not perform material content changes, Git commit, or push.

Execution:
    --check   verify preconditions and generated transforms; no Vault write
    --apply   perform activation, run validator v3.2 --strict-exit, rollback on error

Recovery copies are stored as technical run data under:
    /Users/cp/Library/Application Support/cpKnowledgeTools/Runs/cp-wiki/governance/
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
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
DEFAULT_RUN_ROOT = Path(
    "/Users/cp/Library/Application Support/cpKnowledgeTools/Runs/cp-wiki/governance"
)

VALIDATOR_REL = Path(
    "scripts/cp_wiki/validation/validate_cpwiki_managed_artifacts_v3_2.py"
)

DRAFT_REL = Path(
    "Development/cpKnowledgeSystem/Governance/Draft Baselines/"
    "CPKS-BL@0.46 cpKnowledgeSystem Authoritative Baseline.md"
)
WITHDRAWN_045_REL = Path(
    "Development/cpKnowledgeSystem/Governance/Draft Baselines/Archive/"
    "CPKS-BL@0.45 cpKnowledgeSystem Authoritative Baseline.md"
)
ACTIVE_REL = Path(
    "Systems/cpKnowledgeSystem/Governance/System Control/"
    "CPKS-BL cpKnowledgeSystem Authoritative Baseline.md"
)
ARCHIVE_044_REL = Path(
    "Systems/cpKnowledgeSystem/Governance/Archive/Baselines/"
    "CPKS-BL@0.44 cpKnowledgeSystem Authoritative Baseline.md"
)

OWNER = "Christoph Peters"
ACTIVATION_DATE = "2026-08-08"


class ActivationError(RuntimeError):
    pass


def split_frontmatter(text: str) -> tuple[str, str]:
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        raise ActivationError("Expected YAML frontmatter.")
    for idx in range(1, len(lines)):
        if lines[idx].strip() == "---":
            return "".join(lines[1:idx]), "".join(lines[idx + 1:])
    raise ActivationError("Unclosed YAML frontmatter.")


def parse_frontmatter(text: str) -> dict[str, Any]:
    raw, _ = split_frontmatter(text)
    data = yaml.safe_load(raw) or {}
    if not isinstance(data, dict):
        raise ActivationError("Frontmatter must be a YAML mapping.")
    return data


def rebuild_frontmatter(raw: str, body: str) -> str:
    return f"---\n{raw.rstrip()}\n---\n{body}"


def set_scalar(
    text: str,
    field: str,
    value: str,
    *,
    quote: bool = False,
    insert_after: str | None = None,
) -> str:
    raw, body = split_frontmatter(text)
    rendered = f'"{value}"' if quote else value
    pattern = re.compile(rf"(?m)^{re.escape(field)}:[^\n]*$")

    if pattern.search(raw):
        raw = pattern.sub(f"{field}: {rendered}", raw, count=1)
        return rebuild_frontmatter(raw, body)

    if insert_after is None:
        raise ActivationError(f"Missing frontmatter field and no insertion anchor: {field}")

    anchor = re.compile(rf"(?m)^({re.escape(insert_after)}:[^\n]*)$")
    if not anchor.search(raw):
        raise ActivationError(
            f"Cannot insert {field}; anchor field not found: {insert_after}"
        )
    raw = anchor.sub(rf"\1\n{field}: {rendered}", raw, count=1)
    return rebuild_frontmatter(raw, body)


def set_list(text: str, field: str, items: list[str]) -> str:
    raw, body = split_frontmatter(text)
    lines = raw.splitlines()

    index = None
    for i, line in enumerate(lines):
        if re.match(rf"^{re.escape(field)}\s*:\s*(?:\[\s*\])?\s*$", line):
            index = i
            break
        if re.match(rf"^{re.escape(field)}\s*:\s*\[.*\]\s*$", line):
            index = i
            break

    if index is None:
        raise ActivationError(f"Missing expected list field: {field}")

    # Remove existing block.
    end = index + 1
    if re.match(rf"^{re.escape(field)}\s*:\s*$", lines[index]):
        while end < len(lines):
            line = lines[end]
            if line and not line[0].isspace():
                break
            end += 1

    replacement = [f"{field}:"] + [f"  - {item}" for item in items]
    lines[index:end] = replacement
    return rebuild_frontmatter("\n".join(lines), body)


def replace_section(
    text: str,
    start_heading: str,
    next_heading: str,
    replacement: str,
) -> str:
    start = text.find(start_heading)
    if start < 0:
        raise ActivationError(f"Section not found: {start_heading}")
    end = text.find(next_heading, start + len(start_heading))
    if end < 0:
        raise ActivationError(f"Next section not found: {next_heading}")
    return text[:start] + replacement.rstrip() + "\n\n" + text[end:]


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise ActivationError(
            f"{label}: expected exactly one occurrence, found {count}"
        )
    return text.replace(old, new, 1)


def remove_cu_comments(text: str) -> tuple[str, int]:
    openings = re.findall(
        r"<!-- CONSOLIDATED-UPDATE CU-\d+\b.*?-->",
        text,
        flags=re.S,
    )
    closings = re.findall(
        r"<!-- /CONSOLIDATED-UPDATE CU-\d+ -->",
        text,
    )
    if len(openings) != 5 or len(closings) != 5:
        raise ActivationError(
            "Expected exactly five opening and five closing CU review comments; "
            f"found {len(openings)} opening / {len(closings)} closing."
        )
    text = re.sub(
        r"\n?<!-- CONSOLIDATED-UPDATE CU-\d+\b.*?-->\n?",
        "\n",
        text,
        flags=re.S,
    )
    text = re.sub(
        r"\n?<!-- /CONSOLIDATED-UPDATE CU-\d+ -->\n?",
        "\n",
        text,
    )
    return text, len(openings)


ACTIVE_INTRO = """# CPKS-BL – cpKnowledgeSystem Authoritative Baseline

> [!IMPORTANT]
> Diese Datei ist die aktive systemweite Authoritative Baseline `CPKS-BL@0.46`.
>
> Sie ersetzt `CPKS-BL@0.44`.
>
> Die Vorgängerfassung `CPKS-BL@0.44` besitzt `status: superseded` und wird versioniert unter
> `Systems/cpKnowledgeSystem/Governance/Archive/Baselines/CPKS-BL@0.44 cpKnowledgeSystem Authoritative Baseline.md`
> als historische Evidenz aufbewahrt.
>
> Für diese aktive Baseline gilt aufgrund ihrer primären Current-State-Funktion:
> `evidence_class: verified_current_state`.
"""


ACTIVE_SECTION_4 = """# 4. Baseline-Identität und Lifecycle

## 4.1 Stabile Identität

```yaml
baseline_id: CPKS-BL
former_ids:
  - CPKS-BASELINE
```

## 4.2 Ersetzte aktive Ausgangsfassung

```yaml
reference: CPKS-BL@0.44
status: superseded
evidence_class: historical_evidence
actual_path: Systems/cpKnowledgeSystem/Governance/Archive/Baselines/CPKS-BL@0.44 cpKnowledgeSystem Authoritative Baseline.md
canonical_path: Systems/cpKnowledgeSystem/Governance/Archive/Baselines/CPKS-BL@0.44 cpKnowledgeSystem Authoritative Baseline.md
```

`CPKS-BL@0.44` wurde im kontrollierten Aktivierungsschritt durch `CPKS-BL@0.46` ersetzt und als historische Evidenz erhalten.

## 4.3 Konkrete Fassungen der Artefaktlinie

| Version | Status | Tatsächlicher Pfad |
|---:|---|---|
| `0.1` | `superseded` | `Systems/cpKnowledgeSystem/Governance/Archive/Baselines/CPKS-BL@0.1 cpKnowledgeSystem Authoritative Baseline.md` |
| `0.2` | `superseded` | `Systems/cpKnowledgeSystem/Governance/Archive/Baselines/CPKS-BL@0.2 cpKnowledgeSystem Authoritative Baseline.md` |
| `0.3` | `superseded` | `Systems/cpKnowledgeSystem/Governance/Archive/Baselines/CPKS-BL@0.3 cpKnowledgeSystem Authoritative Baseline.md` |
| `0.4` | `withdrawn` | `Development/cpKnowledgeSystem/Governance/Draft Baselines/Archive/CPKS-BL@0.4 cpKnowledgeSystem Authoritative Baseline.md` |
| `0.41` | `superseded` | `Systems/cpKnowledgeSystem/Governance/Archive/Baselines/CPKS-BL@0.41 cpKnowledgeSystem Authoritative Baseline.md` |
| `0.42` | `superseded` | `Systems/cpKnowledgeSystem/Governance/Archive/Baselines/CPKS-BL@0.42 cpKnowledgeSystem Authoritative Baseline.md` |
| `0.43` | `superseded` | `Systems/cpKnowledgeSystem/Governance/Archive/Baselines/CPKS-BL@0.43 cpKnowledgeSystem Authoritative Baseline.md` |
| `0.44` | `superseded` | `Systems/cpKnowledgeSystem/Governance/Archive/Baselines/CPKS-BL@0.44 cpKnowledgeSystem Authoritative Baseline.md` |
| `0.45` | `withdrawn` | `Development/cpKnowledgeSystem/Governance/Draft Baselines/Archive/CPKS-BL@0.45 cpKnowledgeSystem Authoritative Baseline.md` |
| `0.46` | `active` | `Systems/cpKnowledgeSystem/Governance/System Control/CPKS-BL cpKnowledgeSystem Authoritative Baseline.md` |

`CPKS-BL@0.46` ist die genau eine aktive Fassung der stabilen Artefaktlinie. `CPKS-BL@0.45` war nie aktiv und bleibt als `withdrawn` mit `historical_evidence` erhalten.

Die Aktivierung ändert die konkrete Version `0.46` nicht.
"""


ACTIVE_SECTION_19 = """# 19. Aktivierungsnachweis und verbleibende Abdeckungsgrenzen

`CPKS-BL@0.46` wurde am 8. August 2026 durch den System-Owner Christoph Peters ausdrücklich zur Aktivierung freigegeben.

Für den kontrollierten Lifecycle-Schritt gelten:

- die Version bleibt unverändert `0.46`,
- `status: active`,
- `evidence_class: verified_current_state`,
- `supersedes: CPKS-BL@0.44`,
- `CPKS-BL@0.44` wird `superseded` und als `historical_evidence` im lokalen Baseline-Archiv erhalten,
- `CPKS-BL@0.45` bleibt unverändert `withdrawn`,
- sämtliche temporären `CONSOLIDATED-UPDATE`-Review-Markierungen werden entfernt, während ihr fachlicher Inhalt erhalten bleibt,
- die technische Post-Activation-Validation mit Managed Artifact Validator v3.2 und `--strict-exit` ist Bestandteil desselben kontrollierten Aktivierungsschritts.

Die dokumentierten stichtagsbezogenen Inventarzähler bleiben Scanbeobachtungen und sind keine dauerhafte Aktivierungsinvariante.

Die in dieser Baseline ausdrücklich als offen geführten Konsolidierungs- und Revalidierungsbefunde werden durch die Aktivierung nicht stillschweigend als erledigt behandelt.
"""


ACTIVE_SECTION_20 = """# 20. Kurzform

> `CPKS-BL@0.46` ist die aktive Authoritative Baseline des `cpKnowledgeSystem` und ersetzt `CPKS-BL@0.44`. Die aktive Baseline führt `evidence_class: verified_current_state`. `CPKS-BL@0.44` wird als `superseded` mit `historical_evidence` im lokalen Baseline-Archiv erhalten; `CPKS-BL@0.45` bleibt als nie aktivierter Draft `withdrawn`. Der dokumentierte bereinigte Managed-Artifact-Zustand umfasst 39 vollständig mit `evidence_class` klassifizierte aktive Managed Artifacts, keine blockierenden Duplicate-/Parallelversionsbefunde und einen publizierten Managed-Artifact-Validator-v3.2-Nachweis mit 0 Fehlern. Stichtagsbezogene Vault-Dateizähler bleiben Scanbeobachtungen und keine dauerhafte Aktivierungsinvariante.
"""


def build_active_046(draft_text: str) -> tuple[str, int]:
    text = draft_text

    # Frontmatter: pure activation/lifecycle changes only.
    text = set_scalar(text, "status", "active")
    text = set_scalar(text, "evidence_class", "verified_current_state")
    text = set_scalar(
        text, "approved_by", OWNER, insert_after="owner"
    )
    text = set_scalar(
        text, "approved_at", ACTIVATION_DATE, insert_after="approved_by"
    )
    text = set_scalar(
        text, "effective_from", ACTIVATION_DATE, insert_after="approved_at"
    )
    text = set_scalar(text, "canonical_path", ACTIVE_REL.as_posix())
    text = set_list(text, "supersedes", ["CPKS-BL@0.44"])

    # Replace the draft-only introductory lifecycle note.
    body_start = text.find("# CPKS-BL – cpKnowledgeSystem Authoritative Baseline")
    section1 = text.find("# 1. Zweck")
    if body_start < 0 or section1 < 0 or section1 <= body_start:
        raise ActivationError("Could not locate Baseline intro block.")
    text = text[:body_start] + ACTIVE_INTRO.rstrip() + "\n\n" + text[section1:]

    # Preserve consolidated content; remove only temporary review comments.
    text, cu_count = remove_cu_comments(text)

    # Lifecycle-only consistency changes inside the activated Baseline.
    text = replace_section(
        text,
        "# 4. Baseline-Identität und Lifecycle",
        "# 5. Systemidentität und primäre Komponenten",
        ACTIVE_SECTION_4,
    )

    text = replace_once(
        text,
        "| `CPKS-BL` | baseline | `0.44` | `verified_current_state` | `Systems/cpKnowledgeSystem/Governance/System Control/CPKS-BL cpKnowledgeSystem Authoritative Baseline.md` |",
        "| `CPKS-BL` | baseline | `0.46` | `verified_current_state` | `Systems/cpKnowledgeSystem/Governance/System Control/CPKS-BL cpKnowledgeSystem Authoritative Baseline.md` |",
        "active Managed Artifact Baseline row",
    )

    text = replace_once(
        text,
        "Die aktive Authoritative Baseline `CPKS-BL@0.44` führt ihrer primären Current-State-Funktion entsprechend:",
        "Die aktive Authoritative Baseline `CPKS-BL@0.46` führt ihrer primären Current-State-Funktion entsprechend:",
        "evidence_class active Baseline reference",
    )

    text = replace_once(
        text,
        "`CPKS-BL@0.44` bleibt die unverändert aktive Ausgangs-Baseline. Die früher aktiven Fassungen `0.1`, `0.2`, `0.3`, `0.41`, `0.42` und `0.43` sind `superseded`.",
        "`CPKS-BL@0.46` ist die aktive Authoritative Baseline. Die früher aktiven Fassungen `0.1`, `0.2`, `0.3`, `0.41`, `0.42`, `0.43` und `0.44` sind `superseded`.",
        "history active Baseline lifecycle",
    )

    text = replace_once(
        text,
        "| Authoritative Baseline | `CPKS-BL@0.44 active`; `CPKS-BL@0.45 withdrawn`; dieser Draft `CPKS-BL@0.46 draft` | `0.44` bleibt aktiv, `0.46` ist die aktuelle nicht verbindliche Folgefassung |",
        "| Authoritative Baseline | `CPKS-BL@0.46 active`; `CPKS-BL@0.44 superseded`; `CPKS-BL@0.45 withdrawn` | `0.46` ist die aktive systemweite Current-State-Baseline |",
        "system status Baseline row",
    )

    # Replace the machine-readable baseline subsection only.
    baseline_start = text.find("baseline:\n", text.find("# 18. Maschinenlesbare Kurzfassung"))
    active_governance = text.find("\nactive_governance:\n", baseline_start)
    if baseline_start < 0 or active_governance < 0:
        raise ActivationError("Could not locate machine-readable baseline subsection.")
    active_yaml = """baseline:
  stable_id: CPKS-BL
  former_ids:
    - CPKS-BASELINE
  active_version: "0.46"
  active_status: active
  active_evidence_class: verified_current_state
  supersedes: CPKS-BL@0.44
  active_canonical_path: Systems/cpKnowledgeSystem/Governance/System Control/CPKS-BL cpKnowledgeSystem Authoritative Baseline.md
  previous_active_version:
    version: "0.44"
    status: superseded
    evidence_class: historical_evidence
    canonical_path: Systems/cpKnowledgeSystem/Governance/Archive/Baselines/CPKS-BL@0.44 cpKnowledgeSystem Authoritative Baseline.md
  previous_development_draft:
    version: "0.45"
    status: withdrawn
    evidence_class: historical_evidence
    canonical_path: Development/cpKnowledgeSystem/Governance/Draft Baselines/Archive/CPKS-BL@0.45 cpKnowledgeSystem Authoritative Baseline.md
"""
    text = text[:baseline_start] + active_yaml.rstrip() + "\n" + text[active_governance:]

    text = replace_section(
        text,
        "# 19. Review- und Aktivierungsgrenze",
        "# 20. Kurzform",
        ACTIVE_SECTION_19,
    )

    start20 = text.find("# 20. Kurzform")
    if start20 < 0:
        raise ActivationError("Section 20 not found.")
    text = text[:start20] + ACTIVE_SECTION_20.rstrip() + "\n"

    if re.search(r"<!--\s*/?CONSOLIDATED-UPDATE\b", text):
        raise ActivationError("Actual CONSOLIDATED-UPDATE HTML comment remains in active text.")

    return text, cu_count


def build_superseded_044(active_044_text: str) -> str:
    text = active_044_text
    text = set_scalar(text, "status", "superseded")
    text = set_scalar(text, "evidence_class", "historical_evidence")
    text = set_scalar(text, "canonical_path", ARCHIVE_044_REL.as_posix())

    body_start = text.find("# CPKS-BL – cpKnowledgeSystem Authoritative Baseline")
    section1 = text.find("# 1. Zweck")
    if body_start < 0 or section1 < 0 or section1 <= body_start:
        raise ActivationError("Could not locate 0.44 intro block.")

    intro = """# CPKS-BL – cpKnowledgeSystem Authoritative Baseline

> [!IMPORTANT]
> Diese Datei ist die historische, durch `CPKS-BL@0.46` ersetzte Authoritative Baseline `CPKS-BL@0.44`.
>
> `CPKS-BL@0.44` war ab dem 27. Juli 2026 aktiv und wurde am 8. August 2026 durch `CPKS-BL@0.46` supersediert.
>
> Für diese historische Fassung gilt:
> `status: superseded` und `evidence_class: historical_evidence`.
>
> Der nachfolgende Inhalt bleibt als periodengerechter Zustands- und Provenienznachweis erhalten.
"""
    return text[:body_start] + intro.rstrip() + "\n\n" + text[section1:]


def assert_preconditions(vault: Path) -> tuple[str, str]:
    draft_path = vault / DRAFT_REL
    active_path = vault / ACTIVE_REL
    withdrawn_045 = vault / WITHDRAWN_045_REL
    archive_044 = vault / ARCHIVE_044_REL

    for path, label in (
        (draft_path, "0.46 draft"),
        (active_path, "0.44 active Baseline"),
        (withdrawn_045, "0.45 withdrawn Baseline"),
    ):
        if not path.is_file():
            raise ActivationError(f"Required {label} missing: {path}")

    if archive_044.exists():
        raise ActivationError(
            f"Archive target for 0.44 already exists: {archive_044}"
        )

    draft_text = draft_path.read_text(encoding="utf-8")
    active_text = active_path.read_text(encoding="utf-8")
    withdrawn_text = withdrawn_045.read_text(encoding="utf-8")

    draft_fm = parse_frontmatter(draft_text)
    active_fm = parse_frontmatter(active_text)
    withdrawn_fm = parse_frontmatter(withdrawn_text)

    expected_draft = {
        "document_type": "baseline",
        "baseline_id": "CPKS-BL",
        "version": "0.46",
        "status": "draft",
        "evidence_class": "verified_current_state",
        "canonical_path": DRAFT_REL.as_posix(),
        "source_artifact": "CPKS-BL@0.45",
    }
    for field, expected in expected_draft.items():
        if str(draft_fm.get(field)) != expected:
            raise ActivationError(
                f"0.46 precondition failed for {field}: "
                f"{draft_fm.get(field)!r} != {expected!r}"
            )

    expected_active = {
        "document_type": "baseline",
        "baseline_id": "CPKS-BL",
        "version": "0.44",
        "status": "active",
        "evidence_class": "verified_current_state",
        "canonical_path": ACTIVE_REL.as_posix(),
    }
    for field, expected in expected_active.items():
        if str(active_fm.get(field)) != expected:
            raise ActivationError(
                f"0.44 precondition failed for {field}: "
                f"{active_fm.get(field)!r} != {expected!r}"
            )

    expected_withdrawn = {
        "version": "0.45",
        "status": "withdrawn",
        "evidence_class": "historical_evidence",
        "canonical_path": WITHDRAWN_045_REL.as_posix(),
    }
    for field, expected in expected_withdrawn.items():
        if str(withdrawn_fm.get(field)) != expected:
            raise ActivationError(
                f"0.45 precondition failed for {field}: "
                f"{withdrawn_fm.get(field)!r} != {expected!r}"
            )

    return draft_text, active_text


def validate_generated(active_046_text: str, superseded_044_text: str) -> None:
    fm46 = parse_frontmatter(active_046_text)
    fm44 = parse_frontmatter(superseded_044_text)

    checks46 = {
        "version": "0.46",
        "status": "active",
        "evidence_class": "verified_current_state",
        "approved_by": OWNER,
        "approved_at": ACTIVATION_DATE,
        "effective_from": ACTIVATION_DATE,
        "canonical_path": ACTIVE_REL.as_posix(),
    }
    for field, expected in checks46.items():
        if str(fm46.get(field)) != expected:
            raise ActivationError(
                f"Generated 0.46 invalid {field}: {fm46.get(field)!r}"
            )

    if fm46.get("supersedes") != ["CPKS-BL@0.44"]:
        raise ActivationError(
            f"Generated 0.46 supersedes invalid: {fm46.get('supersedes')!r}"
        )

    checks44 = {
        "version": "0.44",
        "status": "superseded",
        "evidence_class": "historical_evidence",
        "canonical_path": ARCHIVE_044_REL.as_posix(),
    }
    for field, expected in checks44.items():
        if str(fm44.get(field)) != expected:
            raise ActivationError(
                f"Generated 0.44 invalid {field}: {fm44.get(field)!r}"
            )

    if re.search(r"<!--\s*/?CONSOLIDATED-UPDATE\b", active_046_text):
        raise ActivationError("Generated active 0.46 still contains an actual CU HTML comment.")


def validator_command(repo: Path, vault: Path) -> list[str]:
    python_exe = repo / ".venv/bin/python"
    validator = repo / VALIDATOR_REL
    if not python_exe.is_file():
        raise ActivationError(f"Python environment not found: {python_exe}")
    if not validator.is_file():
        raise ActivationError(f"Validator not found: {validator}")

    cmd = [
        str(python_exe),
        str(validator),
        "--vault",
        str(vault),
        "--strict-exit",
    ]
    validator_text = validator.read_text(encoding="utf-8")
    if "--publish-report" in validator_text:
        cmd.append("--publish-report")
    return cmd


def run_validator(repo: Path, vault: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        validator_command(repo, vault),
        cwd=str(repo),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )


def copy_recovery(vault: Path, rel: Path, recovery_root: Path) -> None:
    source = vault / rel
    target = recovery_root / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def remove_published_reports_from_failed_run(output: str, vault: Path) -> None:
    prefix = "Published report:"
    for line in output.splitlines():
        if prefix not in line:
            continue
        candidate = line.split(prefix, 1)[1].strip()
        try:
            path = Path(candidate).expanduser().resolve()
            generated = (vault / "Generated" / "Validation").resolve()
            path.relative_to(generated)
        except Exception:
            continue
        if path.is_file():
            path.unlink()


def rollback(vault: Path, run_dir: Path) -> None:
    recovery = run_dir / "recovery"

    # Remove activated/transient destinations.
    for rel in (ACTIVE_REL, ARCHIVE_044_REL):
        path = vault / rel
        if path.exists():
            path.unlink()

    # Restore original draft 0.46 and active 0.44.
    for rel in (DRAFT_REL, ACTIVE_REL):
        source = recovery / rel
        target = vault / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--apply", action="store_true")
    parser.add_argument("--vault", type=Path, default=DEFAULT_VAULT)
    parser.add_argument("--repo", type=Path, default=DEFAULT_REPO)
    parser.add_argument("--run-root", type=Path, default=DEFAULT_RUN_ROOT)
    args = parser.parse_args()

    if not args.apply:
        args.check = True

    vault = args.vault.expanduser().resolve()
    repo = args.repo.expanduser().resolve()
    if not vault.is_dir():
        raise ActivationError(f"Vault not found: {vault}")
    if not repo.is_dir():
        raise ActivationError(f"Repository not found: {repo}")

    draft_text, active_044_text = assert_preconditions(vault)
    active_046_text, removed_cus = build_active_046(draft_text)
    superseded_044_text = build_superseded_044(active_044_text)
    validate_generated(active_046_text, superseded_044_text)

    print("ACTIVATION CHECK PASSED.")
    print(f"Target:                  CPKS-BL@0.46")
    print(f"Version remains:         0.46")
    print(f"Target status:           active")
    print(f"Target evidence_class:   verified_current_state")
    print(f"Approval:                {OWNER}, {ACTIVATION_DATE}")
    print(f"Supersedes:              CPKS-BL@0.44")
    print(f"Active path:             {ACTIVE_REL}")
    print(f"Archive 0.44:            {ARCHIVE_044_REL}")
    print(f"Preserve 0.45:           withdrawn, unchanged")
    print(f"CU review pairs removed: {removed_cus}")
    print("Material content changes: none")

    if args.check:
        print("No Vault files changed.")
        return 0

    timestamp = dt.datetime.now().astimezone().strftime("%Y%m%dT%H%M%S%z")
    run_dir = (
        args.run_root.expanduser().resolve()
        / f"{timestamp}-activate-cpks-bl-0.46"
    )
    recovery = run_dir / "recovery"
    run_dir.mkdir(parents=True, exist_ok=False)

    copy_recovery(vault, DRAFT_REL, recovery)
    copy_recovery(vault, ACTIVE_REL, recovery)

    manifest = {
        "action": "activate_managed_artifact",
        "artifact": "CPKS-BL@0.46",
        "owner": OWNER,
        "activation_date": ACTIVATION_DATE,
        "active_target": ACTIVE_REL.as_posix(),
        "superseded_source": "CPKS-BL@0.44",
        "superseded_archive": ARCHIVE_044_REL.as_posix(),
        "unchanged_withdrawn": WITHDRAWN_045_REL.as_posix(),
        "removed_cu_pairs": removed_cus,
        "material_content_changes": False,
    }
    (run_dir / "activation-manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    draft_path = vault / DRAFT_REL
    active_path = vault / ACTIVE_REL
    archive_044 = vault / ARCHIVE_044_REL

    try:
        archive_044.parent.mkdir(parents=True, exist_ok=True)

        # First materialize the historical predecessor and the new active Baseline.
        archive_044.write_text(superseded_044_text, encoding="utf-8")
        active_path.write_text(active_046_text, encoding="utf-8")

        # Remove the former Development draft only after both destinations exist.
        draft_path.unlink()

        proc = run_validator(repo, vault)
        (run_dir / "validator-output.txt").write_text(
            proc.stdout,
            encoding="utf-8",
        )
        print(proc.stdout, end="" if proc.stdout.endswith("\n") else "\n")

        if proc.returncode != 0:
            remove_published_reports_from_failed_run(proc.stdout, vault)
            raise ActivationError(
                f"Post-activation validator failed with exit code {proc.returncode}."
            )

    except Exception:
        rollback(vault, run_dir)
        raise

    print()
    print("ACTIVATION COMPLETED.")
    print(f"Active Baseline:          {ACTIVE_REL}")
    print(f"Superseded 0.44 archive:  {ARCHIVE_044_REL}")
    print(f"Recovery/run directory:   {run_dir}")
    print("CPKS-BL@0.45 remains withdrawn and unchanged.")
    print("No Git commit or push was performed.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ActivationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
