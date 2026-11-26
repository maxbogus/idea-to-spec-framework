"""Проверка применимости и полноты набора диаграмм прогона (DoR-отчёт).

Зачем. `check_run` проверяет согласованность присутствующих диаграмм, но не их
полноту и не их содержание: scaffold копирует все шаблоны, поэтому «файл есть»
верно даже для пустышки. Прогон с 11 из 14 `.mmd` проходил гейт, а
`dfd-level2.mmd`, оставшийся копией шаблона, считался построенным.

Два правила P2:

1. **Применимость вместо наличия.** В `run-report.md` §«Пакеты диаграмм» прогон
   объявляет неприменимые диаграммы с причиной:
   `{"not_applicable": {"dfd-level2": "процесс описан одним шагом (spec.md §9)"}}`.
   Ожидаемый набор = профиль минус объявленные неприменимыми. Декларация без
   причины — проблема; построенная диаграмма, объявленная неприменимой, — тоже
   (декларация и артефакт расходятся). Старый прогон без блока принимается:
   все диаграммы применимы.
2. **Пустышка — не диаграмма.** Файл, совпадающий с `templates/<name>.mmd`
   после нормализации, или файл со скелетными подписями («2.1. Под-процесс»,
   «1. Шаг 1») помечается как шаблонная пустышка.

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
import json
import re
import sys
from pathlib import Path

from idea_to_spec.paths import REPO_ROOT

#: Каталог шаблонов: по нему распознаётся шаблонная пустышка.
TEMPLATES_DIR = REPO_ROOT / "templates"

#: Файл прогона, где объявляется применимость диаграмм.
RUN_REPORT = "run-report.md"

#: Раздел отчёта с декларацией паков и применимости.
_APPLICABILITY_SECTION_RE = re.compile(r"(?ms)^## Пакеты диаграмм[ \t]*$(.*?)(?=^## |\Z)")
#: JSON-блок внутри раздела.
_JSON_BLOCK_RE = re.compile(r"```json\n(.*?)```", re.S)
#: Ключ декларации: диаграмма → причина неприменимости.
NOT_APPLICABLE_KEY = "not_applicable"
#: Скелетные подписи шаблонов: если они остались, диаграмма не построена.
_PLACEHOLDER_RE = re.compile(r'"(?:\d+(?:\.\d+)*)\.\s*(?:Шаг \d+|Под-процесс)"')
#: Формулировки, которыми нельзя объявлять неприменимость (причина не названа).
_EMPTY_REASONS = frozenset({"", "-", "—", "–", "нет", "n/a", "na"})


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


def load_applicability(run_dir: Path) -> tuple[dict[str, str], list[str]]:
    """Прочитать декларацию неприменимых диаграмм из `run-report.md`.

    Наличие файла больше не считается доказательством: scaffold копирует все
    шаблоны, поэтому «диаграмма есть» верно даже для пустышки. Применимость
    объявляется явно — диаграмма → причина, — и проверяется здесь.

    Args:
        run_dir: Каталог прогона.

    Returns:
        Пары «декларация неприменимости» и «проблемы разбора». Пустая
        декларация без проблем — блок не заполнен: все диаграммы применимы
        (поведение старых прогонов сохраняется).
    """
    path = run_dir / RUN_REPORT
    if not path.is_file():
        return {}, []
    match = _APPLICABILITY_SECTION_RE.search(path.read_text(encoding="utf-8"))
    if match is None:
        return {}, []

    plan: dict[str, str] = {}
    problems: list[str] = []
    for index, block in enumerate(_JSON_BLOCK_RE.findall(match.group(1)), start=1):
        try:
            parsed = json.loads(block)
        except json.JSONDecodeError as exc:
            problems.append(
                f"{RUN_REPORT}: блок «Пакеты диаграмм» №{index} — невалидный JSON ({exc})"
            )
            continue
        if not isinstance(parsed, dict) or NOT_APPLICABLE_KEY not in parsed:
            problems.append(
                f"{RUN_REPORT}: блок №{index} без ключа {NOT_APPLICABLE_KEY!r} — "
                "применимость не объявлена"
            )
            continue
        raw = parsed[NOT_APPLICABLE_KEY]
        if not isinstance(raw, dict):
            problems.append(
                f"{RUN_REPORT}: {NOT_APPLICABLE_KEY} должен быть объектом "
                "«диаграмма → причина»"
            )
            continue
        for diagram, reason in raw.items():
            plan[str(diagram)] = str(reason or "")
    return plan, problems


def _normalize(text: str) -> str:
    """Привести диаграмму к сравнимому виду: без комментариев и пробелов.

    Args:
        text: Содержимое `.mmd`/`.bpmn`.

    Returns:
        Нормализованный текст.
    """
    lines = [line.strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line and not line.startswith("%%"))


def stub_reason(run_dir: Path, name: str) -> str:
    """Назвать причину, по которой диаграмма — шаблонная пустышка.

    Два признака: файл совпадает с шаблоном после нормализации или в нём
    остались скелетные подписи (`2.1. Под-процесс`, `1. Шаг 1`). Оба означают,
    что диаграмма скопирована, а не построена из артефактов.

    Args:
        run_dir: Каталог прогона.
        name: Имя диаграммы без расширения.

    Returns:
        Причина или пустая строка, если диаграмма содержательная.
    """
    path = run_dir / "diagrams" / f"{name}.mmd"
    if not path.is_file():
        return ""
    text = path.read_text(encoding="utf-8")
    template = TEMPLATES_DIR / f"{name}.mmd"
    if template.is_file() and _normalize(text) == _normalize(template.read_text(encoding="utf-8")):
        return f"совпадает с templates/{name}.mmd — содержимое не построено"
    placeholders = sorted(set(_PLACEHOLDER_RE.findall(text)))
    if placeholders:
        return "остались скелетные подписи шаблона: " + ", ".join(placeholders)
    return ""


def check_dor(run_dir: Path, profile: str = "auto") -> list[str]:
    """Проверить применимость и полноту набора диаграмм прогона.

    Ожидаемый набор = профиль минус явно неприменимые диаграммы. Для каждого
    ожидаемого файла проверяется не только наличие, но и содержание: пустышка
    (копия шаблона) считается отсутствующей. Декларация неприменимости без
    причины — проблема, как и построенная диаграмма, объявленная неприменимой.

    Args:
        run_dir: Каталог прогона (`output/<run-id>`).
        profile: Имя профиля полноты; `auto` выводит его из состава файлов.

    Returns:
        Список проблем; пустой список означает, что набор полон и применим.
    """
    if not run_dir.is_dir():
        return [f"нет каталога прогона: {run_dir}"]

    expected, resolved = resolve_profile(run_dir, profile)
    diagrams = run_dir / "diagrams"
    present = {path.stem for path in diagrams.glob("*.mmd")} if diagrams.is_dir() else set()

    not_applicable, problems = load_applicability(run_dir)
    known = {path.stem for path in TEMPLATES_DIR.glob("*.mmd")}
    for name in sorted(set(not_applicable) - known):
        problems.append(f"{RUN_REPORT}: неизвестная диаграмма в {NOT_APPLICABLE_KEY}: {name}")
    for name, reason in sorted(not_applicable.items()):
        if name in known and reason.strip().lower() in _EMPTY_REASONS:
            problems.append(
                f"{RUN_REPORT}: {name} объявлена неприменимой без причины — "
                "«не применимо» требует объяснения"
            )

    required = [name for name in expected if name not in not_applicable]
    problems.extend(
        f"нет диаграммы {name}.mmd (профиль {resolved})"
        for name in required
        if name not in present
    )
    if "bpmn-process" in required and not (diagrams / BPMN_FILE).is_file():
        problems.append(f"нет {BPMN_FILE} (профиль {resolved})")

    for name in sorted(present):
        reason = stub_reason(run_dir, name)
        if reason:
            problems.append(f"{name}.mmd: шаблонная пустышка — {reason}")

    bpmn_path = diagrams / BPMN_FILE
    bpmn_template = TEMPLATES_DIR / BPMN_FILE
    if (
        bpmn_path.is_file()
        and bpmn_template.is_file()
        and _normalize(bpmn_path.read_text(encoding="utf-8"))
        == _normalize(bpmn_template.read_text(encoding="utf-8"))
    ):
        problems.append(
            f"{BPMN_FILE}: шаблонная пустышка — совпадает с templates/{BPMN_FILE}"
        )

    for name in sorted(not_applicable):
        if name in present and not stub_reason(run_dir, name):
            problems.append(
                f"{name}.mmd: объявлена неприменимой, но диаграмма построена — "
                "исправьте декларацию или удалите файл"
            )
    if "bpmn-process" in not_applicable and (diagrams / BPMN_FILE).is_file():
        problems.append(
            f"{BPMN_FILE}: объявлен неприменимым, но построен — "
            "исправьте декларацию или удалите файл"
        )

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
