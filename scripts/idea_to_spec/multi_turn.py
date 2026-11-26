"""Многоходовый диалог: разбор ответа роли и сценарий «вопрос → ответ».

Зачем. Измерено (F023): кейсы режимов `chat` и `hybrid` в eval-наборе
проверяли ОДИН ход в режиме диалога, а не сам диалог. Провайдер отправлял
ровно одно сообщение (`messages: [{role: user, content: prompt}]`), истории
переписки не было. Значит, не покрыты: второй ход, реакция на ответ
заказчика, критерий остановки диалога и развилка в `hybrid`.

Модуль закрывает разрыв на уровне данных: он умеет разобрать ответ роли на
вопросы, сопоставить вопрос с парой «вопрос → ответ» из сценария кейса,
накопить ходы и построить историю переписки для следующего запроса.

Формат сценария в контракте кейса:

    "dialogue": {
      "turns": [
        {"question_contains": "срок хранения", "answer": "12 месяцев (ответ заказчика)"},
        {"question_contains": "цена тарифа", "answer": "990 ₽ в месяц (ответ заказчика)"}
      ]
    }

`question_contains` — фрагмент текста вопроса, по которому сценарий узнаёт
свой вопрос. Точное совпадение не требуется: модель формулирует вопрос
по-своему, и жёсткое сравнение сделало бы многоходовый кейс хрупким.
Ответ помечен источником «ответ заказчика» — так его узнаёт проверка
`dialogue_uses_customer_answer`.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

#: Метка источника ответа заказчика. Её же ищет проверка второго хода.
CUSTOMER_ANSWER_MARKER = "ответ заказчика"

#: Маркер, по которому запрос следующего хода отличается от первого.
#: Считается и в реальном провайдере, и в mock: оба считают ходы одинаково.
FOLLOWUP_MARKER = "ОТВЕТ ЗАКАЗЧИКА на твой последний вопрос"

#: Предохранитель: больше ходов диалога, чем пар в сценарии, не бывает.
#: Число берётся из сценария, этот предел — только защита от зацикливания.
MAX_TURNS = 10


@dataclass(frozen=True)
class DialogueTurn:
    """Один ход диалога: вопрос роли и ответ заказчика.

    Attributes:
        question: Текст вопроса, который задала роль.
        answer: Ответ заказчика на этот вопрос.
        question_contains: Фрагмент, по которому вопрос узнаётся в сценарии.
    """

    question: str
    answer: str
    question_contains: str = ""


def _load_payload(output: str) -> dict[str, Any] | None:
    """Разобрать ответ как JSON-объект.

    Args:
        output: Текст ответа модели.

    Returns:
        Словарь ответа или None, если разобрать не удалось.
    """
    text = output.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```\s*$", "", text)
    text = text.strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def parse_questions(output: str) -> list[str]:
    """Извлечь вопросы из ответа роли.

    Args:
        output: Текст ответа модели.

    Returns:
        Список текстов вопросов (пустой, если вопросов нет или ответ не JSON).
    """
    payload = _load_payload(output)
    if payload is None:
        return []
    questions = payload.get("questions")
    if not isinstance(questions, list):
        return []
    return [str(question) for question in questions if isinstance(question, str)]


def _scenario_turns(scenario: dict[str, Any]) -> list[dict[str, Any]]:
    """Собрать пары «вопрос → ответ» из сценария.

    Args:
        scenario: Блок `dialogue` контракта кейса.

    Развилка (`fork`) играется последней парой: ответ на неё — тоже ответ
    заказчика, и провайдер обязан провести его как ход диалога, иначе
    `expect_next` проверял бы этап, до которого диалог не дошёл.

    Returns:
        Список пар с ключами `question_contains` и `answer`.
    """
    raw_turns = scenario.get("turns")
    candidates = list(raw_turns) if isinstance(raw_turns, list) else []
    fork = scenario.get("fork")
    if isinstance(fork, dict):
        candidates.append(fork)
    turns: list[dict[str, Any]] = []
    for turn in candidates:
        if not isinstance(turn, dict):
            continue
        contains = str(turn.get("question_contains") or "").strip()
        answer = str(turn.get("answer") or "").strip()
        if not contains or not answer:
            continue
        turns.append({"question_contains": contains, "answer": answer})
    return turns


def _find_turn(
    questions: list[str], scenario: dict[str, Any], answered: set[str] | None = None
) -> dict[str, Any] | None:
    """Найти пару сценария, которой соответствует заданный вопрос.

    Уже отвеченные пары пропускаются. Причина измерена на qwen3:8b: модель
    на втором ходу повторяет свой первый вопрос («Какой контур…»), и поиск по
    всему сценарию отдавал ответ на уже закрытую тему — пара «цена» не
    наступала, а диалог топтался на месте до предела в 10 ходов.

    Args:
        questions: Вопросы, которые задала роль.
        scenario: Блок `dialogue` контракта кейса.
        answered: Фрагменты вопросов, на которые уже ответили.

    Returns:
        Пара сценария или None, если ни одна не подошла.
    """
    skipped = answered or set()
    for turn in _scenario_turns(scenario):
        if turn["question_contains"] in skipped:
            continue
        needle = turn["question_contains"].lower()
        if any(needle in question.lower() for question in questions):
            return turn
    return None


def match_customer_answer(
    questions: list[str], scenario: dict[str, Any], answered: set[str] | None = None
) -> str | None:
    """Найти ответ заказчика на заданные вопросы.

    Args:
        questions: Вопросы, которые задала роль.
        scenario: Блок `dialogue` контракта кейса.
        answered: Фрагменты вопросов, на которые уже ответили.

    Returns:
        Ответ заказчика или None, если вопрос не найден в сценарии.
    """
    turn = _find_turn(questions, scenario, answered)
    return turn["answer"] if turn is not None else None


def next_customer_answer(scenario: dict[str, Any], answered: set[str]) -> str | None:
    """Найти ответ заказчика для следующего хода диалога.

    Args:
        scenario: Блок `dialogue` контракта кейса.
        answered: Фрагменты вопросов, на которые уже ответили.

    Returns:
        Ответ заказчика или None, если сценарий исчерпан.
    """
    for turn in _scenario_turns(scenario):
        if turn["question_contains"] not in answered:
            answer: str = turn["answer"]
            return answer
    return None


def select_next_turn(
    scenario: dict[str, Any], answered: set[str], questions: list[str] | None = None
) -> DialogueTurn | None:
    """Выбрать следующий ход диалога по сценарию.

    Порядок выбора:
    1. пара, чей `question_contains` встречается в тексте вопроса роли, —
       точное совпадение темы;
    2. первая ещё не отвеченная пара по порядку.

    Args:
        scenario: Блок `dialogue` контракта кейса.
        answered: Фрагменты вопросов, на которые уже ответили.
        questions: Вопросы, которые задала роль (для поиска по теме).

    Returns:
        Следующий ход или None, если сценарий исчерпан.
    """
    pairs = _scenario_turns(scenario)

    # 1. Совпадение по теме: модель спросила про контур — отвечаем про контур.
    #    Уже отвеченные пары пропускаются: модель на втором ходу повторяет
    #    свой первый вопрос, и поиск по всему сценарию отдавал бы ответ на
    #    закрытую тему (измерено на qwen3:8b: пара «цена» не наступала,
    #    диалог топтался 10 ходов подряд).
    if questions:
        for turn in pairs:
            if turn["question_contains"] in answered:
                continue
            needle = turn["question_contains"].lower()
            if any(needle in question.lower() for question in questions):
                return DialogueTurn(
                    question=turn["question_contains"],
                    answer=turn["answer"],
                    question_contains=turn["question_contains"],
                )

    # 2. Первая ещё не отвеченная пара по порядку.
    for turn in pairs:
        if turn["question_contains"] not in answered:
            return DialogueTurn(
                question=turn["question_contains"],
                answer=turn["answer"],
                question_contains=turn["question_contains"],
            )
    return None


def scenario_fork(scenario: dict[str, Any]) -> dict[str, Any] | None:
    """Вернуть блок `fork` сценария — последнюю развилку диалога.

    Зачем. В режиме `hybrid` вопрос задаётся только на развилке, и смысл
    ответа — в следствии: ветка меняет следующий этап. Ожидание хранится
    рядом с ответом (`expect_next`), чтобы проверка `dialogue_fork_branch`
    сверяла его с полем `next` финального ответа, а не с формулировкой.

    Args:
        scenario: Блок `dialogue` контракта кейса.

    Returns:
        Словарь с `question_contains`, `answer` и `expect_next` или None,
        если развилки в сценарии нет.
    """
    fork = scenario.get("fork")
    if not isinstance(fork, dict):
        return None
    contains = str(fork.get("question_contains") or "").strip()
    answer = str(fork.get("answer") or "").strip()
    if not contains or not answer:
        return None
    return {
        "question_contains": contains,
        "answer": answer,
        "expect_next": str(fork.get("expect_next") or "").strip(),
    }


def scenario_turns(scenario: dict[str, Any]) -> list[dict[str, Any]]:
    """Публичная обёртка над разбором пар «вопрос → ответ».

    Args:
        scenario: Блок `dialogue` контракта кейса.

    Returns:
        Список пар с ключами `question_contains` и `answer`.
    """
    return _scenario_turns(scenario)


def build_history(turns: list[DialogueTurn]) -> list[dict[str, str]]:
    """Собрать историю переписки для следующего запроса к модели.

    Роли расставлены от лица модели: её собственные реплики — `assistant`,
    ответы заказчика — `user`. Исходный запрос (промпт роли с входом)
    добавляется провайдером первым сообщением, поэтому история начинается
    с вопроса роли.

    Args:
        turns: Произошедшие ходы диалога.

    Returns:
        Список сообщений в формате Ollama.
    """
    history: list[dict[str, str]] = []
    for turn in turns:
        history.append({"role": "assistant", "content": turn.question})
        history.append({"role": "user", "content": turn.answer})
    return history


def followup_prompt(
    prompt: str,
    customer_answer: str,
    mode: str = "",
    input_text: str = "",
    all_answers: list[str] | None = None,
    scenario_exhausted: bool = False,
) -> str:
    """Собрать промпт следующего хода с ответами заказчика.

    Зачем. Модель должна видеть ответы заказчика не только в истории, но и в
    самом запросе: иначе она продолжит отвечать на исходный вход.

    Промпт следующего хода **короткий**: роль, вход, ответы заказчика и блок
    формата ответа — без полного промпта роли и без общих правил. Причина
    измерена на qwen3:8b: полный промпт (10 КБ) плюс история переписки
    перегружали модель, и формат ответа деградировал с каждым ходом —
    8 полей на первом, 7 на втором («next» превращался в «next_stage»),
    6 на третьем плюс чужие поля (`answers`, `regional_checklist`). Короткий
    follow-up (~1 КБ) держит полный формат на всех ходах.

    Передаются **все** накопленные ответы заказчика, а не только последний.
    Причина измерена на qwen3:8b: при передаче только последнего ответа модель
    теряла предыдущие — в `assumptions` попадала величина «990 ₽», а ответ
    «B2C» исчезал. Со списком всех ответов модель фиксирует каждый.

    Args:
        prompt: Исходный промпт роли (из него берётся блок формата ответа).
        customer_answer: Ответ заказчика на последний вопрос.
        mode: Режим прогона.
        input_text: Исходный вход кейса.
        all_answers: Все ответы заказчика за диалог (по порядку).
        scenario_exhausted: Исчерпан ли сценарий — если да, диалог закрывается.

    Returns:
        Промпт следующего хода.
    """
    parts = [
        "Ты продолжаешь диалог в роли мультиагентной системы «идея → "
        "спецификация». Твоя роль та же, что и в предыдущем ответе.",
    ]
    if input_text:
        parts.append(f"ВХОД:\n{input_text}")

    answers = list(all_answers or [])
    if customer_answer and customer_answer not in answers:
        answers.append(customer_answer)
    if answers:
        parts.append(
            "Ответы заказчика, полученные за этот диалог:\n"
            + "\n".join(f"- {answer}" for answer in answers)
        )

    parts.append(
        "Учти эти ответы. Ссылайся на них как на источник «ответ заказчика», "
        "не выдумывай свои значения. Каждое утверждение без источника помечай "
        "как допущение или гипотезу."
    )
    if mode:
        parts.append(f"Режим работы: {mode}.")
    parts.append(
        "Зафиксируй КАЖДЫЙ ответ заказчика в assumptions — отдельной строкой, "
        "со ссылкой на источник «ответ заказчика»."
    )
    if scenario_exhausted:
        # Правило остановки даётся только когда сценарий исчерпан. Раньше оно
        # срабатывало всегда («если все вопросы закрыты»), и модель закрывала
        # диалог после ПЕРВОГО ответа — второй ответ терялся. Измерено на
        # qwen3:8b: без этого правила модель фиксировала оба ответа.
        #
        # Формулировка — по A/B-замеру (2 повтора × 2 кейса, qwen3:8b).
        # Работают ОБА ингредиента, каждый по отдельности не работает:
        #   - условие «ответ заказчика закрыл последний невыясненный вопрос»
        #     вместо «все вопросы закрыты» — иначе ORCH-10 продолжал спрашивать;
        #   - императив «Больше не задавай вопросов» — иначе ORCH-10 снова
        #     продолжал спрашивать (модель читала условие как описание, а не
        #     как команду).
        # Итог: «поле questions пустое» → «поле questions — пустой список []»
        # (явный тип значения вместо описания).
        parts.append(
            "КРИТЕРИЙ ОСТАНОВКИ ДИАЛОГА: ответ заказчика закрыл последний "
            "невыясненный вопрос — диалог окончен, новых ответов не будет. "
            "Больше не задавай вопросов: поле questions — пустой список []. "
            "Зафиксируй ответы в assumptions и перейди к следующему этапу."
        )
    else:
        parts.append(
            "Диалог продолжается: заказчик ответил не на все вопросы. Задай "
            "следующий вопрос — не больше одного, по теме, которая меняет "
            "следующий шаг."
        )

    format_block = extract_format_block(prompt)
    if format_block:
        parts.append(
            "Твой ответ — JSON-объект РОВНО в этом формате (все поля "
            f"обязательны):\n```json\n{format_block}\n```"
        )
    else:
        # Блок формата не нашёлся — отдаём исходный промпт целиком: лучше
        # лишний контекст, чем ответ без формата.
        parts.insert(0, prompt)
    return "\n\n".join(parts)


def extract_format_block(prompt: str) -> str:
    """Извлечь блок формата ответа из промпта роли.

    Args:
        prompt: Текст промпта (уже отрендеренный шаблоном eval).

    Returns:
        Содержимое JSON-блока формата ответа (пустая строка, если блока нет).
    """
    match = re.search(r"```json\n(.*?)```", prompt, re.S)
    return match.group(1).strip() if match is not None else ""


def customer_answer_from_prompt(prompt: str) -> str | None:
    """Извлечь ответ заказчика из промпта следующего хода.

    Args:
        prompt: Текст запроса.

    Returns:
        Ответ заказчика или None, если это запрос первого хода.
    """
    if FOLLOWUP_MARKER not in prompt:
        return None
    tail = prompt.split(FOLLOWUP_MARKER, 1)[1]
    lines = [line.strip() for line in tail.splitlines() if line.strip()]
    if not lines:
        return None
    return lines[0]


def run_turns(
    prompt: str,
    scenario: dict[str, Any],
    call: Callable[[str, list[DialogueTurn]], str],
    mode: str = "",
    input_text: str = "",
) -> tuple[str, list[DialogueTurn]]:
    """Провести диалог по сценарию.

    Логика ходов общая для реального провайдера и mock: оба считают ходы
    одинаково, иначе eval-mock не воспроизводил бы то, что проверяет
    реальный прогон.

    Args:
        prompt: Текст запроса (промпт роли с входом).
        scenario: Блок `dialogue` контракта кейса.
        call: Функция вызова модели: получает промпт и историю ходов,
            возвращает ответ роли.
        mode: Режим прогона — попадает в короткий промпт следующего хода.
        input_text: Исходный вход кейса — попадает в короткий промпт.

    Returns:
        Последний ответ роли и список состоявшихся ходов.
    """
    turns: list[DialogueTurn] = []
    answered: set[str] = set()
    current_prompt = prompt

    output = call(current_prompt, turns)
    for _ in range(MAX_TURNS):
        questions = parse_questions(output)
        if not questions:
            break

        turn = select_next_turn(scenario, answered, questions)
        if turn is None:
            break

        # Ответ заказчика берётся только из пары, выбранной `select_next_turn`:
        # при непустом сценарии пара находится всегда — сначала по теме
        # вопроса, затем первая неотвеченная по порядку. Второй шаг и есть
        # обработка переформулированного вопроса: модель спросила «Какой
        # контур у сервиса: B2C, B2B или B2G?», а сценарий ждал вопрос про
        # срок хранения — пара всё равно находится, иначе второй ход не
        # проверялся бы вовсе.
        #
        # Отдельного fallback здесь нет намеренно: ответ пары непустой по
        # построению (`_scenario_turns` отбрасывает пары без `answer`), а
        # поиск по теме в fallback повторял бы первый шаг `select_next_turn` и
        # мог вернуть только None — то есть испортить валидный ход строкой
        # «- None» в списке ответов заказчика.
        customer_answer = turn.answer

        turns.append(
            DialogueTurn(
                question=questions[0],
                answer=customer_answer,
                question_contains=turn.question_contains,
            )
        )
        answered.add(turn.question_contains)

        current_prompt = followup_prompt(
            prompt,
            customer_answer,
            mode,
            input_text,
            all_answers=[t.answer for t in turns],
            # Сценарий исчерпан, когда после текущего ответа пар больше нет:
            # тогда диалог закрывается и модель не задаёт новых вопросов.
            scenario_exhausted=len(answered) >= len(_scenario_turns(scenario)),
        )
        output = call(current_prompt, turns)

    return output, turns
