from openreflex.entrypoint import _tokens


def test_tokens_help_shows_usage_instead_of_unknown_action(capsys):
    code = _tokens(["--help"])
    out = capsys.readouterr().out
    assert code == 0
    assert "Unknown tokens action" not in out
    assert "enable" in out and "disable" in out and "status" in out


def test_tokens_unknown_action_prints_usage(capsys):
    code = _tokens(["bogus"])
    out = capsys.readouterr().out
    assert code == 2
    assert "usage: openreflex tokens" in out
