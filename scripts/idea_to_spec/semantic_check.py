"""Структурные проверки контракта: семантика вместо лексики.

Модуль общий для двух потребителей:
- `tests/test_eval_contract.py` — pytest-контракты;
- `eval/promptfooconfig.yaml` — assert в реальном прогоне (через вызов
  `scripts/semantic_check.py` из JS-ассерта).

Причина, по которой проверка структурная. Кейс
`DISC-01-no-solution-as-need` требовал `must_contain: ["потребност"]` —
буквального слова «потребность». Проверялось семь моделей разных семейств
и размеров (3B–12B): все они описывали потребность правильно — в
`jobs_to_be_done[].want` («Получить награду за покупку»), — но ни одна не
написала слово «потребность». Провал принадлежал ассерту, а не модели.

Правильный критерий: потребность отделена от решения. Проверяется, что
потребность выражена и что решение не выдано за неё.
"""

from __future__ import annotations

import json
import re
from typing import Any, Protocol

from idea_to_spec.gate_checklists import validate_gate_payload
from idea_to_spec.multi_turn import CUSTOMER_ANSWER_MARKER
from idea_to_spec.role_schemas import validate_role_payload


class SemanticChecker(Protocol):
    """Сигнатура структурной проверки контракта.

    Единая сигнатура у всех проверок нужна, чтобы их можно было хранить в
    одном словаре и вызывать одинаково: `run_semantic_check` не должен
    разбирать сигнатуры рефлексией — это хрупко (проверка молча не получила бы
    контекст диалога) и не типизируется.

    Attributes:
        payload: Разобранный ответ роли.
        output: Текст ответа роли.
        expected_mode: Режим, заданный контрактом кейса.
        context: Контекст проверки. Для проверок диалога это
            `customer_answer`, `answered_question` и `scenario_exhausted`.
    """

    def __call__(
        self,
        payload: dict[str, Any],
        output: str,
        expected_mode: str = "",
        context: dict[str, Any] | None = None,
    ) -> list[str]: ...


#: Пометки гипотезы о решении: с ними решение в поле потребности допустимо.
HYPOTHESIS_MARKERS = ("допущени", "гипотез", "предположен", "вариант решения")

#: Термины-решения: их присутствие в поле потребности — признак подмены.
SOLUTION_HINTS = (
    "блокчейн",
    "blockchain",
    "postgresql",
    "mysql",
    "redis",
    "kafka",
    "docker",
    "kubernetes",
    "микросервис",
    "nosql",
    "mongodb",
    "graphql",
)


def load_payload(output: str) -> dict[str, Any] | None:
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


def need_text(payload: dict[str, Any]) -> str:
    """Собрать текст, выражающий потребность.

    Args:
        payload: Разобранный ответ роли.

    Returns:
        Текст потребности (пустая строка, если потребность не выражена).
    """
    parts: list[str] = []
    jobs = payload.get("jobs_to_be_done")
    if isinstance(jobs, list):
        for job in jobs:
            if isinstance(job, dict) and isinstance(job.get("want"), str):
                parts.append(job["want"])
    for key in ("as_is", "to_be"):
        value = payload.get(key)
        if isinstance(value, str):
            parts.append(value)
    return " ".join(parts)


def check_needs_separated(
    payload: dict[str, Any],
    output: str,
    expected_mode: str = "",
    context: dict[str, Any] | None = None,
) -> list[str]:
    """Проверить, что потребность отделена от решения.

    Args:
        payload: Разобранный ответ роли.
        output: Текст ответа (не используется, нужен для единой сигнатуры).
        expected_mode: Режим, заданный контрактом кейса (не используется).
        context: Контекст проверки (не используется).

    Returns:
        Список проблем (пустой, если критерий выполнен).
    """
    problems: list[str] = []
    if not need_text(payload).strip():
        problems.append("потребность не выражена: пусты jobs_to_be_done[].want и to_be")

    jobs = payload.get("jobs_to_be_done")
    if isinstance(jobs, list):
        for job in jobs:
            if not isinstance(job, dict):
                continue
            want = str(job.get("want") or "")
            lowered = want.lower()
            hit = next((hint for hint in SOLUTION_HINTS if hint in lowered), None)
            if hit is None:
                continue
            if not any(marker in lowered for marker in HYPOTHESIS_MARKERS):
                problems.append(
                    f"решение {hit!r} выдано за потребность (jobs_to_be_done[].want): {want[:60]!r}"
                )
    return problems


