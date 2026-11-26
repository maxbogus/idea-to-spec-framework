"""Третий ход диалога: сценарий из трёх пар и покрытие всех ответов заказчика.

Зачем. `docs/evaluation/README.md` (таблица «Чего в покрытии нет») фиксирует
пробел: «третий и последующие ходы с новыми темами» не покрыты — в сценариях
кейсов было ровно две пары «вопрос → ответ». Логика ходов уже умеет N пар
(`run_turns` крутит до `MAX_TURNS` и останавливается на исчерпании сценария),
поэтому пробел закрывается двумя вещами:

1. данными кейса — сценарий из трёх пар с разными темами (ORCH-11);
2. структурной проверкой `dialogue_covers_all_turns`: если третий ответ
   заказчика не попал в допущения роли, третьего хода фактически не было.

Проверка опирается на величину, а не на порядок слов: ответ «12 месяцев»
должен дать величину «12 месяцев» в тексте роли, ответ «B2C» — значимое слово.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from idea_to_spec.multi_turn import run_turns
from idea_to_spec.semantic_check import run_semantic_check

REPO_ROOT = Path(__file__).resolve().parent.parent
CASES = REPO_ROOT / "eval" / "cases" / "roles.jsonl"

#: Сценарий из трёх пар. Третья тема («срок хранения») не повторяет первые две —
#: именно так проверяется требование «третий ход с новой темой».
SCENARIO_THREE: dict[str, Any] = {
    "turns": [
        {"question_contains": "контур", "answer": "B2C (ответ заказчика)"},
        {"question_contains": "цена", "answer": "990 ₽ (ответ заказчика)"},
        {"question_contains": "срок хранения", "answer": "12 месяцев (ответ заказчика)"},
    ]
}


def _reply(questions: list[str], assumptions: list[str] | None = None) -> str:
    """Собрать ответ оркестратора для тестов.

    Args:
        questions: Вопросы, которые задаёт роль.
        assumptions: Зафиксированные допущения.

    Returns:
        JSON-строка ответа.
    """
    return json.dumps(
        {
            "mode": "chat",
            "stage": "business",
            "completeness": {"passed": not questions, "missing": []},
            "questions": questions,
            "artifacts": ["output/chat-002/brief.md"],
            "assumptions": assumptions or [],
            "next": "ba_gate",
        },
        ensure_ascii=False,
    )


def _question_about(topic: str) -> str:
    """Собрать вопрос роли про заданную тему.

    Args:
        topic: Фрагмент темы вопроса.

    Returns:
        Текст ответа с одним вопросом.
    """
    return _reply([f"Вопрос: какой {topic}? Зачем я это спрашиваю: нужен для гейта. Термины: x."])


def test_run_turns_plays_three_turns() -> None:
    """Сценарий из трёх пар проигрывается целиком: три хода, четыре вызова."""
    replies = [
        _question_about("контур"),
        _question_about("цена"),
        _question_about("срок хранения"),
        _reply([], ["B2C", "990 ₽", "12 месяцев"]),
    ]
    calls: list[str] = []

    def call(prompt: str, turns: list[Any]) -> str:
        calls.append(prompt)
        return replies[len(calls) - 1]

    output, turns = run_turns("промпт", SCENARIO_THREE, call, mode="chat", input_text="идея")

    assert len(turns) == 3, "сценарий из трёх пар должен дать три хода"
    assert turns[2].answer == "12 месяцев (ответ заказчика)"
    assert len(calls) == 4, "после третьей пары нужен финальный ход без вопросов"
    assert json.loads(output)["questions"] == []


def test_covers_all_turns_flags_missing_third_answer() -> None:
    """Третий ответ не отражён — проверка обязана провалиться."""
    output = _reply([], ["B2C", "990 ₽"])
    problems = run_semantic_check(
        "dialogue_covers_all_turns",
        output,
        "chat",
        customer_answers=[turn["answer"] for turn in SCENARIO_THREE["turns"]],
    )

    assert problems, "потеря третьего ответа заказчика должна ловиться"
    assert any("12 месяцев" in problem for problem in problems)


def test_covers_all_turns_passes_when_all_answers_present() -> None:
    """Все три ответа в допущениях — проверка молчит."""
    output = _reply(
        [],
        [
            "Контур — B2C (ответ заказчика)",
            "Цена — 990 ₽ (ответ заказчика)",
            "Срок хранения — 12 месяцев (ответ заказчика)",
        ],
    )
    problems = run_semantic_check(
        "dialogue_covers_all_turns",
        output,
        "chat",
        customer_answers=[turn["answer"] for turn in SCENARIO_THREE["turns"]],
    )

    assert problems == []


def test_covers_all_turns_silent_without_context() -> None:
    """Без контекста (одноходовый кейс) проверка не даёт ложных срабатываний."""
    assert run_semantic_check("dialogue_covers_all_turns", _reply([]), "chat") == []


def test_covers_all_turns_does_not_count_marker_words() -> None:
    """Слова маркера «ответ заказчика» не считаются покрытием ответа.

    Иначе любое допущение с источником проходило бы проверку: маркер
    «ответ заказчика» есть в каждом зафиксированном ответе по построению.
    """
    output = _reply([], ["Цена — 990 ₽ (ответ заказчика)"])
    problems = run_semantic_check(
        "dialogue_covers_all_turns",
        output,
        "chat",
        customer_answers=["B2C (ответ заказчика)"],
    )

    assert problems, "ответ «B2C» не отражён, а маркерные слова покрытием не являются"


def test_orch11_case_declares_three_distinct_turns() -> None:
    """Кейс третьего хода существует и объявляет три разные темы."""
    rows = [
        json.loads(line) for line in CASES.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    matches = [
        row for row in rows if json.loads(row["vars"]["contract"])["id"].startswith("ORCH-11")
    ]

    assert matches, "нужен кейс ORCH-11 — третий ход диалога"
    contract = json.loads(matches[0]["vars"]["contract"])
    turns = contract["dialogue"]["turns"]

    assert len(turns) == 3
    topics = [turn["question_contains"] for turn in turns]
    assert len(set(topics)) == 3, "третий ход обязан задавать новую тему"
    assert contract["mode"] == "chat"
    assert "dialogue_covers_all_turns" in contract["semantic_checks"]
    assert matches[0].get("providers") == ["multi-turn"]
    for turn in turns:
        assert turn["answer"].split(" (")[0] in contract["must_contain"], (
            "величина каждого хода должна проверяться лексически"
        )


def test_bridge_passes_customer_answers_to_check() -> None:
    """JS-ассерт доносит список ответов заказчика до Python-проверки."""
    request = {
        "check": "dialogue_covers_all_turns",
        "output": _reply([], ["B2C (ответ заказчика)"]),
        "mode": "chat",
        "customer_answers": ["B2C (ответ заказчика)", "990 ₽ (ответ заказчика)"],
    }
    completed = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "semantic_check_bridge.py")],
        input=json.dumps(request, ensure_ascii=False),
        capture_output=True,
        text=True,
        check=True,
    )
    problems = json.loads(completed.stdout)["problems"]

    assert any("990 ₽" in problem for problem in problems)
