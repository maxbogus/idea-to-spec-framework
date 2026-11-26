"""Чеклисты гейтов: загрузка, рендер справочника, проверка ответа гейта.

Зачем модуль. До P1 чеклисты существовали только прозой в
`prompts/gate-checklists.md`, а гейт возвращал свободный список `missing`.
Из этого нельзя было ответить на вопрос «какой именно пункт провален»: в
отчёте оставалась фраза, а не идентификатор, и проверить ответ гейта машиной
было нечем. «Гейты-штампы» из HANDOFF и невоспроизводимый замер (F034) —
следствия одного: вердикт гейта не имел контракта.

Здесь:

- `load_gates` — источник правды `prompts/gate-checklists.yaml`: у каждого
  пункта стабильный id, флаг `na_allowed` и подраздел;
- `render_markdown` / `check_markdown` — человеческий справочник
  `prompts/gate-checklists.md` — производная от YAML (как `skills/INDEX.md`);
- `render_gate_input` — блок «гейт + чеклист + куда возвращать», который
  получает отдельный вызов гейта (`prompts/roles/gate-reviewer.md`);
- `validate_gate_payload` — проверка ответа гейта: полнота `checks[]`,
  согласованность `status` / `missing` / `return_to`, `na` только там, где
  он допустим;
- `extract_gate_payloads` — вытащить `checks[]`-блоки из
  `validation-report.md` (раздел «Гейты») для `check_run`.

Почему чеклист не в промпте оркестратора: измерено (F019), что чеклист внутри
промпта роль принимает за формат ответа. Поэтому чеклист передаётся только
отдельному вызову гейта, где он и есть предмет проверки.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import yaml

from idea_to_spec.paths import REPO_ROOT

#: YAML-источник и производный справочник.
CHECKLISTS_YAML = Path("prompts") / "gate-checklists.yaml"
CHECKLISTS_MD = Path("prompts") / "gate-checklists.md"

#: Допустимые статусы пункта и гейта.
CHECK_STATUSES: frozenset[str] = frozenset({"pass", "fail", "na"})
GATE_STATUSES: frozenset[str] = frozenset({"passed", "failed"})

#: Регулярка JSON-блока в markdown.
_JSON_BLOCK_RE = re.compile(r"```json\n(.*?)```", re.S)
#: Раздел «Гейты» в validation-report.md.
_GATE_SECTION_RE = re.compile(r"(?ms)^## Гейты[ \t]*$(.*?)(?=^## |\Z)")


@dataclass(frozen=True)
class GateItem:
    """Пункт чеклиста гейта.

    Attributes:
        id: Стабильный идентификатор (`BA-01`).
        text: Формулировка пункта.
        na_allowed: Допустим ли статус `na` (пункт условный).
        section: Подраздел внутри чеклиста (пусто — основной список).
    """

    id: str
    text: str
    na_allowed: bool = False
    section: str = ""


@dataclass(frozen=True)
class GateSpec:
    """Описание гейта.

    Attributes:
        name: Имя гейта (`BA-gate`).
        stage: Этап из enum оркестратора (`ba_gate`).
        owners: Роли-владельцы.
        return_to: Допустимые этапы возврата доработки.
        items: Пункты чеклиста в порядке проверки.
    """

    name: str
    stage: str
    owners: tuple[str, ...]
    return_to: tuple[str, ...]
    items: tuple[GateItem, ...]

    def item(self, item_id: str) -> GateItem | None:
        """Вернуть пункт по идентификатору.

        Args:
            item_id: Идентификатор пункта.

        Returns:
            Пункт или None, если такого id в чеклисте нет.
        """
        for item in self.items:
            if item.id == item_id:
                return item
        return None


def gate_names(root: Path | None = None) -> tuple[str, ...]:
    """Вернуть имена гейтов в порядке объявления.

    Args:
        root: Корень репозитория.

    Returns:
        Кортеж имён гейтов.
    """
    return tuple(load_gates(root))


def _require(mapping: dict[str, Any], key: str, where: str) -> Any:
    """Взять обязательное поле YAML или упасть с адресом ошибки.

    Args:
        mapping: Словарь записи.
        key: Имя поля.
        where: Человеческое описание места (для сообщения об ошибке).

    Returns:
        Значение поля.

    Raises:
        ValueError: Поле отсутствует или пустое.
    """
    value = mapping.get(key)
    if value in (None, "", []):
        raise ValueError(f"{where}: нет поля {key!r}")
    return value


def load_gates(root: Path | None = None) -> dict[str, GateSpec]:
    """Прочитать чеклисты из YAML.

    Args:
        root: Корень репозитория (по умолчанию — фактический).

    Returns:
        Словарь «имя гейта → описание» в порядке файла.

    Raises:
        FileNotFoundError: Нет `prompts/gate-checklists.yaml`.
        ValueError: Структура файла нарушена (нет id, дубликаты, пустой текст).
    """
    base = root or REPO_ROOT
    path = base / CHECKLISTS_YAML
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("gates"), list):
        raise ValueError(f"{path}: ожидался объект с ключом gates (список)")

    gates: dict[str, GateSpec] = {}
    for gate_index, raw_gate in enumerate(cast(list[Any], data["gates"])):
        where_gate = f"gates[{gate_index}]"
        if not isinstance(raw_gate, dict):
            raise ValueError(f"{where_gate}: запись гейта должна быть объектом")
        gate = cast(dict[str, Any], raw_gate)
        name = str(_require(gate, "id", where_gate))
        if name in gates:
            raise ValueError(f"{where_gate}: гейт {name!r} объявлен дважды")
        stage = str(_require(gate, "stage", name))
        return_to = tuple(str(value) for value in _require(gate, "return_to", name))
        owners = tuple(str(owner) for owner in gate.get("owners") or ())
        raw_items = _require(gate, "items", name)
        if not isinstance(raw_items, list):
            raise ValueError(f"{name}: items должен быть списком")

        items: list[GateItem] = []
        seen: set[str] = set()
        for item_index, raw_item in enumerate(raw_items):
            where_item = f"{name}: items[{item_index}]"
            if not isinstance(raw_item, dict):
                raise ValueError(f"{where_item}: пункт должен быть объектом")
            item = cast(dict[str, Any], raw_item)
            item_id = str(_require(item, "id", where_item))
            if item_id in seen:
                raise ValueError(f"{name}: пункт {item_id!r} объявлен дважды")
            seen.add(item_id)
            items.append(
                GateItem(
                    id=item_id,
                    text=str(_require(item, "text", item_id)),
                    na_allowed=bool(item.get("na_allowed", False)),
                    section=str(item.get("section") or ""),
                )
            )
        gates[name] = GateSpec(
            name=name,
            stage=stage,
            owners=owners,
            return_to=return_to,
            items=tuple(items),
        )
    return gates


def gate_spec(name: str, root: Path | None = None) -> GateSpec:
    """Вернуть описание гейта по имени.

    Args:
        name: Имя гейта (`BA-gate`).
        root: Корень репозитория.

    Returns:
        Описание гейта.

    Raises:
        ValueError: Гейт не объявлен в чеклистах.
    """
    gates = load_gates(root)
    spec = gates.get(name)
    if spec is None:
        known = ", ".join(gates)
        raise ValueError(f"неизвестный гейт {name!r}; объявлены: {known}")
    return spec



def render_markdown(root: Path | None = None) -> str:
    """Собрать `prompts/gate-checklists.md` из YAML.

    Args:
        root: Корень репозитория.

    Returns:
        Текст справочника.
    """
    gates = load_gates(root)
    lines: list[str] = [
        "# Чеклисты гейтов — справочник оркестратора и вход отдельного вызова гейта",
        "",
        "> Генерируется `scripts/render_gate_checklists.py` из",
        "> `prompts/gate-checklists.yaml`. Не править вручную: проверка —",
        "> `make check-gates`, перегенерация — `make gates-index`.",
        ">",
        "> В промпт оркестратора и ролей файл **не подключается**: измерено",
        "> (qwen2.5:7b), что чеклист внутри промпта модель принимает за формат",
        "> ответа и отвечает чеклистом вместо JSON роли.",
        ">",
        "> Отдельному вызову гейта (`prompts/roles/gate-reviewer.md`) чеклист",
        "> передаётся во входе — там он и есть предмет проверки. Вердикт",
        "> возвращается как `checks[]` со статусом по каждому id.",
        "",
    ]
    for spec in gates.values():
        lines.append(f"## Чеклист {spec.name}")
        lines.append("")
        lines.append(
            f"Этап: `{spec.stage}`. Возврат доработки: "
            + ", ".join(f"`{stage}`" for stage in spec.return_to)
            + "."
        )
        if spec.owners:
            owners = ", ".join(f"`{owner}`" for owner in spec.owners)
            lines.append(f"Владельцы: {owners}.")
        lines.append("")
        current_section = ""
        for item in spec.items:
            if item.section != current_section:
                current_section = item.section
                if current_section:
                    lines.append("")
                    lines.append(f"### {current_section}")
                    lines.append("")
            suffix = " — допустим статус `na` с причиной" if item.na_allowed else ""
            lines.append(f"- [ ] `{item.id}`. {item.text}{suffix}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def check_markdown(root: Path | None = None) -> list[str]:
    """Проверить, что справочник соответствует YAML.

    Args:
        root: Корень репозитория.

    Returns:
        Список проблем (пустой, если файл актуален).
    """
    base = root or REPO_ROOT
    path = base / CHECKLISTS_MD
    if not path.is_file():
        return [f"{CHECKLISTS_MD.as_posix()}: файл не найден (запусти `make gates-index`)"]
    if path.read_text(encoding="utf-8") != render_markdown(base):
        return [f"{CHECKLISTS_MD.as_posix()}: устарел (запусти `make gates-index`)"]
    return []


def render_gate_input(name: str, root: Path | None = None) -> str:
    """Собрать вход отдельного вызова гейта.

    Args:
        name: Имя гейта (`BA-gate`).
        root: Корень репозитория.

    Returns:
        Блок «ГЕЙТ / КУДА ВОЗВРАЩАТЬ / ЧЕКЛИСТ» — его получает модель.
    """
    spec = gate_spec(name, root)
    lines = [
        f"ГЕЙТ: {spec.name}",
        "КУДА ВОЗВРАЩАТЬ: " + ", ".join(spec.return_to),
        "ЧЕКЛИСТ (id — пункт; «допустим na» — можно поставить na с причиной):",
    ]
    for item in spec.items:
        suffix = " [допустим na]" if item.na_allowed else ""
        lines.append(f"- {item.id} — {item.text}{suffix}")
    return "\n".join(lines)



def validate_gate_payload(payload: Any, expected_gate: str = "") -> list[str]:
    """Проверить ответ гейта по контракту `checks[]`.

    Args:
        payload: Разобранный JSON-ответ гейта.
        expected_gate: Ожидаемое имя гейта (пусто — доверять ответу).

    Returns:
        Список проблем; пустой список — контракт выполнен.
    """
    if not isinstance(payload, dict):
        return ["ответ гейта — не JSON-объект"]
    data = cast(dict[str, Any], payload)
    gates = load_gates()
    name = str(data.get("gate") or "")
    spec = gates.get(name)
    if spec is None:
        return [f"неизвестный гейт {name!r}; объявлены: {', '.join(gates)}"]

    problems: list[str] = []
    if expected_gate and name != expected_gate:
        problems.append(f"гейт {name!r} не совпадает с ожидаемым {expected_gate!r}")

    status = str(data.get("status") or "")
    if status not in GATE_STATUSES:
        problems.append(f"недопустимый статус гейта {status!r} (passed|failed)")

    raw_checks = data.get("checks")
    if not isinstance(raw_checks, list) or not raw_checks:
        problems.append("checks пуст: вердикта по пунктам нет")
        raw_checks = []

    verdicts: dict[str, str] = {}
    for index, raw_check in enumerate(raw_checks):
        where = f"checks[{index}]"
        if not isinstance(raw_check, dict):
            problems.append(f"{where}: запись должна быть объектом")
            continue
        check = cast(dict[str, Any], raw_check)
        item_id = str(check.get("id") or "")
        item = spec.item(item_id)
        if item is None:
            problems.append(f"{where}: пункта {item_id!r} нет в чеклисте {name}")
            continue
        if item_id in verdicts:
            problems.append(f"{item_id}: пункт повторяется в checks")
            continue
        check_status = str(check.get("status") or "")
        if check_status not in CHECK_STATUSES:
            problems.append(f"{item_id}: недопустимый статус {check_status!r} (pass|fail|na)")
            continue
        verdicts[item_id] = check_status
        evidence = str(check.get("evidence") or "").strip()
        if check_status in {"pass", "fail"} and not evidence:
            problems.append(f"{item_id}: статус {check_status} без evidence")
        if check_status == "na":
            if not item.na_allowed:
                problems.append(f"{item_id}: пункт не допускает na")
            if not str(check.get("reason") or "").strip():
                problems.append(f"{item_id}: na без причины")

    dropped = [item.id for item in spec.items if item.id not in verdicts]
    if dropped:
        problems.append("в checks нет пунктов: " + ", ".join(dropped))

    failed = sorted(item_id for item_id, verdict in verdicts.items() if verdict == "fail")
    raw_missing = data.get("missing")
    if not isinstance(raw_missing, list):
        problems.append("missing должен быть списком id проваленных пунктов")
    else:
        missing = sorted(str(item_id) for item_id in raw_missing)
        if missing != failed:
            problems.append(
                "missing не совпадает с проваленными пунктами: "
                f"missing={missing}, fail={failed}"
            )

    return_to = str(data.get("return_to") or "")
    if failed and not return_to:
        problems.append("failed без return_to: неизвестно, куда возвращать")
    if return_to and return_to not in spec.return_to:
        allowed = ", ".join(spec.return_to)
        problems.append(f"return_to {return_to!r} недопустим для {name}; допустимо: {allowed}")

    if status == "passed" and failed:
        problems.append("status=passed, но есть проваленные пункты: " + ", ".join(failed))
    if status == "failed" and not failed:
        problems.append("status=failed, но ни один пункт не провален")
    return problems


def extract_gate_payloads(text: str) -> tuple[list[dict[str, Any]], list[str]]:
    """Вытащить ответы гейтов из раздела «Гейты» в markdown.

    Args:
        text: Содержимое `validation-report.md` (или любого отчёта).

    Returns:
        Пары «список разобранных ответов» и «список проблем разбора». Пустой
        список ответов без проблем — раздела нет или он не заполнен: старые
        прогоны принимаются.
    """
    section_match = _GATE_SECTION_RE.search(text)
    if section_match is None:
        return [], []

    payloads: list[dict[str, Any]] = []
    problems: list[str] = []
    for block_index, block in enumerate(_JSON_BLOCK_RE.findall(section_match.group(1)), start=1):
        try:
            parsed = json.loads(block)
        except json.JSONDecodeError as exc:
            problems.append(f"блок Гейты №{block_index}: невалидный JSON ({exc})")
            continue
        if not isinstance(parsed, dict):
            problems.append(f"блок Гейты №{block_index}: ожидался JSON-объект")
            continue
        payloads.append(cast(dict[str, Any], parsed))
    return payloads, problems

