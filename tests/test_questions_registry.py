"""Реестр вопросов между этапами: контракт `open-questions.md`.

Зачем. Дефект волны C (chat-002): BA/SA/Architect оставляли в `open_questions`
то, что заказчик уже ответил, а гейт спрашивал то, что уже закрыто. Проверка
`Q-*` → ответ знала только «закрыт обязан содержать ответ заказчика» и не
видела ни этапа закрытия, ни артефакта, куда ответ попал.

Контракт P3 — таблица-реестр: у вопроса есть объявленная тема, а у снятого
вопроса — этап, источник и список обновлённых артефактов. Повтор темы
закрытого вопроса без `Переоткрывает: Q-n: причина` — дефект, а не «новый
вопрос». Старый формат (без колонок `Тема` / `Закрыт на этапе`) проверяется
по прежним правилам: исторические прогоны не краснеют.
"""

from __future__ import annotations

import re
from pathlib import Path

from check_run import QUESTION_STAGES, check_run

REPO_ROOT = Path(__file__).resolve().parent.parent

#: Шапка реестра P3: 10 колонок.
HEADER = (
    "| ID | Тема | Вопрос | Почему блокирует | Кто отвечает | Статус | "
    "Закрыт на этапе | Источник ответа | Что обновлено | Переоткрывает |\n"
    "|---|---|---|---|---|---|---|---|---|---|\n"
)

#: Шапка старого формата (chat-001 / chat-002): статус — последняя колонка.
LEGACY_HEADER = "| ID | Вопрос | Ответ (источник) | Статус |\n|---|---|---|---|\n"


def _run(tmp_path: Path, table: str, artifacts: dict[str, str] | None = None) -> Path:
    """Создать каталог прогона с реестром и артефактами.

    Args:
        tmp_path: Временный каталог теста.
        table: Содержимое `open-questions.md`.
        artifacts: Дополнительные файлы прогона (имя → содержимое).

    Returns:
        Путь к каталогу прогона.
    """
    run = tmp_path / "run"
    run.mkdir()
    (run / "open-questions.md").write_text(table, encoding="utf-8")
    for name, content in (artifacts or {}).items():
        path = run / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return run


def _row(
    question_id: str,
    *,
    topic: str = "контур",
    question: str = "Какой контур у сервиса?",
    status: str = "закрыт",
    stage: str = "business",
    source: str = "ответ заказчика",
    artifacts: str = "business-requirements.md",
    reopens: str = "—",
) -> str:
    """Собрать строку реестра с разумными значениями по умолчанию."""
    return (
        f"| {question_id} | {topic} | {question} | меняет требования | заказчик | "
        f"{status} | {stage} | {source} | {artifacts} | {reopens} |\n"
    )


def _q_problems(problems: list[str]) -> list[str]:
    """Отфильтровать проблемы, относящиеся к реестру вопросов."""
    return [problem for problem in problems if "Q-" in problem]



def test_registry_accepts_closed_question_with_stage_source_and_artifact(tmp_path: Path) -> None:
    """Полная строка реестра (этап, источник, артефакт) — проблем нет."""
    run = _run(
        tmp_path,
        HEADER
        + _row("Q-1")
        + _row(
            "Q-2",
            topic="метрики",
            status="открыт",
            stage="—",
            source="—",
            artifacts="—",
        ),
        {"business-requirements.md": "| BR-1 | требование |\n"},
    )
    assert _q_problems(check_run(run)) == []


def test_registry_closed_question_requires_stage(tmp_path: Path) -> None:
    """Закрытый вопрос без этапа закрытия — проблема: между этапами не проверить."""
    run = _run(
        tmp_path,
        HEADER + _row("Q-1", stage="—"),
        {"business-requirements.md": "| BR-1 | требование |\n"},
    )
    problems = _q_problems(check_run(run))
    assert any("Q-1" in problem and "этап" in problem for problem in problems), problems


def test_registry_rejects_unknown_stage(tmp_path: Path) -> None:
    """Опечатка в этапе — проблема, а не молчаливое принятие."""
    run = _run(
        tmp_path,
        HEADER + _row("Q-1", stage="bussines"),
        {"business-requirements.md": "| BR-1 | требование |\n"},
    )
    problems = _q_problems(check_run(run))
    assert any("Q-1" in problem and "bussines" in problem for problem in problems), problems


def test_registry_closed_question_requires_source(tmp_path: Path) -> None:
    """Закрытый вопрос без источника ответа — проблема (как и в старом формате)."""
    run = _run(
        tmp_path,
        HEADER + _row("Q-1", source="—"),
        {"business-requirements.md": "| BR-1 | требование |\n"},
    )
    problems = _q_problems(check_run(run))
    assert any("Q-1" in problem and "источник" in problem for problem in problems), problems


