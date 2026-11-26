# Skills — повторяемые процедуры

Здесь живут **скилы**: повторяемые процедуры, оформленные как пошаговые
инструкции с проверкой. Скил описывает «как сделать», а не «что решить».

## Формат скила (контракт Cline, без внешних зависимостей)

Скил — каталог `skills/<name>/`:

```
skills/<name>/
├── SKILL.md        # frontmatter + тело <= 60 строк (guard <= 30)
├── references/*.md # тяжёлые каталоги и примеры, грузятся по требованию
├── scripts/*       # детерминированные проверки (если есть)
└── tests/*         # pytest-контракты скила (если есть)
```

`SKILL.md` начинается с YAML frontmatter:

```yaml
---
name: <kebab-case>
description: |
  Что делает и когда применять.
  Triggers on: ...
allowed-tools: Read Write
---
```

Правила:

- `name` совпадает с именем каталога;
- `allowed-tools` ограничивает инструменты вместо прозы «чего нельзя»;
- тело <= 60 строк (guard <= 30); всё тяжёлое — в `references/`;
- `references` перечислены в `registry.yaml` и лежат внутри каталога скила;
- фреймворк самодостаточен: никаких ссылок на личную конфигурацию агента и
  внешние playbook.

## Реестр и индекс

`skills/registry.yaml` (schema 2) — метаданные жизненного цикла: версия,
область, входы/выходы, зависимости, evals, references, владелец, риск и
машинные поля `kind`, `stage`, `gate`, `check`.

`skills/INDEX.md` — производная таблица «стадия → скил → триггер → проверка».
Генерируется командой `make skills-index`; ручная правка запрещена.

Проверки:

- `make check-skills` — реестр, frontmatter, бюджет тела, references,
  резолвинг `check`, актуальность `INDEX.md`;
- `make check-public` — нет личных путей, секретов и внешних зависимостей.

Подключение фреймворка — по пути и точке входа, без копирования скилов:
см. `docs/connect.md`.

## Индекс

| Скил | Kind | Стадия | Гейт | Проверка | Риск |
|---|---|---|---|---|---|
| `collect-sources` | procedure | business | ba_gate | `eval/cases/roles.jsonl` | medium |
| `mock-respondents` | procedure | business | ba_gate | `eval/cases/roles.jsonl` | high |
| `analyze-data` | procedure | business | ba_gate | `eval/cases/roles.jsonl` | high |
| `detect-contradictions` | guard | system | sa_gate | `eval/cases/roles.jsonl` | medium |
| `quantify-nfr` | procedure | system | sa_gate | `tests/test_run_checks.py` | high |
| `define-acceptance` | procedure | system | sa_gate | `tests/test_run_checks.py` | high |
| `record-decision` | procedure | architecture | spec_gate | `tests/test_run_checks.py` | high |
| `diagram-generation` | procedure | architecture | sa_gate | `tests/test_diagram_source_sections.py` | low |

`Evals: []` в реестре — честная запись: поведенческих A/B по скилу ещё нет.
Поле `check` при этом машинное: скрипт или тест, который ловит класс ошибок.
Обоснование отбора — `docs/skills-rationale.md`.

> Скил добавляется, только если он уменьшает число немаркированных
> допущений и имеет проверку. Процедура без `check` не регистрируется;
> `check: manual` допустим только для guard.
