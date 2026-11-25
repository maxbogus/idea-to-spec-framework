"""Проверки сводки метрик eval (`scripts/summarize_eval.py`).

Метрики ловят типовые ошибки промптов: непомеченное изобретённое утверждение,
нарушение границ ролей (BA пишет use cases), нарушение режима (auto задаёт
вопросы; chat игнорирует три блока вопроса).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from idea_to_spec.paths import EVAL_CASES_FILE
from summarize_eval import summarize


def _case(case_id: str) -> dict[str, Any]:
    """Найти контракт кейса по идентификатору.

    Args:
        case_id: Идентификатор кейса.

    Returns:
        Контракт кейса.

    Raises:
        AssertionError: Если кейс не найден.
    """
    for line in EVAL_CASES_FILE.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        contract = json.loads(json.loads(line)["vars"]["contract"])
        if contract["id"] == case_id:
            return dict(contract)
    raise AssertionError(f"Кейс {case_id} не найден")


def _result(case: dict[str, Any], output: str, success: bool) -> dict[str, Any]:
    """Собрать элемент отчёта promptfoo для одного кейса.

    Args:
        case: Контракт кейса.
        output: Текст ответа модели.
        success: Признак успеха кейса.

    Returns:
        Словарь в формате отчёта promptfoo.
    """
    return {
        "vars": {
            "id": case["id"],
            "scenario": case["scenario"],
            "contract": json.dumps(case, ensure_ascii=False),
        },
        "response": {"output": output},
        "success": success,
    }


def _write_report(tmp_path: Path, results: list[dict[str, Any]]) -> Path:
    """Записать отчёт promptfoo во временный файл.

    Args:
        tmp_path: Каталог для временных файлов.
        results: Элементы отчёта.

    Returns:
        Путь к записанному отчёту.
    """
    report = tmp_path / "eval.json"
    report.write_text(
        json.dumps({"results": {"results": results}}, ensure_ascii=False),
        encoding="utf-8",
    )
    return report


def test_pass_rate_counts(tmp_path: Path) -> None:
    """Pass rate считается по всем результатам отчёта."""
    pm = _case("PM-01-measurable-metric-vague-idea")
    orch = _case("ORCH-01-auto-no-questions")
    report = _write_report(tmp_path, [_result(pm, "ok", True), _result(orch, "bad", False)])

    summary = summarize(report)
    assert summary["total"] == 2
    assert summary["passed"] == 1
    assert summary["pass_rate"] == 0.5


def test_fact_discipline_counts(tmp_path: Path) -> None:
    """Кейс, требующий маркера допущения, засчитывается только с маркером."""
    ba = _case("BA-02-fact-vs-assumption")
    marked = _write_report(tmp_path, [_result(ba, "10 млн пользователей — допущение", True)])
    assert summarize(marked)["fact_discipline"]["marked"] == 1

    unmarked = tmp_path / "unmarked"
    unmarked.mkdir()
    plain = _write_report(unmarked, [_result(ba, "10 млн пользователей", True)])
    summary = summarize(plain)
    assert summary["fact_discipline"]["required_cases"] == 1
    assert summary["fact_discipline"]["marked"] == 0


def test_boundary_violation_detected(tmp_path: Path) -> None:
    """BA-ответ с use cases (UC-) фиксируется как нарушение границы ролей."""
    ba = _case("BA-01-personas-jtbd")
    report = _write_report(tmp_path, [_result(ba, "UC-1 FR-1", False)])

    summary = summarize(report)
    assert "BA-01-personas-jtbd" in summary["boundary_violations"]


def test_mode_violation_detected(tmp_path: Path) -> None:
    """Chat-ответ без трёх блоков вопроса фиксируется как нарушение режима."""
    orch = _case("ORCH-02-chat-three-block-questions")
    report = _write_report(tmp_path, [_result(orch, "Вопрос: какой контур?", False)])

    summary = summarize(report)
    assert "ORCH-02-chat-three-block-questions" in summary["mode_violations"]


def test_auto_question_is_mode_violation(tmp_path: Path) -> None:
    """Вопрос в режиме auto фиксируется как нарушение режима."""
    orch = _case("ORCH-01-auto-no-questions")
    report = _write_report(
        tmp_path,
        [_result(orch, "Зачем я это спрашиваю: чтобы понять контур", False)],
    )

    summary = summarize(report)
    assert "ORCH-01-auto-no-questions" in summary["mode_violations"]


def test_summary_requires_results(tmp_path: Path) -> None:
    """Пустой отчёт — ошибка разбора, а не нулевые метрики."""
    report = tmp_path / "empty.json"
    report.write_text(json.dumps({"results": {"results": []}}), encoding="utf-8")
    with pytest.raises(ValueError):
        summarize(report)
