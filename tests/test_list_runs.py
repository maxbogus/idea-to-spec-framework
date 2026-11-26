"""Контракты поиска прогонов для `make check-runs`.

Зачем. Раньше прогоны брались через `git ls-files output`: вне git команда
печатала «нет прогонов» и завершалась успешно — гейт молча ничего не
проверял. Скрипт обязан либо отдать список, либо упасть.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from list_runs import NoRunsError, discover_runs


def _write_run(root: Path, run_id: str) -> None:
    """Создать минимальный каталог прогона."""
    run = root / run_id
    run.mkdir(parents=True)
    (run / "brief.md").write_text("x", encoding="utf-8")


def _git(root: Path, *args: str) -> None:
    """Выполнить git-команду в root (для тестов git-источника)."""
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


@pytest.mark.skipif(shutil.which("git") is None, reason="git недоступен")
def test_tracked_runs_are_preferred(tmp_path: Path) -> None:
    """В git-репозитории берутся отслеживаемые прогоны."""
    _git(tmp_path, "init")
    _write_run(tmp_path, "tracked-001")
    _write_run(tmp_path, "untracked-001")
    _git(tmp_path, "add", "tracked-001")

    assert discover_runs(tmp_path) == ["tracked-001"]


@pytest.mark.skipif(shutil.which("git") is None, reason="git недоступен")
def test_untracked_runs_are_not_masked(tmp_path: Path) -> None:
    """Если ничего не отслеживается, но прогоны есть — проверяются они."""
    _git(tmp_path, "init")
    _write_run(tmp_path, "fresh-001")

    assert discover_runs(tmp_path) == ["fresh-001"]


def test_non_git_directory_uses_disk(tmp_path: Path) -> None:
    """Вне git список берётся с диска, а не превращается в тихий успех."""
    _write_run(tmp_path, "run-b")
    _write_run(tmp_path, "run-a")

    assert discover_runs(tmp_path) == ["run-a", "run-b"]


def test_missing_root_fails_loudly(tmp_path: Path) -> None:
    """Отсутствующий каталог прогонов — ошибка, а не пустой результат."""
    with pytest.raises(NoRunsError):
        discover_runs(tmp_path / "missing")


def test_empty_root_fails_loudly(tmp_path: Path) -> None:
    """Пустой каталог прогонов — ошибка с подсказкой, что делать."""
    (tmp_path / "not-a-run.txt").write_text("x", encoding="utf-8")
    with pytest.raises(NoRunsError):
        discover_runs(tmp_path)


@pytest.mark.skipif(shutil.which("git") is None, reason="git недоступен")
def test_populated_untracked_run_is_checked(tmp_path: Path) -> None:
    """Заполненный, но ещё не добавленный в git прогон не выпадает из гейта.

    Измерено на auto-005: до `git add` `make check-runs` его не видел.
    """
    _git(tmp_path, "init")
    _write_run(tmp_path, "tracked-001")
    _write_run(tmp_path, "ready-002")
    diagrams = tmp_path / "ready-002" / "diagrams"
    diagrams.mkdir()
    (diagrams / "use-case.png").write_bytes(b"png")
    _git(tmp_path, "add", "tracked-001")

    assert discover_runs(tmp_path) == ["ready-002", "tracked-001"]


@pytest.mark.skipif(shutil.which("git") is None, reason="git недоступен")
def test_fresh_scaffold_is_skipped(tmp_path: Path) -> None:
    """Пустой scaffold не ломает гейт: он не считается прогоном."""
    _git(tmp_path, "init")
    _write_run(tmp_path, "tracked-001")
    _write_run(tmp_path, "fresh-002")
    _git(tmp_path, "add", "tracked-001")

    assert discover_runs(tmp_path) == ["tracked-001"]
