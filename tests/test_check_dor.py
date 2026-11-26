"""Контракты полноты набора диаграмм (`scripts/check_dor.py`).

Зачем. `check_run` пропускал прогон с 11 из 14 диаграмм: он проверяет только
присутствующие файлы. Эти тесты фиксируют правило «базовый набор целиком или
расширенный целиком» и строгий режим, который роняет гейт.
"""

from __future__ import annotations

from pathlib import Path

from check_dor import BASE_DIAGRAMS, EXTENDED_DIAGRAMS, check_dor, main


def _write_run(
    run: Path,
    names: tuple[str, ...],
    *,
    bpmn: bool = False,
    png: tuple[str, ...] = (),
) -> None:
    """Создать каталог прогона с указанными диаграммами."""
    diagrams = run / "diagrams"
    diagrams.mkdir(parents=True)
    for name in names:
        (diagrams / f"{name}.mmd").write_text("flowchart LR\n", encoding="utf-8")
    if bpmn:
        (diagrams / "bpmn-process.bpmn").write_text("<xml/>", encoding="utf-8")
    for name in png:
        (diagrams / f"{name}.png").write_text("png", encoding="utf-8")


def test_base_run_is_complete(tmp_path: Path) -> None:
    """Прогон только с базовым набором — полный."""
    run = tmp_path / "run"
    _write_run(run, BASE_DIAGRAMS)

    assert check_dor(run) == []


def test_full_run_is_complete(tmp_path: Path) -> None:
    """Полный набор `.mmd` и канонический BPMN — полный."""
    run = tmp_path / "run"
    _write_run(run, BASE_DIAGRAMS + EXTENDED_DIAGRAMS, bpmn=True)

    assert check_dor(run, "full") == []


def test_partial_extended_run_is_flagged(tmp_path: Path) -> None:
    """Начатый расширенный уровень без трёх диаграмм — проблема."""
    run = tmp_path / "run"
    _write_run(run, (*BASE_DIAGRAMS, "er", "dfd-context"), bpmn=True)

    problems = check_dor(run)

    assert any("dfd-level2" in problem for problem in problems)
    assert any("c4-deployment" in problem for problem in problems)
    assert any("dfd-level3" in problem for problem in problems)


def test_base_profile_ignores_extra_files(tmp_path: Path) -> None:
    """Явный профиль base проверяет только базовый набор."""
    run = tmp_path / "run"
    _write_run(run, BASE_DIAGRAMS + EXTENDED_DIAGRAMS)

    assert check_dor(run, "base") == []


def test_png_without_source_is_flagged(tmp_path: Path) -> None:
    """PNG без `.mmd` — нарушение «диаграмма как код»."""
    run = tmp_path / "run"
    _write_run(run, BASE_DIAGRAMS, png=("ghost",))

    assert any("PNG без источника" in problem for problem in check_dor(run))


def test_strict_returns_nonzero(tmp_path: Path) -> None:
    """Без STRICT отчёт не роняет гейт, со STRICT — роняет."""
    run = tmp_path / "run"
    _write_run(run, (*BASE_DIAGRAMS, "er"))

    assert main([str(run)]) == 0
    assert main([str(run), "--strict"]) == 1


def test_missing_run_dir_is_reported(tmp_path: Path) -> None:
    """Отсутствующий каталог — проблема, а не тихий успех."""
    assert check_dor(tmp_path / "missing") != []
