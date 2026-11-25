"""Проверка реестра скилов: метаданные жизненного цикла.

Зачем. `skills/registry.yaml` отвечает на вопросы, которые иначе задают
заново каждую сессию: какая у скила версия, что он берёт на вход, от чего
зависит, чем измерен, кто владелец и насколько высок риск. Если реестр
разъедется с каталогом `skills/*.md`, он превратится в мёртвый файл:
скил добавлен — записи нет; зависимость не резолвится — никто не заметил.

Проверяется:
- каждый `skills/*.md` (кроме README) имеет запись, и наоборот;
- обязательные поля на месте, `scope` и `owner` непустые;
- `version` — semver, `risk_level` — low/medium/high;
- `file` указывает на существующий `.md` внутри `skills/`, имя совпадает;
- `dependencies` резолвятся, без self-зависимостей и циклов;
- `evals` ссылаются на существующий eval-кейс или файл (пустой список допустим).

Запуск: `python3 scripts/check_skills_registry.py` или `make check-skills`.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml

#: Корень репозитория (скрипт лежит в `scripts/`).
REPO_ROOT = Path(__file__).resolve().parent.parent

#: Путь к реестру относительно корня.
REGISTRY_PATH = Path("skills") / "registry.yaml"

#: Каталог скилов относительно корня.
SKILLS_DIR = Path("skills")

#: Файл eval-кейсов (источник допустимых ссылок из поля `evals`).
CASES_PATH = Path("eval") / "cases" / "roles.jsonl"

#: Обязательные поля записи.
REQUIRED_FIELDS = (
    "name",
    "file",
    "version",
    "scope",
    "inputs",
    "outputs",
    "dependencies",
    "evals",
    "owner",
    "risk_level",
)

#: Списочные поля записи.
LIST_FIELDS = ("inputs", "outputs", "dependencies", "evals")

#: Допустимые уровни риска.
RISK_LEVELS = frozenset({"low", "medium", "high"})

#: Версия схемы реестра.
SCHEMA_VERSION = 1

#: Semver: major.minor.patch + необязательные prerelease/build.
_SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$")

#: Имя скила: kebab-case.
_NAME_RE = re.compile(r"^[a-z][a-z0-9-]*$")


def load_registry(path: Path) -> dict[str, Any]:
    """Загрузить реестр из YAML.

    Args:
        path: Путь к `registry.yaml`.

    Returns:
        Разобранный словарь реестра.

    Raises:
        ValueError: файл пуст или верхний уровень — не объект.
        yaml.YAMLError: синтаксическая ошибка YAML.
    """

    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("верхний уровень реестра должен быть объектом")
    return data


def _case_ids(root: Path) -> set[str]:
    """Собрать идентификаторы eval-кейсов из `eval/cases/roles.jsonl`."""

    path = root / CASES_PATH
    if not path.exists():
        return set()
    ids: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(record, dict):
            continue
        metadata = record.get("metadata")
        variables = record.get("vars")
        for source in (metadata, variables):
            if isinstance(source, dict) and isinstance(source.get("id"), str):
                ids.add(source["id"])
    return ids


def _check_fields(record: dict[str, Any], label: str, problems: list[str]) -> None:
    """Проверить наличие и типы обязательных полей записи."""

    for field in REQUIRED_FIELDS:
        if field not in record:
            problems.append(f"{label}: нет поля {field!r}")
    for field in ("name", "file", "scope", "owner"):
        value = record.get(field)
        if field in record and not isinstance(value, str):
            problems.append(f"{label}: поле {field} должно быть строкой")
    if "version" in record and not isinstance(record.get("version"), str):
        problems.append(f"{label}: версия должна быть строкой в semver (X.Y.Z)")
    if "risk_level" in record and not isinstance(record.get("risk_level"), str):
        problems.append(f"{label}: risk_level должен быть строкой")
    name = record.get("name")
    if isinstance(name, str) and not _NAME_RE.match(name):
        problems.append(f"{label}: имя {name!r} не в kebab-case")
    for field in ("scope", "owner"):
        value = record.get(field)
        if isinstance(value, str) and not value.strip():
            problems.append(f"{label}: поле {field} пустое")
    version = record.get("version")
    if isinstance(version, str) and not _SEMVER_RE.match(version):
        problems.append(f"{label}: версия {version!r} не semver (нужно X.Y.Z)")
    risk = record.get("risk_level")
    if isinstance(risk, str) and risk not in RISK_LEVELS:
        allowed = ", ".join(sorted(RISK_LEVELS))
        problems.append(f"{label}: risk_level {risk!r} вне {allowed}")
    for field in LIST_FIELDS:
        value = record.get(field)
        if field not in record:
            continue
        if not isinstance(value, list) or any(
            not isinstance(entry, str) or not entry.strip() for entry in value
        ):
            problems.append(f"{label}: поле {field} должно быть списком непустых строк")


def _check_file(root: Path, record: dict[str, Any], label: str, problems: list[str]) -> str | None:
    """Проверить, что `file` указывает на существующий скил внутри `skills/`."""

    raw = record.get("file")
    if not isinstance(raw, str) or not raw.strip():
        return None
    path = Path(raw)
    if path.is_absolute() or ".." in path.parts:
        problems.append(f"{label}: file {raw!r} должен быть относительным путём в skills/")
        return raw
    if path.parent != SKILLS_DIR:
        problems.append(f"{label}: file {raw!r} вне skills/")
    if path.suffix != ".md":
        problems.append(f"{label}: file {raw!r} не .md")
    if not (root / path).exists():
        problems.append(f"{label}: file {raw!r} не найден")
    name = record.get("name")
    if isinstance(name, str) and path.stem != name:
        problems.append(f"{label}: имя {name!r} не совпадает с файлом {path.stem!r}")
    return raw


def _find_cycle(graph: dict[str, list[str]]) -> list[str] | None:
    """Найти цикл в графе зависимостей (DFS, три цвета)."""

    state: dict[str, int] = {}
    stack: list[str] = []

    def visit(node: str) -> list[str] | None:
        state[node] = 1
        stack.append(node)
        for neighbour in graph.get(node, []):
            if state.get(neighbour) == 1:
                return [*stack[stack.index(neighbour) :], neighbour]
            if state.get(neighbour, 0) == 0:
                found = visit(neighbour)
                if found is not None:
                    return found
        stack.pop()
        state[node] = 2
        return None

    for node in graph:
        if state.get(node, 0) == 0:
            found = visit(node)
            if found is not None:
                return found
    return None


def _check_dependencies(entries: list[tuple[str, str, list[str]]], problems: list[str]) -> None:
    """Проверить, что зависимости резолвятся и не образуют циклов."""

    names = {name for _, name, _ in entries}
    graph: dict[str, list[str]] = {}
    for label, name, dependencies in entries:
        graph[name] = dependencies
        for dependency in dependencies:
            if dependency == name:
                problems.append(f"{label}: скил зависит сам от себя")
            elif dependency not in names:
                problems.append(f"{label}: зависимость {dependency!r} не найдена в реестре")
    cycle = _find_cycle(graph)
    if cycle is not None:
        problems.append("цикл зависимостей: " + " -> ".join(cycle))


def _check_evals(
    root: Path, label: str, references: list[str], cases: set[str], problems: list[str]
) -> None:
    """Проверить ссылки `evals`: существующий кейс или существующий файл."""

    for reference in references:
        path_part = reference.split("::", 1)[0]
        looks_like_path = "/" in path_part or path_part.endswith((".md", ".py", ".jsonl", ".json"))
        if looks_like_path:
            if not (root / path_part).exists():
                problems.append(f"{label}: evals ссылается на несуществующий файл {reference!r}")
        elif reference not in cases:
            problems.append(f"{label}: evals ссылается на неизвестный кейс {reference!r}")


def check_registry(root: Path) -> list[str]:
    """Проверить реестр скилов в указанном корне.

    Args:
        root: Корень репозитория.

    Returns:
        Список проблем (пустой, если реестр корректен).
    """

    registry_path = root / REGISTRY_PATH
    if not registry_path.exists():
        return [f"{REGISTRY_PATH.as_posix()}: файл не найден"]
    try:
        data = load_registry(registry_path)
    except yaml.YAMLError as exc:
        return [f"{REGISTRY_PATH.as_posix()}: невалидный YAML ({exc})"]
    except ValueError as exc:
        return [f"{REGISTRY_PATH.as_posix()}: {exc}"]

    problems: list[str] = []
    if data.get("schema") != SCHEMA_VERSION:
        problems.append(f"{REGISTRY_PATH.as_posix()}: schema должна быть {SCHEMA_VERSION}")
    records = data.get("skills")
    if not isinstance(records, list) or not records:
        problems.append(f"{REGISTRY_PATH.as_posix()}: skills должен быть непустым списком")
        return problems

    skills_dir = root / SKILLS_DIR
    if not skills_dir.is_dir():
        problems.append(f"{SKILLS_DIR.as_posix()}: каталог скилов не найден")

    seen_names: set[str] = set()
    seen_files: set[str] = set()
    dependency_entries: list[tuple[str, str, list[str]]] = []
    eval_entries: list[tuple[str, list[str]]] = []

    for index, record in enumerate(records):
        if not isinstance(record, dict):
            problems.append(f"skills[{index}]: запись не объект")
            continue
        raw_name = record.get("name")
        name = raw_name if isinstance(raw_name, str) and raw_name else None
        label = f"skills/{name}" if name else f"skills[{index}]"
        _check_fields(record, label, problems)
        raw_file = _check_file(root, record, label, problems)
        if name is not None:
            if name in seen_names:
                problems.append(f"{label}: повтор имени {name!r}")
            seen_names.add(name)
        if raw_file is not None:
            if raw_file in seen_files:
                problems.append(f"{label}: повтор файла {raw_file!r}")
            seen_files.add(raw_file)
        dependencies = record.get("dependencies")
        if name is not None and isinstance(dependencies, list):
            dependency_entries.append(
                (label, name, [str(item) for item in dependencies if isinstance(item, str)])
            )
        references = record.get("evals")
        if isinstance(references, list):
            eval_entries.append(
                (label, [str(item) for item in references if isinstance(item, str)])
            )

    if skills_dir.is_dir():
        for skill_file in sorted(skills_dir.glob("*.md")):
            if skill_file.name == "README.md":
                continue
            relative = f"{SKILLS_DIR.as_posix()}/{skill_file.name}"
            if relative not in seen_files:
                problems.append(f"{relative}: скил без записи в registry.yaml")

    _check_dependencies(dependency_entries, problems)
    cases = _case_ids(root)
    for label, references in eval_entries:
        _check_evals(root, label, references, cases, problems)
    return problems


def main(argv: list[str] | None = None) -> int:
    """Проверить реестр скилов.

    Args:
        argv: Аргументы командной строки (по умолчанию — `sys.argv[1:]`).

    Returns:
        0 — реестр корректен; 1 — есть проблемы.
    """

    parser = argparse.ArgumentParser(description="Проверка реестра скилов")
    parser.add_argument(
        "--root",
        type=Path,
        default=REPO_ROOT,
        help="корень репозитория (по умолчанию — каталог над scripts/)",
    )
    args = parser.parse_args(argv)

    problems = check_registry(args.root)
    if problems:
        print("check-skills: FAILED")
        for problem in problems:
            print(f"  {problem}")
        return 1

    print("check-skills: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
