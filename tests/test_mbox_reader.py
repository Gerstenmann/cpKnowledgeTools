from pathlib import Path

from knowledge_importer.mbox.reader import read_mbox


def test_read_mbox_first_email() -> None:
    input_path = Path(
        "/Users/cp/Documents/converter/_Knowledge/Email-imports/mbox/"
        "JuniorCodingClub/input/codingclub_sent.mbox"
    )

    emails = read_mbox(input_path)
    first_email = next(emails)

    assert first_email.index == 1
    assert isinstance(first_email.sender, str)
    assert isinstance(first_email.to, list)
    assert isinstance(first_email.cc, list)
    assert isinstance(first_email.bcc, list)
    assert isinstance(first_email.references, list)
    assert isinstance(first_email.body_clean, str)
    assert first_email.source_file == "codingclub_sent.mbox"