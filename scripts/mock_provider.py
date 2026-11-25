"""Детерминированный mock-провайдер для promptfoo (режим eval-mock).

Скрипт вызывается promptfoo как `exec:`-провайдер:

    exec:python3 ../scripts/mock_provider.py

promptfoo передаёт три аргумента:
    1. prompt  — отрендеренный текст запроса;
    2. options — JSON с конфигурацией провайдера;
    3. context — JSON с переменными тест-кейса (vars, metadata).

Скрипт определяет кейс по `context.vars.id` и печатает заранее зафиксированный
«идеальный» ответ, проходящий контракт кейса. Никаких сетевых вызовов и никакой
зависимости от модели — поэтому прогон воспроизводим и используется в CI.

Контракт ответа выведен из форматов ролей (`prompts/roles/*.md`,
`prompts/orchestrator.md`) и общего правила факт/гипотеза/прогноз
(`methods/fact-hypothesis-forecast.md`).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

#: Пакет `idea_to_spec` лежит рядом со скриптом. Путь добавляется до импорта
#: — иначе модуль не найдётся при запуске exec-провайдера из другого
#: каталога.
_SCRIPTS_DIR = str(Path(__file__).resolve().parent)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from idea_to_spec.multi_turn import run_turns, scenario_turns  # noqa: E402


def _load_context(raw: str) -> dict[str, Any]:
    """Разобрать JSON-аргумент context.

    Args:
        raw: Строка с JSON.

    Returns:
        Словарь (пустой, если разбор не удался).
    """
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _vars(context: dict[str, Any]) -> dict[str, Any]:
    """Извлечь переменные тест-кейса.

    Args:
        context: Разобранный context.

    Returns:
        Словарь переменных (пустой, если их нет).
    """
    vars_block = context.get("vars")
    if isinstance(vars_block, dict):
        return vars_block
    return {}


def _contract(vars_block: dict[str, Any]) -> dict[str, Any]:
    """Извлечь контракт кейса из переменной `contract`.

    Args:
        vars_block: Переменные тест-кейса.

    Returns:
        Словарь контракта (пустой, если контракт не передан).
    """
    raw = vars_block.get("contract")
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str) or not raw.strip():
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _json(payload: dict[str, Any]) -> str:
    """Сериализовать ответ в JSON.

    Args:
        payload: Поля ответа роли.

    Returns:
        JSON-строка в UTF-8.
    """
    return json.dumps(payload, ensure_ascii=False)


def _orchestrator(
    mode: str,
    stage: str,
    next_stage: str,
    questions: list[str],
    artifacts: list[str],
    assumptions: list[str],
) -> str:
    """Собрать ответ оркестратора в формате из `prompts/orchestrator.md`.

    Args:
        mode: Режим прогона.
        stage: Текущий этап.
        next_stage: Следующий этап.
        questions: Вопросы (пустой список в режиме auto).
        artifacts: Пути созданных артефактов.
        assumptions: Явные допущения.

    Returns:
        JSON-строка ответа.
    """
    return _json(
        {
            "mode": mode,
            "stage": stage,
            "completeness": {
                "passed": not questions,
                "missing": [] if not questions else ["данные"],
            },
            "questions": questions,
            "artifacts": artifacts,
            "assumptions": assumptions,
            "next": next_stage,
        }
    )


def _orchestrator_auto() -> str:
    """Идеальный ответ оркестратора в режиме auto."""
    return _orchestrator(
        mode="auto",
        stage="intake",
        next_stage="business",
        questions=[],
        artifacts=["output/auto-001/brief.md", "output/auto-001/open-questions.md"],
        assumptions=["контур не указан — допущение", "платежи не указаны — нет данных"],
    )


def _orchestrator_chat() -> str:
    """Идеальный ответ оркестратора в режиме chat (три блока вопроса)."""
    question = (
        "Вопрос: какие платежи поддерживаем — карта, СБП, наличные? "
        "Зачем я это спрашиваю: от этого зависят интеграции, комиссия и "
        "юридические требования. "
        "Термины: эквайринг — приём платежей по карте; СБП — система быстрых платежей."
    )
    return _orchestrator(
        mode="chat",
        stage="business",
        next_stage="ba_gate",
        questions=[question],
        artifacts=["output/chat-001/brief.md"],
        assumptions=["контур B2C — допущение"],
    )


def _orchestrator_hybrid() -> str:
    """Идеальный ответ оркестратора в режиме hybrid (вопрос про развилку)."""
    question = (
        "Вопрос: какие внешние интеграции нужны — платежи, логистика, склад? "
        "Зачем я это спрашиваю: развилка по интеграциям меняет архитектуру и сроки. "
        "Термины: интеграция — подключение внешней системы по API."
    )
    return _orchestrator(
        mode="hybrid",
        stage="business",
        next_stage="ba_gate",
        questions=[question],
        artifacts=["output/hybrid-001/brief.md"],
        assumptions=["география — Россия — допущение"],
    )


def _pm() -> str:
    """Идеальный ответ Product Manager (метрика + варианты)."""
    return _json(
        {
            "problem_statement": (
                "Пользователю нужно быстро создавать и синхронизировать заметки "
                "между устройствами; текущий способ теряет мысли."
            ),
            "success_metric": {
                "name": "Доля активных пользователей (WAU/MAU)",
                "target": "+5 п.п. к базе",
                "baseline": "текущая база — требует проверки (допущение)",
            },
            "opportunity_solution_tree": {
                "desired_outcome": "пользователь не теряет мысли",
                "opportunities": ["быстрое создание заметки", "синхронизация устройств"],
                "solutions": ["мобильное приложение с офлайн-черновиком"],
                "experiments": ["замер времени создания заметки на 5 пользователях"],
            },
            "prioritization": {
                "framework": "RICE",
                "hypotheses": [
                    {
                        "id": "H-1",
                        "reach": 1000,
                        "impact": 3,
                        "confidence": 0.8,
                        "effort": 5,
                        "score": 480,
                    }
                ],
            },
            "pmf_signals": {
                "sean_ellis_test": "не измерено",
                "retention_curve": "не построена",
            },
            "gtm_hypothesis": {
                "channels": ["личные рекомендации"],
                "cac_target": "не измерено — допущение",
                "ltv_target": "не измерено — допущение",
                "payback_period_months": 12,
            },
            "constraints": ["бюджет не указан — допущение", "сроки не указаны — допущение"],
            "risk_appetite": "medium",
            "out_of_scope": ["офлайн-редактирование", "совместная работа"],
            "assumptions": [
                "база метрики не указана — допущение",
                "бюджет и сроки не указаны — допущение",
            ],
            "open_questions": ["какой контур: B2C или B2B?", "какая модель монетизации?"],
            "variants": [
                {
                    "name": "Оставить как есть",
                    "objections": [
                        "Возражение: не решает запрос роста активных пользователей",
                        "Возражение: не проверяет реальный спрос",
                    ],
                },
                {
                    "name": "Закрыть направление",
                    "objections": [
                        "Возражение: спрос не проверен, отказ может быть преждевременным",
                        "Возражение: аудитория может быть большой",
                    ],
                },
                {
                    "name": "Основной — приложение заметок",
                    "objections": [
                        "Возражение: конкуренция высокая, дифференциация не показана",
                        "Возражение: модель монетизации не определена",
                    ],
                },
            ],
        }
    )


def _ba(assumptions: list[str] | None = None) -> str:
    """Идеальный ответ Business Analyst (персоны, JTBD, BR, AC).

    Args:
        assumptions: Явные допущения; по умолчанию — контур и аудитория.

    Returns:
        JSON-строка ответа.
    """
    return _json(
        {
            "personas": [{"id": "P-1", "name": "Студент", "contour": "B2C"}],
            "contour": "B2C",
            "jobs_to_be_done": [
                {
                    "id": "J-1",
                    "persona": "P-1",
                    "when": "на паре или в дороге",
                    "want": "быстро записать мысль",
                    "so_that": "не потерять идею",
                }
            ],
            "as_is": "заметки в мессенджере (допущение)",
            "to_be": "приложение с синхронизацией между устройствами",
            "business_requirements": [
                {
                    "id": "BR-1",
                    "text": (
                        "Пользователь создаёт заметку за ≤ 30 секунд. Потребность — "
                        "не терять мысли; блокчейн — гипотеза о решении (допущение)."
                    ),
                    "source": "допущение",
                    "status": "draft",
                    "owner": "владелец продукта",
                }
            ],
            "mvp_scope": ["BR-1"],
            "full_scope": ["BR-1"],
            "scope_prioritization": {
                "must_have": ["BR-1"],
                "should_have": [],
                "could_have": [],
                "wont_have": [],
            },
            "competitor_analysis": [
                {
                    "name": "Существующее приложение для заметок",
                    "strengths": ["уже установлено у пользователей"],
                    "gaps": ["нет синхронизации между устройствами"],
                    "feature_parity": "med",
                    "source": "допущение",
                }
            ],
            "privacy_impact": {
                "personal_data": "да",
                "regulatory_triggers": ["GDPR"],
                "dpia_required": "нет",
                "dpia_reason": "текст заметок пользователя — риск ограничен",
            },
            "acceptance_criteria": [{"id": "AC-1", "text": "Заметка создаётся за ≤ 30 секунд"}],
            "assumptions": assumptions
            or ["контур B2C — допущение", "целевая аудитория — студенты — допущение"],
            "open_questions": ["какая модель монетизации?"],
        }
    )


def _sa() -> str:
    """Идеальный ответ System Analyst (use cases, FR/NFR, интеграции)."""
    return _json(
        {
            "use_cases": [
                {
                    "id": "UC-1",
                    "actor": "P-1",
                    "goal": "создать заметку",
                    "preconditions": ["пользователь вошёл в систему"],
                    "main_flow": ["открыть приложение", "ввести текст", "сохранить"],
                    "alternative_flows": ["сохранение не удалось — показать ошибку"],
                    "postconditions": ["заметка сохранена"],
                }
            ],
            "functional_requirements": [
                {
                    "id": "FR-1",
                    "text": "Система сохраняет заметку за ≤ 30 секунд",
                    "source": "BR-1",
                    "priority": "P0",
                    "status": "draft",
                    "owner": "владелец продукта",
                    "risk": "low",
                    "version": 1,
                    "compliance": ["GDPR Art.6"],
                    "acceptance_criteria": [
                        {
                            "id": "AC-1",
                            "format": "BDD",
                            "given": "пользователь вошёл в систему",
                            "when": "он вводит текст заметки и сохраняет",
                            "then": "заметка сохранена и видна в списке",
                        }
                    ],
                    "threat_model": {
                        "stride": ["spoofing"],
                        "mitigation": "аутентификация по токену",
                    },
                }
            ],
            "nonfunctional_requirements": [
                {
                    "id": "NFR-1",
                    "category": "performance",
                    "text": "Синхронизация между устройствами ≤ 2 секунд",
                    "standard": "ISO 25010",
                },
                {
                    "id": "NFR-2",
                    "category": "accessibility",
                    "text": "Контраст текста не ниже 4.5:1, работа с клавиатуры",
                    "standard": "WCAG 2.1 AA",
                },
            ],
            "integrations": ["сервис синхронизации"],
            "data": ["текст заметок — персональные данные; срок хранения — до удаления"],
            "spec": "черновик спецификации: цели, UC-1, FR-1, NFR-1",
            "open_questions": ["какой контур: B2C или B2B?"],
        }
    )


def _architect() -> str:
    """Идеальный ответ Architect (компоненты, интеграции, ADR, контроли)."""
    return _json(
        {
            "components": [
                {
                    "name": "Notes API",
                    "responsibility": "создание и чтение заметок",
                    "regional_constraints": [],
                },
                {
                    "name": "Sync Service",
                    "responsibility": "синхронизация между устройствами",
                    "regional_constraints": [],
                },
            ],
            "integrations": [
                {
                    "from": "Notes API",
                    "to": "Sync Service",
                    "contract": "REST/JSON",
                    "security": "TLS, аутентификация по токену",
                },
            ],
            "adr": [
                {
                    "id": "ADR-1",
                    "title": "Синхронизация через очередь событий",
                    "status": "Accepted",
                    "decision": "синхронизация через очередь событий",
                    "context": "нужна доставка ≤ 2 с при офлайн-устройствах",
                    "alternatives_considered": [
                        "Очередь событий (+переживает офлайн, −eventual consistency)",
                        "Синхронизация по опросу (+проще, −не масштабируется на офлайн)",
                    ],
                    "consequences": "возникает eventual consistency",
                }
            ],
            "observability": ["лог запросов API", "метрика sync_latency"],
            "risk_controls": [
                {
                    "risk": "R-1",
                    "control": "ретраи, таймауты и идемпотентность",
                    "rto_rpo": "RTO: 1h, RPO: 15m",
                },
            ],
            "open_questions": ["какой контур: B2C или B2B?"],
        }
    )


def _designer() -> str:
    """Идеальный ответ Designer (поток, экраны, трения, доступность)."""
    return _json(
        {
            "user_flows": [
                {
                    "actor": "P-1",
                    "steps": ["открыть приложение", "создать заметку", "сохранить"],
                    "mobile_first": True,
                }
            ],
            "screens": [
                {
                    "name": "Список заметок",
                    "purpose": "просмотр и создание заметок",
                    "elements": ["кнопка создать", "список заметок"],
                    "breakpoints": ["mobile", "tablet", "desktop"],
                    "design_tokens": {
                        "color": "основной акцент, контраст 4.5:1",
                        "typography": "системный шрифт, базовый размер 16px",
                        "spacing": "шаг 8px",
                    },
                }
            ],
            "heuristic_evaluation": [
                {
                    "heuristic": "Nielsen #1 (visibility of system status)",
                    "finding": "после сохранения нет подтверждения",
                    "severity": "med",
                }
            ],
            "friction_points": ["долгий ввод текста на телефоне"],
            "accessibility": {
                "wcag_level": "AA",
                "contrast_ratio": "4.5:1",
                "keyboard_navigation": True,
                "screen_reader_tested": False,
                "regional_standards": ["EN 301 549 (EU)", "ГОСТ Р 52872 (RU)"],
            },
            "localization": {
                "supported_locales": ["ru", "en"],
                "rtl": False,
            },
        }
    )


def _project_manager() -> str:
    """Идеальный ответ Project Manager (задачи, риски, roadmap)."""
    return _json(
        {
            "wbs": [
                {"id": "WBS-1", "name": "Реализация", "level": 1, "parent": None},
                {"id": "WBS-1.1", "name": "API", "level": 2, "parent": "WBS-1"},
            ],
            "tasks": [
                {
                    "id": "T-1",
                    "wbs_ref": "WBS-1.1",
                    "requirement_refs": ["FR-1", "BR-1"],
                    "title": "API заметок",
                    "estimate_hours": 24,
                    "story_points": 5,
                    "depends_on": [],
                    "is_critical_path": True,
                    "buffer_percent": 20,
                    "owner": "tech lead",
                    "status": "todo",
                    "dor": {"passed": True, "missing": []},
                    "dod": ["unit tests", "code review", "deployed to staging"],
                },
            ],
            "critical_path": ["T-1"],
            "total_buffer_hours": 5,
            "agile_metrics": {
                "velocity_target": 30,
                "cycle_time_target_days": 5,
            },
            "risks": [
                {
                    "id": "R-1",
                    "description": "задержка синхронизации",
                    "likelihood": "medium",
                    "impact": "high",
                    "owner": "tech lead",
                }
            ],
            "roadmap": ["MVP: создание и синхронизация", "beta: офлайн"],
            "review_points": ["после MVP", "после beta"],
            "open_questions": ["какая модель монетизации?"],
        }
    )


def _requirements_critic() -> str:
    """Идеальный ответ субагента-критика: противоречие, слабый AC, додуманное."""
    return _json(
        {
            "findings": [
                {
                    "where": "FR-1 / NFR-1",
                    "status": "противоречие",
                    "why": "FR-1 обещает загрузку до 2 секунд, NFR-1 разрешает p95 до 5 секунд",
                    "fix": "согласовать один порог и сослаться на него в обоих требованиях",
                    "severity": "blocker",
                },
                {
                    "where": "AC-2",
                    "status": "слабый AC",
                    "why": "«работает быстро» нельзя проверить: нет порога и окна измерения",
                    "fix": "заменить на измеримый порог (например, p95 ≤ 2 с на 1000 запросов)",
                    "severity": "major",
                },
                {
                    "where": "FR-3",
                    "status": "додумано",
                    "why": "рост конверсии на 30% не имеет источника во входе",
                    "fix": "пометить как гипотезу или убрать число",
                    "severity": "major",
                },
            ],
            "verdict": {
                "status": "return_to_system",
                "reason": "противоречие порогов, слабый AC и додуманное число",
            },
            "open_questions": ["какой порог загрузки считаем целевым — 2 или 5 секунд?"],
        }
    )


def _critic_gap() -> str:
    """Ответ критика для кейса «BR без FR»: единственная находка — пробел."""
    return _json(
        {
            "findings": [
                {
                    "where": "BR-2",
                    "status": "пробел",
                    "why": "бизнес-требование про экспорт в CSV не закрыто ни одним FR",
                    "fix": "добавить FR на экспорт или понизить BR-2 до гипотезы",
                    "severity": "blocker",
                }
            ],
            "verdict": {
                "status": "return_to_system",
                "reason": "BR-2 без покрытия: пробел в требованиях",
            },
            "open_questions": ["экспорт в CSV входит в MVP или это отдельная задача?"],
        }
    )


def _fact_check() -> str:
    """Идеальный ответ fact-check (три статуса + причины отклонения)."""
    return _json(
        {
            "findings": [
                {
                    "claim": "Комиссия 299 ₽",
                    "status": "подтверждено",
                    "source": "tariff@2024-01-01",
                    "reason": "",
                },
                {
                    "claim": "Клиенты любят приложение",
                    "status": "допущение",
                    "reason": "нет источника, требует проверки",
                },
                {
                    "claim": "Срок хранения 5 лет",
                    "status": "нет данных",
                    "reason": "нет данных в брифе",
                },
            ]
        }
    )


def _orchestrator_chat_medical() -> str:
    """Эталон: оркестратор в режиме chat для регулируемого домена (медицина)."""
    question = (
        "Вопрос: где хранятся медицинские данные пациентов — в РФ или в ЕС? "
        "Зачем я это спрашиваю: домен «медицина» запрещает режим auto, потому что "
        "цена ошибки (152-ФЗ, HIPAA) выше стоимости уточнений; от географии хранения "
        "зависят требования и подрядчики. "
        "Термины: ПДн — персональные данные; data residency — требование хранить "
        "данные в юрисдикции пользователя."
    )
    return _orchestrator(
        mode="chat",
        stage="business",
        next_stage="ba_gate",
        questions=[question],
        artifacts=["output/chat-001/brief.md", "output/chat-001/open-questions.md"],
        assumptions=["тип клиники и регион — нет данных, уточняется на BA-gate"],
    )


def _orchestrator_chat_answered() -> str:
    """Эталон: оркестратор в chat, часть вопросов уже закрыта заказчиком."""
    question = (
        "Вопрос: какие цены тарифов и какой срок хранения персональных данных? "
        "Зачем я это спрашиваю: контур, аудитория и модель монетизации уже закрыты "
        "заказчиком, но без цен не проверить ARR-цель, а без retention — модель "
        "данных и стоимость хранения. "
        "Термины: ARR — годовая выручка; retention — срок хранения данных."
    )
    return _orchestrator(
        mode="chat",
        stage="business",
        next_stage="ba_gate",
        questions=[question],
        artifacts=["output/chat-001/brief.md"],
        assumptions=[
            "цена тарифа — нет данных (вопрос Q-15)",
            "срок хранения ПДн — нет данных (вопрос Q-16)",
        ],
    )


def _orchestrator_hybrid_cross_border() -> str:
    """Эталон: оркестратор в hybrid, трансграничный контур — обязательный вопрос."""
    question = (
        "Вопрос: в какой юрисдикции хранить данные покупателей и продавцов? "
        "Зачем я это спрашиваю: контур трансграничный, значит нужен обязательный "
        "вопрос о data residency (GDPR / PIPL / 152-ФЗ) — от ответа зависят "
        "инфраструктура и договоры с провайдерами. "
        "Термины: GDPR — защита данных в ЕС; PIPL — закон о данных в Китае; "
        "152-ФЗ — закон о персональных данных в РФ."
    )
    return _orchestrator(
        mode="hybrid",
        stage="business",
        next_stage="ba_gate",
        questions=[question],
        artifacts=["output/hybrid-001/brief.md"],
        assumptions=["структура комиссии и валюта расчёта — нет данных"],
    )


def _orchestrator_hybrid_high_risk() -> str:
    """Эталон: оркестратор в hybrid, высокий риск для пользователя."""
    question = (
        "Вопрос: кто и по какой схеме принимает решение о выдаче кредита? "
        "Зачем я это спрашиваю: домен «деньги» — высокий риск для пользователя, "
        "поэтому hybrid обязателен; от схемы принятия решения зависит "
        "и ответственность, и требования к объяснимости. "
        "Термины: скоринг — автоматическая оценка кредитоспособности; "
        "объяснимость — способность системы обосновать решение."
    )
    return _orchestrator(
        mode="hybrid",
        stage="business",
        next_stage="ba_gate",
        questions=[question],
        artifacts=["output/hybrid-001/brief.md"],
        assumptions=["ставка и лимиты — нет данных, уточняются на BA-gate"],
    )


def _ba_chat_delivery() -> str:
    """Эталон: BA в режиме chat — неизвестное в open_questions и assumptions."""
    return _json(
        {
            "personas": [{"id": "P-1", "name": "Покупатель", "contour": "B2C"}],
            "contour": "B2C",
            "jobs_to_be_done": [
                {
                    "id": "J-1",
                    "persona": "P-1",
                    "when": "когда нужно заказать продукты подвезти",
                    "want": "оформить заказ и оплатить без лишних шагов",
                    "so_that": "не тратить время на оформление",
                }
            ],
            "as_is": "заказ по телефону (допущение — источника нет)",
            "to_be": "самостоятельное оформление заказа онлайн с оплатой картой",
            "business_requirements": [
                {
                    "id": "BR-1",
                    "text": "Покупатель оформляет заказ и оплачивает онлайн",
                    "source": "ответ заказчика",
                    "status": "draft",
                    "owner": "владелец продукта",
                }
            ],
            "mvp_scope": ["BR-1"],
            "full_scope": ["BR-1"],
            "scope_prioritization": {
                "must_have": ["BR-1"],
                "should_have": [],
                "could_have": [],
                "wont_have": [],
            },
            "competitor_analysis": [],
            "privacy_impact": {
                "personal_data": "да",
                "regulatory_triggers": ["152-ФЗ"],
                "dpia_required": "нет",
                "dpia_reason": "данные покупателя — ограниченный риск",
            },
            "acceptance_criteria": [
                {"id": "AC-1", "text": "Покупатель оформляет заказ и оплачивает онлайн"}
            ],
            "assumptions": [
                "бюджет проекта — нет данных, вопрос на BA-gate",
                "срок MVP — нет данных, вопрос на BA-gate",
            ],
            "open_questions": [
                "какой бюджет проекта?",
                "какой срок MVP?",
            ],
        }
    )


def _sa_chat_requirements() -> str:
    """Эталон: SA в режиме chat — неизвестные пороги NFR помечены, а не выдуманы."""
    return _json(
        {
            "use_cases": [
                {
                    "id": "UC-1",
                    "actor": "P-1",
                    "goal": "оформить и оплатить заказ",
                    "preconditions": ["пользователь вошёл в систему"],
                    "main_flow": ["выбрать продукты", "оформить заказ", "оплатить"],
                    "alternative_flows": ["оплата не прошла — показать ошибку"],
                    "postconditions": ["заказ оплачен"],
                }
            ],
            "functional_requirements": [
                {
                    "id": "FR-1",
                    "text": "Пользователь оформляет заказ за ≤ 30 секунд",
                    "source": "BR-1",
                    "priority": "P0",
                    "status": "draft",
                    "owner": "владелец продукта",
                    "risk": "low",
                    "version": 1,
                    "compliance": ["152-ФЗ"],
                    "acceptance_criteria": [
                        {
                            "id": "AC-1",
                            "format": "BDD",
                            "given": "пользователь выбрал продукты",
                            "when": "он оформляет заказ",
                            "then": "заказ создан за ≤ 30 секунд",
                        }
                    ],
                    "threat_model": {
                        "stride": ["tampering"],
                        "mitigation": "подпись заказа и журнал изменений",
                    },
                }
            ],
            "nonfunctional_requirements": [
                {
                    "id": "NFR-1",
                    "category": "availability",
                    "text": "uptime 99,9% — порог не задан, значение уточняется на SA-gate",
                    "standard": "ISO 25010",
                }
            ],
            "integrations": ["платёжный провайдер (СБП)", "карточная эквайринговая система"],
            "data": ["адрес доставки и контакты покупателя — ПДн, 152-ФЗ"],
            "spec": "черновик спецификации: цели, UC-1, FR-1, NFR-1",
            "open_questions": [
                "какие пороги uptime и RTO/RPO? — вопрос на SA-gate",
                "какой срок хранения ПДн? — вопрос на SA-gate",
            ],
        }
    )


def _orchestrator_chat_paraphrase() -> str:
    """Эталон: оркестратор в chat, вход перефразирован — контракт тот же."""
    question = (
        "Вопрос: какие способы оплаты поддерживаем — карта, СБП, наличные при получении? "
        "Зачем я это спрашиваю: от набора способов оплаты зависят интеграции, "
        "комиссия и юридические требования к чекам. "
        "Термины: эквайринг — приём оплаты картой; СБП — система быстрых платежей."
    )
    return _orchestrator(
        mode="chat",
        stage="business",
        next_stage="ba_gate",
        questions=[question],
        artifacts=["output/chat-001/brief.md"],
        assumptions=["контур B2C — допущение"],
    )


def _ba_chat_shuffled() -> str:
    """Эталон: BA в chat, порядок полей ответа изменён — контракт не меняется."""
    return _json(
        {
            "open_questions": [
                "какова стоимость приёма?",
                "как ведётся расписание врачей?",
            ],
            "assumptions": [
                "стоимость приёма — нет данных, вопрос на BA-gate",
                "расписание врачей — нет данных, вопрос на BA-gate",
            ],
            "acceptance_criteria": [{"id": "AC-1", "text": "Пациент записывается к врачу онлайн"}],
            "business_requirements": [
                {
                    "id": "BR-1",
                    "text": "Пациент записывается к врачу онлайн",
                    "source": "ответ заказчика",
                    "status": "draft",
                    "owner": "владелец продукта",
                }
            ],
            "scope_prioritization": {
                "must_have": ["BR-1"],
                "should_have": [],
                "could_have": [],
                "wont_have": [],
            },
            "mvp_scope": ["BR-1"],
            "full_scope": ["BR-1"],
            "to_be": "онлайн-запись к врачу",
            "as_is": "запись по телефону в регистратуре (допущение)",
            "jobs_to_be_done": [
                {
                    "id": "J-1",
                    "persona": "P-1",
                    "when": "когда нужно попасть к врачу",
                    "want": "записаться без звонков и ожидания",
                    "so_that": "не потерять время на запись",
                }
            ],
            "contour": "B2C",
            "personas": [{"id": "P-1", "name": "Пациент", "contour": "B2C"}],
            "competitor_analysis": [],
            "privacy_impact": {
                "personal_data": "да",
                "regulatory_triggers": ["152-ФЗ"],
                "dpia_required": "да",
                "dpia_reason": "данные о здоровье — специальная категория ПДн",
            },
        }
    )


def _orchestrator_dialogue_turn(
    question: str,
    answer: str,
    mode: str = "chat",
    collected: list[str] | None = None,
) -> str:
    """Собрать ответ оркестратора в ходе диалога (первый ход).

    Зачем. Mock-провайдер обслуживает многоходовые кейсы: он должен вести
    диалог так же, как реальный провайдер (`scripts/multi_turn_provider.py`),
    иначе `eval-mock` не воспроизводил бы то, что проверяет реальный прогон.
    Логика ходов общая — `idea_to_spec.multi_turn.run_turns`.

    Args:
        question: Текст вопроса роли.
        answer: Ответ заказчика на этот вопрос.
        mode: Режим прогона.
        collected: Все ответы заказчика, полученные к этому ходу.

    Returns:
        JSON-строка ответа.
    """
    return _orchestrator(
        mode=mode,
        stage="business",
        next_stage="ba_gate",
        questions=[
            f"Вопрос: {question} "
            "Зачем я это спрашиваю: от ответа зависит следующий шаг прогона. "
            "Термины: уточняемые термины — в глоссарии."
        ],
        artifacts=["output/chat-001/brief.md", "output/chat-001/open-questions.md"],
        assumptions=list(collected or [answer]),
    )


def _orchestrator_dialogue_final(
    answers: list[str],
    mode: str = "chat",
) -> str:
    """Собрать финальный ответ оркестратора: диалог исчерпан, вопросов нет.

    Args:
        answers: Ответы заказчика, на которые роль опирается.
        mode: Режим прогона.

    Returns:
        JSON-строка ответа.
    """
    return _orchestrator(
        mode=mode,
        stage="business",
        next_stage="ba_gate",
        questions=[],
        artifacts=["output/chat-001/brief.md", "output/chat-001/open-questions.md"],
        assumptions=list(answers),
    )


def _dialogue_answer(contract: dict[str, Any], turns: list[Any]) -> str:
    """Собрать ответ роли для текущего хода многоходового диалога.

    Зачем. Mock-провайдер обслуживает многоходовые кейсы: он должен вести
    диалог так же, как реальный провайдер (`scripts/multi_turn_provider.py`),
    иначе `eval-mock` не воспроизводил бы то, что проверяет реальный прогон.
    Логика ходов общая — `idea_to_spec.multi_turn.run_turns`.

    Номер хода известен по числу уже состоявшихся ходов: на ходе N роль
    спрашивает про N-ю пару сценария, а после последней пары — закрывает
    диалог (вопросов нет, ответы заказчика зафиксированы).

    Args:
        contract: Контракт кейса.
        turns: Уже состоявшиеся ходы диалога.

    Returns:
        JSON-строка ответа роли.
    """
    scenario = contract.get("dialogue")
    pairs = scenario_turns(scenario) if isinstance(scenario, dict) else []
    mode = str(contract.get("mode") or "chat")

    if len(turns) >= len(pairs):
        answers = [str(pair.get("answer") or "") for pair in pairs]
        return _orchestrator_dialogue_final(answers, mode)

    current = pairs[len(turns)]
    question = str(current.get("question_contains") or "")
    answer = str(current.get("answer") or "")
    # Все ответы заказчика, полученные к этому ходу: модель фиксирует каждый
    # (измерено на qwen3:8b — при передаче только последнего ответа
    # предыдущие терялись).
    collected = [str(pair.get("answer") or "") for pair in pairs[: len(turns) + 1]]
    return _orchestrator_dialogue_turn(question, answer, mode, collected)


def build_answer(merged: dict[str, Any]) -> str:
    """Собрать эталонный ответ для кейса.

    Args:
        merged: Объединённые переменные кейса (контракт поверх vars).

    Returns:
        Текст ответа роли.
    """
    case_id = str(merged.get("id", ""))

    scenario = merged.get("dialogue")
    if isinstance(scenario, dict) and scenario.get("turns"):
        # Многоходовый кейс: ведём диалог по общей логике (run_turns), чтобы
        # mock воспроизводил ровно то, что проверяет реальный прогон.
        output, _turns = run_turns(
            str(merged.get("input") or ""),
            scenario,
            lambda _prompt, turns: _dialogue_answer(merged, turns),
            mode=str(merged.get("mode") or ""),
            input_text=str(merged.get("input") or ""),
        )
        return output

    if case_id.startswith("ORCH-01"):
        return _orchestrator_auto()
    if case_id.startswith("ORCH-02"):
        return _orchestrator_chat()
    if case_id.startswith("ORCH-03"):
        return _orchestrator_hybrid()
    if case_id.startswith("ORCH-04"):
        return _orchestrator_chat_medical()
    if case_id.startswith("ORCH-05"):
        return _orchestrator_chat_answered()
    if case_id.startswith("ORCH-06"):
        return _orchestrator_hybrid_cross_border()
    if case_id.startswith("ORCH-07"):
        return _orchestrator_hybrid_high_risk()
    if case_id.startswith("ORCH-08"):
        return _orchestrator_chat_paraphrase()
    if case_id.startswith("BA-03"):
        return _ba_chat_delivery()
    if case_id.startswith("BA-04"):
        return _ba_chat_shuffled()
    if case_id.startswith("SA-03"):
        return _sa_chat_requirements()
    if case_id.startswith("NEG-01"):
        return "Пришлите, пожалуйста, одну строку с идеей — и я начну прогон."
    if case_id.startswith("NEG-02"):
        return _orchestrator_auto()
    if case_id.startswith("PM-"):
        return _pm()
    if case_id.startswith("BA-02"):
        return _ba(
            [
                "10 млн пользователей и выручка 5 млрд — требует проверки (допущение), а не факт",
            ]
        )
    if case_id.startswith("BA-"):
        return _ba()
    if case_id.startswith("DISC-"):
        return _ba()
    if case_id.startswith("SA-"):
        return _sa()
    if case_id.startswith("ARCH-"):
        return _architect()
    if case_id.startswith("DESIGN-"):
        return _designer()
    if case_id.startswith("PROJ-"):
        return _project_manager()
    if case_id.startswith("CRIT-02"):
        return _critic_gap()
    if case_id.startswith("CRIT-"):
        return _requirements_critic()
    if case_id.startswith("FC-"):
        return _fact_check()

    return f"не удалось определить кейс: {case_id or '<пусто>'}"


def main() -> int:
    """Точка входа exec-провайдера.

    Returns:
        Всегда 0 — ответ печатается в stdout.
    """
    context_raw = sys.argv[3] if len(sys.argv) > 3 else "{}"
    context = _load_context(context_raw)
    vars_block = _vars(context)
    contract = _contract(vars_block)
    merged = {**vars_block, **contract}
    print(build_answer(merged))
    return 0


if __name__ == "__main__":
    sys.exit(main())