#: Блоки, которыми обязан оформляться каждый вопрос в режимах chat / hybrid.
#: Константа живёт здесь, а не в summarize_eval: оба потребителя смотрят
#: в одно место (тот же приём, что для needs_separated).
QUESTION_BLOCKS = ("вопрос", "зачем я это спрашиваю", "термины")


def check_mode_respected(
    payload: dict[str, Any],
    output: str,
    expected_mode: str = "",
    context: dict[str, Any] | None = None,
) -> list[str]:
    """Проверить, что модель не подменила заданный режим своим.

    Зачем. Режим приходит в запрос строкой («Режим работы: {{mode}}»), и ни
    один ролевой промпт про режим не знает: модель выбирает его сама. Измерено
    на qwen2.5:7b — модель отвечала `auto` вместо заданного `chat`.

    Args:
        payload: Разобранный ответ роли.
        output: Текст ответа (не используется, нужен для единой сигнатуры).
        expected_mode: Режим, заданный контрактом кейса.
        context: Контекст проверки (не используется).

    Returns:
        Список проблем (пустой, если режим соблюдён).
    """
    problems: list[str] = []
    declared = payload.get("mode")
    if not isinstance(declared, str) or not declared.strip():
        problems.append("поле mode не заполнено: модель не объявила режим")
        return problems
    # Ответ может содержать пояснение вроде "chat (диалог)".
    normalized = declared.strip().lower()
    if not normalized.startswith(("auto", "chat", "hybrid")):
        problems.append(f"в поле mode не режим прогона: {declared!r}")
        return problems
    wanted = expected_mode.strip().lower()
    if wanted and not normalized.startswith(wanted):
        problems.append(f"режим подменён: в ответе {declared!r}, а задан {expected_mode!r}")
    return problems


def check_questions_three_blocks(
    payload: dict[str, Any],
    output: str,
    expected_mode: str = "",
    context: dict[str, Any] | None = None,
) -> list[str]:
    """Проверить, что каждый вопрос оформлен тремя блоками.

    Зачем. Контракт `chat_three_blocks` проверял наличие блоков где-то в
    ответе: достаточно было одного правильно оформленного вопроса, чтобы
    остальные — сырые — прошли незамеченными. Проверка идёт по каждому
    элементу массива `questions`.

    Args:
        payload: Разобранный ответ роли.
        output: Текст ответа.
        expected_mode: Режим, заданный контрактом кейса (не используется).
        context: Контекст проверки (не используется).

    Returns:
        Список проблем (пустой, если все вопросы оформлены).
    """
    problems: list[str] = []
    questions = payload.get("questions")
    if not isinstance(questions, list):
        problems.append("поле questions — не массив")
        return problems
    for index, question in enumerate(questions):
        if not isinstance(question, str):
            problems.append(f"вопрос {index + 1}: не строка, а {type(question).__name__}")
            continue
        lowered = question.lower()
        missing = [block for block in QUESTION_BLOCKS if block not in lowered]
        if missing:
            problems.append(
                f"вопрос {index + 1}: нет блока(ов) {', '.join(repr(m) for m in missing)}"
            )
    return problems


