import json

from cp_knowledge_tools.reuse.__main__ import main


def test_module_inspect_and_candidate(candidate, target, capsys):
    assert (
        main(
            [
                "inspect",
                "--target",
                str(candidate),
                "--need",
                "normalization",
                "--term",
                "normalize",
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["matches"]
    assert main(["candidate", "--target", str(target), "--source", str(candidate)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["snapshot"]["commit"]
    assert result["vulnerability_state"] == "not_checked"


def test_module_blocked_input(target, capsys):
    assert (
        main(
            [
                "candidate",
                "--target",
                str(target),
                "--source",
                "https://user:secret@example.invalid/repo",
            ]
        )
        == 2
    )
    output = capsys.readouterr()
    assert "secret" not in output.err
    assert not output.out
