"""Многоходовый диалог: провайдер с историей и проверки второго хода.

Зачем. Измерено (F023): кейсы режимов `chat` и `hybrid` проверяли ОДИН ход
в режиме диалога, а не сам диалог. `gated_provider.py` отправлял ровно одно
сообщение (`messages: [{role: user, content: prompt}]`), истории переписки
не было, поэтому не покрыты: второй ход, реакция на ответ заказчика,
критерий остановки диалога и развилка в `hybrid`.

Этот файл закрывает разрыв:

1. `scripts/idea_to_spec/multi_turn.py` — разбор ответа роли на вопросы,
   сопоставление с парой «вопрос → ответ» из сценария, накопление ходов
   и критерий остановки диалога;
2. `scripts/idea_to_spec/semantic_check.py` — структурные проверки ответа
   второго хода (опирается на ответ заказчика, закрывает отвеченный вопрос,
   останавливает диалог);
3. `scripts/multi_turn_provider.py` — exec-провайдер, который сам вызывает
   Ollama по ходам и передаёт историю.

Проверки пишутся по тем же правилам, что и остальной набор: семантика
вместо лексики, проверка структуры ответа, а не набора ключевых слов.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from idea_to_spec.multi_turn import (
    DialogueTurn,
    build_history,
    followup_prompt,
    match_customer_answer,
    next_customer_answer,
    parse_questions,
    run_turns,
    select_next_turn,
)
from idea_to_spec.semantic_check import run_semantic_check


def _orchestrator(questions: list[str], assumptions: list[str] | None = None) -> str:
    """Собрать ответ оркестратора для тестов.

    Args:
        questions: Вопросы, которые задаёт роль.
        assumptions: Явные допущения.

    Returns:
        JSON-строка ответа.
    """
    return json.dumps(
        {
            "mode": "chat",
            "stage": "business",
            "completeness": {"passed": not questions, "missing": []},
            "questions": questions,
            "artifacts": ["output/chat-001/brief.md"],
            "assumptions": assumptions or [],
            "next": "ba_gate",
        },
        ensure_ascii=False,
    )


#: Сценарий из двух пар «вопрос → ответ». Ключ `question_contains` — фрагмент
#: текста вопроса, по которому сценарий узнаёт свой вопрос.
SCENARIO: dict[str, Any] = {
    "turns": [
        {
            "question_contains": "срок хранения",
            "answer": "12 месяцев (ответ заказчика)",
        },
        {
            "question_contains": "цена тарифа",
            "answer": "990 ₽ в месяц (ответ заказчика)",
        },
    ]
}


def test_parse_questions_reads_question_strings() -> None:
    """Вопросы роли разбираются из поля `questions`."""
    output = _orchestrator(
        [
            "Вопрос: какой срок хранения данных? "
            "Зачем я это спрашиваю: влияет на модель данных. Термины: retention — срок хранения.",
            "Вопрос: какая цена тарифа? "
            "Зачем я это спрашиваю: нужна для юнит-экономики. Термины: ARPU — доход на пользователя.",
        ]
    )
    questions = parse_questions(output)
    assert len(questions) == 2
    assert "срок хранения" in questions[0]


def test_parse_questions_ignores_non_list_payload() -> None:
    """Не-list поле `questions` не ломает разбор — возвращается пустой список."""
    output = json.dumps({"questions": {"question": "хм"}}, ensure_ascii=False)
    assert parse_questions(output) == []


def test_match_customer_answer_finds_pair() -> None:
    """Вопрос узнаётся по фрагменту, и ответ заказчика находится."""
    questions = [
        "Вопрос: какой срок хранения данных? Зачем я это спрашиваю: x. Термины: y.",
    ]
    answer = match_customer_answer(questions, SCENARIO)
    assert answer == "12 месяцев (ответ заказчика)"


def test_match_customer_answer_returns_none_when_unknown() -> None:
    """Вопрос, которого нет в сценарии, не получает чужой ответ."""
    questions = ["Вопрос: неизвестный вопрос? Зачем я это спрашиваю: x. Термины: y."]
    assert match_customer_answer(questions, SCENARIO) is None


def test_match_customer_answer_skips_answered_pair() -> None:
    """Уже отвеченная пара не выдаётся повторно.

    Регрессия, измеренная на qwen3:8b: модель на втором ходу повторяет
    свой первый вопрос («Какой контур…»), и поиск по всему сценарию
    возвращал «B2C» вместо «990 ₽» — величина терялась, а кейс падал на
    `must_contain`.
    """
    questions = [
        "Вопрос: какой срок хранения данных? Зачем я это спрашиваю: x. Термины: y.",
    ]
    answer = match_customer_answer(questions, SCENARIO, {"срок хранения"})
    assert answer is None, "отвеченная пара не должна выдаваться повторно"


def test_next_customer_answer_is_none_after_last_pair() -> None:
    """После последней пары сценарий исчерпан — диалог останавливается."""
    answered = {"срок хранения", "цена тарифа"}
    assert next_customer_answer(SCENARIO, answered) is None


def test_next_customer_answer_returns_first_unanswered() -> None:
    """Следующий ответ — от первой ещё не отвеченной пары."""
    answered = {"срок хранения"}
    assert next_customer_answer(SCENARIO, answered) == "990 ₽ в месяц (ответ заказчика)"


def test_select_next_turn_returns_turn_object() -> None:
    """Выбор хода возвращает объект с вопросом и ответом заказчика."""
    turn = select_next_turn(SCENARIO, {"срок хранения"})
    assert isinstance(turn, DialogueTurn)
    assert turn.answer == "990 ₽ в месяц (ответ заказчика)"
    assert "цена тарифа" in turn.question_contains


def test_select_next_turn_skips_answered_pair_on_repeated_question() -> None:
    """Повторный вопрос по отвеченной теме даёт СЛЕДУЮЩУЮ пару.

    Регрессия, измеренная на qwen3:8b: модель на втором ходу повторяет
    свой первый вопрос («Какой контур сервиса: B2C, B2B или B2G?»). Поиск
    пары по теме во всём сценарии отдавал «B2C» второй раз — пара «цена» не
    наступала, диалог топтался на месте 10 ходов подряд, а `must_contain`
    «990 ₽» не выполнялся.
    """
    repeated = ["Вопрос: какой срок хранения данных? Зачем я это спрашиваю: x."]
    turn = select_next_turn(SCENARIO, {"срок хранения"}, repeated)
    assert turn is not None
    assert turn.answer == "990 ₽ в месяц (ответ заказчика)"
    assert "цена тарифа" in turn.question_contains


def test_followup_prompt_lists_all_answers() -> None:
    """В follow-up передаются ВСЕ ответы заказчика, а не только последний.

    Причина измерена на qwen3:8b: при передаче только последнего ответа
    модель теряла предыдущие — в `assumptions` попадала величина «990 ₽»,
    а ответ «B2C» исчезал.
    """
    prompt = followup_prompt(
        "промпт",
        "990 ₽ в месяц (ответ заказчика)",
        "chat",
        "вход",
        all_answers=["12 месяцев (ответ заказчика)", "990 ₽ в месяц (ответ заказчика)"],
    )
    assert "12 месяцев (ответ заказчика)" in prompt
    assert "990 ₽ в месяц (ответ заказчика)" in prompt


def test_followup_prompt_stop_criterion_states_imperative() -> None:
    """Стоп-критерий говорит «не задавай вопросов» и называет пустой список.

    Формулировка отмерена A/B-замером (2 повтора × 2 кейса, qwen3:8b):
    нужны оба ингредиента — условие «ответ заказчика закрыл последний
    невыясненный вопрос» и императив «Больше не задавай вопросов».
    Без императива ORCH-10 продолжал задавать вопросы.
    """
    prompt = followup_prompt(
        "промпт",
        "990 ₽ (ответ заказчика)",
        "chat",
        "вход",
        all_answers=["990 ₽ (ответ заказчика)"],
        scenario_exhausted=True,
    )
    assert "Больше не задавай вопросов" in prompt
    assert "пустой список []" in prompt
    assert "закрыл последний невыясненный вопрос" in prompt


def test_build_history_keeps_turn_order() -> None:
    """История передаётся модели в порядке ходов.

    Роли в истории расставлены от лица модели: её реплики — `assistant`,
    ответы заказчика — `user`.
    """
    history = build_history(
        [
            DialogueTurn(question="Вопрос: срок хранения?", answer="12 месяцев"),
            DialogueTurn(question="Вопрос: цена?", answer="990 ₽"),
        ]
    )
    assert [message["role"] for message in history] == ["assistant", "user", "assistant", "user"]
    assert history[0]["content"] == "Вопрос: срок хранения?"
    assert history[1]["content"] == "12 месяцев"
    assert history[2]["content"] == "Вопрос: цена?"
    assert history[3]["content"] == "990 ₽"


def _question_about(topic: str) -> str:
    """Собрать ответ роли с одним вопросом по теме.

    Args:
        topic: Фрагмент вопроса, который задаёт роль.

    Returns:
        JSON-строка ответа оркестратора.
    """
    return _orchestrator([f"Вопрос: {topic}? Зачем я это спрашиваю: x. Термины: y."])


def test_run_turns_answers_question_from_pair() -> None:
    """Ход берёт ответ той пары, о которой спросила роль.

    Вопрос задан про цену, хотя первой в сценарии стоит пара про срок
    хранения: выбор идёт по теме вопроса, а не по порядку. Ответ пары
    попадает в промпт следующего хода — иначе модель продолжила бы отвечать
    на исходный вход, не видя ответа заказчика.
    """
    prompts: list[str] = []
    outputs = [_question_about("какая цена тарифа"), _orchestrator([])]

    def call(prompt: str, turns: list[DialogueTurn]) -> str:
        prompts.append(prompt)
        return outputs[len(prompts) - 1]

    output, turns = run_turns("промпт", SCENARIO, call, mode="chat", input_text="вход")

    assert len(turns) == 1
    assert turns[0].answer == "990 ₽ в месяц (ответ заказчика)"
    assert "990 ₽ в месяц (ответ заказчика)" in prompts[1]
    assert "срок хранения" not in prompts[1]
    assert output == outputs[1]


def test_run_turns_stops_after_last_pair() -> None:
    """Диалог идёт по парам сценария и закрывается после последней.

    Пар в сценарии две — значит ходов ровно два, а вызовов модели три:
    первый ответ роли, ответ после каждой пары. На последнем ходе сценарий
    исчерпан, и промпт содержит императивный критерий остановки.
    """
    prompts: list[str] = []
    outputs = [
        _question_about("какой срок хранения данных"),
        _question_about("какая цена тарифа"),
        _orchestrator([]),
    ]

    def call(prompt: str, turns: list[DialogueTurn]) -> str:
        prompts.append(prompt)
        return outputs[len(prompts) - 1]

    _output, turns = run_turns("промпт", SCENARIO, call)

    assert [turn.answer for turn in turns] == [
        "12 месяцев (ответ заказчика)",
        "990 ₽ в месяц (ответ заказчика)",
    ]
    assert len(prompts) == 3
    assert "Диалог продолжается" in prompts[1]
    assert "Больше не задавай вопросов" in prompts[2]
    assert "12 месяцев (ответ заказчика)" in prompts[2]


def test_dialogue_uses_customer_answer_detects_fabrication() -> None:
    """Выдуманное значение вместо ответа заказчика — проблема."""
    output = _orchestrator(
        ["Вопрос: какой срок хранения? Зачем я это спрашиваю: x. Термины: y."],
        assumptions=["срок хранения — 36 месяцев"],
    )
    problems = run_semantic_check(
        "dialogue_uses_customer_answer",
        output,
        "chat",
        customer_answer="12 месяцев (ответ заказчика)",
    )
    assert problems, "выдуманное значение должно ловиться"
    assert "12 месяцев" in problems[0]
    assert "подменена" in problems[0]


def test_dialogue_uses_customer_answer_accepts_grounded_answer() -> None:
    """Ответ, опирающийся на ответ заказчика, — проблем не даёт."""
    output = _orchestrator(
        ["Вопрос: какой срок хранения? Зачем я это спрашиваю: x. Термины: y."],
        assumptions=["срок хранения — 12 месяцев (ответ заказчика)"],
    )
    assert (
        run_semantic_check(
            "dialogue_uses_customer_answer",
            output,
            "chat",
            customer_answer="12 месяцев (ответ заказчика)",
        )
        == []
    )


def test_dialogue_closes_answered_question_detects_open_question() -> None:
    """Отвеченный вопрос, оставшийся открытым, — проблема."""
    output = json.dumps(
        {
            "mode": "chat",
            "stage": "business",
            "questions": [],
            "open_questions": ["какой срок хранения данных?"],
            "assumptions": [],
            "next": "ba_gate",
        },
        ensure_ascii=False,
    )
    problems = run_semantic_check(
        "dialogue_closes_answered_question",
        output,
        "chat",
        answered_question="какой срок хранения данных?",
    )
    assert problems
    assert "срок хранения" in problems[0]


def test_dialogue_closes_answered_question_accepts_closed_question() -> None:
    """Отвеченный вопрос, снятый из open_questions, — проблем не даёт."""
    output = json.dumps(
        {
            "mode": "chat",
            "stage": "business",
            "questions": [],
            "open_questions": ["какая цена тарифа?"],
            "assumptions": [],
            "next": "ba_gate",
        },
        ensure_ascii=False,
    )
    assert (
        run_semantic_check(
            "dialogue_closes_answered_question",
            output,
            "chat",
            answered_question="какой срок хранения данных?",
        )
        == []
    )


def test_dialogue_stops_when_answered_detects_extra_question() -> None:
    """После последней пары новых вопросов быть не должно."""
    output = _orchestrator(
        ["Вопрос: ещё что-то? Зачем я это спрашиваю: x. Термины: y."],
    )
    problems = run_semantic_check(
        "dialogue_stops_when_answered",
        output,
        "chat",
        scenario_exhausted=True,
    )
    assert problems
    assert "диалог" in problems[0].lower()


def test_dialogue_stops_when_answered_accepts_no_questions() -> None:
    """Без вопросов диалог остановлен корректно."""
    output = _orchestrator([])
    assert (
        run_semantic_check(
            "dialogue_stops_when_answered",
            output,
            "chat",
            scenario_exhausted=True,
        )
        == []
    )


def test_dialogue_checks_are_inert_without_context() -> None:
    """Без параметров диалога проверки не дают ложных срабатываний."""
    output = _orchestrator(["Вопрос: какой срок хранения? Зачем я это спрашиваю: x. Термины: y."])
    for name in (
        "dialogue_uses_customer_answer",
        "dialogue_closes_answered_question",
        "dialogue_stops_when_answered",
    ):
        assert run_semantic_check(name, output, "chat") == []


@pytest.mark.parametrize(
    "name",
    [
        "dialogue_uses_customer_answer",
        "dialogue_closes_answered_question",
        "dialogue_stops_when_answered",
    ],
)
def test_dialogue_checks_report_non_json(name: str) -> None:
    """Не-JSON ответ помечается проблемой разбора, а не тихо проходит."""
    problems = run_semantic_check(name, "просто текст", "chat", customer_answer="x")
    assert problems == [f"ответ не разобран как JSON (проверка {name})"]


def test_provider_without_scenario_makes_single_call(monkeypatch: pytest.MonkeyPatch) -> None:
    """Кейс без сценария — обычный одноходовый вызов модели."""
    import multi_turn_provider

    calls: list[dict[str, object]] = []

    def _fake_call(
        prompt: str,
        options: dict[str, Any],
        history: list[dict[str, str]] | None = None,
        name: str = "turn",
    ) -> str:
        calls.append({"prompt": prompt, "history": history, "name": name})
        return _orchestrator(["Вопрос: какой срок хранения?"])

    monkeypatch.setattr(multi_turn_provider, "_call_ollama", _fake_call)
    output, turns = multi_turn_provider.run_dialogue("промпт", {}, {})
    assert turns == []
    assert len(calls) == 1
    assert calls[0]["history"] == [], "на первом ходе история пуста"
    assert calls[0]["name"] == "turn1", "без кейса в имени остаётся номер хода"
    assert "срок хранения" in output


def test_provider_continues_dialogue_with_history(monkeypatch: pytest.MonkeyPatch) -> None:
    """Провайдер ведёт диалог по сценарию и передаёт историю."""
    import multi_turn_provider

    replies = [
        _orchestrator(
            ["Вопрос: какой срок хранения данных? Зачем я это спрашиваю: x. Термины: y."]
        ),
        _orchestrator(["Вопрос: какая цена тарифа? Зачем я это спрашиваю: x. Термины: y."]),
        _orchestrator([]),
    ]
    calls: list[dict[str, Any]] = []

    def _fake_call(
        prompt: str,
        options: dict[str, Any],
        history: list[dict[str, str]] | None = None,
        name: str = "turn",
    ) -> str:
        calls.append({"prompt": prompt, "history": history, "name": name})
        return replies[len(calls) - 1]

    monkeypatch.setattr(multi_turn_provider, "_call_ollama", _fake_call)
    output, turns = multi_turn_provider.run_dialogue("промпт", {}, SCENARIO)

    assert len(calls) == 3, "диалог должен длиться до исчерпания сценария"
    assert len(turns) == 2
    assert turns[0].answer == "12 месяцев (ответ заказчика)"
    assert turns[1].answer == "990 ₽ в месяц (ответ заказчика)"

    # Второй вызов идёт с историей, третий — с историей двух ходов.
    second_history = calls[1]["history"]
    third_history = calls[2]["history"]
    assert isinstance(second_history, list)
    assert isinstance(third_history, list)
    assert len(second_history) == 2
    assert len(third_history) == 4
    # Ответ заказчика попадает и в историю, и в сам промпт.
    assert "12 месяцев" in str(calls[1]["prompt"])
    assert "12 месяцев" in str(second_history)
    assert "990 ₽" in str(calls[2]["prompt"])
    assert output


def test_provider_stops_when_model_asks_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Если модель не задала вопросов, диалог сразу заканчивается."""
    import multi_turn_provider

    calls: list[str] = []

    def _fake_call(
        prompt: str,
        options: dict[str, Any],
        history: list[dict[str, str]] | None = None,
        name: str = "turn",
    ) -> str:
        calls.append(prompt)
        return _orchestrator([])

    monkeypatch.setattr(multi_turn_provider, "_call_ollama", _fake_call)
    _output, turns = multi_turn_provider.run_dialogue("промпт", {}, SCENARIO)
    assert len(calls) == 1
    assert turns == []


