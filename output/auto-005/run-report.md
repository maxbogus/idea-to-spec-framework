# Run Report — auto-005

> Источник: ответ роли оркестратор (сборка и гейты) (`qwen3:8b`, temperature 0, top_p 1, num_ctx 16384, think false). Сборка — оркестратор: таблицы, ID и ссылки; содержание не дописывалось. Пробелы в ответе модели помечены явно.

## Вход

Сырая идея as-is:

> У меня три барбершопа, всё пишем в блокнот: клиенты путают время, половина не приходит, мастера сами переносят, а я вообще не понимаю, кто когда работает. Сделайте приложение, чтобы был порядок и клиенты не пропадали.

Режим: `auto` (без вопросов). Модель: `qwen3:8b` через Ollama, локально.
Сборка промпта — как в eval (`eval/promptfooconfig.yaml` +
`scripts/promptfoo_transform.py`), `temperature 0`, `top_p 1`,
`num_predict 3500`, `think false`, **`num_ctx 16384`**.

> Отклонение от eval-конфига: eval не задаёт `num_ctx`, Ollama берёт 4096 и при
> генерации вытесняет начало промпта. Замер 2026-11-26: промпт 46 КБ →
> `prompt_eval_count=4096`, инструкция в начале теряется, инструкция в конце
> остаётся. Здесь `num_ctx` задан явно.

## Созданные артефакты

- `brief.md`, `open-questions.md`, `personas.md`, `jtbd.md`
- `business-requirements.md`, `functional-requirements.md`, `nonfunctional-requirements.md`
- `use-cases.md`, `spec.md`, `traceability-matrix.md`, `risk-register.md`
- `human-oversight-plan.md`, `validation-report.md`, `hallucination-log.md`, `cjm.md`
- `diagrams/` — 11 `.mmd` + `bpmn-process.bpmn`

## Журнал стадий

| Этап | Роль | prompt tokens | eval tokens | сек | finish |
|---|---|---|---|---|---|
| intake | orchestrator | 3821 | 138 | 7.4 | stop |
| business (PM) | product-manager | 2832 | 797 | 29.4 | stop |
| business (BA), версия 1 | business-analyst | 3856 | 1250 | 50.0 | stop |
| BA-gate, проверка 1 | orchestrator | 6003 | 193 | 11.7 | stop |
| business (BA), версия 2 — после возврата | business-analyst | 5254 | 1656 | 70.9 | stop |
| BA-gate, проверка 2 | orchestrator | 6413 | 245 | 14.3 | stop |
| design_sketch | designer | 4936 | 1545 | 65.6 | stop |
| system (SA), версия 1 | system-analyst | 6343 | 2900 | 125.9 | stop |
| SA-gate | orchestrator | 7250 | 174 | 12.5 | stop |
| architecture | architect | 5714 | 1368 | 58.1 | stop |
| validation, fact-check | fact-check | 2510 | 1835 | 66.9 | stop |
| validation, critic (до доработки) | critic | 4858 | 1510 | 63.2 | stop |
| system (SA), версия 2 | system-analyst | 9284 | 3279 | 152.0 | stop |
| system (SA), версия 3 — битый JSON | system-analyst | 8460 | 2999 | 139.4 | stop |
| system (SA), версия 3, повтор | system-analyst | 8460 | 3008 | 134.1 | stop |
| system (SA), + FR-5 | system-analyst | 3690 | 2543 | 102.8 | stop |
| system (SA), FR-5 переписан | system-analyst | 3899 | 386 | 15.0 | stop |
| system (SA), негативные AC для FR-2…FR-4 | system-analyst | 4647 | 1929 | 85.4 | stop |
| validation, critic (после доработки) | critic | 5105 | 1731 | 75.6 | stop |
| Spec-gate | orchestrator | 5101 | 556 | 26.2 | stop |
| plan | project-manager | 5752 | 3109 | 139.5 | stop |
| design_cjm, попытка 1 (формат роли) | designer | 3166 | 850 | 35.2 | stop |
| design_cjm, попытка 2 (явная схема) | designer | 2564 | 476 | 17.8 | stop |

Всего вызовов: 23; prompt-токенов: **119918**, eval-токенов:
**34477**, машинного времени: **1499 с**.

## Гейты

| Гейт | Решение модели | Что по факту |
|---|---|---|
| BA-gate (1) | passed | чеклист не закрыт: нет доменов/тарифов, JTBD без метрики PM, неполные персоны → возврат |
| BA-gate (2) | passed | 3 из 5 пунктов закрыты; домены/тарифы и конкуренты — нет |
| SA-gate | passed | NFR без порогов и интеграции без внешних систем остались |
| Spec-gate | failed | return_to: architecture; критик — return_to_system |

> Гейты модели говорят «passed» там, где чеклист `prompts/gate-checklists.md` не
> закрыт: чеклисты в промпт не подключаются (это записано в самом файле), и
> оркестратор проверяет по памяти. Здесь это зафиксировано, а не сглажено.

## Итерации и повторы

- BA: 2 версии (возврат по чеклисту, 5 пунктов).
- SA: 6 вызовов — v1 → v2 → v3 (битый JSON, строгий парсинг упал на обрыве
  строки) → v3b → FR-5 → негативные AC для FR-2…FR-4.
- CJM: 2 вызова — в формате роли поля CJM нет, карта получена отдельной схемой.
- Critic: 2 прогона; после доработки вердикт снова `return_to_system`, находки
  сместились (проверка «стало ли лучше» не выполняется).

## Дефекты, найденные прогоном

1. **Промпт Designer не содержит CJM**, хотя роль обязуется её собирать.
2. **SA не выдаёт негативные сценарии** без отдельного требования; FR-5 потерян
   при переписывании (BR-5 остался без FR).
3. **Гейты-штампы**: `passed` при незакрытом чеклисте; Spec-gate вернул
   `return_to: architecture`, хотя недостающие пункты — системного анализа.
4. **Валидность JSON**: один ответ SA из шести — битый JSON при `finish=stop`.
5. **Fact-check искажает цитату** (80% → «8,0%») и понижает утверждение
   «не подтверждено цитатой», хотя цитата есть.
6. **`num_ctx` не прибит в eval** → вытеснение начала промпта при длинных
   ответах (транспортный дефект, не дефект модели).

## Метрики прогона

| Метрика | Значение | Источник |
|---|---|---|
| Модель | qwen3:8b (Q4_K_M, 8.2B) | `ollama ps` |
| Контекст | 16384 | options |
| Уточнения у заказчика | 0 | режим auto |
| Артефактов | 16 md + 11 mmd + 1 bpmn | каталог прогона |
| Допущений | 4 | brief.md |
| Находок fact-check | 12 (подтверждено 0) | validation-report.md |
| Находок критика | 16 | validation-report.md |
| Spec-gate | failed | JSON оркестратора |
| Успех | **нет**: Spec-gate не пройден, находки открыты | гейты |
