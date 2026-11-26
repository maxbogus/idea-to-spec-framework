"""Контракты новых проверок `check_run.py`: NFR, негативные AC, ADR.

Проверки условны по формату: они включаются только когда в шапке таблицы есть
новая колонка (`Мера / Порог`, `Негативный сценарий (BDD)`, `Статус` в ADR).
Так golden-прогоны старого формата не ломаются, а шаблон задаёт новый уровень.
"""

from __future__ import annotations

from pathlib import Path

from check_run import check_run


def _write(path: Path, text: str) -> None:
    """Записать файл прогона."""

    path.write_text(text, encoding="utf-8")


def test_nfr_measure_column_requires_value(tmp_path: Path) -> None:
    """Пустая «Мера / Порог» — проблема."""

    run = tmp_path / "run"
    run.mkdir()
    _write(
        run / "nonfunctional-requirements.md",
        "| ID | Категория | Требование | Мера / Порог | Метод проверки |\n"
        "|---|---|---|---|---|\n"
        "| NFR-1 | performance | быстрый отклик |  | нагрузочный тест |\n",
    )
    problems = check_run(run)
    assert any("NFR-1" in problem and "мер" in problem for problem in problems), problems


def test_nfr_measure_filled_passes(tmp_path: Path) -> None:
    """Заполненная мера и метод — проблемы нет."""

    run = tmp_path / "run"
    run.mkdir()
    _write(
        run / "nonfunctional-requirements.md",
        "| ID | Категория | Требование | Мера / Порог | Метод проверки |\n"
        "|---|---|---|---|---|\n"
        "| NFR-1 | performance | отклик | p95 ≤ 300 мс | нагрузочный тест |\n",
    )
    problems = check_run(run)
    assert not any("NFR-1" in problem and "мер" in problem for problem in problems), problems


def test_nfr_without_measure_column_is_ignored(tmp_path: Path) -> None:
    """Старый формат без колонки меры не проверяется."""

    run = tmp_path / "run"
    run.mkdir()
    _write(
        run / "nonfunctional-requirements.md",
        "| ID | Категория | Требование | Как проверяем |\n"
        "|---|---|---|---|\n"
        "| NFR-1 | performance | отклик |  |\n",
    )
    problems = check_run(run)
    assert not any("NFR-1" in problem and "мер" in problem for problem in problems), problems


def test_negative_acceptance_column_requires_value(tmp_path: Path) -> None:
    """Пустой негативный сценарий — проблема."""

    run = tmp_path / "run"
    run.mkdir()
    _write(
        run / "functional-requirements.md",
        "| ID | Требование | Источник | Критерий приёмки (BDD) | "
        "Негативный сценарий (BDD) |\n"
        "|---|---|---|---|---|\n"
        "| FR-1 | x | BR-1 | AC-1. Given a, When b, Then c |  |\n",
    )
    problems = check_run(run)
    assert any("FR-1" in problem and "негатив" in problem for problem in problems), problems


def test_negative_acceptance_filled_passes(tmp_path: Path) -> None:
    """Заполненный негативный сценарий — проблемы нет."""

    run = tmp_path / "run"
    run.mkdir()
    _write(
        run / "functional-requirements.md",
        "| ID | Требование | Источник | Критерий приёмки (BDD) | "
        "Негативный сценарий (BDD) |\n"
        "|---|---|---|---|---|\n"
        "| FR-1 | x | BR-1 | AC-1. Given a, When b, Then c | "
        "AC-2. Given a, When b fails, Then error |\n",
    )
    problems = check_run(run)
    assert not any("FR-1" in problem and "негатив" in problem for problem in problems), problems


def test_vague_word_in_acceptance_is_reported(tmp_path: Path) -> None:
    """Стоп-слово в критерии приёмки — проблема."""

    run = tmp_path / "run"
    run.mkdir()
    _write(
        run / "functional-requirements.md",
        "| ID | Требование | Источник | Критерий приёмки (BDD) | "
        "Негативный сценарий (BDD) |\n"
        "|---|---|---|---|---|\n"
        "| FR-1 | x | BR-1 | AC-1. Given a, When b, Then c | "
        "AC-2. Given a, When b fails, Then быстро сообщаем |\n",
    )
    problems = check_run(run)
    assert any("FR-1" in problem and "быстро" in problem for problem in problems), problems


def test_adr_requires_two_alternatives(tmp_path: Path) -> None:
    """Меньше двух альтернатив в ADR — проблема."""

    run = tmp_path / "run"
    run.mkdir()
    _write(
        run / "spec.md",
        "## 10. ADR\n\n"
        "| ID | Решение | Контекст | Статус | "
        "Рассмотренные альтернативы (Pros/Cons) | Последствия |\n"
        "|---|---|---|---|---|---|\n"
        "| ADR-1 | x | y | Accepted | 1. Вариант А (+/−) | z |\n",
    )
    problems = check_run(run)
    assert any("ADR-1" in problem and "альтернатив" in problem for problem in problems), problems


def test_adr_valid_passes(tmp_path: Path) -> None:
    """Две альтернативы, статус и последствия — проблемы нет."""

    run = tmp_path / "run"
    run.mkdir()
    _write(
        run / "spec.md",
        "## 10. ADR\n\n"
        "| ID | Решение | Контекст | Статус | "
        "Рассмотренные альтернативы (Pros/Cons) | Последствия |\n"
        "|---|---|---|---|---|---|\n"
        "| ADR-1 | x | y | Accepted | 1. Вариант А (+/−)<br>2. Вариант Б (+/−) | z |\n",
    )
    problems = check_run(run)
    assert not any("ADR-1" in problem for problem in problems), problems


def test_adr_without_status_column_is_ignored(tmp_path: Path) -> None:
    """Старый ADR без статуса не проверяется."""

    run = tmp_path / "run"
    run.mkdir()
    _write(
        run / "spec.md",
        "## 10. ADR\n\n"
        "| ID | Решение | Контекст | Рассмотренные альтернативы (Pros/Cons) | "
        "Последствия |\n"
        "|---|---|---|---|---|\n"
        "| ADR-1 | x | y | нужен ревью | z |\n",
    )
    problems = check_run(run)
    assert not any("ADR-1" in problem for problem in problems), problems


def test_adr_invalid_status_is_reported(tmp_path: Path) -> None:
    """Неизвестный статус ADR — проблема."""

    run = tmp_path / "run"
    run.mkdir()
    _write(
        run / "spec.md",
        "## 10. ADR\n\n"
        "| ID | Решение | Контекст | Статус | "
        "Рассмотренные альтернативы (Pros/Cons) | Последствия |\n"
        "|---|---|---|---|---|---|\n"
        "| ADR-1 | x | y | Maybe | 1. А<br>2. Б | z |\n",
    )
    problems = check_run(run)
    assert any("ADR-1" in problem and "статус" in problem for problem in problems), problems
