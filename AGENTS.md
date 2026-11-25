# AGENTS.md — карта framework

> Единая точка входа для агента: что где лежит, как устроен пайплайн, какие
> команды запускать и где легко ошибиться.

## Стек

Markdown-промпты, Mermaid/BPMN, `@mermaid-js/mermaid-cli` (`mmdc`), GNU Make,
`uv` + pytest/ruff/mypy, promptfoo + Ollama для eval.

## Пайплайн

```
Intake (оркестратор)
  → Business (PM + BA)         → BA-gate
  → System (SA)                → SA-gate
  → Architecture (Architect)
  → Validation (fact-check + requirements-critic) → Spec-gate
  → Plan (PM)
  → Design (Designer)
```

Режимы: `auto` (без вопросов), `chat` (≤ 3 вопроса за гейт),
`hybrid` (вопросы только на развилках).

## Структура

```
framework/
├── README.md               обзор и быстрый старт
├── AGENTS.md               этот файл
├── architecture.md         оркестратор, роли, режимы, гейты
├── handout-index.md        роль → метод → скил → артефакт → гейт
├── standards-mapping.md    SDLC/PDLC и нормы США / ЕС / РФ
├── Makefile                команды
├── pyproject.toml          uv + pytest + ruff + mypy
├── package.json            promptfoo
├── prompts/                роли, правила, start, ledger/
├── methods/                методики
├── skills/                 процедуры + registry.yaml
├── subagents/              fact-check, requirements-critic
├── templates/              артефакты, .mmd, .bpmn, regional/
├── eval/                   кейсы и конфиги promptfoo
├── scripts/                scaffold, render, check_*, eval-обвязка
├── tests/                  pytest-контракты
├── output/                 проверенные прогоны-примеры
└── docs/                   HANDOFF, prompt-anatomy, skills-rationale,
                            agent-in-sdd-mode, evaluation/
```

## Команды

```bash
make setup                 # preflight
make scaffold RUN=demo-001
make render RUN=demo-001
make check                 # полный гейт
make check-run RUN=demo-001
make check-runs
make analytics RUN=demo-001
make eval-setup            # uv sync + npm install
make test-eval
make eval-mock
make eval
make lint-py
```

## Требования

`node` 18+, `mmdc` >= 12.0.0, GNU make, `uv` >= 0.5, `npm` 18+.
Для реального eval — Ollama и `qwen3:8b`.

## Соглашения

- **Факт без источника — не факт.** Всё неподтверждённое — гипотеза или
  допущение с явной пометкой.
- **Не смешивать бизнес- и системный анализ.** BA — потребность и
  требования, SA — use cases и спецификация.
- **Диаграмма — производная.** Узлы строятся из ID артефактов (`UC-*`,
  `J-*`, `BR-*`).
- **JTBD → use cases → CJM.** Каждый `UC-*` трассируется до `J-*`.
- **Гейты не пропускать:** BA-gate → SA-gate → fact-check → Spec-gate.
- **Формат ответа роли задаёт только промпт роли.** Общий контекст не
  содержит имён полей ролей.
- **Справочники не подключаются к запросу модели** (глоссарий, чек-листы
  гейтов, гайд оркестратора).
- **Провалы модели не маскировать:** `xfail(strict=True)` +
  `KNOWN_MODEL_FAILURES`.
- **Новый tracked-файл** размещается в `../docs/migration/OWNERSHIP.yaml`;
  проверка — `make -C .. check-split`.

## Типичные ошибки

- Чинить формат ответа добавлением текста в промпт: измерено, что +1.9 КБ
  стоили двух рабочих кейсов. Сначала целевой замер
  `make eval-target FILTER="..."`.
- Разъяснение формата после JSON-блока: правило читается позже, чем нужно.
- Режим в начале промпта: между ним и входом ~9 КБ, режим забывается.
- Запуск framework-целей из чужого cwd: JS-ассерты promptfoo используют
  `process.cwd()` для поиска `scripts/semantic_check_bridge.py`.