def check_chat_keeps_open_questions(
    payload: dict[str, Any],
    output: str,
    expected_mode: str = "",
    context: dict[str, Any] | None = None,
) -> list[str]:
    """Проверить, что роль в режиме chat держит открытые вопросы.

    Зачем. У ролевых промптов нет поля `mode` в формате ответа — объявлять
    режим роль не обязана. Проверять «модель не подменила режим» для ролей
    нельзя, но можно проверить поведение: в режиме chat роль обязана оставить
    открытым то, что заказчик не ответил, а не выдумать это как факт.

    Args:
        payload: Разобранный ответ роли.
        output: Текст ответа (не используется, нужен для единой сигнатуры).
        expected_mode: Режим, заданный контрактом кейса.
        context: Контекст проверки (не используется).

    Returns:
        Список проблем (пустой, если поведение верное).
    """
    problems: list[str] = []
    if expected_mode.strip().lower() != "chat":
        # Проверка имеет смысл только в chat: в auto вопросов нет по правилу,
        # а в hybrid роль уточняет только развилки.
        return problems
    questions = payload.get("open_questions")
    if not isinstance(questions, list):
        problems.append("поле open_questions отсутствует или не массив")
        return problems
    if not questions:
        problems.append(
            "chat: роль не оставила ни одного открытого вопроса — "
            "незакрытое заказчиком выдумано как факт"
        )
    return problems


def _dialogue_context(context: dict[str, Any]) -> dict[str, Any]:
    """Собрать контекст диалога из параметров проверки.

    Args:
        context: Дополнительные параметры проверки.

    Returns:
        Словарь с ключами `customer_answer`, `customer_answers`,
        `expected_next`, `answered_question` и `scenario_exhausted`.
    """
    raw_answers = context.get("customer_answers")
    answers = [str(item) for item in raw_answers] if isinstance(raw_answers, list) else []
    answered = str(context.get("answered_question") or "")
    raw_questions = context.get("answered_questions")
    questions = [str(item) for item in raw_questions] if isinstance(raw_questions, list) else []
    if not questions and answered:
        questions = [answered]
    return {
        "customer_answer": str(context.get("customer_answer") or ""),
        "customer_answers": answers,
        "expected_next": str(context.get("expected_next") or ""),
        "answered_question": answered,
        "answered_questions": questions,
        "scenario_exhausted": bool(context.get("scenario_exhausted")),
    }


def _answer_text(payload: dict[str, Any]) -> str:
    """Собрать текст, в котором роль могла опереться на ответ заказчика.

    Args:
        payload: Разобранный ответ роли.

    Returns:
        Текст допущений и открытых вопросов роли.
    """
    parts: list[str] = []
    for key in ("assumptions", "open_questions"):
        value = payload.get(key)
        if isinstance(value, list):
            parts.extend(str(item) for item in value)
        elif isinstance(value, str):
            parts.append(value)
    return " ".join(parts)


def _significant_words(text: str) -> set[str]:
    """Выделить значимые слова текста.

    Args:
        text: Исходный текст.

    Returns:
        Множество слов длиной от трёх символов в нижнем регистре.
    """
    cleaned = "".join(char if char.isalnum() else " " for char in text.lower())
    return {word for word in cleaned.split() if len(word) >= 3}


#: Числа с единицами измерения: именно они чаще всего подменяются моделью.
#: Слово «месяцев» совпадает в ответе «12 месяцев» и в подделке «36 месяцев»,
#: поэтому сравниваются и числа, и единицы.
_NUMBER_WITH_UNIT_RE = re.compile(
    r"(\d[\d\s.,]*)\s*"
    r"(месяц\w*|год\w*|день\w*|недел\w*|час\w*|минут\w*|секунд\w*|"
    r"руб\w*|₽|доллар\w*|\$|евро|€|тыс\w*|млн\w*|процент\w*|%)",
    re.IGNORECASE,
)


def _quantities(text: str) -> set[str]:
    """Собрать числовые величины с единицами измерения.

    Args:
        text: Исходный текст.

    Returns:
        Множество нормализованных величин вроде «12 месяцев».
    """
    found: set[str] = set()
    for number, unit in _NUMBER_WITH_UNIT_RE.findall(text):
        digits = re.sub(r"[^\d]", "", number)
        if not digits:
            continue
        found.add(f"{digits} {unit.lower().rstrip('.')}")
    return found


