"""Фреймворк «идея → спецификация» как устанавливаемый пакет.

Пакет поставляет файловое содержимое фреймворка (промпты, методы, скилы,
субагентов, шаблоны, eval-кейсы, прогоны, документы, скрипты и тесты) и
разворачивает его в каталог потребителя.

Почему копирование, а не импорт: материалы воркшопа и Makefile ссылаются на
файлы относительными путями (`framework/prompts/start.md`), значит эти файлы
обязаны существовать на диске. Логику фреймворка читают человек и проверки,
а не импортируют как модуль.

Манифест `.export-manifest.json` в целевом каталоге хранит версию пакета и
sha256 каждого файла: команда `verify` ловит ручные правки и удаления.

Запуск: `idea-to-spec-framework export --dest framework`; проверка
подключения по пути — `idea-to-spec-framework connect --framework <dir>`.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path

#: Версия пакета. Совпадение с `pyproject.toml` проверяет tests/test_export.py.
__version__ = "0.3.1"

#: Каталог с содержимым внутри установленного колеса. В репозитории его нет:
#: он собирается hatchling-ом (`force-include`) при сборке пакета.
DATA_DIR = "_itsf"

#: Верхнеуровневые элементы, которые не попадают в экспорт.
DEFAULT_EXCLUDE: tuple[str, ...] = (".github",)

#: Манифест, который пишется в целевой каталог.
MANIFEST_NAME = ".export-manifest.json"

#: Обязательные элементы подключения по пути.
CONNECT_REQUIRED: tuple[str, ...] = (
    "prompts/start.md",
    "prompts/roles",
    "skills",
    "templates",
    "Makefile",
    "scripts/check_run.py",
)

#: Служебные каталоги и файлы, которые пропускаются при экспорте.
_SKIP_PARTS = frozenset(
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
_SKIP_SUFFIXES = (".local.json",)


class ExportError(RuntimeError):
    """Экспорт невозможен: цель занята или содержимое пакета не найдено."""


@dataclass(frozen=True)
class ExportReport:
    """Итог экспорта: куда, какая версия, сколько файлов."""

    dest: Path
    version: str
    files: int


def _resource_root() -> Path:
    """Отдать каталог с содержимым фреймворка.

    Returns:
        Каталог внутри установленного пакета (`_itsf`) либо корень исходного
        дерева репозитория: второй случай нужен тестам и разработке.

    Raises:
        ExportError: содержимое не найдено ни в пакете, ни в исходном дереве.
    """
    module_dir = Path(__file__).resolve().parent
    packaged = module_dir / DATA_DIR
    if packaged.is_dir():
        return packaged
    if (module_dir / "prompts").is_dir() and (module_dir / "templates").is_dir():
        return module_dir
    raise ExportError(
        f"содержимое не найдено: нет ни {packaged}, ни {module_dir}/prompts — "
        "пакет собран без force-include"
    )


def _iter_files(root: Path, exclude: tuple[str, ...]) -> Iterator[tuple[str, Path]]:
    """Перечислить файлы для экспорта.

    Args:
        root: Каталог-источник содержимого.
        exclude: Имена верхнеуровневых элементов, которые пропускаются.

    Yields:
        Пары «относительный POSIX-путь, абсолютный путь».
    """
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if relative.parts[0] in exclude or relative.name == MANIFEST_NAME:
            continue
        if _SKIP_PARTS.intersection(relative.parts):
            continue
        if path.name.endswith(_SKIP_SUFFIXES):
            continue
        yield relative.as_posix(), path


def _sha256(path: Path) -> str:
    """SHA-256 файла."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_manifest(dest: Path) -> dict[str, object] | None:
    """Прочитать манифест прежнего экспорта, если он есть."""
    manifest = dest / MANIFEST_NAME
    if not manifest.is_file():
        return None
    data: dict[str, object] = json.loads(manifest.read_text(encoding="utf-8"))
    return data


def _prepare_dest(dest: Path, *, force: bool) -> None:
    """Подготовить целевой каталог или отказаться.

    Перезапись разрешена только для пустого каталога или для прежнего экспорта
    (в нём есть манифест): чужие файлы никогда не удаляются.

    Args:
        dest: Целевой каталог.
        force: Разрешить перезапись прежнего экспорта.

    Raises:
        ExportError: цель занята, это файл или чужой непустой каталог.
    """
    if not dest.exists():
        dest.mkdir(parents=True)
        return
    if not dest.is_dir():
        raise ExportError(f"{dest}: существует и не является каталогом")
    if not any(dest.iterdir()):
        return
    if not force:
        raise ExportError(f"{dest}: каталог не пуст; нужен --force")
    if _read_manifest(dest) is None:
        raise ExportError(f"{dest}: непустой каталог создан не экспортом; удалите его вручную")
    shutil.rmtree(dest)
    dest.mkdir(parents=True)


