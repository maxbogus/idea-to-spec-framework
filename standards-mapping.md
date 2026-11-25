# Наложение на SDLC / PDLC и стандарты

## 1. SDLC vs PDLC

- **SDLC** — производство артефакта: требования → дизайн → код → тест → релиз.
- **PDLC** — цикл продукта: discovery → deliver → operate → sunset.
- **Модель:** PDLC вкладывает SDLC; пост-AI добавляет третью петлю —
  жизненный цикл модели (данные → артефакт → eval → дрейф).

Воркшоп моделирует **Discover + Design + часть Sign-off**: от «плохого
брифа» до спецификации и валидации. Это upstream-часть жизненного цикла.

## 2. Стандарты по регионам

| Регион | Документ | Что берём |
|---|---|---|
| Международный | ISO/IEC/IEEE 12207:2026 | процессы ЖЦ, выходные артефакты |
| США | NIST AI RMF | Govern / Map / Measure / Manage |
| США | NIST SP 800-218A | безопасная разработка GenAI |
| ЕС | EU AI Act | risk management (ст. 9), human oversight (ст. 14), документация, мониторинг |
| ЕС | GDPR | data protection by design (ст. 25), минимизация, purpose limitation |
| ЕС | NIS2 / DORA | устойчивость и инциденты (для отраслей) |
| РФ | ГОСТ Р 57193-2025 | процессы ЖЦ, карта прослеживаемости |
| РФ | ГОСТ Р 59853-2021 | терминология автоматизированных систем |

## 3. Что совпадает с воркшопом

| Элемент воркшопа | Стандарт / практика | Вердикт |
|---|---|---|
| «Плохой бриф → вопросы» | PDLC Discover; NIST AI RMF Map; EU AI Act risk mgmt | ✅ сильное совпадение |
| Роли BA/SA/PM/Architect/Designer/PM | ISO 12207 роли; AI RMF Govern | ✅ но не хватает Security/Compliance |
| Оркестратор auto/chat/hybrid | EU AI Act human oversight | ✅ основа, но oversight нужен артефактом |
| Артефакты в папках | ISO 12207 выходные результаты; ГОСТ Р 57193 | ⚠️ нет traceability / risk / oversight |
| Валидация и hallucination log | NIST AI RMF Measure/Manage | ✅ привязать к риск-классу |
| Сравнение auto vs HITL | PDLC Verify; EU AI Act oversight | ✅ сильный учебный приём |

## 4. Разделение часть 1 / часть 2

**Часть 1 (спикер 1) — до спецификации:**

- NIST AI RMF → Map;
- EU AI Act → ст. 9 (риск-менеджмент на дизайне), ст. 14 (проектирование oversight);
- GDPR → data protection by design;
- ГОСТ Р 57193 → прослеживаемость и выходные результаты этапа.

**Часть 2 (спикер 2) — архитектура / реализация / пост-релиз:**

- ISO 12207 → Architectural Design, Implementation, Verification, Transition, Operation;
- NIST AI RMF → Measure и Manage;
- EU AI Act → post-market monitoring, логирование, инциденты;
- NIST SP 800-218A → безопасная разработка GenAI.

## 5. Что добавить, чтобы стать «standard-ready»

1. **Human Oversight Plan** — кто, на каком этапе, какие решения утверждает.
2. **Traceability Matrix** — цель → требование → спека → критерий → тест.
3. **Risk Register** + классификация рисков.
4. **GDPR/AI Act checkpoint** в chat-режиме (5 вопросов).
5. **Мини-блок post-release** (10 минут) — передать спикеру 2.
6. **Роль Security/Compliance** в оркестраторе.

## 6. Вывод

Разделение на две части делает архитектуру чище: часть 1 — «требовательная
инженерия с ИИ», часть 2 — архитектура, безопасность и эксплуатация. Часть 1
обязана отдать traceability matrix, risk register и human oversight plan как
язык передачи второму спикеру.
