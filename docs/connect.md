# Подключение фреймворка по пути

> Фреймворк не запускает агентов сам. Он поставляет файлы: точку входа,
> роли, скилы, шаблоны и гейты. Подключение — указать путь к корню и открыть
> `prompts/start.md`; дальше агент или человек выполняет роли.

## Контракт

| Элемент | Значение |
|---|---|
| Корень | каталог, где лежат `prompts/`, `skills/`, `templates/`, `Makefile` |
| Точка входа | `prompts/start.md` |
| Скилы | `skills/<name>/SKILL.md`, читаются по относительным путям |
| Выход | `output/<run-id>/`, переопределяется `OUT_ROOT` |
| Проверка | `uv run idea-to-spec-framework connect --framework <корень>` |

## Режим 1. Локальный путь (исходный репозиторий)

1. Открыть каталог фреймворка как рабочую папку.
2. `make setup` — проверить node, mmdc, make, uv.
3. Открыть `prompts/start.md`, вставить идею и выбрать режим.
4. `make scaffold RUN=demo-001` — развернуть каркас.
5. `make check-run RUN=demo-001` — проверить согласованность.

Проверка подключения:

```bash
uv run idea-to-spec-framework connect --framework .
```

## Режим 2. Как библиотека

```bash
uv add "idea-to-spec-framework @ git+https://github.com/maxbogus/idea-to-spec-framework.git@v0.3.0"
uv run idea-to-spec-framework export --dest framework
uv run idea-to-spec-framework verify --dest framework
uv run idea-to-spec-framework connect --framework framework
```

Точка входа после экспорта — `framework/prompts/start.md`. Все относительные
пути считаются от `framework/`, поэтому команды запускаются через
`make -C framework ...`.

`export` не запускает пайплайн: он только раскладывает файлы. Роли выполняет
агент, гейты — `make check*`.

## Режим 3. Агент в проекте

- Открыть `framework/` как рабочую папку или указать агенту путь к
  `framework/prompts/start.md`.
- Скилы **не копируются**: роль-промпт содержит `skills/<name>/SKILL.md`,
  агент читает файл по относительному пути.
- Если агент не разрешает относительные пути, зафиксируйте cwd = корень
  фреймворка.
- Артефакты: `framework/output/<run-id>/` или
  `OUT_ROOT=/path/to/project/specs`.

## Проверка подключения

`connect` проверяет `prompts/start.md`, `prompts/roles`, `skills/*/SKILL.md`,
`templates`, `Makefile` и `scripts/check_run.py`.

```bash
uv run idea-to-spec-framework connect --framework .
make setup
make check
```

Ожидаемый вывод `connect`:

```text
entry point: /path/to/framework/prompts/start.md
next: make -C /path/to/framework scaffold RUN=demo-001
```

## Чего не делаем

- Не копируем скилы в каталог агента: пути и точки входа достаточно.
- Не переписываем `prompts/start.md` под проект: проектные данные идут в
  `output/`.
- Не запускаем пайплайн из CLI: роли выполняет агент, гейты — `make check*`.
