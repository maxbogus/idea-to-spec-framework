"""Контрактные проверки eval-набора idea-to-spec-ai.

Разделены на две группы:
1. `mock` — детерминированные проверки контракта, зелёные всегда.
2. `slow` — реальный прогон микро-LLM; провалы фиксируются как
   xfail(strict=True) по конвенции hh-matcher, а не маскируются.

Известные провалы модели перечислены в KNOWN_MODEL_FAILURES. Если модель
начнёт проходить кейс, xfail(strict=True) превратится в XPASS-ошибку — это
сигнал обновить список, а не тихо убрать проверку.

Кейсы вне KNOWN_MODEL_FAILURES обязаны проходить: их провал — настоящая
регрессия контракта промпта, а не свойство слабой модели.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from idea_to_spec.paths import EVAL_CASES_FILE, EVAL_REPORT_FILE
from idea_to_spec.semantic_check import run_semantic_check

#: Допустимые роли и виды кейсов.
ALLOWED_ROLES = {
    "orchestrator",
    "product-manager",
    "business-analyst",
    "system-analyst",
    "architect",
    "designer",
    "project-manager",
    "fact-check",
    "critic",
    "gate-reviewer",
}
ALLOWED_KINDS = {"role", "discipline", "negative", "gate"}
ALLOWED_MODES = {"auto", "chat", "hybrid"}


def _load_cases() -> list[dict[str, Any]]:
    """Загрузить кейсы eval-набора.

    Returns:
        Список контрактов кейсов (JSON `contract` распакован).
    """
    cases: list[dict[str, Any]] = []
    for line in EVAL_CASES_FILE.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        cases.append(json.loads(item["vars"]["contract"]))
    return cases


CASES = _load_cases()
CASE_IDS = [str(case["id"]) for case in CASES]

#: Кейсы, которые микро-LLM не проходит. Заполняется после `make eval`.
#:
#: Провал фиксируется, а не скрывается: внезапный XPASS означает, что список
#: надо пересмотреть. Кейс вне списка, который провалился, — регрессия.
#:
#: Состав обновлён после прогона 2026-11-23 на qwen3:8b (23 кейса): 23/23.
#: Список пуст — ни одного известного провала не осталось. XPASS (strict)
#: на этом механизме и означает сигнал «обнови список»: он сработал на
#: DISC-01, который закрыла структурная проверка.
#:
#: Важно: список относится к основной модели (qwen3:8b). На других моделях
#: набор провалов другой — см. docs/evaluation/README.md.
#: Список пуст: на qwen3:8b проходят все 23 кейса (2026-11-23).
#:
#: История списка:
#: - NEG-01 убран: пустая идея отсекается кодом до вызова модели
#:   (scripts/idea_to_spec/input_gate.py) — ответ детерминирован.
#: - DISC-01 убран: контракт требовал буквального слова «потребность»,
#:   которое ни один промпт не предписывает; все шесть моделей с валидным
#:   JSON описывали потребность правильно, но слово не употребляли. Проверка
#:   заменена структурной (semantic_check) — и кейс проходит.
#: - FC-01, ORCH-02, NEG-02 убраны: на qwen3:8b проходят; прежде падали
#:   на qwen2.5:7b — расхождение было в дисциплине формата, не в кейсе.
#: - SA-03 добавлен 2026-11-24: на qwen3:8b модель держит первые поля
#:   формата (use_cases, functional_requirements, nonfunctional_requirements),
#:   но выбрасывает хвост (integrations, data, spec) и подставляет структуру
#:   {question, reason} вместо массива строк в open_questions. Плюс выдумывает
#:   числа, которых во входе нет: вход говорит «пороги NFR (uptime, RTO) не
#:   заданы», а ответ содержит uptime 99.9% и RTO 15 минут. Граница объёма
#:   ответа измерена (F021): 8B-модель теряет хвост формата на длинных
#:   ответах. Это свойство модели, а не ошибка ассерта — кейс оставлен
#:   проваленным, а не переписан под модель.
KNOWN_MODEL_FAILURES: set[str] = {
    # SA-03 проходил при num_ctx=4096 нестабильно и был в этом списке. После
    # пина num_ctx=16384 (2026-11-26, набор 41 кейс) кейс прошёл: модель видит
    # полный промпт роли, а не его усечённый хвост. Список обновлён по замеру,
    # а не «на всякий случай».
    # CRIT-02: 8B не выводит «пробел в покрытии» (BR без FR), когда остальные
    # требования заполнены. Измерено 2026-11-25 (P6): два прогона, 0/2; попытка
    # подсказать правило в промпте не помогла (1/2 -> 0/2, откатана по D013).
    # CRIT-01 (противоречие, слабый AC, додуманное) модель выполняет — он вне списка.
    "CRIT-02-detects-uncovered-business-requirement",
    # ORCH-10 и ORCH-13 сняты 2026-11-27 по замеру, а не «на всякий случай»
    # (P5, F039). Полный прогон 44 кейсов (concurrency 4) дал ORCH 13/13, а
    # целевой прогон этих двух кейсов на concurrency 1 — 2/2 за 53 с. До этого
    # (2026-11-26) было 4 провала из 5: модель повторяла уже отвеченный вопрос
    # про контур, и единственный проход списывали на недетерминизм батчинга
    # Ollama. Новый замер показал, что проход воспроизводится на обоих уровнях
    # параллелизма: держать кейсы в списке провалов нельзя — xfail(strict=True)
    # требовал бы провала там, где модель справляется.
    # SA-04: ответы заказчика модель использует в `data` и `spec` («1С», «12
    # месяцев»), но не переносит их в требования. Поле `assumptions` добавлено в
    # схему роли (2026-11-26), однако кейс всё равно провален на 41 кейсе: ответы
    # не попадают в FR/assumptions. Измерено: 1 прогон из 1 на новой схеме.
    "SA-04-chat-dialogue-role",
}

#: Кейсы, не входящие в KNOWN_MODEL_FAILURES: их провал — настоящая регрессия.
KNOWN_MODEL_PASSES: set[str] = set(CASE_IDS) - KNOWN_MODEL_FAILURES


def _dialogue_context(case: dict[str, Any]) -> dict[str, Any]:
    """Собрать контекст диалога для структурных проверок.

    Проверки второго хода (`dialogue_*`) без контекста молчат: они не знают,
    что ответил заказчик и какой вопрос закрыт. Контекст собирается из
    сценария кейса — последняя пара «вопрос → ответ» считается закрытой,
    а сам сценарий — исчерпанным, если пары кончились.

    Args:
        case: Контракт кейса.

    Returns:
        Словарь контекста (пустой, если кейс не многоходовый).
    """
    scenario = case.get("dialogue")
    if not isinstance(scenario, dict):
        return {}
    turns = scenario.get("turns")
    if not isinstance(turns, list) or not turns:
        return {}

    last = turns[-1]
    if not isinstance(last, dict):
        return {}
    answer = str(last.get("answer") or "")
    question = str(last.get("question_contains") or "")
    fork = scenario.get("fork")
    fork_answer = str(fork.get("answer") or "") if isinstance(fork, dict) else ""
    expected_next = str(fork.get("expect_next") or "") if isinstance(fork, dict) else ""
    answers = [str(turn.get("answer") or "") for turn in turns]
    if fork_answer:
        answers.append(fork_answer)
    return {
        "customer_answer": answer,
        # Все ответы сценария: `dialogue_covers_all_turns` проверяет, что
        # каждый из них отражён в допущениях роли (третий ход не оборван),
        # а развилка — что ветка сменила следующий этап.
        "customer_answers": answers,
        "expected_next": expected_next,
        "answered_question": question,
        # Все отвеченные вопросы сценария: проверка закрытия смотрит на каждый
        # ход, а не только на последний.
        "answered_questions": [
            str(turn.get("question_contains") or "") for turn in turns
        ],
        # Две пары и больше (включая развилку): после последней пары новых
        # вопросов быть не должно — это и есть критерий остановки диалога.
        "scenario_exhausted": len(answers) >= 2,
    }


def _contract_problems(case: dict[str, Any], output: str) -> list[str]:
    """Проверить ответ по контракту кейса (must_contain / not_contain / поля).

    Args:
        case: Контракт кейса.
        output: Текст ответа.

    Returns:
        Список проблем (пустой, если контракт выполнен).
    """
    problems: list[str] = []
    lower = output.lower()
    for needle in case.get("must_contain", []):
        # Регистронезависимо: маркеры естественного языка («потребность»)
        # могут стоять в начале предложения с заглавной буквы. ID (BR-1, UC-1)
        # при этом всё равно совпадают.
        if str(needle).lower() not in lower:
            problems.append(f"must_contain отсутствует: {needle!r}")
    for needle in case.get("must_not_contain", []):
        if str(needle).lower() in lower:
            problems.append(f"must_not_contain присутствует: {needle!r}")
    for field in case.get("expected_fields", []):
        if f'"{field}"' not in output and f"{field}:" not in output:
            problems.append(f"нет обязательного поля: {field}")
    # Структурная проверка: семантика вместо лексики (см.
    # scripts/idea_to_spec/semantic_check.py).
    mode = str(case.get("mode") or "")
    raw_checks = case.get("semantic_checks")
    checks = list(raw_checks) if isinstance(raw_checks, list) else []
    if not checks:
        # Старый формат: одна проверка в `semantic_check`.
        single = case.get("semantic_check")
        checks = [single] if single else []
    # Схема ответа роли (P4) — та же проверка, что в реальном прогоне.
    # Отрицательные кейсы проверяют поведение на плохом входе, а не формат:
    # NEG-01 намеренно возвращает текст, а не JSON.
    if case.get("role") and case.get("kind") != "negative" and "role_schema" not in checks:
        checks.append("role_schema")
    dialogue_context = _dialogue_context(case)
    for semantic in checks:
        problems.extend(
            run_semantic_check(
                str(semantic),
                output,
                mode,
                role=str(case.get("role") or ""),
                gate=str(case.get("gate") or ""),
                **dialogue_context,
            )
        )
    # Ответ должен быть на русском: кириллица обязательна (см. JS-проверку).
    cyrillic = sum(1 for ch in output if "а" <= ch.lower() <= "я" or ch.lower() == "ё")
    if cyrillic < 20:
        problems.append("ответ не на русском языке (нет кириллицы)")
    return problems


def _mode_problems(case: dict[str, Any], output: str) -> list[str]:
    """Проверить дисциплину режима по контракту кейса.

    Args:
        case: Контракт кейса.
        output: Текст ответа.

    Returns:
        Список проблем режима (пустой, если режим соблюдён).
    """
    check = case.get("mode_check")
    lower = output.lower()
    if check == "auto_no_questions":
        if "зачем я это спрашиваю" in lower:
            return ["auto: задан вопрос, хотя auto = 0 вопросов"]
        return []
    if check == "chat_three_blocks":
        problems = [
            f"chat: нет блока {block!r}"
            for block in ("вопрос", "зачем я это спрашиваю", "термины")
            if block not in lower
        ]
        if output.count("Вопрос") > 3:
            problems.append("chat: больше 3 вопросов за гейт")
        return problems
    if check == "hybrid_forks_only" and "вопрос" in lower:
        forks = ("контур", "пользовател", "платеж", "интеграц")
        if not any(fork in lower for fork in forks):
            return ["hybrid: вопрос не про критичную развилку"]
    return []


def test_eval_set_has_expected_size() -> None:
    """Набор содержит 44 кейса: роли, гейты, дисциплина и диалоги."""
    assert len(CASES) == 44, f"Ожидалось 44 кейса, получено {len(CASES)}"
    by_scenario: dict[str, int] = {}
    for case in CASES:
        scenario = str(case["scenario"])
        by_scenario[scenario] = by_scenario.get(scenario, 0) + 1
    assert by_scenario == {
        "ORCH": 13,
        "PM": 3,
        "BA": 5,
        "SA": 4,
        "DISC": 4,
        "NEG": 2,
        "ARCH": 2,
        "DESIGN": 2,
        "PROJ": 2,
        "FC": 2,
        "CRIT": 2,
        "GATE": 3,
    }


def test_eval_set_covers_dialogue_modes() -> None:
    """Диалоговые режимы покрыты: chat >= 4 кейсов, hybrid >= 3.

    Зачем. 23/23 на наборе, где режимы `chat` и `hybrid` занимали 2 кейса
    из 23 (8.7%), — это подгонка под ассерты, а не устойчивость промптов.
    Порог зафиксирован, чтобы следующее сокращение набора не убрало покрытие
    молча.
    """
    by_mode: dict[str, int] = {}
    for case in CASES:
        mode = str(case["mode"])
        by_mode[mode] = by_mode.get(mode, 0) + 1
    assert by_mode.get("chat", 0) >= 4, (
        f"chat покрыт {by_mode.get('chat', 0)} кейсами, нужно минимум 4"
    )
    assert by_mode.get("hybrid", 0) >= 3, (
        f"hybrid покрыт {by_mode.get('hybrid', 0)} кейсами, нужно минимум 3"
    )


def test_case_ids_are_unique() -> None:
    """Идентификаторы кейсов уникальны."""
    assert len(CASE_IDS) == len(set(CASE_IDS))


def test_known_lists_cover_all_cases() -> None:
    """Списки известных провалов и проходов покрывают весь набор без пересечений."""
    assert not (KNOWN_MODEL_FAILURES & KNOWN_MODEL_PASSES), "Кейс попал в оба списка"
    covered = KNOWN_MODEL_FAILURES | KNOWN_MODEL_PASSES
    assert set(CASE_IDS) <= covered, f"Кейсы не покрыты: {sorted(set(CASE_IDS) - covered)}"
    assert covered <= set(CASE_IDS), f"Несуществующие кейсы: {sorted(covered - set(CASE_IDS))}"


def test_case_contract_is_complete() -> None:
    """Каждый кейс содержит полный контракт и допустимые значения."""
    for case in CASES:
        for field in (
            "id",
            "role",
            "scenario",
            "kind",
            "title",
            "mode",
            "input",
            "expected_fields",
            "must_contain",
            "must_not_contain",
            "notes",
        ):
            assert field in case, f"В кейсе {case.get('id')} нет поля {field}"
        assert case["role"] in ALLOWED_ROLES, f"{case['id']}: неизвестная роль {case['role']}"
        assert case["kind"] in ALLOWED_KINDS, f"{case['id']}: неизвестный вид {case['kind']}"
        assert case["mode"] in ALLOWED_MODES, f"{case['id']}: неизвестный режим {case['mode']}"


def test_forbidden_phrases_absent_in_contracts() -> None:
    """Запрещённые формулировки не попадают в must_contain; записи не пустые."""
    forbidden = {"вернём", "верну", "возврат одобрен", "одобрим кредит", "выдадим кредит"}
    for case in CASES:
        for needle in case["must_contain"]:
            assert needle.strip(), f"{case['id']}: пустой must_contain"
            assert needle.lower() not in forbidden, (
                f"{case['id']}: в must_contain нельзя требовать запрещённую формулировку {needle!r}"
            )


@pytest.mark.mock
def test_mock_provider_returns_ideal_answers() -> None:
    """Mock-провайдер возвращает ответ, проходящий контракт каждого кейса."""
    from mock_provider import build_answer

    for case in CASES:
        output = build_answer(dict(case))
        problems = _contract_problems(case, output) + _mode_problems(case, output)
        assert not problems, f"{case['id']}: mock-ответ не выполнил контракт: {problems}"


@pytest.mark.slow
def test_known_failures_match_report() -> None:
    """Список известных провалов соответствует фактическому отчёту.

    Список провалов — не «состояние на дату», а утверждение о том, какие
    кейсы модель заведомо не выполняет. Если отчёт разошёлся со списком —
    это ошибка, которую надо увидеть сразу.
    """
    if not EVAL_REPORT_FILE.exists():
        pytest.skip("Нет отчёта реального прогона — выполните `make eval`")

    from summarize_eval import summarize

    summary = summarize(EVAL_REPORT_FILE)
    failed = set(summary["failed_cases"])
    assert failed == KNOWN_MODEL_FAILURES, (
        "Список известных провалов разошёлся с отчётом. "
        f"Провалы в отчёте, которых нет в списке: {sorted(failed - KNOWN_MODEL_FAILURES)}. "
        f"Кейсы в списке, которые прошли: {sorted(KNOWN_MODEL_FAILURES - failed)}"
    )


@pytest.mark.slow
@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
def test_real_model_meets_contract(case: dict[str, Any]) -> None:
    """Реальный микро-LLM проверяется по контракту кейса.

    Провал микро-LLM — ожидаемое состояние, зафиксированное как
    xfail(strict=True). Случайный XPASS означает, что список
    KNOWN_MODEL_FAILURES надо обновить.
    """
    if not EVAL_REPORT_FILE.exists():
        pytest.skip("Нет отчёта реального прогона — выполните `make eval`")

    payload = json.loads(EVAL_REPORT_FILE.read_text(encoding="utf-8"))
    results = payload.get("results", {}).get("results", [])
    matching = [item for item in results if item.get("vars", {}).get("id") == case["id"]]
    if not matching:
        pytest.skip(f"Кейс {case['id']} отсутствует в отчёте")

    result = matching[0]
    success = bool(result.get("success"))
    components = (result.get("gradingResult") or {}).get("componentResults") or []
    reason = str(components[0].get("reason", "")) if components else ""

    case_id = str(case["id"])
    if case_id in KNOWN_MODEL_FAILURES:
        if success:
            pytest.fail(
                f"XPASS (strict): {case_id} теперь проходит микро-LLM — "
                "обновите KNOWN_MODEL_FAILURES в tests/test_eval_contract.py"
            )
        pytest.xfail(f"Известный провал микро-LLM: {reason}")
    if not success:
        pytest.fail(
            f"РЕГРЕССИЯ: кейс {case_id} вне KNOWN_MODEL_FAILURES, но микро-LLM "
            f"не выполнил контракт: {reason}"
        )
    assert success, f"{case_id}: микро-LLM не выполнил контракт: {reason}"