def check_dialogue_uses_customer_answer(
    payload: dict[str, Any],
    output: str,
    expected_mode: str = "",
    context: dict[str, Any] | None = None,
) -> list[str]:
    """Проверить, что ответ второго хода опирается на ответ заказчика.

    Зачем. Во втором ходе у роли появляется факт, которого не было во входе:
    ответ заказчика. Проверка ловит подмену этого факта — модель вправе
    интерпретировать ответ, но не вправе выдумать другое число или другой
    срок.

    Проверка двухчастная:
    - величины (число + единица) из ответа заказчика не должны подменяться
      на другие: «12 месяцев» и «36 месяцев» — разные факты, хотя слово
      «месяцев» совпадает;
    - в тексте роли должно быть хотя бы одно значимое слово ответа заказчика,
      иначе ответ заказчика просто проигнорирован.

    Args:
        payload: Разобранный ответ роли.
        output: Текст ответа (не используется, нужен для единой сигнатуры).
        expected_mode: Режим, заданный контрактом кейса.
        context: Контекст диалога (`customer_answer`).

    Returns:
        Список проблем (пустой, если ответ опирается на ответ заказчика).
    """
    dialogue = _dialogue_context(context or {})
    customer_answer = dialogue["customer_answer"]
    if not customer_answer:
        return []

    role_text = _answer_text(payload)
    if not role_text.strip():
        return [
            "второй ход: роль не зафиксировала ответ заказчика ни в допущениях, "
            "ни в открытых вопросах"
        ]

    expected_quantities = _quantities(customer_answer)
    actual_quantities = _quantities(role_text)
    if expected_quantities:
        replaced = sorted(expected_quantities - actual_quantities)
        if replaced:
            return [
                "второй ход: величина из ответа заказчика подменена — ожидалось "
                f"{', '.join(sorted(expected_quantities))}, в ответе роли "
                f"{', '.join(sorted(actual_quantities)) or 'ни одной'}"
            ]
        return []

    answer_words = _significant_words(customer_answer)
    if not answer_words:
        return []

    used = answer_words & _significant_words(role_text)
    if not used:
        return [
            "второй ход: ответ заказчика не использован — роль продолжила "
            f"без него (ожидалось: {customer_answer!r})"
        ]
    return []


def check_dialogue_closes_answered_question(
    payload: dict[str, Any],
    output: str,
    expected_mode: str = "",
    context: dict[str, Any] | None = None,
) -> list[str]:
    """Проверить, что отвеченный вопрос не остался открытым.

    Зачем. Второй ход бессмыслен, если вопрос, на который заказчик ответил,
    снова висит в `open_questions`: диалог топчется на месте, а следующий
    гейт снова спросит то же самое.

    Проверяются все отвеченные пары (`answered_questions`), а не только
    последняя: иначе вопрос, закрытый на первом ходе, мог вернуться в
    `open_questions` незамеченным.

    Args:
        payload: Разобранный ответ роли.
        output: Текст ответа (не используется, нужен для единой сигнатуры).
        expected_mode: Режим, заданный контрактом кейса.
        context: Контекст диалога (`answered_questions`, устаревшее —
            `answered_question`).

    Returns:
        Список проблем (пустой, если вопрос закрыт).
    """
    dialogue = _dialogue_context(context or {})
    answered_questions = dialogue["answered_questions"]
    if not answered_questions:
        return []

    open_questions = payload.get("open_questions")
    if open_questions is None:
        return []
    if not isinstance(open_questions, list):
        return ["поле open_questions — не массив"]

    # Проверяются ВСЕ отвеченные пары, а не только последняя: дефект волны C —
    # роль оставляла вопрос, на который заказчик ответил раньше, и проверка
    # последней пары его не видела.
    for answered in answered_questions:
        asked = _significant_words(answered)
        if not asked:
            continue
        for item in open_questions:
            text = str(item)
            if asked & _significant_words(text):
                return [
                    "второй ход: вопрос, на который заказчик ответил, остался "
                    f"открытым: {text!r}"
                ]
    return []