def test_dialogue_continues_when_model_rephrases_question(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Модель переформулировала вопрос — диалог всё равно продолжается.

    Регрессия, измеренная на qwen3:8b: модель задала вопрос «Какой контур у
    сервиса: B2C, B2B или B2G?», а сценарий ждал вопрос про срок хранения.
    При жёсткой привязке к формулировке диалог обрывался на первом ходу —
    второй ход не проверялся вовсе, а кейс падал на must_contain.
    """
    import multi_turn_provider

    replies = [
        _orchestrator(
            [
                "Вопрос: Какой контур у сервиса: B2C, B2B или B2G? "
                "Зачем я это спрашиваю: контур определяет регуляторику. Термины: контур — тип клиента."
            ]
        ),
        _orchestrator(
            ["Вопрос: какой срок хранения данных? Зачем я это спрашиваю: x. Термины: y."]
        ),
        _orchestrator([]),
    ]
    calls: list[str] = []

    def _fake_call(
        prompt: str,
        options: dict[str, Any],
        history: list[dict[str, str]] | None = None,
        name: str = "turn",
    ) -> str:
        calls.append(prompt)
        return replies[len(calls) - 1]

    monkeypatch.setattr(multi_turn_provider, "_call_ollama", _fake_call)
    _output, turns = multi_turn_provider.run_dialogue("промпт", {}, SCENARIO)

    assert len(turns) == 2, "диалог должен продолжиться, даже если вопрос переформулирован"
    assert turns[0].answer == "12 месяцев (ответ заказчика)"
    assert len(calls) == 3


def test_dialogue_calls_carry_case_name(monkeypatch: pytest.MonkeyPatch) -> None:
    """Каждый ход помечен кейсом и номером хода — иначе трейс не атрибутируется.

    Без этого все диалоговые вызовы писались как `turn`: в append-only трейсе
    нельзя было понять, какой кейс усечён, а сырые дампы CHAT/HYB/SA
    становились неотличимы друг от друга (F035).
    """
    import multi_turn_provider

    names: list[str] = []

    def _fake_call(
        prompt: str,
        options: dict[str, Any],
        history: list[dict[str, str]] | None = None,
        name: str = "turn",
    ) -> str:
        names.append(name)
        return _orchestrator([])

    monkeypatch.setattr(multi_turn_provider, "_call_ollama", _fake_call)
    multi_turn_provider.run_dialogue("промпт", {}, SCENARIO, name="SA-04")

    assert names == ["SA-04-turn1"]