def test_registry_closed_question_requires_existing_artifact(tmp_path: Path) -> None:
    """Ответ, не дошедший до артефакта, — дефект: файл обязан существовать."""
    run = _run(
        tmp_path,
        HEADER + _row("Q-1", artifacts="missing-artifact.md"),
        {"business-requirements.md": "| BR-1 | требование |\n"},
    )
    problems = _q_problems(check_run(run))
    assert any("Q-1" in problem and "missing-artifact.md" in problem for problem in problems), problems


def test_registry_closed_question_requires_named_artifact(tmp_path: Path) -> None:
    """Пустая колонка «Что обновлено» — ответ закрыт на бумаге."""
    run = _run(
        tmp_path,
        HEADER + _row("Q-1", artifacts="—"),
        {"business-requirements.md": "| BR-1 | требование |\n"},
    )
    problems = _q_problems(check_run(run))
    assert any("Q-1" in problem and "обновл" in problem for problem in problems), problems


def test_registry_open_question_repeating_closed_topic_fails(tmp_path: Path) -> None:
    """Тот же вопрос снова открыт (chat-002: контур закрыт, допущение про контур) — дефект."""
    run = _run(
        tmp_path,
        HEADER
        + _row("Q-1")
        + _row(
            "Q-2",
            topic="контур",
            question="Приложение будет B2C?",
            status="допущение",
            source="допущение: клиенты — физлица",
            artifacts="brief.md",
        )
        + _row(
            "Q-3",
            topic="метрики",
            question="Какие метрики?",
            status="открыт",
            stage="—",
            source="—",
            artifacts="—",
        ),
        {"business-requirements.md": "| BR-1 | требование |\n", "brief.md": "идея\n"},
    )
    problems = _q_problems(check_run(run))
    assert any("Q-2" in problem and "Q-1" in problem and "тем" in problem for problem in problems), problems


def test_registry_open_question_reopens_closed_topic_with_reason(tmp_path: Path) -> None:
    """Переоткрытие закрытой темы со ссылкой и причиной — легальный ход."""
    run = _run(
        tmp_path,
        HEADER
        + _row("Q-1")
        + _row(
            "Q-2",
            topic="контур",
            question="Контур изменился?",
            status="открыт",
            stage="—",
            source="—",
            artifacts="—",
            reopens="Q-1: заказчик сменил контур",
        ),
        {"business-requirements.md": "| BR-1 | требование |\n"},
    )
    assert _q_problems(check_run(run)) == []


def test_registry_reopen_target_must_exist_and_be_closed(tmp_path: Path) -> None:
    """Ссылка на несуществующий или незакрытый вопрос — проблема."""
    run = _run(
        tmp_path,
        HEADER
        + _row("Q-1", status="открыт", stage="—", source="—", artifacts="—")
        + _row(
            "Q-2",
            question="Другой вопрос?",
            status="открыт",
            stage="—",
            source="—",
            artifacts="—",
            reopens="Q-1: причина",
        )
        + _row(
            "Q-3",
            question="Третий вопрос?",
            status="открыт",
            stage="—",
            source="—",
            artifacts="—",
            reopens="Q-9: причина",
        ),
        {"business-requirements.md": "| BR-1 | требование |\n"},
    )
    problems = _q_problems(check_run(run))
    assert any("Q-2" in problem and "не закрыт" in problem for problem in problems), problems
    assert any("Q-3" in problem and "Q-9" in problem for problem in problems), problems


def test_registry_reopen_requires_reason(tmp_path: Path) -> None:
    """Ссылка без причины — переоткрытие «потому что»."""
    run = _run(
        tmp_path,
        HEADER
        + _row("Q-1")
        + _row(
            "Q-2",
            question="Другой вопрос?",
            status="открыт",
            stage="—",
            source="—",
            artifacts="—",
            reopens="Q-1",
        ),
        {"business-requirements.md": "| BR-1 | требование |\n"},
    )
    problems = _q_problems(check_run(run))
    assert any("Q-2" in problem and "формат" in problem for problem in problems), problems


def test_registry_closed_question_requires_topic(tmp_path: Path) -> None:
    """Без темы повтор вопроса не отличить от нового — проблема."""
    run = _run(
        tmp_path,
        HEADER + _row("Q-1", topic="—"),
        {"business-requirements.md": "| BR-1 | требование |\n"},
    )
    problems = _q_problems(check_run(run))
    assert any("Q-1" in problem and "тем" in problem for problem in problems), problems



def test_registry_closed_question_with_hypothesis_marker_fails(tmp_path: Path) -> None:
    """Ответ получен, а артефакт всё ещё помечает вопрос как гипотезу — дефект."""
    run = _run(
        tmp_path,
        HEADER + _row("Q-1", artifacts="functional-requirements.md"),
        {
            "business-requirements.md": "| BR-1 | требование |\n",
            "functional-requirements.md": "| FR-1 | x | [HYPOTHESIS: Q-1] |\n",
        },
    )
    problems = _q_problems(check_run(run))
    assert any("Q-1" in problem and "HYPOTHESIS" in problem for problem in problems), problems


