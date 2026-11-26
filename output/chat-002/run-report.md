# Run Report — chat-002

> Источник: ответ роли оркестратор (сборка и гейты) (`qwen3:8b`, temperature 0, top_p 1, num_ctx 16384, think false). Сборка — оркестратор: таблицы, ID и ссылки; содержание не дописывалось. Пробелы в ответе модели помечены явно.

## Вход

Сырая идея as-is:

> У меня три барбершопа, всё пишем в блокнот: клиенты путают время, половина не приходит, мастера сами переносят, а я вообще не понимаю, кто когда работает. Сделайте приложение, чтобы был порядок и клиенты не пропадали.

Режим: `chat` (human-in-the-loop, ≤3 вопроса за гейт). Модель `qwen3:8b`,
Ollama, `temperature 0`, `top_p 1`, `num_predict 3500`, `think false`,
`num_ctx 16384`.

## Диалог с заказчиком

| Ход | Вопрос оркестратора | Ответ заказчика |
|---|---|---|
| 1 | Какой контур у приложения: B2C, B2B, B2G? | B2C: приложение для клиентов, мастера и я — только админка внутри |
| 2 | Какие конкретные функции приложения будут наиболее востребованы у мастеров? | Мастерам нужно видеть своё расписание и переносить записи, больше ничего не просили |
| 3 | Какие метрики будут использоваться для измерения эффективности приложения? | Доля визитов вовремя и число неявок по каждому мастеру |
| — | Нужно ли включать регуляторные требования в спецификацию? | не задан: критерий остановки — ответ не меняет следующий шаг (152-ФЗ уже в FR-4) |

## Созданные артефакты

- `brief.md`, `open-questions.md`, `personas.md`, `jtbd.md`
- `business-requirements.md`, `functional-requirements.md`, `nonfunctional-requirements.md`
- `use-cases.md`, `spec.md`, `traceability-matrix.md`, `risk-register.md`
- `human-oversight-plan.md`, `validation-report.md`, `hallucination-log.md`, `cjm.md`
- `diagrams/` — 11 `.mmd` + `bpmn-process.bpmn`

## Журнал стадий

| Этап | Роль | prompt tokens | eval tokens | сек | finish |
|---|---|---|---|---|---|
| intake (вопрос о контуре) | orchestrator | 3821 | 230 | 13.3 | stop |
| business (PM) | product-manager | 3243 | 988 | 39.2 | stop |
| business (BA), версия 1 | business-analyst | 4982 | 1336 | 55.9 | stop |
| BA-gate (вопрос мастеров) | orchestrator | 6259 | 231 | 13.4 | stop |
| business (BA), версия 2 | business-analyst | 5346 | 1312 | 54.2 | stop |
| system (SA), версия 1 — битый JSON | system-analyst | 5973 | 2035 | 87.6 | stop |
| system (SA), повтор — битый JSON | system-analyst | 5973 | 1815 | 72.3 | stop |
| system (SA), доработка — битый JSON, починен разбором | system-analyst | 4753 | 2740 | 106.0 | stop |
| SA-gate (вопрос метрик) | orchestrator | 6608 | 296 | 15.8 | stop |
| architecture | architect | 5189 | 1179 | 47.3 | stop |
| validation, fact-check | fact-check | 2472 | 600 | 21.2 | stop |
| validation, critic | critic | 4234 | 589 | 24.1 | stop |
| Spec-gate | orchestrator | 4219 | 680 | 26.7 | stop |
| plan | project-manager | 4647 | 2250 | 89.9 | stop |
| design_cjm (явная схема) | designer | 2559 | 411 | 15.6 | stop |

Всего вызовов: 15; prompt-токенов: **70278**, eval-токенов:
**16692**, машинного времени: **683 с**.

## Гейты

| Гейт | Решение модели | Что по факту |
|---|---|---|
| BA-gate | passed | задан вопрос про функции мастеров; вопрос «какие метрики» остался в open_questions после ответа PM |
| SA-gate | passed | задан вопрос про метрики, которые PM уже задал; ответ заказчика на него не изменил требования |
| Spec-gate | failed | return_to: architecture; 6 пунктов missing, из них traceability/risk/oversight создаются на этапе plan — после гейта |

## Итерации и повторы

- SA: 4 вызова. Два подряд вернули битый JSON (обрыв строки в `threat_model`),
  третий — тоже битый (`"tam` в `stride`); разбор починен удалением оборванной
  строки, потерян элемент `"tampering"`.
- BA: 2 версии (после ответов заказчика и замечания про фрилансеров).
- CJM: 1 вызов с явной схемой (у роли Designer поля CJM нет).

## Дефекты, найденные прогоном

1. **Dialogue closing**: отвеченные вопросы остаются в `open_questions` у BA, SA и Architect.
2. **JSON validity**: 3 из 4 ответов SA — невалидный JSON при `finish=stop`.
3. **FR sources**: SA писал `source: «ответ заказчика»` вместо `BR-*` — трассировка рвалась; потребовалась доработка.
4. **NFR без меры**: первый ответ SA не заполнил measure/threshold/method.
5. **Fact-check**: в ответе нет поля `claim` (сопоставление по порядку), метрики заказчика понижены до «допущение».
6. **Spec-gate требует артефакты, создаваемые после гейта** (traceability, risk register, oversight план) — гейт не может пройти по построению.
7. **Гейт спрашивает то, что уже answered** — критерий остановки сработал только на 4-м вопросе (его задал я, не модель).

## Метрики прогона

| Метрика | Значение | Источник |
|---|---|---|
| Модель | qwen3:8b (Q4_K_M, 8.2B) | `ollama ps` |
| Контекст | 16384 | options |
| Ходов диалога | 3 (заданы и закрыты) | open-questions.md |
| Уточнения у заказчика | 3 | run-report |
| Артефактов | 16 md + 11 mmd + 1 bpmn | каталог прогона |
| Допущений | 4 | brief.md |
| Находок fact-check | 10 (подтверждено 3) | validation-report.md |
| Находок критика | 3 | validation-report.md |
| Spec-gate | failed | JSON оркестратора |
| Успех | **нет**: Spec-gate не пройден, находки открыты | гейты |
