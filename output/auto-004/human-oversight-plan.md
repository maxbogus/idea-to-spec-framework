# Human Oversight Plan

> Кто, на каком этапе и какие решения утверждает. Oversight — артефакт,
> а не «режим чата».

| Этап | Решение | Кто утверждает | Какие логи сохраняем |
|---|---|---|---|
| Intake | контур, получатель, ограничения | Product Manager + заказчик (P-1) | бриф, open-questions |
| Business analysis | персоны, JTBD, scope по MoSCoW | Business Analyst + Product Manager | personas, jtbd, business-requirements |
| BA-gate | полнота бизнес-анализа | Business Analyst | ответ гейта в run-report |
| System analysis | use cases, FR/NFR, критерии | System Analyst | use-cases, functional-requirements, nonfunctional-requirements |
| SA-gate | полнота системного анализа | System Analyst + Architect | ответ гейта в run-report |
| Validation | основания и качество требований | Architect + заказчик (P-1) | validation-report, hallucination-log |
| Spec-gate | допуск спецификации к разработке | System Analyst + Architect | run-report, traceability-matrix |
| Plan | задачи, оценки, буферы | Project Manager | traceability-matrix, risk-register, gantt |
| Release | допуск к разработке v0.3 | Владелец фреймворка | run-report и записи гейтов |

## Что человек подтверждает пост-фактум

В `auto` модель приняла восемь допущений (Q-1…Q-8). Человек не отвечает на
вопросы до прогона — он подтверждает или отменяет значения после.

| Вопрос | Что подтвердить | Что пересобрать при отмене |
|---|---|---|
| Q-1 | аудитория 5–50 команд | бриф, персоны, scope |
| Q-2 | успех: 80% требований и один рабочий день | success metric и приоритеты |
| Q-3 | лимит 200 000 токенов и 30 минут | FR-15, NFR-1 |
| Q-4 | только локальная LLM | §6, NFR-7, ADR-3 |
| Q-5 | структурные гейты машинные | FR-5 и scope v0.3 |
| Q-6 | 16 артефактов обязательны | DoD, FR-2 |
| Q-7 | Windows только через WSL2 | NFR-4 |
| Q-8 | маскирование при экспорте | §6, FR-13 |

- Любое повышение статуса требования `draft` → `approved` — только человек.

## Требования

- Oversight должен быть компетентным и прослеживаемым (EU AI Act, ст. 14).
- Решения фиксируются записью с владельцем и датой.
- Логи достаточны, чтобы восстановить, кто и что утвердил.
