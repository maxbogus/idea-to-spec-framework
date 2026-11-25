# Human Oversight Plan

> Кто, на каком этапе и какие решения утверждает. Oversight — артефакт,
> а не «режим чата». Режим прогона: `chat` (human-in-the-loop).

| Этап | Решение | Кто утверждает | Какие логи сохраняем |
|---|---|---|---|
| Intake | контур, аудитория, монетизация, цель ARR | Заказчик | 14 ответов интервью (brief.md) |
| Business analysis | персоны, JTBD, бизнес-требования | Product Manager + BA + Заказчик | business-requirements.md, personas.md |
| BA-gate | полнота бизнес-требований; цены тарифов (Q-15) | BA + Заказчик | validation-report.md |
| System analysis | use cases, FR, NFR | System Analyst | use-cases.md, *-requirements.md |
| SA-gate | NFR-пороги (Q-16), retention (Q-17) | SA + юрист | nonfunctional-requirements.md |
| Architecture | ADR, интеграции, провайдеры (Q-18) | Architect | spec.md §9–10 |
| Spec-gate | полнота спецификации, трассируемость, fact-check | SA + Architect | validation-report.md, hallucination-log.md |
| Release | допуск к разработке | Product Manager + Заказчик | run-report.md |

## Требования

- Oversight компетентный и прослеживаемый (EU AI Act, ст. 14) — применимо по духу; для РФ основной регулятор — 152-ФЗ.
- Решения фиксируются записью с владельцем и датой.
- Логи достаточны, чтобы восстановить, кто и что утвердил.
- Все допущения и открытые вопросы (Q-15..Q-18) остаются на контроле человека.
