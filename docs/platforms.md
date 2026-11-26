# Платформы: Linux, macOS, Windows

> Что нужно, чтобы `make check`, `make scaffold` и `make eval-mock` работали
> на вашей ОС. Проверяется командой `make setup`.

## Матрица

| Платформа | Статус | Как запускать |
|---|---|---|
| Linux | Полная поддержка | `make <target>` |
| macOS | Поддержка (нужен GNU make) | `brew install make`, затем `gmake <target>` |
| Windows | Через WSL2 (рекомендуется) или Git for Windows | см. ниже |
| Windows (cmd/PowerShell) | Не поддерживается | рецепты Makefile требуют POSIX-shell |

## Общее

Фреймворк — это файлы (промпты, шаблоны, диаграммы, eval-кейсы) плюс
make-цели. Гейты написаны на bash и Python, поэтому нужен POSIX-шелл:

| Инструмент | Версия | Зачем |
|---|---|---|
| GNU make | 4.x | `.DEFAULT_GOAL`, `MAKEFILE_LIST`, `CURDIR`, `$(if)` |
| bash | 3.2+ | скрипты `scripts/` (совместимы с 3.2) |
| Python | 3.11+ | `check_run`, eval-обвязка, генерация конфигов |
| uv | >= 0.5 | `uv run`, зависимости проверок |
| node / npm | 18+ | `mmdc`, promptfoo |
| mmdc | >= 12.0.0 | рендер `.mmd` → `.png` |
| git | любая | `check-runs` (список прогонов) |

Проверка: `make setup` (на macOS — `gmake setup`). Preflight сообщает
`FAIL` для отсутствующих инструментов и `HINT` для необязательных
(promptfoo нужен только для eval).

## Linux

Ничего специфического: `make setup && make check`.

## macOS

1. `brew install make` — системный `make` в macOS это BSD make, Makefile он
   не разбирает.
2. Дальше используйте `gmake` (или добавьте `gnubin` в `PATH` и вызывайте
   `make`):

   ```bash
   gmake setup
   gmake check
   ```

3. `/bin/bash` в macOS — 3.2. Скрипты с ним совместимы; в preflight будет
   `WARN`, это не ошибка. При желании `brew install bash`.

`mmdc` и Chromium ставятся через npm и работают на Intel и Apple Silicon.

## Windows

### Вариант A — WSL2 (рекомендуется)

Внутри WSL2 окружение неотличимо от Linux:

```bash
sudo apt install build-essential
# далее — setup из README (uv, node, mmdc)
make setup && make check
```

### Вариант B — Git for Windows (best effort)

Нужны Git Bash (идёт с Git for Windows) и GNU make:

1. Установите `make` (например, `choco install make`).
2. Запускайте цели из **Git Bash**, а не из cmd/PowerShell.
3. Если в системе нет `python3` (обычно есть только `python`), передайте
   интерпретатор явно:

   ```bash
   make PYTHON=python setup
   make PYTHON=python check
   ```

`PYTHON` используется всеми целями (`check-run`, `check-runs`, `analytics`),
а eval-конфиг генерируется с абсолютным путём к интерпретатору — поэтому
`make eval` / `make eval-mock` не зависят от имени `python3`.

### Почему не cmd/PowerShell

`Makefile` объявляет `SHELL := /bin/bash`, а рецепты используют `shopt`,
`compgen`, `mktemp`, `find`, `grep`, `sed`. Кроме того, нет `make` «из
коробки». Нативный запуск без POSIX-слоя не поддерживается.

### Переводы строк

`.gitattributes` фиксирует `eol=lf` для `*.sh`, `Makefile`, `*.mmd`,
`*.bpmn`. Без этого `core.autocrlf=true` превращает shebang в
`bash: ...\r: bad interpreter`.

## Что считается проверенным

- `make check` — полный гейт (ссылки, фенсы, диаграммы, BPMN, реестр
  скилов, ledger, кросс-ссылки, отчёты, прогоны).
- `make test-eval` — pytest-контракты без модели.
- `make eval-mock` — детерминированный replay promptfoo без LLM.

Реальный `make eval` требует Ollama с моделью (`qwen3:8b`) и к портируемости
не относится.