def test_registry_assumption_with_hypothesis_marker_passes(tmp_path: Path) -> None:
    """Допущение, помеченное `[HYPOTHESIS: Q-n]`, — норма, а не дефект."""
    run = _run(
        tmp_path,
        HEADER
        + _row(
            "Q-1",
            status="допущение",
            source="допущение: нет данных",
            artifacts="functional-requirements.md",
        ),
        {
            "business-requirements.md": "| BR-1 | требование |\n",
            "functional-requirements.md": "| FR-1 | x | [HYPOTHESIS: Q-1] |\n",
        },
    )
    assert _q_problems(check_run(run)) == []


def test_registry_detects_dangling_question_reference(tmp_path: Path) -> None:
    """Ссылка на удалённый вопрос — проблема: реестр потерял строку."""
    run = _run(
        tmp_path,
        HEADER + _row("Q-1"),
        {
            "business-requirements.md": "| BR-1 | требование |\n",
            "spec.md": "## 2. Контекст\n\nРешает Q-9.\n",
        },
    )
    problems = _q_problems(check_run(run))
    assert any("Q-9" in problem and "реестр" in problem for problem in problems), problems


def test_registry_ignores_unfilled_template_row(tmp_path: Path) -> None:
    """Пустая шаблонная строка (`Q-1` без текста) не считается вопросом."""
    run = _run(
        tmp_path,
        HEADER + "| Q-1 |  |  |  |  |  |  |  |  |  |\n",
        {"business-requirements.md": "| BR-1 | требование |\n"},
    )
    assert _q_problems(check_run(run)) == []


def test_legacy_format_keeps_previous_rules(tmp_path: Path) -> None:
    """Старый формат без `Тема` / `Закрыт на этапе` проверяется по-прежнему."""
    run = _run(
        tmp_path,
        LEGACY_HEADER + "| Q-1 | Тип клиента? | B2B | закрыт |\n",
        {"business-requirements.md": "| BR-1 | требование |\n"},
    )
    problems = _q_problems(check_run(run))
    assert any("Q-1" in problem and "источник" in problem for problem in problems), problems


def test_legacy_format_is_not_held_to_registry_columns(tmp_path: Path) -> None:
    """Исторический прогон без колонок P3 не краснеет из-за их отсутствия."""
    run = _run(
        tmp_path,
        LEGACY_HEADER + "| Q-1 | Тип клиента? | B2B (ответ заказчика) | закрыт |\n",
        {"business-requirements.md": "| BR-1 | требование |\n"},
    )
    assert _q_problems(check_run(run)) == []


def test_registry_stage_enum_matches_orchestrator() -> None:
    """Значения «Закрыт на этапе» — из enum `stage` промпта оркестратора."""
    text = (REPO_ROOT / "prompts" / "orchestrator.md").read_text(encoding="utf-8")
    match = re.search(r'"stage":\s*"([^"]+)"', text)
    assert match is not None, "в промпте оркестратора нет поля stage"
    stages = set(match.group(1).split("|"))
    gates_and_service = {"ba_gate", "sa_gate", "spec_gate", "done"}
    assert stages - gates_and_service == QUESTION_STAGES


def test_legacy_closed_question_marker_is_not_checked_by_registry(
    tmp_path: Path,
) -> None:
    """Смешанный формат: старый закрытый вопрос не судится по контракту P3."""
    run = _run(
        tmp_path,
        LEGACY_HEADER
        + "| Q-1 | Тип клиента? | B2B (ответ заказчика) | закрыт |\n\n"
        + HEADER
        + _row("Q-2", topic="метрики", question="Какие метрики?"),
        {
            "business-requirements.md": "| BR-1 | требование |\n",
            "functional-requirements.md": "| FR-1 | x | [HYPOTHESIS: Q-1] |\n",
        },
    )
    assert _q_problems(check_run(run)) == []


def test_registry_accepts_source_section_that_exists(tmp_path: Path) -> None:
    """Источник `spec.md §2` проверяется по разделу, а не только по файлу."""
    run = _run(
        tmp_path,
        HEADER + _row("Q-1", source="spec.md §2", artifacts="spec.md"),
        {"spec.md": "## 2. Контекст\n\nтекст\n"},
    )
    assert _q_problems(check_run(run)) == []


def test_registry_missing_source_section_is_reported(tmp_path: Path) -> None:
    """Раздела-источника нет — ссылка на источник ложная."""
    run = _run(
        tmp_path,
        HEADER + _row("Q-1", source="spec.md §2", artifacts="spec.md"),
        {"spec.md": "## 3. Решение\n\nтекст\n"},
    )
    problems = _q_problems(check_run(run))
    assert any("Q-1" in problem and "§2" in problem for problem in problems), problems
