"""Сводка результатов eval-прогона promptfoo для idea-to-spec-ai.

Читает JSON-отчёт promptfoo и считает метрики, которые ловят типовые ошибки
промптов:
- pass rate по ролям/сценариям;
- дисциплина «факт / гипотеза / прогноз» — изобретённое помечено;
- нарушения границ ролей (BA пишет use cases, SA проектирует архитектуру);
- нарушения режима (auto задаёт вопросы, chat превышает 3 вопроса).

Возвращает 0 при успешном разборе, 1 при ошибке формата.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

#: Маркеры, которыми помечают неподтверждённое утверждение.
DISCIPLINE_MARKERS = ("допущение", "гипотеза", "требует проверки", "прогноз")

#: Признаки критичных развилок для режима hybrid.
HYBRID_FORK_MARKERS = ("контур", "пользовател", "платеж", "интеграц")

#: Блоки, которыми обязан оформляться каждый вопрос в chat / hybrid.
QUESTION_BLOCKS = ("вопрос", "зачем я это спрашиваю", "термины")


def _results(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Извлечь список результатов из отчёта promptfoo.

    Args:
        payload: Разобранный JSON-отчёт.

    Returns:
        Список результатов (пустой, если структура неожиданная).
    """
    results = payload.get("results")
    if isinstance(results, dict):
        items = results.get("results")
        if isinstance(items, list):
            return [item for item in items if isinstance(item, dict)]
    if isinstance(results, list):
        return [item for item in results if isinstance(item, dict)]
    return []


def _output_of(result: dict[str, Any]) -> str:
    """Получить текст ответа из результата.

    Args:
        result: Элемент результатов.

    Returns:
        Текст ответа (пустая строка, если нет).
    """
    response = result.get("response")
    if isinstance(response, str):
        return response
    if isinstance(response, dict):
        output = response.get("output")
        if isinstance(output, str):
            return output
    return ""


def _contract_of(vars_block: dict[str, Any]) -> dict[str, Any]:
    """Извлечь контракт кейса из переменных результата.

    Args:
        vars_block: Переменные результата.

    Returns:
        Словарь контракта (пустой, если контракт не передан).
    """
    raw = vars_block.get("contract")
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str) or not raw.strip():
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _mode_violated(mode_check: str, output: str) -> bool:
    """Проверить нарушение режима по ответу.

    Args:
        mode_check: Тип проверки режима из контракта.
        output: Текст ответа.

    Returns:
        True, если режим нарушен.
    """
    lower = output.lower()
    if mode_check == "auto_no_questions":
        return "зачем я это спрашиваю" in lower
    if mode_check == "chat_three_blocks":
        if not all(block in lower for block in QUESTION_BLOCKS):
            return True
        return output.count("Вопрос") > 3
    if mode_check == "hybrid_forks_only" and "вопрос" in lower:
        return not any(marker in lower for marker in HYBRID_FORK_MARKERS)
    return False


def summarize(report_path: Path) -> dict[str, Any]:
    """Посчитать сводные метрики по отчёту promptfoo.

    Args:
        report_path: Путь к JSON-отчёту.

    Returns:
        Словарь с метриками.

    Raises:
        FileNotFoundError: Если отчёт не найден.
        ValueError: Если отчёт не содержит результатов.
    """
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    results = _results(payload)
    if not results:
        raise ValueError(f"В отчёте нет результатов: {report_path}")

    by_scenario: Counter[str] = Counter()
    passed_by_scenario: Counter[str] = Counter()
    failures: list[str] = []
    discipline_required = 0
    discipline_marked = 0
    boundary_violations: list[str] = []
    mode_violations: list[str] = []

    for result in results:
        vars_block = result.get("vars") or {}
        case_id = str(vars_block.get("id", "?"))
        scenario = str(vars_block.get("scenario", "?"))
        by_scenario[scenario] += 1
        if result.get("success"):
            passed_by_scenario[scenario] += 1
        else:
            failures.append(case_id)

        output = _output_of(result)
        lower = output.lower()
        contract = _contract_of(vars_block)

        if contract.get("requires_assumption_marker"):
            discipline_required += 1
            if any(marker in lower for marker in DISCIPLINE_MARKERS):
                discipline_marked += 1

        boundaries = contract.get("boundary_markers") or []
        if any(str(marker).lower() in lower for marker in boundaries):
            boundary_violations.append(case_id)

        if _mode_violated(str(contract.get("mode_check") or ""), output):
            mode_violations.append(case_id)

    total = len(results)
    passed = sum(passed_by_scenario.values())

    return {
        "report": str(report_path),
        "total": total,
        "passed": passed,
        "failed": total - passed,
        "pass_rate": round(passed / total, 4) if total else 0.0,
        "by_scenario": {
            scenario: {
                "total": by_scenario[scenario],
                "passed": passed_by_scenario[scenario],
            }
            for scenario in sorted(by_scenario)
        },
        "fact_discipline": {
            "required_cases": discipline_required,
            "marked": discipline_marked,
            "rate": round(discipline_marked / discipline_required, 4) if discipline_required else 0.0,
        },
        "boundary_violations": boundary_violations,
        "mode_violations": mode_violations,
        "failed_cases": failures,
    }


def render(summary: dict[str, Any]) -> str:
    """Собрать человекочитаемый отчёт по метрикам.

    Args:
        summary: Словарь с метриками.

    Returns:
        Текст отчёта.
    """
    lines = [
        "=== Сводка eval-прогона (idea-to-spec-ai) ===",
        f"Отчёт: {summary['report']}",
        f"Кейсов: {summary['total']}  |  Пройдено: {summary['passed']}  "
        f"|  Провалено: {summary['failed']}  |  Доля успеха: {summary['pass_rate']:.1%}",
        "",
        "По сценариям:",
    ]
    for scenario, stats in summary["by_scenario"].items():
        lines.append(f"  {scenario:<8} {stats['passed']}/{stats['total']} пройдено")

    discipline = summary["fact_discipline"]
    lines.extend(
        [
            "",
            "Метрики качества промптов:",
            f"  Дисциплина факт/гипотеза: {discipline['marked']}/{discipline['required_cases']} "
            f"({discipline['rate']:.1%}) — изобретённое помечено",
            f"  Нарушений границ ролей:  {len(summary['boundary_violations'])} (цель: 0)",
            f"  Нарушений режима:        {len(summary['mode_violations'])} (цель: 0)",
        ]
    )
    if summary["boundary_violations"]:
        lines.append(f"    границы: {', '.join(summary['boundary_violations'])}")
    if summary["mode_violations"]:
        lines.append(f"    режим:   {', '.join(summary['mode_violations'])}")

    if summary["failed_cases"]:
        lines.extend(["", "Провалившиеся кейсы:"])
        lines.extend(f"  - {case_id}" for case_id in summary["failed_cases"])

    lines.extend(
        [
            "",
            "Интерпретация: провалы фиксируются как xfail(strict=True) в",
            "tests/test_eval_contract.py — не маскируются.",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    """Точка входа CLI.

    Returns:
        0 — сводка построена; 1 — ошибка разбора.
    """
    if len(sys.argv) < 2:
        print("Использование: summarize_eval.py <путь к JSON-отчёту>")
        return 1

    report_path = Path(sys.argv[1])
    try:
        summary = summarize(report_path)
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        print(f"[FAIL] Не удалось разобрать отчёт: {exc}")
        return 1

    print(render(summary))
    return 0


if __name__ == "__main__":
    sys.exit(main())
