"""Контракты экспорта содержимого пакета.

Тесты проверяют три свойства: экспорт кладёт именно те файлы, на которые
ссылаются материалы воркшопа; повторный экспорт не затирает чужой каталог;
`verify` ловит ручные правки и удаления.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from idea_to_spec_framework import MANIFEST_NAME, ExportError, __version__, export, main, verify

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_version_matches_pyproject() -> None:
    """Версия в коде совпадает с версией дистрибутива."""
    data = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    project = data["project"]
    assert isinstance(project, dict)
    assert project["version"] == __version__


def test_export_copies_content_and_manifest(tmp_path: Path) -> None:
    """Экспорт кладёт файлы, на которые ссылается воркшоп, и манифест."""
    dest = tmp_path / "framework"
    report = export(dest)
    assert report.files > 0
    assert (dest / "prompts" / "start.md").is_file()
    assert (dest / "templates" / "mermaid-config.json").is_file()
    assert (dest / "skills" / "INDEX.md").is_file()
    assert (dest / "skills" / "quantify-nfr" / "SKILL.md").is_file()
    assert (dest / "docs" / "connect.md").is_file()
    assert (dest / MANIFEST_NAME).is_file()


def test_export_refuses_non_empty_dest(tmp_path: Path) -> None:
    """Непустой каталог без force не перезаписывается."""
    dest = tmp_path / "framework"
    dest.mkdir()
    (dest / "keep.txt").write_text("x", encoding="utf-8")
    with pytest.raises(ExportError):
        export(dest)


def test_export_force_rewrites_previous_export(tmp_path: Path) -> None:
    """force разрешён для каталога, созданного экспортом."""
    dest = tmp_path / "framework"
    export(dest)
    (dest / "prompts" / "start.md").write_text("tampered", encoding="utf-8")
    export(dest, force=True)
    assert verify(dest) == []


def test_verify_reports_tampered_file(tmp_path: Path) -> None:
    """Ручная правка внутри экспорта видна verify."""
    dest = tmp_path / "framework"
    export(dest)
    (dest / "prompts" / "start.md").write_text("tampered", encoding="utf-8")
    problems = verify(dest)
    assert problems
    assert any("prompts/start.md" in problem for problem in problems)


def test_verify_reports_missing_manifest(tmp_path: Path) -> None:
    """Без манифеста проверять нечего — это проблема, а не тихий успех."""
    dest = tmp_path / "framework"
    dest.mkdir()
    assert verify(dest)


def test_cli_export_and_verify(tmp_path: Path) -> None:
    """CLI export и verify работают на одном каталоге."""

    dest = tmp_path / "framework"
    assert main(["export", "--dest", str(dest)]) == 0
    assert main(["verify", "--dest", str(dest)]) == 0
