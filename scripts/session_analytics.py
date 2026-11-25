"""Сводка метрик прогона из `run-report.md` (P5).

Зачем. Оркестратор отдаёт блок `metrics` в JSON-ответе, а итоговый отчёт
прогона фиксирует те же числа для человека: модель, версию промпта,
использованные скилы, токены, стоимость, число уточнений, длительность и
успех. Без парсера эти числа остаются текстом в одном файле и не сводятся
в отчёт по прогону.

Принцип тот же, что и в остальных артефактах: **число без источника — не
число**. Незаполненная метрика остаётся прочерком и попадает в список
«не заполнено» — скрипт не подставляет значения по умолчанию и не падает
на прогонах, записанных до P5.

Запуск: `python3 scripts/session_analytics.py output/auto-002` или
`make analytics RUN=auto-002`.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

#: Канонические имена метрик прогона (порядок вывода в сводке).
REQUIRED_METRICS: tuple[str, ...] = (
    "model",
    "prompt_version",
    "skills_used",
    "tokens_in",
    "tokens_out",
    "cost_usd",
    "clarifications",
    "duration_sec",
    "success",
)

#: Заголовок секции метрик в `run-report.md`.
METRICS_HEADING = "Метрики прогона"

#: Значения, которые означают «не измерено».
PLACEHOLDER_VALUES: frozenset[str] = frozenset({"", "—", "-", "n/a", "не заполнено"})

#: Алиасы заголовков таблицы → каноническое имя метрики.
_METRIC_ALIASES: dict[str, str] = {
    "модель": "model",
    "model": "model",
    "версия промпта": "prompt_version",
    "prompt_version": "prompt_version",
    "скилы": "skills_used",
    "skills_used": "skills_used",
    "токены (вход)": "tokens_in",
    "tokens_in": "tokens_in",
    "токены (выход)": "tokens_out",
    "tokens_out": "tokens_out",
    "стоимость": "cost_usd",
    "cost_usd": "cost_usd",
    "уточнения": "clarifications",
    "clarifications": "clarifications",
    "длительность": "duration_sec",
    "duration_sec": "duration_sec",
    "успех": "success",
    "success": "success",
}

#: Строка-разделитель markdown-таблицы.
_SEPARATOR_RE = re.compile(r"^[-: ]+$")
#: Заголовок markdown-раздела.
_HEADING_RE = re.compile(r"^#{1,6}\s+(?P<title>.*)$")


def _normalize(text: str) -> str:
    """Нормализовать заголовок метрики: нижний регистр, один пробел.

    Args:
        text: Исходный текст ячейки.

    Returns:
        Нормализованный текст.
    """
    return " ".join(text.strip().lower().split())


def _section_lines(text: str, heading: str) -> list[str] | None:
    """Взять строки раздела markdown по его заголовку.

    Args:
        text: Текст документа.
        heading: Заголовок раздела (без решёток).

    Returns:
        Строки раздела без самого заголовка или ``None``, если раздела нет.
    """
    lines = text.splitlines()
    start: int | None = None
    for index, line in enumerate(lines):
        match = _HEADING_RE.match(line.strip())
        if match is not None and heading.lower() in match.group("title").lower():
            start = index + 1
            break
    if start is None:
        return None

    section: list[str] = []
    for line in lines[start:]:
        if _HEADING_RE.match(line.strip()) is not None:
            break
        section.append(line)
    return section


def parse_metrics(text: str) -> dict[str, str]:
    """Извлечь метрики прогона из текста `run-report.md`.

    Args:
        text: Текст отчёта прогона.

    Returns:
        Словарь «каноническое имя → значение». Пустой, если секции метрик
        нет (отчёт старого формата) или в ней нет узнаваемых строк.
    """
    section = _section_lines(text, METRICS_HEADING)
    if section is None:
        return {}

    metrics: dict[str, str] = {}
    for line in section:
        if not line.lstrip().startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 2:
            continue
        key = _METRIC_ALIASES.get(_normalize(cells[0]))
        if key is None:
            continue
        value = cells[1].strip()
        if not value or _SEPARATOR_RE.fullmatch(value):
            continue
        metrics.setdefault(key, value)
    return metrics


def summarize_run(run_dir: Path) -> dict[str, str]:
    """Прочитать метрики прогона из его `run-report.md`.

    Args:
        run_dir: Каталог прогона (`output/<run-id>`).

    Returns:
        Словарь метрик (пустой, если секции нет).

    Raises:
        FileNotFoundError: В каталоге нет `run-report.md`.
    """
    path = run_dir / "run-report.md"
    if not path.is_file():
        raise FileNotFoundError(path)
    return parse_metrics(path.read_text(encoding="utf-8"))


def missing_metrics(metrics: dict[str, str]) -> list[str]:
    """Перечислить обязательные метрики, которые не заполнены.

    Args:
        metrics: Разобранные метрики прогона.

    Returns:
        Имена метрик в порядке `REQUIRED_METRICS`.
    """
    missing: list[str] = []
    for name in REQUIRED_METRICS:
        value = metrics.get(name, "")
        if _normalize(value) in PLACEHOLDER_VALUES:
            missing.append(name)
    return missing


def main(argv: list[str]) -> int:
    """Точка входа CLI.

    Args:
        argv: Аргументы командной строки (путь к прогону).

    Returns:
        0 — сводка построена (в том числе для прогона без метрик);
        1 — отчёта прогона нет; 2 — неверные аргументы.
    """
    if len(argv) < 2:
        print("Использование: session_analytics.py <output/run-id>")
        return 2
    run_dir = Path(argv[1])
    try:
        metrics = summarize_run(run_dir)
    except FileNotFoundError:
        print(f"session_analytics: нет файла {run_dir / 'run-report.md'}")
        return 1

    if not metrics:
        print(
            f"session_analytics: в {run_dir}/run-report.md нет секции "
            f"«{METRICS_HEADING}» — прогон записан до P5"
        )
        return 0

    print(f"Метрики прогона {run_dir.name}:")
    for name in REQUIRED_METRICS:
        print(f"  {name}: {metrics.get(name, '—')}")
    missing = missing_metrics(metrics)
    if missing:
        print(f"  не заполнено: {', '.join(missing)} (human-review)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