def check_dialogue_stops_when_answered(
    payload: dict[str, Any],
    output: str,
    expected_mode: str = "",
    context: dict[str, Any] | None = None,
) -> list[str]:
    """Проверить критерий остановки диалога.

    Зачем. Правило прогона: «ответ перестал менять следующий шаг — прекращаем
    спрашивать и фиксируем допущение». После последней пары «вопрос → ответ»
    диалог обязан закончиться. Если роль продолжает задавать вопросы, диалог
    не остановился — это регрессия режима, а не особенность модели.

    Args:
        payload: Разобранный ответ роли.
        output: Текст ответа (не используется, нужен для единой сигнатуры).
        expected_mode: Режим, заданный контрактом кейса.
        context: Контекст диалога (`scenario_exhausted`).

    Returns:
        Список проблем (пустой, если диалог остановлен).
    """
    dialogue = _dialogue_context(context or {})
    if not dialogue["scenario_exhausted"]:
        return []

    questions = payload.get("questions")
    if questions is None:
        return []
    if not isinstance(questions, list):
        return ["поле questions — не массив"]
    if questions:
        return [
            "диалог не остановлен: после последнего ответа заказчика роль "
            f"продолжает задавать {len(questions)} вопрос(ов)"
        ]
    return []


def check_dialogue_covers_all_turns(
    payload: dict[str, Any],
    output: str,
    expected_mode: str = "",
    context: dict[str, Any] | None = None,
) -> list[str]:
    """Проверить, что в ответе отражён каждый ответ заказчика из сценария.

    Зачем. Сценарий из трёх пар закрывает пробел «третий ход с новой темой»,
    но сама по себе третья пара ничего не доказывает: модель может оборвать
    диалог после второй и всё равно отдать валидный JSON. Признак того, что
    третий ход состоялся, — ответ заказчика на него попал в допущения роли.
    Проверка обобщает `dialogue_uses_customer_answer` на все пары сценария.

    Сравниваются величины, а не слова: ответ «12 месяцев» обязан дать
    величину «12 месяцев», ответ «B2C» — значимое слово. Слова маркера
    «ответ заказчика» из сравнения исключены: они есть в каждом допущении
    по построению и превратили бы проверку в тавтологию.

    Args:
        payload: Разобранный ответ роли.
        output: Текст ответа (не используется, нужен для единой сигнатуры).
        expected_mode: Режим, заданный контрактом кейса.
        context: Контекст диалога (`customer_answers`).

    Returns:
        Список проблем (пустой, если отражены все ответы).
    """
    dialogue = _dialogue_context(context or {})
    answers = dialogue["customer_answers"]
    if not answers:
        return []

    role_text = _answer_text(payload)
    role_quantities = _quantities(role_text)
    role_words = _significant_words(role_text)

    problems: list[str] = []
    for turn_number, raw_answer in enumerate(answers, start=1):
        answer = raw_answer.replace(CUSTOMER_ANSWER_MARKER, " ").strip()
        expected_quantities = _quantities(answer)
        if expected_quantities:
            missing = sorted(expected_quantities - role_quantities)
            if missing:
                problems.append(
                    f"диалог: ответ заказчика на ход {turn_number} не отражён — "
                    f"нет величины {', '.join(missing)}"
                )
            continue
        expected_words = _significant_words(answer)
        if expected_words and not expected_words & role_words:
            problems.append(
                f"диалог: ответ заказчика на ход {turn_number} не отражён в "
                f"допущениях роли ({raw_answer})"
            )
    return problems


def check_dialogue_fork_branch(
    payload: dict[str, Any],
    output: str,
    expected_mode: str = "",
    context: dict[str, Any] | None = None,
) -> list[str]:
    """Проверить, что ответ на развилку изменил следующий этап.

    Зачем. В `hybrid` вопрос задаётся только на развилке, и ценность ответа —
    в следствии: ветка меняет следующий шаг. Если после ответа «хранение
    только в России» роль идёт тем же путём, что и после «трансгранично»,
    развилка декоративна, а режим `hybrid` не соблюдён.

    Сравнивается поле `next` с ожиданием сценария (`expect_next`), а не текст
    вопроса: формулировку модель вправе менять, этап — нет.

    Args:
        payload: Разобранный ответ роли.
        output: Текст ответа (не используется, нужен для единой сигнатуры).
        expected_mode: Режим, заданный контрактом кейса.
        context: Контекст диалога (`expected_next`).

    Returns:
        Список проблем (пустой, если развилка изменила этап).
    """
    dialogue = _dialogue_context(context or {})
    expected = dialogue["expected_next"]
    if not expected:
        return []

    actual = str(payload.get("next") or "").strip()
    if actual == expected:
        return []
    return [
        "развилка не изменила следующий шаг: ожидался этап "
        f"{expected!r}, в ответе {actual or '<пусто>'!r}"
    ]


