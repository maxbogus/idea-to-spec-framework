"""Проверка публикуемости содержимого фреймворка.

Зачем. Фреймворк — публичный MIT-пакет. В него не должны попадать домашние
пути, токены и приватные ключи, а также ссылки на личную конфигурацию Cline:
фреймворк обязан быть самодостаточным и работать у потребителя, у которого
`~/.cline` нет.

Проверяется:
- запрещённые для git файлы (`.env`, `*.pem`);
- известные маркеры: абсолютные домашние пути, GitHub/AWS токены,
  заголовки приватных ключей, ссылки на `~/.cline` и `cline-agent-playbook`.

Сканер — сеть, а не гарантия: он ловит известные маркеры, а не намерение.
Запуск: `python3 scripts/check_public.py` или `make check-public`.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

#: Корень репозитория (скрипт лежит в `scripts/`).
REPO_ROOT = Path(__file__).resolve().parent.parent

#: Расширения, которые не должны попадать в git.
FORBIDDEN_TRACKED_SUFFIXES = (".pem", ".env")

#: Каталоги, которые не сканируются: артефакты окружения.
SKIP_PARTS = frozenset(
    {
        ".git",
        ".venv",
        "node_modules",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
    }
)

#: Файлы больше этого размера не сканируются: lock-файлы и бинарь.
MAX_SCAN_BYTES = 1_000_000

#: Сканер и его тест содержат сами паттерны в виде строк — их не сканируем.
ALLOWLIST = frozenset({"scripts/check_public.py", "tests/test_check_public.py"})

#: Признаки, недопустимые в публикуемом содержимом.
PATTERNS: dict[str, re.Pattern[str]] = {
    "personal path": re.compile(r"(?<![\w.-])/home/[A-Za-z0-9._-]+"),
    "windows user path": re.compile(r"[A-Za-z]:\\\\Users\\\\[A-Za-z0-9][A-Za-z0-9._-]*"),
    "private key": re.compile(r"BEGIN [A-Z ]*PRIVATE KEY"),
    "github token": re.compile(r"\b(?:ghp|gho|ghs)_[A-Za-z0-9]{20,}\b"),
    "aws key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "external cline dependency": re.compile(r"(?:~/\.cline|cline-agent-playbook)"),
}


def scan_text(text: str) -> list[str]:
    """Найти недопустимые маркеры в тексте.

    Args:
        text: Содержимое файла.

    Returns:
        Список найденных маркеров (пустой, если текст чист).
    """

    found: list[str] = []
    for name, pattern in PATTERNS.items():
        match = pattern.search(text)
        if match:
            found.append(f"{name}: {match.group(0)[:40]!r}")
    return found


def _tracked_files(root: Path) -> list[str]:
    """Вернуть файлы, отслеживаемые git в указанном корне.

    Args:
        root: Корень репозитория.

    Returns:
        Пути от корня; пустой список, если git недоступен или репозитория нет.
    """

    commands = (
        ["git", "-C", str(root), "ls-files"],
        ["git", "-C", str(root), "ls-files", "--others", "--exclude-standard"],
    )
    found: set[str] = set()
    for command in commands:
        try:
            completed = subprocess.run(command, capture_output=True, text=True, check=True)
        except (OSError, subprocess.CalledProcessError):
            return []
        found.update(line for line in completed.stdout.splitlines() if line)
    return sorted(found)


def check_public(root: Path, tracked: list[str] | None = None) -> list[str]:
    """Проверить, что содержимое можно публиковать.

    Args:
        root: Корень репозитория.
        tracked: Список путей от корня; по умолчанию — `git ls-files`.

    Returns:
        Список проблем (пустой, если содержимое чистое).
    """

    paths = _tracked_files(root) if tracked is None else tracked
    problems: list[str] = []
    for relative in paths:
        parts = Path(relative).parts
        if relative in ALLOWLIST or SKIP_PARTS.intersection(parts):
            continue
        if relative.endswith(FORBIDDEN_TRACKED_SUFFIXES):
            problems.append(f"{relative}: запрещённый для git файл")
            continue
        path = root / relative
        if not path.is_file() or path.stat().st_size > MAX_SCAN_BYTES:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for marker in scan_text(text):
            problems.append(f"{relative}: {marker}")
    return problems


def main(argv: list[str] | None = None) -> int:
    """Проверить публикуемость содержимого.

    Args:
        argv: Аргументы командной строки (по умолчанию — `sys.argv[1:]`).

    Returns:
        0 — проблем нет; 1 — есть проблемы.
    """

    parser = argparse.ArgumentParser(description="Проверка публикуемости фреймворка")
    parser.add_argument("--root", type=Path, default=REPO_ROOT, help="корень репозитория")
    args = parser.parse_args(argv)

    problems = check_public(args.root)
    if problems:
        print("check-public: FAILED")
        for problem in problems:
            print(f"  {problem}")
        return 1

    print("check-public: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
