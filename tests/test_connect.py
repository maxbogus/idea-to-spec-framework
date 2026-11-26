"""Контракты подключения по пути: `connect` и его CLI."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from idea_to_spec_framework import connect, main

REPO_ROOT = Path(__file__).resolve().parent.parent


def make_framework(root: Path) -> Path:
    """Собрать минимальный валидный каталог фреймворка."""

    (root / "prompts" / "roles").mkdir(parents=True)
    (root / "prompts" / "start.md").write_text("# start\n", encoding="utf-8")
    (root / "prompts" / "roles" / "system-analyst.md").write_text(
        "# role\n", encoding="utf-8"
    )
    skill = root / "skills" / "collect-sources"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("# skill\n", encoding="utf-8")
    (root / "templates").mkdir()
    (root / "scripts").mkdir()
    (root / "scripts" / "check_run.py").write_text("", encoding="utf-8")
    (root / "Makefile").write_text("all:\n", encoding="utf-8")
    return root


def test_repo_is_connectable() -> None:
    """Реальный репозиторий проходит проверку подключения."""

    assert connect(REPO_ROOT) == []


def test_missing_directory_is_reported(tmp_path: Path) -> None:
    """Несуществующий каталог — проблема."""

    problems = connect(tmp_path / "missing")
    assert any("нет каталога" in problem for problem in problems), problems


def test_missing_entry_point_is_reported(tmp_path: Path) -> None:
    """Без `prompts/start.md` подключение невалидно."""

    root = make_framework(tmp_path / "framework")
    (root / "prompts" / "start.md").unlink()
    problems = connect(root)
    assert any("prompts/start.md" in problem for problem in problems), problems


def test_missing_skills_is_reported(tmp_path: Path) -> None:
    """Без каталога скилов подключение невалидно."""

    root = make_framework(tmp_path / "framework")
    shutil.rmtree(root / "skills")
    problems = connect(root)
    assert any("skills" in problem for problem in problems), problems


def test_empty_skills_is_reported(tmp_path: Path) -> None:
    """Каталог скилов без SKILL.md — проблема."""

    root = make_framework(tmp_path / "framework")
    (root / "skills" / "collect-sources" / "SKILL.md").unlink()
    problems = connect(root)
    assert any("EMPTY" in problem for problem in problems), problems


def test_cli_connect_prints_entry_point(capsys: pytest.CaptureFixture[str]) -> None:
    """CLI печатает точку входа и следующий шаг."""

    assert main(["connect", "--framework", str(REPO_ROOT)]) == 0
    captured = capsys.readouterr()
    assert "entry point" in captured.out
    assert "prompts/start.md" in captured.out
    assert "scaffold RUN=demo-001" in captured.out


def test_cli_connect_fails_on_broken_framework(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """CLI возвращает 1 и перечисляет проблемы."""

    root = make_framework(tmp_path / "framework")
    (root / "prompts" / "start.md").unlink()
    assert main(["connect", "--framework", str(root)]) == 1
    captured = capsys.readouterr()
    assert "connect: FAILED" in captured.out
    assert "prompts/start.md" in captured.out
