"""Tests for safe project .env loading (no real secrets)."""

from __future__ import annotations

import os
from pathlib import Path

from api import load_project_env


def test_load_project_env_loads_placeholder_without_exposing_secrets(tmp_path: Path, monkeypatch):
    """Prove .env values are loaded into os.environ without printing secrets."""
    marker_name = "RECONENGINE_TEST_ENV_MARKER"
    # Ensure a clean slate for the marker (do not touch GEMINI_API_KEY).
    monkeypatch.delenv(marker_name, raising=False)

    env_file = tmp_path / ".env"
    env_file.write_text(
        "# synthetic test env — not a real secret\n"
        f"{marker_name}=loaded_from_dotenv\n",
        encoding="utf-8",
    )

    loaded = load_project_env(env_file)
    assert loaded is True
    assert os.environ.get(marker_name) == "loaded_from_dotenv"

    # Clean up marker so it cannot leak into later tests.
    monkeypatch.delenv(marker_name, raising=False)


def test_load_project_env_does_not_override_existing_env(tmp_path: Path, monkeypatch):
    """Shell/process env must win over .env when override=False."""
    marker_name = "RECONENGINE_TEST_ENV_MARKER"
    monkeypatch.setenv(marker_name, "from_shell")

    env_file = tmp_path / ".env"
    env_file.write_text(f"{marker_name}=from_dotenv_file\n", encoding="utf-8")

    loaded = load_project_env(env_file)
    assert loaded is True
    assert os.environ.get(marker_name) == "from_shell"


def test_load_project_env_missing_file_returns_false(tmp_path: Path):
    missing = tmp_path / "does-not-exist.env"
    assert load_project_env(missing) is False


def test_env_example_documents_gemini_key_placeholder():
    """Tracked example file documents GEMINI_API_KEY as an empty placeholder."""
    example = Path(__file__).resolve().parent.parent / ".env.example"
    text = example.read_text(encoding="utf-8")
    assert "GEMINI_API_KEY=" in text
    assert "GEMINI_MODEL=gemini-3.5-flash" in text
    # Ensure the example does not contain a non-empty key assignment.
    for line in text.splitlines():
        if line.strip().startswith("GEMINI_API_KEY="):
            assert line.strip() == "GEMINI_API_KEY="
            break
    else:
        raise AssertionError("GEMINI_API_KEY placeholder missing from .env.example")
