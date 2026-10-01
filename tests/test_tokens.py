import sys

import pytest

from wildrift import security, tokens


def test_generates_valid_app_tokens_line(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["tokens", "ChocoLoco", "sam"])
    tokens.main()
    line = capsys.readouterr().out.splitlines()[0]
    assert line.startswith("APP_TOKENS=chocoloco:")
    monkeypatch.setenv("APP_TOKENS", line.removeprefix("APP_TOKENS="))
    assert sorted(security._tokens().values()) == ["chocoloco", "sam"]  # the app accepts what it prints


def test_rejects_bad_names(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["tokens", "Bad Name!"])
    with pytest.raises(SystemExit):
        tokens.main()


def test_needs_a_name(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["tokens"])
    with pytest.raises(SystemExit):
        tokens.main()
