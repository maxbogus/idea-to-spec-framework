# Индекс скилов

> Генерируется `scripts/render_skills_index.py` из `skills/registry.yaml`
> и frontmatter `SKILL.md`. Не править вручную: проверка — `make check-skills`.
> Бандл стадии — это скилы, которые нужны на этой стадии; тело каждого
> скила <= 60 строк, тяжёлые каталоги лежат в `references/`.

## Business analysis

| Скил | Kind | Гейт | Строк | Триггер | Проверка |
|---|---|---|---:|---|---|
| `analyze-data` | procedure | ba_gate | 36 | метрика, baseline, формула, provenance, median, percentile, CAGR, «+10%», расчёт по данным, пропуск «н/д». | `eval/cases/roles.jsonl` |
| `collect-sources` | procedure | ba_gate | 25 | внешний источник, рынок, контур, тарифы, отрасль, цитата, «требует проверки», чего не хватает в брифе. | `eval/cases/roles.jsonl` |
| `mock-respondents` | procedure | ba_gate | 30 | персона, синтетика, модельный респондент, интервью нет, personas, JTBD, «ответ модели», гипотеза о пользователе. | `eval/cases/roles.jsonl` |

## System analysis

| Скил | Kind | Гейт | Строк | Триггер | Проверка |
|---|---|---|---:|---|---|
| `define-acceptance` | procedure | sa_gate | 36 | критерий приёмки, acceptance criteria, BDD, Given When Then, негативный сценарий, отказ, ошибка, пустое состояние, доступ запрещён. | `tests/test_run_checks.py` |
| `detect-contradictions` | guard | sa_gate | 27 | противоречие, расхождение требований, BR против FR, ось расхождения, validation-report, «не сглаживать». | `eval/cases/roles.jsonl` |
| `quantify-nfr` | procedure | sa_gate | 37 | NFR без меры, «быстро», «удобно», «надёжно», latency, p95, throughput, uptime, SLA, RTO, RPO, порог, метод проверки. | `tests/test_run_checks.py` |

## Architecture

| Скил | Kind | Гейт | Строк | Триггер | Проверка |
|---|---|---|---:|---|---|
| `diagram-generation` | procedure | sa_gate | 51 | диаграмма, use case diagram, sequence, ER, DFD, C4, BPMN, activity, gantt, CJM, state, domain map, event storming, DMN, SIPOC, data lineage, RAG pipeline, agent workflow, mermaid, mmdc, визуализировать требования, паки диаграмм. | `tests/test_diagram_source_sections.py` |
| `record-decision` | procedure | spec_gate | 35 | ADR, архитектурное решение, выбор БД, стек, протокол, интеграция, альтернативы, trade-off, consequences, статус решения. | `tests/test_run_checks.py` |
