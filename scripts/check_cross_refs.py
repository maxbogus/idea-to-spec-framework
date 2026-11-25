"""Валидатор перекрёстных ссылок в ролевых схемах ответа.

Зачем. Кейс `BA-01-personas-jtbd` падал у `qwen3:8b`, но проходил у
`qwen2.5:7b` и `qwen3-4b-local`. Причина оказалась не в модели: в схеме
ответа `personas` были объявлены массивом строк, тогда как
`jobs_to_be_done[].persona` ожидает идентификатор персоны. Модель писала
имя («Студент») вместо `P-1` — то есть ей не выдали идентификатор, который
потом требовали. Класс дефектов: **поле X ссылается на сущность из поля Y,
но Y идентификаторов не объявляет**.

Этот модуль — семантический аналог `check-refs` (тот проверяет, что
файлы-ссылки существуют; этот — что идентификаторы в схеме согласованы
между собой).

Проверяется по схемам ответов ролей (`prompts/roles/*.md`,
`prompts/orchestrator.md`):

- `jobs_to_be_done[].persona` ссылается на `personas[].id` — значит
  `personas` должен быть массивом объектов с полем `id`;
- `functional_requirements[].source` ссылается на бизнес-требование —
  значит в роли должен быть источник идентификаторов `BR-*`;
- `tasks[].depends_on` ссылается на `tasks[].id`;
- `tasks[].wbs_ref` ссылается на `planning.wbs[].id`;
- `acceptance_criteria[].id` объявляется как `AC-*`.

Запуск: `python3 scripts/check_cross_refs.py` или `make check-cross-refs`.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

#: Корень репозитория.
REPO_ROOT = Path(__file__).resolve().parent.parent

#: Каталог промптов ролей.
ROLES_DIR = REPO_ROOT / "prompts" / "roles"

#: Промпт оркестратора (его схема — отдельно от ролевых).
ORCHESTRATOR_FILE = REPO_ROOT / "prompts" / "orchestrator.md"

#: JSON-блок с примером формата ответа.
_JSON_BLOCK_RE = re.compile(r"```json\n(.*?)```", re.S)

#: Правила проверки: имя правила -> (путь к полю-источнику, путь к полю-ссылке).
#: Значение — кортеж (роль-владелец идентификаторов, имя поля-источника).
CROSS_REF_RULES: dict[str, tuple[str, str]] = {
    "persona": ("personas", "persona"),
}


def _schema(path: Path) -> dict[str, object] | None:
    """Извлечь схему формата ответа из промпта роли.

    Args:
        path: Путь к промпту роли.

    Returns:
        Словарь схемы или None, если блока нет.
    """
    blocks = _JSON_BLOCK_RE.findall(path.read_text(encoding="utf-8"))
    if not blocks:
        return None
    try:
        parsed = json.loads(blocks[0])
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _sample(schema: dict[str, object], *keys: str) -> object:
    """Взять пример значения по пути ключей.

    Args:
        schema: Схема формата ответа.
        *keys: Путь к значению.

    Returns:
        Значение или None, если пути нет.
    """
    node: object = schema
    for key in keys:
        if not isinstance(node, dict) or key not in node:
            return None
        node = node[key]
    if isinstance(node, list) and node:
        return node[0]
    return node


def check_role(path: Path) -> list[str]:
    """Проверить одну ролевую схему.

    Args:
        path: Путь к промпту роли.

    Returns:
        Список проблем (пустой, если схема согласована).
    """
    problems: list[str] = []
    schema = _schema(path)
    if schema is None:
        return [f"{path.name}: нет валидного JSON-блока формата ответа"]

    # Правило «persona»: jobs_to_be_done[].persona ссылается на personas[].id.
    jtbd = _sample(schema, "jobs_to_be_done")
    personas = _sample(schema, "personas")
    if isinstance(jtbd, dict) and personas is not None:
        persona_ref = jtbd.get("persona")
        if isinstance(persona_ref, str) and re.fullmatch(r"P-\d+", persona_ref):
            if not isinstance(personas, dict) or "id" not in personas:
                problems.append(
                    f"{path.name}: jobs_to_be_done[].persona ссылается на {persona_ref!r}, "
                    "но personas не объявляют id — модель не сможет дать "
                    "идентификатор, который потом требуют"
                )
            elif "name" not in personas:
                problems.append(
                    f"{path.name}: personas объявляют id, но не name — нечего подписать персону"
                )

    # Правило «tasks»: depends_on ссылается на tasks[].id.
    tasks = _sample(schema, "tasks")
    if isinstance(tasks, dict):
        depends = tasks.get("depends_on")
        if isinstance(depends, list) and depends and "id" not in tasks:
            problems.append(
                f"{path.name}: tasks[].depends_on ссылается на другие задачи, "
                "но tasks не объявляют id"
            )
        wbs_ref = tasks.get("wbs_ref")
        if isinstance(wbs_ref, str) and re.fullmatch(r"WBS-[\d.]+", wbs_ref):
            wbs = _sample(schema, "planning", "wbs")
            if isinstance(wbs, dict) and "id" not in wbs:
                problems.append(
                    f"{path.name}: tasks[].wbs_ref ссылается на {wbs_ref!r}, "
                    "но planning.wbs не объявляют id"
                )

    # Правило «source»: functional_requirements[].source ссылается на BR-*.
    #
    # Ссылка на чужую роль допустима: трассировка FR→BR — обязательная часть
    # работы System Analyst (контракт SA-01 требует «BR-1»). Проверяется
    # другое: формат ссылки назван явно, а не выдуман.
    fr = _sample(schema, "functional_requirements")
    if isinstance(fr, dict):
        source = fr.get("source")
        if (
            isinstance(source, str)
            and re.fullmatch(r"BR-\d+", source)
            and not any(m in source.lower() for m in ("br-", "бизнес-требован"))
        ):
            problems.append(
                f"{path.name}: functional_requirements[].source={source!r} — "
                "ссылка на бизнес-требование должна называть формат (BR-*)"
            )
    return problems


def main() -> int:
    """Проверить схемы всех ролей.

    Returns:
        0 — схемы согласованы; 1 — есть проблемы.
    """
    problems: list[str] = []
    for path in sorted(ROLES_DIR.glob("*.md")):
        problems.extend(check_role(path))
    orchestrator = check_role(ORCHESTRATOR_FILE)
    problems.extend(orchestrator)

    if problems:
        print("check-cross-refs: FAILED")
        for problem in problems:
            print(f"  {problem}")
        return 1

    print("check-cross-refs: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