def export(dest: Path, *, force: bool = False) -> ExportReport:
    """Развернуть содержимое фреймворка в `dest`.

    Args:
        dest: Целевой каталог (у потребителя это `framework/`).
        force: Перезаписать прежний экспорт, созданный этой же командой.

    Returns:
        Отчёт с числом файлов и версией пакета.

    Raises:
        ExportError: цель занята или содержимое пакета не найдено.
    """
    target = dest.resolve()
    _prepare_dest(target, force=force)

    checksums: dict[str, str] = {}
    for relative, source in _iter_files(_resource_root(), DEFAULT_EXCLUDE):
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        checksums[relative] = _sha256(destination)

    manifest = {
        "package": "idea-to-spec-framework",
        "version": __version__,
        "files": checksums,
    }
    (target / MANIFEST_NAME).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return ExportReport(dest=target, version=__version__, files=len(checksums))


def verify(dest: Path) -> list[str]:
    """Сверить каталог с манифестом экспорта.

    Проверяются версия, наличие файлов и их sha256. Лишние файлы проблемой не
    считаются: в каталоге появляются артефакты сборки (`.venv`, прогоны eval).

    Args:
        dest: Каталог, куда выполнялся экспорт.

    Returns:
        Список проблем; пустой список — расхождений нет.
    """
    target = dest.resolve()
    manifest = _read_manifest(target)
    if manifest is None:
        return [f"MANIFEST MISSING: {target / MANIFEST_NAME}"]

    problems: list[str] = []
    version = manifest.get("version")
    if version != __version__:
        problems.append(f"VERSION MISMATCH: {version} != {__version__}")

    raw_files = manifest.get("files")
    if not isinstance(raw_files, dict):
        return [*problems, f"MANIFEST BROKEN: {target / MANIFEST_NAME}"]

    for relative, expected in raw_files.items():
        path = target / str(relative)
        if not path.is_file():
            problems.append(f"MISSING: {relative}")
        elif _sha256(path) != expected:
            problems.append(f"MODIFIED: {relative}")
    return problems


def connect(framework: Path) -> list[str]:
    """Проверить каталог как точку подключения фреймворка.

    Проверяется только контракт «путь + точка входа»: файлы и каталоги,
    которые обязаны существовать, чтобы агент мог открыть
    `prompts/start.md` и разрешить относительные пути.

    Args:
        framework: Каталог фреймворка (исходный репозиторий или export).

    Returns:
        Список проблем; пустой список — подключение валидно.
    """

    root = framework.resolve()
    if not root.is_dir():
        return [f"нет каталога: {root}"]

    problems = [
        f"MISSING: {relative}"
        for relative in CONNECT_REQUIRED
        if not (root / relative).exists()
    ]
    skills = root / "skills"
    if skills.is_dir() and not any(skills.glob("*/SKILL.md")):
        problems.append("EMPTY: skills/*/SKILL.md")
    return problems


def build_parser() -> argparse.ArgumentParser:
    """Собрать парсер аргументов командной строки."""
    parser = argparse.ArgumentParser(
        prog="idea-to-spec-framework",
        description="Развернуть содержимое фреймворка или проверить развёрнутое.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    commands = parser.add_subparsers(dest="command", required=True)

    exporter = commands.add_parser("export", help="развернуть содержимое в каталог")
    exporter.add_argument("--dest", type=Path, required=True, help="целевой каталог")
    exporter.add_argument("--force", action="store_true", help="перезаписать прежний экспорт")

    checker = commands.add_parser("verify", help="сверить каталог с манифестом")
    checker.add_argument("--dest", type=Path, required=True, help="каталог экспорта")

    connector = commands.add_parser("connect", help="проверить подключение по пути")
    connector.add_argument("--framework", type=Path, required=True, help="каталог фреймворка")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Точка входа CLI.

    Args:
        argv: Аргументы командной строки (по умолчанию `sys.argv[1:]`).

    Returns:
        0 — успех, 1 — найдены расхождения, 2 — ошибка экспорта.
    """
    args = build_parser().parse_args(argv)
    if args.command == "connect":
        framework = Path(args.framework).resolve()
        problems = connect(framework)
        if problems:
            print("connect: FAILED")
            for problem in problems:
                print(f"  {problem}")
            return 1
        print(f"entry point: {framework / 'prompts' / 'start.md'}")
        print(f"next: make -C {framework} scaffold RUN=demo-001")
        return 0

    dest: Path = Path(args.dest).resolve()
    try:
        if args.command == "export":
            report = export(dest, force=bool(args.force))
            print(f"export: {report.dest} v{report.version}, файлов {report.files}")
            return 0
        problems = verify(dest)
    except ExportError as error:
        print(f"{args.command}: FAILED — {error}", file=sys.stderr)
        return 2

    if problems:
        print("verify: FAILED")
        for problem in sorted(problems):
            print(f"  {problem}")
        return 1
    print(f"verify: OK ({dest}, v{__version__})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
