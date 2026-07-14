from pathlib import Path

from knowledge_importer.mbox.cli import run_import


def test_run_import(tmp_path: Path) -> None:
    input_path = Path(
        "/Users/cp/Documents/converter/_Knowledge/Email-imports/mbox/"
        "JuniorCodingClub/input/codingclub_sent.mbox"
    )

    jsonl_path = tmp_path / "emails.jsonl"
    markdown_dir = tmp_path / "markdown"

    statistics = run_import(
        input_mbox=input_path,
        jsonl_path=jsonl_path,
        markdown_dir=markdown_dir,
    )

    assert statistics["total"] > 0
    assert statistics["jsonl"] == statistics["total"]
    assert (
        statistics["analyze"]
        + statistics["review"]
        + statistics["archive_only"]
        + statistics["discard"]
        == statistics["total"]
    )
    assert jsonl_path.exists()

