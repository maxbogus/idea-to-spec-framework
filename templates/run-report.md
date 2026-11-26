# Run Report — <run-id>

> Итоговый отчёт оркестратора. Режим `auto` (без human-in-the-loop).
> Заполняется по итогам прогона; ссылается на реальные артефакты
> `output/<run-id>/`.

## Вход

Сырая идея as-is и источник (если есть).

## Созданные артефакты

- `brief.md`, `open-questions.md`
- `personas.md`, `jtbd.md`, `business-requirements.md`
- `use-cases.md`, `functional-requirements.md`, `nonfunctional-requirements.md`
- `spec.md`
- `validation-report.md`, `hallucination-log.md`
- `traceability-matrix.md`, `risk-register.md`, `human-oversight-plan.md`
- `cjm.md`
- `diagrams/` (`.mmd` + `.bpmn` + PNG при рендере)

## Метрики прогона

> Числа прогона, а не оценка «на глаз». Неизвестное значение — прочерк;
> `make analytics RUN=<run-id>` собирает сводку из этой таблицы.

| Метрика | Значение | Источник |
|---|---|---|
| Модель | — | конфиг прогона |
| Версия промпта | — | git |
| Скилы | — | handout-index |
| Токены (вход) | — | usage модели |
| Токены (выход) | — | usage модели |
| Стоимость | — | прайс модели (локальная — 0) |
| Уточнения | — | open-questions.md |
| Длительность | — | лог прогона, секунды |
| Успех | — | гейты |

## Гейты

| Гейт | Статус | Что осталось |
|---|---|---|
| BA-gate |  |  |
| SA-gate |  |  |
| Spec-gate |  |  |

## Пакеты диаграмм

> Заполняется по факту: какие паки включены и почему. Пак без источника в
> `spec.md` — дефект, а не «на всякий случай».

| Пак | Включён | Источник (`spec.md`) | Диаграммы |
|---|---|---|---|
| base | да | §2, §6, §9 | use-case, sequence, c4-context, c4-container |
| extended |  | §6, §9 | er, dfd-*, c4-*, bpmn, activity, gantt |
| behavior |  | §18 | state |
| domain |  | §11 | domain-map, event-storming |
| process |  | §15, §16 | dmn, sipoc |
| ux |  | §17 | service-blueprint |
| data |  | §12 | data-lineage |
| ai |  | §13 | rag-pipeline, vector-schema, agent-workflow, prompt-flow, feedback-loop |
| infra |  | §14 | network-topology, iac |
| architecture |  | §9 | c4-code |

## DoR

> `make check-dor RUN=<run-id> PROFILE=<profile> [STRICT=1]`.

| Проверка | Результат |
|---|---|
| Профиль |  |
| Диаграмм `.mmd` |  |
| BPMN `.bpmn` |  |
| PNG без источника |  |
| Итог |  |

## Что подтверждено

- факт с источником (`[факт]`, ссылка).

## Что осталось допущением

- допущение (`[допущение]`) и почему не подтверждено.

## Compliance & Security Check

> Блок не «для галочки»: пока здесь есть незакрытые пункты, спецификация
> не готова к передаче в разработку — в ней могут быть скрытые
> регуляторные требования, которые никто не проверил.

- [ ] Триггеры регуляторики (GDPR / 152-ФЗ / PIPL / HIPAA) проверены и
      отражены в `spec.md §6`
- [ ] Accessibility (WCAG 2.1 AA) учтена в NFR
- [ ] Для всех FR с `risk: high` прописаны BDD-критерии и mitigations
- [ ] Импортозамещение / локализация стека проверена (для контуров РФ / КНР)

## Главный вывод прогона

Один-два абзаца: что показал прогон, где разрыв.

## Следующий шаг для человека

1. Что валидировать первым.
2. Что закрыть до Spec-gate.
