"""Проверка полноты набора диаграмм прогона (DoR-отчёт).

Зачем. `check_run` проверяет согласованность присутствующих диаграмм, но не
их полноту: прогон с 11 из 14 `.mmd` проходил гейт. `prompts/start.md`
разрешает два уровня — базовый (4 диаграммы) и расширенный (10 + BPMN), — но
частично заполненный расширенный уровень не является допустимым.

Профили:

- `auto` (по умолчанию): если в прогоне нет ни одной расширенной диаграммы,
  ожидается базовый набор; если есть хотя бы одна, ожидается полный;
- `base`, `full` — явно;
- `startup`, `enterprise`, `ai`, `china` — профили DoR, собранные из паков
  (`prompts/start.md`, блок «Паки»): startup — лёгкий набор, enterprise —
  полный + домены/процессы/данные, ai — полный + AI-пак, china — как
  enterprise (региональные требования живут в чек-листах, не в диаграммах).

Режим: по умолчанию отчёт не роняет гейт (как `check-policy`); `--strict`
даёт код 1 при недостающих диаграммах.

Запуск: `python3 scripts/check_dor.py output/auto-004 --profile full` или
`make check-dor RUN=auto-004 STRICT=1`.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

#: Базовый уровень: создаётся всегда.
BASE_DIAGRAMS: tuple[str, ...] = (
    "use-case",
    "sequence",
    "c4-context",
    "c4-container",
)

#: Расширенный уровень: 10 `.mmd`; канонический BPMN проверяется отдельно.
EXTENDED_DIAGRAMS: tuple[str, ...] = (
    "er",
    "dfd-context",
    "dfd-level1",
    "dfd-level2",
    "dfd-level3",
    "c4-component",
    "c4-deployment",
    "bpmn-process",
    "activity",
    "gantt",
)

#: Полный набор `.mmd`.
FULL_DIAGRAMS: tuple[str, ...] = BASE_DIAGRAMS + EXTENDED_DIAGRAMS

#: Канонический BPMN 2.0 XML рядом с `bpmn-process.mmd`.
BPMN_FILE = "bpmn-process.bpmn"

#: Паки диаграмм: имя -> ожидаемые `.mmd`. Источник — `prompts/start.md`,
#: блок «Паки»; согласованность с scaffold проверяет `tests/test_diagram_catalog.py`.
PACK_DIAGRAMS: dict[str, tuple[str, ...]] = {
    "behavior": ("state",),
    "domain": ("domain-map", "event-storming"),
    "process": ("dmn", "sipoc"),
    "ux": ("service-blueprint",),
    "data": ("data-lineage",),
    "ai": ("rag-pipeline", "vector-schema", "agent-workflow", "prompt-flow", "feedback-loop"),
    "infra": ("network-topology", "iac"),
    "architecture": ("c4-code",),
}


def pack_diagrams(*names: str) -> tuple[str, ...]:
    """Собрать ожидаемые `.mmd` из паков.

    Args:
        *names: Имена паков (`ai`, `domain`, ...).

    Returns:
        Объединение диаграмм паков без дубликатов, в порядке перечисления.

    Raises:
        KeyError: Пак неизвестен — опечатка не должна проходить молча.
    """
    result: list[str] = []
    for name in names:
        for diagram in PACK_DIAGRAMS[name]:
            if diagram not in result:
                result.append(diagram)
    return tuple(result)


#: Профили полноты: имя -> ожидаемые `.mmd`.
PROFILES: dict[str, tuple[str, ...]] = {
    "base": BASE_DIAGRAMS,
    "full": FULL_DIAGRAMS,
    "startup": (*BASE_DIAGRAMS, "er", *pack_diagrams("behavior")),
    "enterprise": (
        *FULL_DIAGRAMS,
        *pack_diagrams("behavior", "domain", "process", "data", "architecture"),
    ),
    "ai": (*FULL_DIAGRAMS, *pack_diagrams("behavior", "data", "ai")),
    "china": (
        *FULL_DIAGRAMS,
        *pack_diagrams("behavior", "domain", "process", "data", "architecture"),
    ),
}


def resolve_profile(run_dir: Path, profile: str) -> tuple[tuple[str, ...], str]:
    """Определить ожидаемый набор диаграмм по профилю.

    Args:
        run_dir: Каталог прогона (`output/<run-id>`).
        profile: Имя профиля (`auto`, `base`, `full`, `startup`, ...).

    Returns:
        Пара «ожидаемые `.mmd`» и фактическое имя профиля.

    Raises:
        ValueError: Профиль неизвестен.
    """
    if profile != "auto":
        if profile not in PROFILES:
            raise ValueError(f"неизвестный профиль: {profile}")
        return PROFILES[profile], profile

    diagrams = run_dir / "diagrams"
    present = {path.stem for path in diagrams.glob("*.mmd")} if diagrams.is_dir() else set()
    if present & set(EXTENDED_DIAGRAMS):
        return FULL_DIAGRAMS, "full"
    return BASE_DIAGRAMS, "base"


def check_dor(run_dir: Path, profile: str = "auto") -> list[str]:
    """Проверить полноту набора диаграмм прогона.

    Args:
        run_dir: Каталог прогона (`output/<run-id>`).
        profile: Имя профиля полноты; `auto` выводит его из состава файлов.

    Returns:
        Список проблем; пустой список означает, что набор полон.
    """
    if not run_dir.is_dir():
        return [f"нет каталога прогона: {run_dir}"]

    expected, resolved = resolve_profile(run_dir, profile)
    diagrams = run_dir / "diagrams"
    present = {path.stem for path in diagrams.glob("*.mmd")} if diagrams.is_dir() else set()

    problems = [
        f"нет диаграммы {name}.mmd (профиль {resolved})"
        for name in expected
        if name not in present
    ]
    if "bpmn-process" in expected and not (diagrams / BPMN_FILE).is_file():
        problems.append(f"нет {BPMN_FILE} (профиль {resolved})")
    if diagrams.is_dir():
        for png in sorted(diagrams.glob("*.png")):
            if png.stem not in present:
                problems.append(f"{png.name}: PNG без источника .mmd")
    return problems


def _present(run_dir: Path) -> int:
    """Сколько `.mmd` реально лежит в прогоне.

    Args:
        run_dir: Каталог прогона (`output/<run-id>`).

    Returns:
        Количество `.mmd`-файлов (0, если каталога нет).
    """
    diagrams = run_dir / "diagrams"
    return len(list(diagrams.glob("*.mmd"))) if diagrams.is_dir() else 0


def main(argv: list[str] | None = None) -> int:
    """Точка входа CLI.

    Args:
        argv: Аргументы командной строки; по умолчанию — `sys.argv[1:]`.

    Returns:
        0 — проблем нет или режим без `--strict`; 1 — есть проблемы и `--strict`.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path, help="каталог прогона (output/<run-id>)")
    parser.add_argument(
        "--profile",
        choices=("auto", *PROFILES),
        default="auto",
        help="профиль полноты (по умолчанию auto)",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="exit 1 при недостающих диаграммах",
    )
    args = parser.parse_args(argv)

    run_dir = Path(args.run_dir)
    profile = str(args.profile)
    problems = check_dor(run_dir, profile)
    expected, resolved = resolve_profile(run_dir, profile)

    if problems:
        print(
            f"check-dor: требует внимания ({run_dir}, profile={resolved}) — "
            f"{len(problems)} проблем:"
        )
        for problem in problems:
            print(f"  - {problem}")
        if args.strict:
            print("check-dor: STRICT=1 — гейт не пройден")
            return 1
        return 0

    print(
        f"check-dor: OK ({run_dir}, profile={resolved}, "
        f"требуется {len(expected)}, найдено {_present(run_dir)})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
