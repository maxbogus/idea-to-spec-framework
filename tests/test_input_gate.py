"""Код-гейт: пустая идея не доходит до модели.

Зачем. Кейс `NEG-01-empty-idea` проверяет, что на пустом входе оркестратор
просит одну строку и не начинает прогон. Проверять это моделью дорого и
ненадёжно: все семь измеренных моделей (7B–12B, разные семейства) на пустом
входе начинали прогон и писали артефакты — провал оказался общим, а не
свойством конкретной модели.

Пустой вход — это не задача для модели, а входная ошибка: его должен
отсекать код, до вызова LLM. Тогда проверка становится детерминированной,
не тратит токены и не зависит от того, какая модель стоит на машине.

Правило живёт в `scripts/idea_to_spec/input_gate.py` и используется трансформом
промпта: при пустом входе модель не вызывается, а подставляется
детерминированный ответ.
"""

from __future__ import annotations

import json

import pytest

from idea_to_spec.input_gate import (
    EMPTY_IDEA_ANSWER,
    is_empty_idea,
    is_trivial_input,
)

#: Входы, которые считаются пустой идеей.
EMPTY_INPUTS = ["", "   ", "\n", "\t \n  ", "\u00a0"]

#: Входы, которые НЕ считаются пустой идеей: идея есть, пусть даже короткая.
NON_EMPTY_INPUTS = [
    "Хочу приложение для заметок.",
    "CRM",
    "a",
    "1",
    "...",
    "приложение",
]


@pytest.mark.parametrize("value", EMPTY_INPUTS)
def test_empty_idea_detected(value: str) -> None:
    """Пустые и пробельные входы распознаются как пустая идея."""
    assert is_empty_idea(value)


@pytest.mark.parametrize("value", NON_EMPTY_INPUTS)
def test_non_empty_input_not_detected(value: str) -> None:
    """Короткая, но содержательная идея не считается пустой."""
    assert not is_empty_idea(value)


def test_trivial_input_is_flagged() -> None:
    """Однословный вход помечается как требующий уточнения."""
    assert is_trivial_input("CRM")
    assert is_trivial_input("приложение")
    assert not is_trivial_input("Хочу приложение для заметок с синхронизацией")


def test_empty_answer_is_valid_json_and_mentions_line() -> None:
    """Ответ на пустую идею — валидный JSON, который просит одну строку."""
    payload = json.loads(EMPTY_IDEA_ANSWER)
    assert isinstance(payload, dict)
    assert payload["mode"] == "auto"
    assert payload["stage"] == "intake"
    assert payload["questions"], "ответ должен содержать вопрос"
    assert "строку" in json.dumps(payload, ensure_ascii=False).lower()
    assert not payload["artifacts"], "на пустой идее артефакты не создаются"
