# idea-to-spec-ai — framework

> Мультиагентный SDD-фреймворк: сырой бизнес-запрос → проверяемая
> спецификация. Промпты, методы, скилы, шаблоны и машинные гейты, которые
> превращают «идею» в трассируемый набор артефактов и показывают, где обязан
> вмешаться человек.

## Что внутри

| Слой | Папка | Что это |
|---|---|---|
| Промпты | `prompts/` | роли, правила, стартовый промпт, ledger измерений |
| Методы | `methods/` | факт/гипотеза/прогноз, варианты, стратегия, decision-keeper |
| Скилы | `skills/` | повторяемые процедуры + `registry.yaml` |
| Субагенты | `subagents/` | fact-check и requirements-critic перед Spec-gate |
| Шаблоны | `templates/` | артефакты, Mermaid, BPMN, региональные чек-листы |
| Eval | `eval/` | promptfoo-кейсы, mock-replay, реальный прогон на Ollama |
| Гейты | `scripts/` | scaffold, render, `check_*`, eval-обвязка |
| Контракты | `tests/` | pytest-проверки промптов, схем и прогонов |
| Примеры | `output/` | четыре проверенных прогона (`auto-001/002/003`, `chat-001`) |

Источник правды по ролям и артефактам — `handout-index.md`. Архитектура
пайплайна — `architecture.md`. Региональные нормы — `standards-mapping.md`.

## Требования

| Инструмент | Версия | Зачем |
|---|---|---|
| `node` | 18+ | mermaid-cli и promptfoo |
| `mmdc` | **>= 12.0.0** | нативные use case-диаграммы (`usecase-beta`) |
| `make` | GNU make | команды |
| `uv` | >= 0.5 | Python-зависимости eval и проверок |
| `npm` | 18+ | promptfoo (`make eval-setup`) |
| Ollama + `qwen3:8b` | — | реальный прогон `make eval` |

Проверка: `make setup`.

## Быстрый старт

1. `make setup` — проверить окружение.
2. Открыть `prompts/start.md`, вставить сырую идею и выбрать режим
   (`auto` / `chat` / `hybrid`).
3. `make scaffold RUN=demo-001` — развернуть каркас в `output/demo-001/`.
4. Заполнить артефакты по ролям, пройти гейты BA → SA → fact-check →
   requirements-critic → Spec-gate.
5. `make check-run RUN=demo-001` — проверить согласованность прогона.

## Команды

```bash
make setup                 # preflight: node, mmdc >= 12, make, mermaid-config
make scaffold RUN=demo-001 # каркас прогона (базовый набор диаграмм)
make scaffold-full RUN=demo-001
make render RUN=demo-001   # .mmd -> .png
make render-all
make check                 # полный гейт фреймворка
make check-run RUN=demo-001
make check-runs            # все прогоны, отслеживаемые git
make analytics RUN=demo-001
make list-runs
make start                 # показать prompts/start.md
make eval-setup            # uv sync + npm install
make test-eval             # pytest-контракты без модели
make eval-mock             # детерминированный replay без LLM
make eval                  # реальный прогон на qwen3:8b
make eval-target FILTER="mode=chat"
make eval-compare MODELS="qwen3:8b qwen2.5:7b"
make lint-py               # ruff + mypy
```

## Eval промптов

- Кейсы — `eval/cases/roles.jsonl`: контракт (поля, `must_contain` /
  `must_not_contain`, дисциплина режима).
- `make eval-mock` — детерминированный replay, зелёный без LLM.
- `make eval` — реальный прогон; отчёт в `docs/evaluation/`.
- Провалы модели фиксируются как `xfail(strict=True)`, а не маскируются.
- Разбор находок — `docs/evaluation/README.md`, `prompts/ledger/`.

## Инварианты

- **Факт без источника — не факт.** Неподтверждённое помечается как
  гипотеза или допущение.
- **Формат ответа роли задаёт только промпт роли.** Общий контекст не
  содержит имён полей ролей.
- **Справочники не подключаются к запросу модели** (глоссарий, чек-листы
  гейтов, гайд оркестратора).
- **Диаграмма — производная.** Узлы строятся из ID артефактов.
- **Гейты не пропускаются:** BA-gate → SA-gate → fact-check → Spec-gate.
- **`output/` — проверяемые примеры.** Свежий scaffold содержит
  placeholder-ID и по определению не проходит `check_run`.

## Документация

- `architecture.md` — оркестратор, роли, режимы, артефакты, гейты.
- `handout-index.md` — роль → метод → скил → артефакт → гейт.
- `standards-mapping.md` — SDLC/PDLC и нормы США / ЕС / РФ.
- `docs/HANDOFF.md` — состояние разработки и измеренные находки.
- `docs/prompt-anatomy.md` — почему промпт даёт такой результат.
- `docs/skills-rationale.md` — критерий отбора скилов и его границы.
- `docs/agent-in-sdd-mode.md` — как удержать агента в режиме SDD.
