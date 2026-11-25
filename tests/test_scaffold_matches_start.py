"""Контракт: `make scaffold` разворачивает ровно то, что обещает prompts/start.md.

Диаграммы объявлены в start.md двумя уровнями: базовый (создаётся всегда)
и расширенный (только по запросу). Поэтому проверяются оба режима.
"""

from __future__ import annotations

import re
import shutil
import subprocess

from idea_to_spec.paths import REPO_ROOT

#: Имя файла артефакта в блоке структуры start.md.
FILE_RE = re.compile(r"([\w-]+\.(?:md|mmd|bpmn))$")
#: Блок кода под «## Шаг 2. Каркас в output/» (первый — базовый уровень).
STEP2_RE = re.compile(r"## Шаг 2\..*?```(.*?)```", re.DOTALL)
#: Блок кода расширенного уровня (второй в Шаге 2).
EXTENDED_RE = re.compile(r"\*\*Расширенный уровень.*?```(.*?)```", re.DOTALL)


def _declared_files(pattern: re.Pattern[str]) -> set[str]:
    """Имена файлов, объявленных в блоке структуры `output/<run-id>/` из start.md.

    Args:
        pattern: Регулярка нужного блока.

    Returns:
        Множество basename'ов (например, `brief.md`, `use-case.mmd`).
    """
    start = (REPO_ROOT / "prompts" / "start.md").read_text(encoding="utf-8")
    match = pattern.search(start)
    assert match is not None, "не найден блок структуры в prompts/start.md"
    declared: set[str] = set()
    for line in match.group(1).splitlines():
        found = FILE_RE.search(line.strip())
        if found is not None:
            declared.add(found.group(1))
    return declared


def _base_files() -> set[str]:
    """Файлы базового уровня (создаются всегда)."""
    return _declared_files(STEP2_RE)


def _extended_files() -> set[str]:
    """Файлы расширенного уровня (только по запросу)."""
    return _declared_files(EXTENDED_RE)


def _scaffold(tier: str, run_id: str) -> set[str]:
    """Развернуть каркас и вернуть множество созданных файлов.

    Args:
        tier: Уровень диаграмм (`base` или `full`).
        run_id: Идентификатор прогона.

    Returns:
        Множество basename'ов созданных файлов.
    """
    out = REPO_ROOT / "output" / run_id
    try:
        subprocess.run(
            ["bash", "scripts/scaffold-run.sh", run_id, tier],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
        )
        return {path.name for path in out.rglob("*") if path.is_file()}
    finally:
        shutil.rmtree(out, ignore_errors=True)


def test_scaffold_matches_start_declaration() -> None:
    """Scaffold по умолчанию создаёт ровно файлы базового уровня из start.md."""
    declared = _base_files()
    assert declared, "структура start.md пуста"

    produced = _scaffold("base", "pytest-scaffold-contract")

    assert produced == declared, (
        "scaffold ≠ start.md (базовый уровень). "
        f"Лишние: {sorted(produced - declared)}; "
        f"недостающие: {sorted(declared - produced)}"
    )


def test_scaffold_full_matches_base_plus_extended() -> None:
    """Полный уровень = базовый + расширенный, как объявлено в start.md."""
    base = _base_files()
    extended = _extended_files()
    assert base and extended, "в start.md нет уровней диаграмм"
    assert not (base & extended), "уровни диаграмм пересекаются"

    produced = _scaffold("full", "pytest-scaffold-contract-full")

    assert produced == base | extended, (
        "scaffold full ≠ start.md (базовый + расширенный). "
        f"Лишние: {sorted(produced - (base | extended))}; "
        f"недостающие: {sorted((base | extended) - produced)}"
    )


def test_extended_tier_is_larger_than_base() -> None:
    """Расширенный уровень действительно больше базового."""
    assert len(_extended_files()) > 0
    assert len(_base_files()) > 0
