"""Traceability-леджер (P4): требование → задача → коммит/тест → статус.

Зачем. До P4 матрица трассировки связывала требование с целью, спекой и
критерием приёмки, но не с работой: по артефактам прогона нельзя было
ответить «какая задача закрывает FR-3» и «в каком она состоянии».
Теперь у каждого `FR-*` обязана быть строка с задачей `T-*` и статусом
покрытия; коммит/тест может быть пустым на этапе плана.

Проверки условны (как lifecycle в P1): старый пятиколоночный формат
демо-прогонов принимается, иначе `make check-runs` упал бы на уже
записанных прогонах.
"""

from __future__ import annotations

from pathlib import Path

from check_run import check_run
from idea_to_spec.paths import REPO_ROOT, ROLES_DIR

#: FR-таблица в старом формате: lifecycle-проверки не подключаются.
FR_TABLE = (
    "| ID | Требование | Источник | Приоритет | Критерий приёмки |\n"
    "|---|---|---|---|---|\n"
    "| FR-1 | x | BR-1 | P0 | AC-1 |\n"
)
#: Два FR, чтобы проверять полноту покрытия задачами.
FR_TABLE_TWO = FR_TABLE + "| FR-2 | y | BR-1 | P1 | AC-2 |\n"
BR_TABLE = "| ID | Требование | Источник |\n|---|---|---|\n| BR-1 | x | src |\n"

#: Новый формат матрицы: задача, коммит/тест, статус.
NEW_HEADER = (
    "| Бизнес-цель | Требование | Спецификация | Критерий приёмки | Тест / компонент "
    "| Задача (T-*) | Коммит / тест | Статус |\n"
    "|---|---|---|---|---|---|---|---|\n"
)
#: Старый формат матрицы — без колонок задачи и статуса.
LEGACY_HEADER = (
    "| Бизнес-цель | Требование | Спецификация | Критерий приёмки | Тест / компонент |\n"
    "|---|---|---|---|---|\n"
)

#: Шаблон матрицы — источник нового формата для прогонов.
TEMPLATE_FILE = REPO_ROOT / "templates" / "traceability-matrix.md"
#: Промпт Project Manager — владелец задач `T-*`.
PM_PROMPT_FILE = ROLES_DIR / "project-manager.md"


def _write_run(tmp_path: Path, trac: str, fr_table: str = FR_TABLE) -> Path:
    """Создать минимальный прогон с FR-таблицей, BR и матрицей трассировки."""
    run = tmp_path / "run"
    run.mkdir()
    (run / "functional-requirements.md").write_text(fr_table, encoding="utf-8")
    (run / "business-requirements.md").write_text(BR_TABLE, encoding="utf-8")
    (run / "traceability-matrix.md").write_text(trac, encoding="utf-8")
    return run


def _problems(run: Path) -> str:
    """Текст всех проблем прогона одной строкой (для assertions)."""
    return " | ".join(check_run(run))


def test_template_declares_task_commit_and_status_columns() -> None:
    """Шаблон матрицы содержит колонки задачи, коммита/теста и статуса."""
    text = TEMPLATE_FILE.read_text(encoding="utf-8")
    assert "Задача (T-*)" in text
    assert "Коммит / тест" in text
    assert "Статус" in text


def test_pm_prompt_links_task_to_requirements() -> None:
    """Project Manager обязан связать задачу с требованиями FR-*/BR-*."""
    text = PM_PROMPT_FILE.read_text(encoding="utf-8")
    assert "requirement_refs" in text
    assert "FR-1" in text and "BR-1" in text


def test_legacy_traceability_without_task_columns_is_accepted(tmp_path: Path) -> None:
    """Старый формат матрицы (без задач) принимается: проверка условна."""
    run = _write_run(
        tmp_path,
        LEGACY_HEADER + "| G-1 | BR-1 | FR-1 | AC-1 | test |\n",
    )
    problems = _problems(run)
    assert "Задача (T-*)" not in problems
    assert "Статус" not in problems


def test_traceability_with_task_and_status_is_accepted(tmp_path: Path) -> None:
    """Строка с задачей и допустимым статусом — проблем нет."""
    run = _write_run(
        tmp_path,
        NEW_HEADER + "| G-1 | BR-1 | FR-1 | AC-1 | test | T-1 |  | draft |\n",
    )
    problems = _problems(run)
    assert "FR-1" not in problems


def test_row_without_task_is_reported(tmp_path: Path) -> None:
    """Требование без задачи `T-*` не покрыто работой — проблема."""
    run = _write_run(
        tmp_path,
        NEW_HEADER + "| G-1 | BR-1 | FR-1 | AC-1 | test |  |  | draft |\n",
    )
    problems = _problems(run)
    assert "FR-1" in problems and "T-*" in problems


def test_row_with_malformed_task_id_is_reported(tmp_path: Path) -> None:
    """Некорректный идентификатор задачи фиксируется как проблема."""
    run = _write_run(
        tmp_path,
        NEW_HEADER + "| G-1 | BR-1 | FR-1 | AC-1 | test | task-1 |  | draft |\n",
    )
    problems = _problems(run)
    assert "FR-1" in problems and "T-*" in problems


def test_row_without_status_is_reported(tmp_path: Path) -> None:
    """Покрытие без статуса непроверяемо — проблема."""
    run = _write_run(
        tmp_path,
        NEW_HEADER + "| G-1 | BR-1 | FR-1 | AC-1 | test | T-1 |  |  |\n",
    )
    problems = _problems(run)
    assert "FR-1" in problems and "статус" in problems.lower()


def test_row_with_invalid_status_is_reported(tmp_path: Path) -> None:
    """Статус вне словаря lifecycle фиксируется как проблема."""
    run = _write_run(
        tmp_path,
        NEW_HEADER + "| G-1 | BR-1 | FR-1 | AC-1 | test | T-1 |  | done |\n",
    )
    problems = _problems(run)
    assert "FR-1" in problems and "недопустимый статус" in problems.lower()


def test_requirement_without_task_row_is_reported(tmp_path: Path) -> None:
    """FR, упомянутый в матрице без строки с задачей, — проблема."""
    run = _write_run(
        tmp_path,
        NEW_HEADER
        + "| G-1 | BR-1 | FR-1 | AC-1 | test | T-1 |  | draft |\n"
        + "| G-1 | BR-1 |  |  |  |  |  | FR-2 |\n",
        fr_table=FR_TABLE_TWO,
    )
    problems = _problems(run)
    assert "FR-2" in problems and "T-*" in problems


def test_header_with_task_column_but_no_status_column_is_reported(tmp_path: Path) -> None:
    """Колонка задачи без колонки статуса не даёт проверить покрытие."""
    run = _write_run(
        tmp_path,
        "| Бизнес-цель | Требование | Задача (T-*) |\n|---|---|---|\n"
        "| G-1 | FR-1 | T-1 |\n",
    )
    problems = _problems(run)
    assert "traceability" in problems.lower() and "статус" in problems.lower()
