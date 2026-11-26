"""Развилка с альтернативными ответами: два ответа — два следующих шага.

Зачем. Таблица «Чего в покрытии нет» (`docs/evaluation/README.md`) держит
строку «два разных ответа на одну развилку → разные следующие шаги»: в наборе
не было сценария с альтернативами, поэтому проверялось только отсутствие
вопросов, а не переход на другой этап.

Схема сценария расширяется блоком `fork` — последняя развилка диалога:

    "dialogue": {
      "turns": [{"question_contains": "контур", "answer": "B2C (ответ заказчика)"}],
      "fork": {
        "question_contains": "география хранения",
        "answer": "только Россия (ответ заказчика)",
        "expect_next": "system"
      }
    }

Ответ на развилку играется как обычная пара (провайдер и mock считают ходы
одинаково), а `expect_next` превращает ответ в проверяемое следствие: у двух
кейсов-близнецов одна развилка и разные ответы — и разные следующие этапы.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import mock_provider
from idea_to_spec.multi_turn import run_turns, scenario_fork, scenario_turns
from idea_to_spec.semantic_check import run_semantic_check

REPO_ROOT = Path(__file__).resolve().parent.parent
CASES = REPO_ROOT / "eval" / "cases" / "roles.jsonl"

SCENARIO_FORK: dict[str, Any] = {
    "turns": [
        {"question_contains": "контур", "answer": "B2C (ответ заказчика)"},
    ],
    "fork": {
        "question_contains": "география хранения",
        "answer": "только Россия (ответ заказчика)",
        "expect_next": "system",
    },
}


def _reply(questions: list[str], next_stage: str = "ba_gate") -> str:
    """Собрать ответ оркестратора для тестов.

    Args:
        questions: Вопросы, которые задаёт роль.
        next_stage: Следующий этап в ответе.

    Returns:
        JSON-строка ответа.
    """
    return json.dumps(
        {
            "mode": "hybrid",
            "stage": "business",
            "completeness": {"passed": not questions, "missing": []},
            "questions": questions,
            "artifacts": ["output/auto-005/brief.md"],
            "assumptions": [],
            "next": next_stage,
        },
        ensure_ascii=False,
    )


def test_scenario_turns_includes_fork_as_last_pair() -> None:
    """Развилка играется как последняя пара «вопрос → ответ»."""
    pairs = scenario_turns(SCENARIO_FORK)

    assert [pair["question_contains"] for pair in pairs] == ["контур", "география хранения"]
    assert pairs[-1]["answer"] == "только Россия (ответ заказчика)"


def test_scenario_fork_reads_expectation() -> None:
    """Блок `fork` читается отдельно: из него берётся ожидаемый этап."""
    fork = scenario_fork(SCENARIO_FORK)

    assert fork is not None
    assert fork["expect_next"] == "system"
    assert scenario_fork({"turns": []}) is None


def test_run_turns_plays_fork_then_stops() -> None:
    """Диалог: вопрос про контур, затем развилка, затем остановка."""
    replies = [
        _reply(["Вопрос: какой контур? Зачем я это спрашиваю: x. Термины: y."]),
        _reply(["Вопрос: какая география хранения данных? Зачем: x. Термины: y."]),
        _reply([], next_stage="system"),
    ]
    calls: list[str] = []

    def call(prompt: str, turns: list[Any]) -> str:
        calls.append(prompt)
        return replies[len(calls) - 1]

    output, turns = run_turns("промпт", SCENARIO_FORK, call, mode="hybrid", input_text="идея")

    assert len(turns) == 2
    assert turns[-1].answer == "только Россия (ответ заказчика)"
    assert json.loads(output)["next"] == "system"


def test_fork_branch_passes_when_next_matches() -> None:
    """Ожидаемый этап совпал — проверка молчит."""
    output = _reply([], next_stage="system")
    problems = run_semantic_check("dialogue_fork_branch", output, "hybrid", expected_next="system")

    assert problems == []


def test_fork_branch_flags_wrong_next() -> None:
    """Ответ на развилку не изменил следующий шаг — проверка падает."""
    output = _reply([], next_stage="ba_gate")
    problems = run_semantic_check("dialogue_fork_branch", output, "hybrid", expected_next="system")

    assert problems
    assert any("system" in problem for problem in problems)


def test_fork_branch_silent_without_expectation() -> None:
    """Без `expect_next` проверка не даёт ложных срабатываний."""
    assert run_semantic_check("dialogue_fork_branch", _reply([]), "hybrid") == []


def test_fork_cases_are_twins_with_different_branches() -> None:
    """ORCH-12 и ORCH-13 — одна развилка, разные ответы, разные этапы."""
    rows = [
        json.loads(line) for line in CASES.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    contracts = {
        json.loads(row["vars"]["contract"])["id"]: json.loads(row["vars"]["contract"])
        for row in rows
        if json.loads(row["vars"]["contract"])["id"].startswith(("ORCH-12", "ORCH-13"))
    }

    assert len(contracts) == 2, "нужны оба кейса развилки: ORCH-12 и ORCH-13"
    first, second = (contracts[key] for key in sorted(contracts))
    fork_first = first["dialogue"]["fork"]
    fork_second = second["dialogue"]["fork"]

    assert fork_first["question_contains"] == fork_second["question_contains"]
    assert fork_first["answer"] != fork_second["answer"]
    assert fork_first["expect_next"] != fork_second["expect_next"]
    for contract in (first, second):
        assert "dialogue_fork_branch" in contract["semantic_checks"]
        assert contract["mode"] == "hybrid"


def test_mock_final_turn_follows_fork_branch() -> None:
    """Mock отдаёт этап, заданный развилкой: близнецы расходятся по `next`."""
    base = {
        "mode": "hybrid",
        "dialogue": SCENARIO_FORK,
    }
    russia = mock_provider.build_answer({**base, "id": "ORCH-12"})
    transborder_scenario = {
        **SCENARIO_FORK,
        "fork": {**SCENARIO_FORK["fork"], "expect_next": "architecture"},
    }
    transborder = mock_provider.build_answer(
        {**base, "id": "ORCH-13", "dialogue": transborder_scenario}
    )

    assert json.loads(russia)["next"] == "system"
    assert json.loads(transborder)["next"] == "architecture"


def test_bridge_passes_expected_next() -> None:
    """Мост доносит ожидаемый этап до Python-проверки."""
    request = {
        "check": "dialogue_fork_branch",
        "output": _reply([], next_stage="ba_gate"),
        "mode": "hybrid",
        "expected_next": "system",
    }
    completed = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "semantic_check_bridge.py")],
        input=json.dumps(request, ensure_ascii=False),
        capture_output=True,
        text=True,
        check=True,
    )

    assert json.loads(completed.stdout)["problems"]
