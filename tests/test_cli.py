"""CLI smoke tests — verify commands don't crash on basic invocations."""

import re

from typer.testing import CliRunner

from cinsights.cli import app

runner = CliRunner()


def _strip_ansi(text: str) -> str:
    """Remove ANSI escape codes so we can match plain text."""
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


def test_cli_help():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    out = _strip_ansi(result.output)
    assert "index" in out
    assert "analyze" in out
    assert "digest" in out
    assert "refresh" in out
    assert "serve" in out
    assert "setup" in out


def test_cli_index_help():
    result = runner.invoke(app, ["index", "--help"])
    assert result.exit_code == 0
    out = _strip_ansi(result.output)
    assert "--hours" in out
    assert "--source" in out


def test_cli_analyze_help():
    result = runner.invoke(app, ["analyze", "--help"])
    assert result.exit_code == 0
    out = _strip_ansi(result.output)
    assert "--limit" in out
    assert "--concurrency" in out


def test_cli_digest_help():
    result = runner.invoke(app, ["digest", "--help"])
    assert result.exit_code == 0
    out = _strip_ansi(result.output)
    assert "project" in out
    assert "user" in out


def test_cli_refresh_help():
    result = runner.invoke(app, ["refresh", "--help"])
    assert result.exit_code == 0
    out = _strip_ansi(result.output)
    assert "--hours" in out


def test_cli_setup_help():
    result = runner.invoke(app, ["setup", "--help"])
    assert result.exit_code == 0
    out = _strip_ansi(result.output)
    assert "--provider" in out
    assert "--model" in out


def test_cli_score_help():
    result = runner.invoke(app, ["score", "--help"])
    assert result.exit_code == 0
