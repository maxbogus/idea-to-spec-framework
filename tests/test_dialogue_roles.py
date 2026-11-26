"""Многоходовость ролей PM / BA / SA: сценарии в диалоге.

Зачем. Таблица «Чего в покрытии нет» (`docs/evaluation/README.md`) держит
строку «многоходовость у ролей PM / BA / SA»: сценарии диалога были только
у оркестратора (ORCH-09, ORCH-10), поэтому второй ход ролей не проверялся.

Две особенности ролей, из-за которых диалог не работал бы как у оркестратора:

1. поле вопросов у ролей называется `open_questions`, а не `questions` —
   `parse_questions` обязан читать его, иначе диалог роли обрывается на
   первом ходе;
2. инструкция следующего хода обязана называть то поле, которое есть в
   формате роли: «поле questions — пустой список []» для ответа без поля
   `questions` — это подсказка добавить чужое поле.

Итог диалога роли — пустой `open_questions`: блокирующих вопросов не
осталось, а ответы заказчика зафиксированы в `assumptions`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import mock_provider
from idea_to_spec.multi_turn import followup_prompt, parse_questions, run_turns

REPO_ROOT = Path(__file__).resolve().parent.parent
CASES = REPO_ROOT / "eval" / "cases" / "roles.jsonl"

#: Формат BA/SA/PM: поле вопросов называется `open_questions`.
ROLE_FORMAT = """{
  "personas": [],
  "assumptions": ["допущение"],
  "open_questions": ["что блокирует следующий шаг"]
}"""

#: Формат оркестратора: поле вопросов называется `questions`.
ORCH_FORMAT = """{
  "questions": ["Вопрос: ..."],
  "assumptions": ["допущение"]
}"""


def _ba_reply(open_questions: list[str], assumptions: list[str] | None = None) -> str:
    """Собрать ответ BA в формате роли.

    Args:
        open_questions: Открытые вопросы роли.
        assumptions: Явные допущения.

    Returns:
        JSON-строка ответа.
    """
    return json.dumps(
        {
            "personas": [{"id": "P-1", "name": "Студент", "contour": "B2C"}],
            "contour": "B2C",
            "assumptions": assumptions or [],
            "open_questions": open_questions,
        },
        ensure_ascii=False,
    )


def test_parse_questions_reads_open_questions() -> None:
    """Поле `open_questions` ролей читается как вопросы диалога."""
    questions = parse_questions(_ba_reply(["какой срок хранения данных?"]))

    assert questions == ["какой срок хранения данных?"]


def test_parse_questions_prefers_questions_field() -> None:
    """Если есть оба поля, приоритет у `questions`."""
    payload = json.dumps(
        {"questions": ["вопрос оркестратора"], "open_questions": ["вопрос роли"]},
        ensure_ascii=False,
    )

    assert parse_questions(payload) == ["вопрос оркестратора"]


def test_followup_names_role_open_questions_field() -> None:
    """Инструкция остановки называет поле, которое есть в формате роли."""
    prompt = followup_prompt(
        f"Промпт роли\n```json\n{ROLE_FORMAT}\n```",
        "12 месяцев (ответ заказчика)",
        mode="chat",
        input_text="идея",
        all_answers=["12 месяцев (ответ заказчика)"],
        scenario_exhausted=True,
    )

    assert "поле open_questions — пустой список []" in prompt
    assert "поле questions — пустой список" not in prompt


def test_followup_names_orchestrator_questions_field() -> None:
    """У оркестратора инструкция по-прежнему про `questions`."""
    prompt = followup_prompt(
        f"Промпт роли\n```json\n{ORCH_FORMAT}\n```",
        "B2C (ответ заказчика)",
        mode="chat",
        input_text="идея",
        all_answers=["B2C (ответ заказчика)"],
        scenario_exhausted=True,
    )

    assert "поле questions — пустой список []" in prompt


def test_role_dialogue_runs_two_turns() -> None:
    """Диалог роли проигрывается по сценарию из двух пар."""
    scenario: dict[str, Any] = {
        "turns": [
            {"question_contains": "срок хранения", "answer": "12 месяцев (ответ заказчика)"},
            {"question_contains": "контур", "answer": "B2C (ответ заказчика)"},
        ]
    }
    replies = [
        _ba_reply(["какой срок хранения данных?"]),
        _ba_reply(["какой контур у сервиса?"], ["12 месяцев (ответ заказчика)"]),
        _ba_reply([], ["12 месяцев (ответ заказчика)", "B2C (ответ заказчика)"]),
    ]
    calls: list[str] = []

    def call(prompt: str, turns: list[Any]) -> str:
        calls.append(prompt)
        return replies[len(calls) - 1]

    output, turns = run_turns("промпт", scenario, call, mode="chat", input_text="идея")

    assert len(turns) == 2
    assert len(calls) == 3
    assert json.loads(output)["open_questions"] == []
    # Третий запрос знает, какие вопросы уже закрыты: иначе модель
    # переспрашивает отвеченное, и диалог топчется на месте (дефект волны C).
    assert "какой срок хранения данных?" in calls[2]
    assert "какой контур у сервиса?" in calls[2]
    assert "не задавай их снова" in calls[2]


def test_role_dialogue_cases_are_declared() -> None:
    """Кейсы BA-05 / SA-04 / PM-03 объявлены как многоходовые."""
    rows = [
        json.loads(line) for line in CASES.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    contracts = {
        json.loads(row["vars"]["contract"])["id"]: (
            json.loads(row["vars"]["contract"]),
            row.get("providers"),
        )
        for row in rows
    }
    expected_roles = {
        "BA-05-chat-dialogue-role": "business-analyst",
        "SA-04-chat-dialogue-role": "system-analyst",
        "PM-03-chat-dialogue-role": "product-manager",
    }

    for case_id, role in expected_roles.items():
        matches = [key for key in contracts if key.startswith(case_id)]
        assert matches, f"нужен кейс {case_id}"
        contract, providers = contracts[matches[0]]
        assert contract["role"] == role
        assert contract["mode"] == "chat"
        assert providers == ["multi-turn"]
        assert len(contract["dialogue"]["turns"]) == 2
        for check in (
            "dialogue_uses_customer_answer",
            "dialogue_closes_answered_question",
            "dialogue_covers_all_turns",
        ):
            assert check in contract["semantic_checks"], f"{case_id}: нет проверки {check}"


def test_mock_role_dialogue_keeps_role_shape() -> None:
    """Mock отвечает в формате роли: персоны на месте, вопросы закрыты."""
    contract: dict[str, Any] = {
        "id": "BA-05-chat-dialogue-role",
        "role": "business-analyst",
        "mode": "chat",
        "dialogue": {
            "turns": [
                {"question_contains": "срок хранения", "answer": "12 месяцев (ответ заказчика)"},
                {"question_contains": "контур", "answer": "B2C (ответ заказчика)"},
            ]
        },
    }
    output = mock_provider.build_answer(contract)
    payload = json.loads(output)

    assert payload["personas"], "ответ роли обязан сохранить её формат"
    assert payload["open_questions"] == []
    assert any("12 месяцев" in item for item in payload["assumptions"])
    assert any("B2C" in item for item in payload["assumptions"])
