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
| Скилы | `skills/` | каталоги `<name>/SKILL.md` + `registry.yaml` |
| Субагенты | `subagents/` | fact-check и requirements-critic перед Spec-gate |
| Шаблоны | `templates/` | артефакты, Mermaid, BPMN, региональные чек-листы |
| Eval | `eval/` | promptfoo-кейсы, mock-replay, реальный прогон на Ollama |
| Гейты | `scripts/` | scaffold, render, `check_*`, eval-обвязка |
| Контракты | `tests/` | pytest-проверки промптов, схем и прогонов |
| Примеры | `output/` | пять проверенных прогонов (`auto-001/002/003/004`, `chat-001`) |

Источник правды по ролям и артефактам — `handout-index.md`. Архитектура
пайплайна — `architecture.md`. Региональные нормы — `standards-mapping.md`.

## Требования

| Инструмент | Версия | Зачем |
|---|---|---|
| `node` | 18+ | mermaid-cli и promptfoo |
| `mmdc` | **>= 12.0.0** | нативные use case-диаграммы (`usecase-beta`) |
| `make` | **GNU make** | команды (на macOS — `brew install make`, затем `gmake`) |
| `bash` | 3.2+ | скрипты гейтов |
| Python | 3.11+ | `check_run`, eval-обвязка (на Windows: `make PYTHON=python ...`) |
| `uv` | >= 0.5 | Python-зависимости eval и проверок |
| `npm` | 18+ | promptfoo (`make eval-setup`) |
| `git` | любая | `check-runs` — список прогонов |
| Ollama + `qwen3:8b` | — | реальный прогон `make eval` |

Проверка: `make setup` (на macOS — `gmake setup`).

## Платформы

| Платформа | Статус | Как запускать |
|---|---|---|
| Linux | полная поддержка | `make <target>` |
| macOS | поддержка, нужен GNU make | `brew install make`, затем `gmake <target>` |
| Windows | WSL2 (рекомендуется) или Git for Windows | `PYTHON=python`, POSIX-shell |

Нативный cmd/PowerShell не поддерживается: `Makefile` требует `/bin/bash`.
Подробности и обходные пути — `docs/platforms.md`.

## Быстрый старт

1. `make setup` — проверить окружение.
2. Открыть `prompts/start.md`, вставить сырую идею и выбрать режим
   (`auto` / `chat` / `hybrid`).
3. `make scaffold RUN=demo-001` — развернуть каркас в `output/demo-001/`.
   Каталог прогонов задаётся `OUT_ROOT` (по умолчанию `output`); он же
   используется `render`, `check-run`, `check-runs`, `analytics` и
   `clean-run`. Абсолютный путь удобен, когда фреймворк лежит подкаталогом
   проекта и артефакты должны остаться в проекте:
   `make scaffold RUN=demo-001 OUT_ROOT=/path/to/project/specs`.
4. Заполнить артефакты по ролям, пройти гейты BA → SA → fact-check →
   requirements-critic → Spec-gate.
5. `make check-run RUN=demo-001` — проверить согласованность прогона.

## Подключение

Фреймворк подключается по пути: корень + точка входа `prompts/start.md`.
Скилы не копируются; агент читает их по относительным путям.

```bash
uv run idea-to-spec-framework connect --framework .
```

Три режима (локальный путь, зависимость, агент в проекте), контракт и
проверка — `docs/connect.md`.

## Использование как зависимости

Пакет поставляет содержимое фреймворка и разворачивает его в каталог
потребителя (например, в материалы воркшопа):

```bash
uv add "idea-to-spec-framework @ git+https://github.com/maxbogus/idea-to-spec-framework.git@v0.3.1"
uv run idea-to-spec-framework export --dest framework   # развернуть
uv run idea-to-spec-framework verify --dest framework   # сверить с манифестом
```

`export` копирует `prompts/`, `methods/`, `skills/`, `subagents/`,
`templates/`, `eval/`, `output/`, `docs/`, `scripts/`, `tests/`, корневые
документы, `LICENSE` и lock-файлы (`uv.lock`, `package-lock.json`), поэтому
у потребителя установка воспроизводима. `.github/` не копируется. В целевом
каталоге остаётся `.export-manifest.json` (версия и sha256 каждого файла) —
по нему `verify` находит ручные правки и удаления. Повторный экспорт поверх
прежнего требует `--force` и никогда не удаляет каталог, созданный не
экспортом.

Контент попадает в пакет при сборке (`force-include` в `pyproject.toml`),
поэтому в репозитории вторых копий нет.

## Команды

```bash
make setup                 # preflight: node, mmdc >= 12, make, mermaid-config
make scaffold RUN=demo-001 # каркас прогона (базовый набор диаграмм)
make scaffold-full RUN=demo-001
make render RUN=demo-001   # .mmd -> .png
make render-all
make check                 # полный гейт фреймворка
make check-public          # публикуемость: пути, секреты, внешние зависимости
make skills-index          # перегенерировать skills/INDEX.md
make check-run RUN=demo-001
make check-runs            # все прогоны, отслеживаемые git
make check-dor RUN=demo-001 # полнота набора диаграмм (STRICT=1 — fail)
make check-schemas         # схемы ответов ролей: prompts/schemas.yaml ↔ промпты ↔ eval
make analytics RUN=demo-001
make list-runs
make start                 # показать prompts/start.md
make eval-setup            # uv sync + npm install
make test-eval             # pytest-контракты без модели
make eval-mock             # детерминированный replay без LLM
make eval                  # реальный прогон на qwen3:8b
make eval JSON_MODE=1      # A/B: Ollama format: "json" (по умолчанию выключено)
make eval-target FILTER="mode=chat"
make eval-compare MODELS="qwen3:8b qwen2.5:7b"
make lint-py               # ruff + mypy
```

## Eval промптов

- Кейсы — `eval/cases/roles.jsonl`: контракт (поля, `must_contain` /
  `must_not_contain`, дисциплина режима).
- `make eval-mock` — детерминированный replay, зелёный без LLM. Конфиг
  генерируется во временный `.eval-config-mock.yaml`: интерпретатор и корень
  фреймворка подставляются абсолютными путями (Windows, запуск из чужого cwd).
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
- **Скил — самодостаточный каталог.** `skills/<name>/SKILL.md` с
  frontmatter и `references/`; внешних playbook и личной конфигурации
  агента нет.
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
- `docs/connect.md` — подключение по пути и точке входа.
- `docs/platforms.md` — Linux / macOS / Windows: требования и ограничения.
- `docs/visual-artifacts.md` — каталог диаграмм, паки, DoR-профили, reference-only.
- `docs/openspec-comparison.md` — сравнение с OpenSpec и как совмещать.
