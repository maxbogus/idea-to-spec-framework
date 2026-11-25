# Human Oversight Plan

> Кто, на каком этапе и какие решения утверждает. Oversight — артефакт,
> а не «режим чата».

| Этап | Решение | Кто утверждает | Какие логи сохраняем |
|---|---|---|---|
| Business analysis | контур и персоны | Product Manager + BA | personas.md, business-requirements.md |
| BA-gate | полнота бизнес-требований | BA | business-requirements.md |
| System analysis | use cases и требования | System Analyst | use-cases.md, functional/nonfunctional |
| Spec-gate | полнота спецификации | SA + Architect | spec.md, traceability-matrix.md |
| Release | допуск к разработке | Product Manager | run-report.md |
| Проверка значений | low-confidence очередь | Специалист каталога (P-1) | source_span + accept/fix |

## Требования

- Oversight должен быть компетентным и прослеживаемым (EU AI Act, ст. 14).
- Решения фиксируются записью с владельцем и датой.
- Логи достаточны, чтобы восстановить, кто и что утвердил.