def check_gate_contract(
    payload: dict[str, Any],
    output: str,
    expected_mode: str = "",
    context: dict[str, Any] | None = None,
) -> list[str]:
    """Проверить ответ гейта по чеклисту (`checks[]`).

    Зачем структурная проверка вместо лексики. Гейт-печать нельзя поймать
    поиском слов: ответ «passed» с четырьмя незакрытыми пунктами выглядит
    валидным. Контракт проверяет полноту `checks`, согласованность
    `status`/`missing`/`return_to` и допустимость `na` — по тем же правилам,
    что `scripts/check_gate.py`.

    Args:
        payload: Разобранный ответ гейта.
        output: Текст ответа (не используется, нужен для единой сигнатуры).
        expected_mode: Режим кейса (для гейта не применяется).
        context: Контекст проверки; `gate` — ожидаемое имя гейта.

    Returns:
        Список проблем (пустой, если контракт выполнен).
    """
    expected_gate = str((context or {}).get("gate") or "")
    return validate_gate_payload(payload, expected_gate)


def check_role_schema(
    payload: dict[str, Any],
    output: str,
    expected_mode: str = "",
    context: dict[str, Any] | None = None,
) -> list[str]:
    """Проверить ответ роли по машинно-читаемой схеме (P4).

    Зачем. `expected_fields` проверял наличие имени поля подстрокой: ответ с
    `open_questions` как массивом объектов проходил, потому что имя в тексте
    есть. Схема `prompts/schemas.yaml` проверяет структуру: обязательные поля,
    типы и однородность массивов.

    Args:
        payload: Разобранный ответ роли.
        output: Текст ответа (не используется, нужен для единой сигнатуры).
        expected_mode: Режим кейса (для схемы не применяется).
        context: Контекст проверки; `role` — значение `role` из контракта.

    Returns:
        Список проблем (пустой, если ответ соответствует схеме).
    """
    role = str((context or {}).get("role") or "")
    if not role:
        # Без роли проверка молчит: старые потребители не получают ложных проблем.
        return []
    return validate_role_payload(role, payload)


#: Имена структурных проверок, которые понимает eval-обвязка.
SEMANTIC_CHECKS: dict[str, SemanticChecker] = {
    "needs_separated": check_needs_separated,
    "mode_respected": check_mode_respected,
    "questions_three_blocks": check_questions_three_blocks,
    "chat_keeps_open_questions": check_chat_keeps_open_questions,
    "dialogue_uses_customer_answer": check_dialogue_uses_customer_answer,
    "dialogue_closes_answered_question": check_dialogue_closes_answered_question,
    "dialogue_stops_when_answered": check_dialogue_stops_when_answered,
    "dialogue_covers_all_turns": check_dialogue_covers_all_turns,
    "dialogue_fork_branch": check_dialogue_fork_branch,
    "gate_contract": check_gate_contract,
    "role_schema": check_role_schema,
}


def run_semantic_check(
    name: str,
    output: str,
    expected_mode: str = "",
    **context: Any,
) -> list[str]:
    """Выполнить структурную проверку по имени.

    Args:
        name: Имя проверки (`semantic_check` в контракте кейса).
        output: Текст ответа модели.
        expected_mode: Режим, заданный контрактом кейса.
        **context: Контекст проверки. Для проверок диалога это
            `customer_answer`, `answered_question` и `scenario_exhausted`.

    Returns:
        Список проблем (пустой, если проверка выполнена или неизвестна).
    """
    checker = SEMANTIC_CHECKS.get(name)
    if checker is None:
        return []
    payload = load_payload(output)
    if payload is None:
        return [f"ответ не разобран как JSON (проверка {name})"]
    return checker(payload, output, expected_mode, context)
