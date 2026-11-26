"""Контракт `skills/INDEX.md`: генерируется из реестра, не правится руками."""

from __future__ import annotations

from pathlib import Path

import pytest
from render_skills_index import check_index, render_index

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_repo_index_is_up_to_date() -> None:
    """Индекс репозитория совпадает с рендером реестра."""

    assert check_index(REPO_ROOT) == []


def test_index_contains_stage_bundles() -> None:
    """Индекс группирует скилы по стадиям и показывает триггеры."""

    rendered = render_index(REPO_ROOT)
    assert "## System analysis" in rendered
    assert "## Architecture" in rendered
    assert "quantify-nfr" in rendered
    assert "Triggers on" not in rendered


def test_stale_index_is_reported(tmp_path: Path) -> None:
    """Устаревший индекс — проблема, а не тихий успех."""

    (tmp_path / "skills").mkdir()
    (tmp_path / "skills" / "INDEX.md").write_text("stale\n", encoding="utf-8")
    registry = (REPO_ROOT / "skills" / "registry.yaml").read_text(encoding="utf-8")
    (tmp_path / "skills" / "registry.yaml").write_text(registry, encoding="utf-8")
    for skill in (REPO_ROOT / "skills").glob("*/SKILL.md"):
        target = tmp_path / "skills" / skill.parent.name / "SKILL.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(skill.read_text(encoding="utf-8"), encoding="utf-8")
    problems = check_index(tmp_path)
    assert any("устарел" in problem for problem in problems), problems


def test_missing_index_is_reported(tmp_path: Path) -> None:
    """Отсутствующий индекс — проблема."""

    (tmp_path / "skills").mkdir()
    registry = (REPO_ROOT / "skills" / "registry.yaml").read_text(encoding="utf-8")
    (tmp_path / "skills" / "registry.yaml").write_text(registry, encoding="utf-8")
    for skill in (REPO_ROOT / "skills").glob("*/SKILL.md"):
        target = tmp_path / "skills" / skill.parent.name / "SKILL.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(skill.read_text(encoding="utf-8"), encoding="utf-8")
    problems = check_index(tmp_path)
    assert any("не найден" in problem for problem in problems), problems


def test_index_is_deterministic() -> None:
    """Повторный рендер не меняет результат."""

    assert render_index(REPO_ROOT) == render_index(REPO_ROOT)


def test_render_requires_registry(tmp_path: Path) -> None:
    """Без реестра рендер падает явно."""

    with pytest.raises(FileNotFoundError):
        render_index(tmp_path)
