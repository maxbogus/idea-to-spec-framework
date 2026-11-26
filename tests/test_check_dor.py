"""Контракты полноты набора диаграмм (`scripts/check_dor.py`).

Зачем. `check_run` пропускал прогон с 11 из 14 диаграмм: он проверяет только
присутствующие файлы. Эти тесты фиксируют правило «базовый набор целиком или
расширенный целиком», строгий режим и P2: применимость объявляется явно, а
скопированный из шаблона файл — пустышка, а не диаграмма.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from check_dor import (
    BASE_DIAGRAMS,
    EXTENDED_DIAGRAMS,
    FULL_DIAGRAMS,
    PROFILES,
    check_dor,
    load_applicability,
    main,
    pack_diagrams,
    stub_reason,
)
from idea_to_spec.paths import REPO_ROOT

#: Шаблон, которым пользуются тесты пустышек.
TEMPLATE = REPO_ROOT / "templates" / "dfd-level2.mmd"


def _write_run(
    run: Path,
    names: tuple[str, ...],
    *,
    bpmn: bool = False,
    png: tuple[str, ...] = (),
) -> None:
    """Создать каталог прогона с указанными диаграммами.

    Содержимое — не шаблон: пустышки проверяются отдельными тестами.
    """
    diagrams = run / "diagrams"
    diagrams.mkdir(parents=True)
    for name in names:
        (diagrams / f"{name}.mmd").write_text(
            'flowchart LR\n    A["реальный"] --> B\n', encoding="utf-8"
        )
    if bpmn:
        (diagrams / "bpmn-process.bpmn").write_text("<xml/>", encoding="utf-8")
    for name in png:
        (diagrams / f"{name}.png").write_text("png", encoding="utf-8")


def _write_plan(run: Path, not_applicable: dict[str, str] | str | None) -> None:
    """Записать run-report.md с декларацией применимости.

    Args:
        run: Каталог прогона.
        not_applicable: Объект «диаграмма → причина», сырая строка (для битого
            JSON) или None — блок не добавляется.
    """
    lines = ["# Run report", "", "## Пакеты диаграмм", ""]
    if not_applicable is not None:
        body = (
            not_applicable
            if isinstance(not_applicable, str)
            else json.dumps({"not_applicable": not_applicable}, ensure_ascii=False)
        )
        lines.extend(["```json", body, "```", ""])
    (run / "run-report.md").write_text("\n".join(lines), encoding="utf-8")


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


def test_not_applicable_removes_requirement(tmp_path: Path) -> None:
    """Объявленная неприменимой диаграмма не считается пропущенной."""
    run = tmp_path / "run"
    names = tuple(name for name in FULL_DIAGRAMS if name != "dfd-level2")
    _write_run(run, names, bpmn=True)
    _write_plan(run, {"dfd-level2": "процесс описан одним шагом (spec.md §9)"})

    assert check_dor(run, "full") == []


def test_not_applicable_requires_reason(tmp_path: Path) -> None:
    """«Не применимо» без причины — проблема: это способ обойти проверку."""
    run = tmp_path / "run"
    names = tuple(name for name in FULL_DIAGRAMS if name != "dfd-level2")
    _write_run(run, names, bpmn=True)

    for reason in ("", "—", "нет"):
        _write_plan(run, {"dfd-level2": reason})
        assert any("без причины" in problem for problem in check_dor(run, "full")), reason


def test_not_applicable_unknown_diagram_is_flagged(tmp_path: Path) -> None:
    """Опечатка в имени диаграммы не проходит молча."""
    run = tmp_path / "run"
    _write_run(run, BASE_DIAGRAMS)
    _write_plan(run, {"dfd-leve2": "опечатка"})

    assert any("неизвестная диаграмма" in problem for problem in check_dor(run))


def test_broken_plan_json_is_reported(tmp_path: Path) -> None:
    """Битый JSON в декларации — проблема, а не «все применимы»."""
    run = tmp_path / "run"
    _write_run(run, BASE_DIAGRAMS)
    _write_plan(run, '{"not_applicable": {"dfd-level2": "x"}')

    assert any("невалидный JSON" in problem for problem in check_dor(run))
    assert load_applicability(run)[0] == {}


def test_plan_without_not_applicable_key_is_reported(tmp_path: Path) -> None:
    """Блок без ключа `not_applicable` — декларация не прочитана."""
    run = tmp_path / "run"
    _write_run(run, BASE_DIAGRAMS)
    _write_plan(run, '{"этапы": []}')

    assert any("без ключа" in problem for problem in check_dor(run))


def test_old_run_without_plan_keeps_presence_rule(tmp_path: Path) -> None:
    """Старый прогон без блока: все диаграммы применимы, поведение прежнее."""
    run = tmp_path / "run"
    _write_run(run, (*BASE_DIAGRAMS, "er"))
    _write_plan(run, None)

    problems = check_dor(run)
    assert load_applicability(run) == ({}, [])
    assert any("dfd-level2" in problem for problem in problems)


def test_template_copy_is_a_stub(tmp_path: Path) -> None:
    """Файл, совпадающий с шаблоном, — пустышка, а не диаграмма."""
    run = tmp_path / "run"
    _write_run(run, FULL_DIAGRAMS, bpmn=True)
    (run / "diagrams" / "dfd-level2.mmd").write_text(
        TEMPLATE.read_text(encoding="utf-8"), encoding="utf-8"
    )

    assert stub_reason(run, "dfd-level2").startswith("совпадает с templates/")
    assert any("шаблонная пустышка" in problem for problem in check_dor(run, "full"))


def test_template_bpmn_is_a_stub(tmp_path: Path) -> None:
    """Скопированный канонический BPMN — тоже пустышка, а не диаграмма."""
    run = tmp_path / "run"
    _write_run(run, BASE_DIAGRAMS, bpmn=True)
    template = REPO_ROOT / "templates" / "bpmn-process.bpmn"
    (run / "diagrams" / "bpmn-process.bpmn").write_text(
        template.read_text(encoding="utf-8"), encoding="utf-8"
    )

    assert any("шаблонная пустышка" in problem for problem in check_dor(run))


def test_skeleton_placeholders_are_a_stub(tmp_path: Path) -> None:
    """Оставшиеся скелетные подписи — пустышка, даже если файл правили."""
    run = tmp_path / "run"
    _write_run(run, BASE_DIAGRAMS)
    (run / "diagrams" / "er.mmd").write_text(
        'flowchart LR\n    P21["2.1. Под-процесс"]:::process\n', encoding="utf-8"
    )

    assert "скелетные подписи" in stub_reason(run, "er")
    assert any("шаблонная пустышка" in problem for problem in check_dor(run, "base"))


def test_not_applicable_but_built_is_a_contradiction(tmp_path: Path) -> None:
    """Декларация и артефакт разошлись: диаграмма построена, но объявлена NA."""
    run = tmp_path / "run"
    _write_run(run, FULL_DIAGRAMS, bpmn=True)
    _write_plan(run, {"gantt": "план не нужен"})

    problems = check_dor(run, "full")
    assert any("gantt" in problem and "построена" in problem for problem in problems), problems


def test_not_applicable_stub_is_reported_as_stub(tmp_path: Path) -> None:
    """Пустышка, объявленная неприменимой, — всё равно пустышка."""
    run = tmp_path / "run"
    names = tuple(name for name in FULL_DIAGRAMS if name != "dfd-level2")
    _write_run(run, names, bpmn=True)
    (run / "diagrams" / "dfd-level2.mmd").write_text(
        TEMPLATE.read_text(encoding="utf-8"), encoding="utf-8"
    )
    _write_plan(run, {"dfd-level2": "процесс описан одним шагом"})

    problems = check_dor(run, "full")
    assert any("dfd-level2" in problem and "пустышка" in problem for problem in problems), problems


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


def test_pack_profiles_are_built_from_packs() -> None:
    """Профили DoR собираются из паков, а не дублируют полный набор."""
    assert set(pack_diagrams("ai")) <= set(PROFILES["ai"])
    assert "state" in PROFILES["startup"]
    assert "domain-map" in PROFILES["enterprise"]
    assert "rag-pipeline" in PROFILES["ai"]
    assert "c4-code" not in PROFILES["ai"]


def test_ai_profile_reports_missing_pack_diagrams(tmp_path: Path) -> None:
    """Профиль ai требует AI-пак: полный набор без него — неполный."""
    run = tmp_path / "run"
    _write_run(run, BASE_DIAGRAMS + EXTENDED_DIAGRAMS, bpmn=True)

    problems = check_dor(run, "ai")

    assert any("rag-pipeline" in problem for problem in problems)
    assert any("agent-workflow" in problem for problem in problems)


def test_pack_complete_run_passes_ai_profile(tmp_path: Path) -> None:
    """Полный набор + пак ai закрывает профиль ai."""
    run = tmp_path / "run"
    names = (*BASE_DIAGRAMS, *EXTENDED_DIAGRAMS, *pack_diagrams("behavior", "data", "ai"))
    _write_run(run, names, bpmn=True)

    assert check_dor(run, "ai") == []


def test_unknown_pack_name_is_a_key_error() -> None:
    """Опечатка в имени пака не проходит молча."""
    with pytest.raises(KeyError):
        pack_diagrams("aii")
