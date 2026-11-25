"""Проверки схемы требования и lifecycle (P1/P2).

Инварианты проверяет `scripts/check_run.py`; здесь они зафиксированы как
тесты, чтобы правка чекера не могла тихо ослабить контракт.

Откалибровано на 4 демо-прогонах (auto-001, auto-002, auto-003, chat-001):
все проверки зелёные на валидных данных.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from check_run import check_run

#: Шапка FR-таблицы с lifecycle-колонками (новый формат).
FR_HEADER_NEW = (
    "| ID | Требование | Источник | Приоритет | Статус | Владелец | Риск | Версия | AC |\n"
    "|---|---|---|---|---|---|---|---|---|\n"
)
#: Шапка FR-таблицы без lifecycle-колонок (legacy-формат прогонов 2026-11).
FR_HEADER_LEGACY = (
    "| ID | Требование | Источник | Приоритет | Критерий приёмки |\n|---|---|---|---|---|\n"
)


def _write_run(tmp_path: Path, fr_table: str, br_table: str, trac: str = "") -> Path:
    """Создать минимальный прогон с заданными таблицами FR/BR/traceability."""
    run = tmp_path / "run"
    run.mkdir()
    (run / "functional-requirements.md").write_text(fr_table, encoding="utf-8")
    (run / "business-requirements.md").write_text(br_table, encoding="utf-8")
    (run / "traceability-matrix.md").write_text(trac, encoding="utf-8")
    return run


BR_TABLE = "| ID | Требование | Источник |\n|---|---|---|\n| BR-1 | x | src |\n"


def _problems(run: Path) -> str:
    """Текст всех проблем прогона одной строкой (для assertions)."""
    return " | ".join(check_run(run))


def test_legacy_format_without_lifecycle_columns_is_accepted(tmp_path: Path) -> None:
    """Прогон без lifecycle-колонок принимается: проверки условны наличием колонок."""
    run = _write_run(
        tmp_path,
        FR_HEADER_LEGACY + "| FR-1 | Требование | BR-1 | P0 | AC-1 |\n",
        BR_TABLE,
        trac="| G-1 | BR-1 | FR-1 | AC-1 | test |\n",
    )
    assert not any("Статус" in p or "Статус" in p for p in check_run(run))


def test_invalid_status_is_reported(tmp_path: Path) -> None:
    """Недопустимый status требования фиксируется как проблема."""
    run = _write_run(
        tmp_path,
        FR_HEADER_NEW
        + "| FR-1 | Требование | BR-1 | P0 | in_progress | Максим | low | 1 | AC-1 |\n",
        BR_TABLE,
        trac="| G-1 | BR-1 | FR-1 | AC-1 | test |\n",
    )
    assert "FR-1" in _problems(run) and "статус" in _problems(run).lower()


def test_empty_owner_is_reported(tmp_path: Path) -> None:
    """Пустой owner требования (нарушение DoR) фиксируется как проблема."""
    run = _write_run(
        tmp_path,
        FR_HEADER_NEW + "| FR-1 | Требование | BR-1 | P0 | draft |  | low | 1 | AC-1 |\n",
        BR_TABLE,
        trac="| G-1 | BR-1 | FR-1 | AC-1 | test |\n",
    )
    assert "FR-1" in _problems(run) and "владелец" in _problems(run).lower()


def test_invalid_risk_is_reported(tmp_path: Path) -> None:
    """Риск вне допустимого множества фиксируется как проблема."""
    run = _write_run(
        tmp_path,
        FR_HEADER_NEW + "| FR-1 | Требование | BR-1 | P0 | draft | Максим | critical | 1 | AC-1 |\n",
        BR_TABLE,
        trac="| G-1 | BR-1 | FR-1 | AC-1 | test |\n",
    )
    assert "FR-1" in _problems(run) and "риск" in _problems(run).lower()


def test_non_integer_version_is_reported(tmp_path: Path) -> None:
    """Нечисловая версия требования фиксируется как проблема."""
    run = _write_run(
        tmp_path,
        FR_HEADER_NEW + "| FR-1 | Требование | BR-1 | P0 | draft | Максим | low | v1 | AC-1 |\n",
        BR_TABLE,
        trac="| G-1 | BR-1 | FR-1 | AC-1 | test |\n",
    )
    assert "FR-1" in _problems(run) and "версия" in _problems(run).lower()


def test_high_risk_without_criteria_is_reported(tmp_path: Path) -> None:
    """Требование высокого риска без критерия приёмки — проблема."""
    run = _write_run(
        tmp_path,
        FR_HEADER_NEW
        + "| FR-1 | Требование | BR-1 | P0 | draft | Максим | high | 1 |  |\n",
        BR_TABLE,
        trac="| G-1 | BR-1 | FR-1 |  | test |\n",
    )
    assert "FR-1" in _problems(run) and "риск" in _problems(run).lower()


def test_valid_lifecycle_row_is_accepted(tmp_path: Path) -> None:
    """Корректная строка с lifecycle-полями не даёт проблем."""
    run = _write_run(
        tmp_path,
        FR_HEADER_NEW
        + "| FR-1 | Требование | BR-1 | P0 | draft | Максим | low | 1 | AC-1 |\n",
        BR_TABLE,
        trac="| G-1 | BR-1 | FR-1 | AC-1 | test |\n",
    )
    assert check_run(run) == []


def test_requirement_without_criteria_reference_is_reported(tmp_path: Path) -> None:
    """FR без ссылки на AC/NFR фиксируется как проблема."""
    run = _write_run(
        tmp_path,
        FR_HEADER_NEW
        + "| FR-1 | Требование | BR-1 | P0 | draft | Максим | low | 1 |  |\n",
        BR_TABLE,
        trac="| G-1 | BR-1 | FR-1 |  | test |\n",
    )
    assert "FR-1" in _problems(run) and "критер" in _problems(run).lower()


def test_uncovered_business_requirement_is_reported(tmp_path: Path) -> None:
    """BR, не покрытый ни FR, ни traceability, фиксируется как проблема."""
    run = _write_run(
        tmp_path,
        FR_HEADER_NEW
        + "| FR-1 | Требование | BR-1 | P0 | draft | Максим | low | 1 | AC-1 |\n",
        "| ID | Требование | Источник |\n|---|---|---|\n| BR-1 | x | src |\n| BR-2 | y | src |\n",
        trac="| G-1 | BR-1 | FR-1 | AC-1 | test |\n",
    )
    assert "BR-2" in _problems(run)


def test_business_requirement_covered_by_traceability_is_accepted(tmp_path: Path) -> None:
    """BR, покрытый через traceability (без FR), проблемой не считается."""
    run = _write_run(
        tmp_path,
        FR_HEADER_NEW
        + "| FR-1 | Требование | BR-1 | P0 | draft | Максим | low | 1 | AC-1 |\n",
        "| ID | Требование | Источник |\n|---|---|---|\n| BR-1 | x | src |\n| BR-2 | y | src |\n",
        trac="| G-1 | BR-1 | FR-1 | AC-1 | test |\n| G-1 | BR-2 | NFR-1 | AC-2 | test |\n",
    )
    assert not any("BR-2" in p for p in check_run(run))


@pytest.mark.parametrize("run_id", ["auto-001", "auto-002", "auto-003", "chat-001"])
def test_demo_runs_pass_new_checks(run_id: str) -> None:
    """Все демо-прогоны проходят новые проверки схемы."""
    from idea_to_spec.paths import OUTPUT_DIR

    run_dir = OUTPUT_DIR / run_id
    if not run_dir.is_dir():
        pytest.skip(f"нет прогона {run_id}")
    assert check_run(run_dir) == []


# --- BDD-критерии для требований с высоким риском -------------------------

#: Шапка FR-таблицы с колонкой BDD (новый формат).
FR_HEADER_BDD = (
    "| ID | Требование | Источник | Приоритет | Статус | Владелец | Риск | Compliance | Версия "
    "| Критерий приёмки (BDD) |\n"
    "|---|---|---|---|---|---|---|---|---|---|\n"
)


def test_high_risk_without_bdd_is_reported(tmp_path: Path) -> None:
    """У требования с risk: high критерий должен быть в формате BDD."""
    run = _write_run(
        tmp_path,
        FR_HEADER_BDD
        + "| FR-1 | Требование | BR-1 | P0 | draft | Максим | high | GDPR Art.6 | 1 | AC-1 |\n",
        BR_TABLE,
        trac="| G-1 | BR-1 | FR-1 | AC-1 | test |\n",
    )
    assert "FR-1" in _problems(run) and "BDD" in _problems(run).upper()


def test_high_risk_with_bdd_is_accepted(tmp_path: Path) -> None:
    """BDD-критерий (Given/When/Then) у high risk — проблемы нет."""
    run = _write_run(
        tmp_path,
        FR_HEADER_BDD
        + "| FR-1 | Требование | BR-1 | P0 | draft | Максим | high | GDPR Art.6 | 1 "
        "| AC-1 Given пользователь вошёл, When он создаёт сделку, Then сделка сохранена |\n",
        BR_TABLE,
        trac="| G-1 | BR-1 | FR-1 | AC-1 | test |\n",
    )
    assert not any("BDD" in p.upper() for p in check_run(run))


def test_low_risk_without_bdd_is_accepted(tmp_path: Path) -> None:
    """BDD обязателен только для high risk: low risk проходит без него."""
    run = _write_run(
        tmp_path,
        FR_HEADER_BDD
        + "| FR-1 | Требование | BR-1 | P0 | draft | Максим | low |  | 1 | AC-1 |\n",
        BR_TABLE,
        trac="| G-1 | BR-1 | FR-1 | AC-1 | test |\n",
    )
    assert not any("BDD" in p.upper() for p in check_run(run))


def test_legacy_format_skips_bdd_check(tmp_path: Path) -> None:
    """Старый формат (без колонки BDD) не проверяется — демо-прогоны живы."""
    run = _write_run(
        tmp_path,
        FR_HEADER_LEGACY + "| FR-1 | Требование | BR-1 | P0 | AC-1 |\n",
        BR_TABLE,
        trac="| G-1 | BR-1 | FR-1 | AC-1 | test |\n",
    )
    assert not any("BDD" in p.upper() for p in check_run(run))


# --- Персональные данные vs заполненность spec.md §6 ----------------------

#: Минимальная spec.md с незаполненным разделом 6.
SPEC_EMPTY_SECTION = (
    "# Спецификация\n\n"
    "## 6. Данные и безопасность\n\n"
    "- Какие данные, персональные ли, срок хранения, минимизация.\n"
    "- Сущности (источник для ER-диаграммы): перечислить таблицы/сущности.\n"
)

#: Минимальная spec.md с заполненным разделом 6.
SPEC_FILLED_SECTION = (
    "# Спецификация\n\n"
    "## 6. Данные и безопасность\n\n"
    "- Классификация: персональные данные (ФИО, телефон, email).\n"
    "- Data residency: хранение на территории РФ.\n"
    "- Срок хранения: 12 месяцев, удаление по запросу.\n"
    "- Сущности: User, Contact.\n"
)


def _run_with_spec(tmp_path: Path, fr_table: str, spec_text: str) -> Path:
    """Создать прогон с FR-таблицей и заданным содержимым spec.md."""
    run = _write_run(tmp_path, fr_table, BR_TABLE, trac="| G-1 | BR-1 | FR-1 | AC-1 | test |\n")
    (run / "spec.md").write_text(spec_text, encoding="utf-8")
    return run


def test_personal_data_without_spec_section_is_reported(tmp_path: Path) -> None:
    """ПДн в требованиях, но spec.md §6 пуста — проблема."""
    run = _run_with_spec(
        tmp_path,
        FR_HEADER_NEW + "| FR-1 | Хранить ФИО и телефон | BR-1 | P0 | draft | Максим | low | 1 | AC-1 |\n",
        SPEC_EMPTY_SECTION,
    )
    assert "FR-1" in _problems(run) and "§6" in _problems(run)


def test_personal_data_with_spec_section_is_accepted(tmp_path: Path) -> None:
    """ПДн в требованиях и заполненная §6 — проблемы нет."""
    run = _run_with_spec(
        tmp_path,
        FR_HEADER_NEW + "| FR-1 | Хранить ФИО и телефон | BR-1 | P0 | draft | Максим | low | 1 | AC-1 |\n",
        SPEC_FILLED_SECTION,
    )
    assert not any("§6" in p for p in check_run(run))


def test_no_personal_data_skips_spec_check(tmp_path: Path) -> None:
    """Без ПДн проверка §6 не выполняется."""
    run = _run_with_spec(
        tmp_path,
        FR_HEADER_NEW + "| FR-1 | Считать статистику | BR-1 | P0 | draft | Максим | low | 1 | AC-1 |\n",
        SPEC_EMPTY_SECTION,
    )
    assert not any("§6" in p for p in check_run(run))
