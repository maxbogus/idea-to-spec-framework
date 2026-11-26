"""Генерация `skills/INDEX.md` из реестра и frontmatter.

Зачем. Индекс нужен агенту и человеку, чтобы выбрать скил по стадии, не читая
восемь `SKILL.md`. Ручная таблица разъезжается с реестром; здесь она —
производная: `registry.yaml` + frontmatter, без отдельного источника правды.

Запуск:
- `python3 scripts/render_skills_index.py --write` — перегенерировать;
- `python3 scripts/render_skills_index.py --check` — проверить, что не устарел.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import yaml

#: Корень репозитория (скрипт лежит в `scripts/`).
REPO_ROOT = Path(__file__).resolve().parent.parent

#: Реестр и индекс относительно корня.
REGISTRY_PATH = Path("skills") / "registry.yaml"
INDEX_PATH = Path("skills") / "INDEX.md"

#: Порядок стадий совпадает с enum оркестратора (`prompts/orchestrator.md`).
STAGE_ORDER: tuple[str, ...] = (
    "business",
    "design_sketch",
    "system",
    "architecture",
    "validation",
    "plan",
)

#: Человеческие заголовки стадий.
STAGE_TITLES: dict[str, str] = {
    "business": "Business analysis",
    "design_sketch": "Design (Sketch)",
    "system": "System analysis",
    "architecture": "Architecture",
    "validation": "Validation",
    "plan": "Plan",
}

#: Заголовок индекса.
_PREAMBLE = (
    "# Индекс скилов\n"
    "\n"
    "> Генерируется `scripts/render_skills_index.py` из `skills/registry.yaml`\n"
    "> и frontmatter `SKILL.md`. Не править вручную: проверка — `make check-skills`.\n"
    "> Бандл стадии — это скилы, которые нужны на этой стадии; тело каждого\n"
    "> скила <= 60 строк, тяжёлые каталоги лежат в `references/`.\n"
)


def _frontmatter(path: Path) -> dict[str, Any]:
    """Прочитать YAML frontmatter скила."""

    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return {}
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}
    loaded = yaml.safe_load(parts[1])
    return loaded if isinstance(loaded, dict) else {}


def _trigger(meta: dict[str, Any]) -> str:
    """Вытащить строку `Triggers on` из description."""

    description = meta.get("description")
    if not isinstance(description, str):
        return "—"
    marker = "Triggers on:"
    if marker in description:
        trigger = description.split(marker, 1)[1]
    else:
        trigger = description.strip().splitlines()[0] if description.strip() else ""
    collapsed = " ".join(trigger.split())
    return collapsed.replace("|", "\\|") or "—"


def _body_lines(path: Path) -> int:
    """Посчитать строки тела скила (без frontmatter)."""

    text = path.read_text(encoding="utf-8")
    parts = text.split("---", 2)
    body = parts[2] if len(parts) >= 3 else text
    return len(body.strip("\n").splitlines())


def render_index(root: Path = REPO_ROOT) -> str:
    """Собрать `skills/INDEX.md` из реестра и frontmatter.

    Args:
        root: Корень репозитория.

    Returns:
        Текст индекса.
    """

    data = yaml.safe_load((root / REGISTRY_PATH).read_text(encoding="utf-8"))
    records = data.get("skills") if isinstance(data, dict) else None
    if not isinstance(records, list):
        raise ValueError("registry.yaml: skills должен быть списком")

    lines: list[str] = [_PREAMBLE]
    for stage in STAGE_ORDER:
        group = sorted(
            (record for record in records if isinstance(record, dict) and record.get("stage") == stage),
            key=lambda record: str(record.get("name")),
        )
        if not group:
            continue
        lines.append(f"## {STAGE_TITLES[stage]}\n")
        lines.append("| Скил | Kind | Гейт | Строк | Триггер | Проверка |")
        lines.append("|---|---|---|---:|---|---|")
        for record in group:
            skill_path = root / str(record.get("file"))
            meta = _frontmatter(skill_path)
            lines.append(
                "| `{name}` | {kind} | {gate} | {lines} | {trigger} | `{check}` |".format(
                    name=record.get("name"),
                    kind=record.get("kind"),
                    gate=record.get("gate"),
                    lines=_body_lines(skill_path),
                    trigger=_trigger(meta),
                    check=record.get("check"),
                )
            )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def check_index(root: Path = REPO_ROOT) -> list[str]:
    """Проверить, что `skills/INDEX.md` совпадает с рендером.

    Args:
        root: Корень репозитория.

    Returns:
        Список проблем (пустой, если индекс актуален).
    """

    index_path = root / INDEX_PATH
    expected = render_index(root)
    if not index_path.is_file():
        return [f"{INDEX_PATH.as_posix()}: файл не найден (запусти `make skills-index`)"]
    actual = index_path.read_text(encoding="utf-8")
    if actual != expected:
        return [f"{INDEX_PATH.as_posix()}: устарел (запусти `make skills-index`)"]
    return []


def main(argv: list[str] | None = None) -> int:
    """Точка входа CLI."""

    parser = argparse.ArgumentParser(description="Генерация индекса скилов")
    parser.add_argument("--root", type=Path, default=REPO_ROOT)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--write", action="store_true", help="записать INDEX.md")
    mode.add_argument("--check", action="store_true", help="проверить INDEX.md")
    args = parser.parse_args(argv)

    if args.check:
        problems = check_index(args.root)
        if problems:
            print("check-skills-index: FAILED")
            for problem in problems:
                print(f"  {problem}")
            return 1
        print("check-skills-index: OK")
        return 0

    (args.root / INDEX_PATH).write_text(render_index(args.root), encoding="utf-8")
    print(f"skills-index: записан {INDEX_PATH.as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
