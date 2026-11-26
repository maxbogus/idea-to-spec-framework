"""Крос-артефактные проверки согласованности прогонов (`scripts/check_run.py`)."""

from __future__ import annotations

from pathlib import Path

import pytest

from check_run import check_run
from idea_to_spec.paths import OUTPUT_DIR


@pytest.mark.parametrize("run_id", ["auto-001", "auto-002", "auto-003", "auto-004", "chat-001"])
def test_golden_runs_are_consistent(run_id: str) -> None:
    """Готовые демо-прогоны проходят структурную проверку без ошибок."""
    run_dir = OUTPUT_DIR / run_id
    if not run_dir.is_dir():
        pytest.skip(f"нет прогона {run_id}")
    assert check_run(run_dir) == []


def test_checker_detects_missing_br_source(tmp_path: Path) -> None:
    """FR без источника BR-* фиксируется как проблема."""
    run = tmp_path / "run"
    run.mkdir()
    (run / "functional-requirements.md").write_text(
        "| ID | Требование | Источник |\n|---|---|---|\n| FR-1 | x |  |\n",
        encoding="utf-8",
    )
    assert any("FR-1" in problem for problem in check_run(run))


def test_checker_ignores_prose_trace_map(tmp_path: Path) -> None:
    """Карта UC→J, объявленная прозой, не считается трассировкой.

    Регрессия: прогон `chat-001` держал карту «UC-1→J-1, …» в разделе
    «Правила» файла use-cases.md, но не в строках таблицы и не в jtbd.md.
    Детерминированный чекер такую карту не видел, и прогон проходил гейт
    незаполненным. Теперь такое расхождение — проблема.
    """
    run = tmp_path / "run"
    run.mkdir()
    (run / "use-cases.md").write_text(
        "| ID | Актор | Цель |\n|---|---|---|\n"
        "| UC-1 | P-1 | Сделать дело |\n"
        "\n## Правила\n\n"
        "- Трассировка UC → J: UC-1→J-1.\n",
        encoding="utf-8",
    )
    (run / "jtbd.md").write_text(
        "| ID | Персона | Когда |\n|---|---|---|\n| J-1 | P-1 | утром |\n",
        encoding="utf-8",
    )
    problems = check_run(run)
    assert any("UC-1" in problem and "J-" in problem for problem in problems)


def test_checker_accepts_trace_in_goal_cell(tmp_path: Path) -> None:
    """J-ссылка в ячейке «Цель» — валидная трассировка (конвенция auto-002)."""
    run = tmp_path / "run"
    run.mkdir()
    (run / "use-cases.md").write_text(
        "| ID | Актор | Цель |\n|---|---|---|\n| UC-1 | P-1 | Сделать дело (J-1) |\n",
        encoding="utf-8",
    )
    (run / "jtbd.md").write_text(
        "| ID | Персона | Когда |\n|---|---|---|\n| J-1 | P-1 | утром |\n",
        encoding="utf-8",
    )
    assert not any("UC-1" in problem for problem in check_run(run))


def test_checker_requires_source_for_closed_question(tmp_path: Path) -> None:
    """Закрытый вопрос без источника ответа — проблема.

    Связка «вопрос → ответ» — то, чего не знал `check_run.py` до P13:
    закрытый вопрос без источника означает, что на чём основан ответ,
    непонятно, и «ответ заказчика» неотличим от выдумки.
    """
    run = tmp_path / "run"
    run.mkdir()
    (run / "open-questions.md").write_text(
        "| ID | Вопрос | Ответ (источник) | Статус |\n|---|---|---|---|\n"
        "| Q-1 | Тип клиента? | B2B | закрыт |\n",
        encoding="utf-8",
    )
    problems = check_run(run)
    assert any("Q-1" in problem and "источник" in problem for problem in problems)


def test_checker_flags_open_question_with_source(tmp_path: Path) -> None:
    """Открытый вопрос с указанным источником — проблема."""
    run = tmp_path / "run"
    run.mkdir()
    (run / "open-questions.md").write_text(
        "| ID | Вопрос | Ответ (источник) | Статус |\n|---|---|---|---|\n"
        "| Q-1 | Цена тарифа? | 990 ₽ (ответ заказчика) | открыт |\n",
        encoding="utf-8",
    )
    problems = check_run(run)
    assert any("Q-1" in problem for problem in problems)


def test_checker_accepts_question_answer_pair(tmp_path: Path) -> None:
    """Закрытый вопрос с источником — корректная связка, проблем нет."""
    run = tmp_path / "run"
    run.mkdir()
    (run / "open-questions.md").write_text(
        "| ID | Вопрос | Ответ (источник) | Статус |\n|---|---|---|---|\n"
        "| Q-1 | Цена тарифа? | 990 ₽ (ответ заказчика) | закрыт |\n"
        "| Q-2 | Срок хранения? | нет данных | открыт |\n",
        encoding="utf-8",
    )
    problems = check_run(run)
    assert not any("Q-" in problem for problem in problems)


def test_checker_detects_duplicate_question_id(tmp_path: Path) -> None:
    """Повторяющийся идентификатор вопроса — проблема."""
    run = tmp_path / "run"
    run.mkdir()
    (run / "open-questions.md").write_text(
        "| ID | Вопрос | Ответ (источник) | Статус |\n|---|---|---|---|\n"
        "| Q-1 | Цена тарифа? | 990 ₽ (ответ заказчика) | закрыт |\n"
        "| Q-1 | Цена тарифа? | 990 ₽ (ответ заказчика) | закрыт |\n",
        encoding="utf-8",
    )
    problems = check_run(run)
    assert any("повторяется" in problem for problem in problems)


def test_checker_ignores_run_without_question_table(tmp_path: Path) -> None:
    """Файл без таблицы вопросов не ломает прогон (старый формат)."""
    run = tmp_path / "run"
    run.mkdir()
    (run / "open-questions.md").write_text(
        "# Открытые вопросы\n\n> Таблица не заполнялась.\n",
        encoding="utf-8",
    )
    assert not any("Q-" in problem for problem in check_run(run))


def test_checker_detects_invented_diagram_node(tmp_path: Path) -> None:
    """Узел диаграммы, которого нет в артефактах, фиксируется как проблема."""
    run = tmp_path / "run"
    (run / "diagrams").mkdir(parents=True)
    (run / "personas.md").write_text("| P-1 | x |\n", encoding="utf-8")
    (run / "diagrams" / "use-case.mmd").write_text(
        'usecase-beta\n    actor A("P-9")\n', encoding="utf-8"
    )
    assert any("P-9" in problem for problem in check_run(run))


def test_missing_run_dir_reports_problem(tmp_path: Path) -> None:
    """Несуществующий каталог прогона — проблема, а не тихий успех."""
    assert check_run(tmp_path / "missing")
