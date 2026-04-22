"""CLI smoke tests — verify commands don't crash on basic invocations."""

from typer.testing import CliRunner

from cinsights.cli import app

runner = CliRunner()


def test_cli_help():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "index" in result.output
    assert "analyze" in result.output
    assert "digest" in result.output
    assert "refresh" in result.output
    assert "serve" in result.output
    assert "setup" in result.output


def test_cli_index_help():
    result = runner.invoke(app, ["index", "--help"])
    assert result.exit_code == 0
    assert "--hours" in result.output
    assert "--source" in result.output


def test_cli_analyze_help():
    result = runner.invoke(app, ["analyze", "--help"])
    assert result.exit_code == 0
    assert "--limit" in result.output
    assert "--concurrency" in result.output


def test_cli_digest_help():
    result = runner.invoke(app, ["digest", "--help"])
    assert result.exit_code == 0
    assert "project" in result.output
    assert "user" in result.output


def test_cli_refresh_help():
    result = runner.invoke(app, ["refresh", "--help"])
    assert result.exit_code == 0
    assert "--hours" in result.output


def test_cli_setup_help():
    result = runner.invoke(app, ["setup", "--help"])
    assert result.exit_code == 0
    assert "--provider" in result.output
    assert "--model" in result.output


def test_cli_score_help():
    result = runner.invoke(app, ["score", "--help"])
    assert result.exit_code == 0
