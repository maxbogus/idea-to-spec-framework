"""Схемы ответов ролей: загрузка, сверка с промптами, проверка ответа (P4).

Зачем. До P4 формат ответа роли существовал только как JSON-пример внутри
`prompts/roles/*.md`. Человек его читал, машина — нет: `expected_fields` в
eval-кейсах был ручной копией схемы, и расхождение не ловилось. Проверка
искала подстроку в ответе, поэтому `baseline` (вложенное поле
`success_metric.baseline`) считался полем верхнего уровня, а
`open_questions` как массив объектов проходил как «поле есть».

Здесь:

- `load_schemas` — источник правды `prompts/schemas.yaml` (поля, типы,
  обязательность, тип элементов массива);
- `load_schemas_cached` — тот же реестр с идемпотентным кэшем по отпечатку
  файла (путь, `mtime_ns`, размер): одинаковый файл даёт тот же объект,
  правка подхватывается, чужой `root` не подменяется репозиторным, значение
  неизменяемо;
- `check_prompt_matches_schema` — JSON-пример в промпте обязан совпадать со
  схемой по набору полей и типам;
- `case_contract_problems` / `check_eval_contracts` — `expected_fields`
  каждого кейса обязан быть полем верхнего уровня схемы своей роли;
- `validate_role_payload` — структурная проверка ответа модели: обязательные
  поля, типы, однородность массивов (используется проверкой `role_schema`).

Границы: вложенные формы (`outputs.findings[]`, `scope.prioritization`)
остаются в примерах промптов и `test_role_formats`; перекрёстные
идентификаторы — `check_cross_refs.py`.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from types import MappingProxyType
from typing import Any

import yaml

from idea_to_spec.paths import REPO_ROOT

#: YAML-источник схем и файл eval-кейсов.
SCHEMAS_YAML = Path("prompts") / "schemas.yaml"
CASES_FILE = Path("eval") / "cases" / "roles.jsonl"

#: Допустимые типы полей и элементов массивов.
ALLOWED_TYPES: frozenset[str] = frozenset(
    {"string", "number", "boolean", "object", "array"}
)

#: Блок формата в промпте роли (`## Формат ответа`) и субагента (`## Формат вывода`).
_FORMAT_BLOCK_RE = re.compile(r"## Формат (?:ответа|вывода).*?```json\n(.*?)```", re.S)


@dataclass(frozen=True)
class FieldSpec:
    """Поле верхнего уровня ответа роли.

    Attributes:
        name: Имя поля (ключ JSON-объекта).
        type: Один из `ALLOWED_TYPES`.
        required: Обязательно ли поле в ответе.
        items: Тип элементов массива (для однородных массивов).
    """

    name: str
    type: str
    required: bool = True
    items: str | None = None


@dataclass(frozen=True)
class RoleSchema:
    """Схема ответа одной роли.

    Attributes:
        role: Значение `role` в контракте eval-кейса.
        prompt: Путь к промпту-источнику (от корня репозитория).
        fields: Поля верхнего уровня ответа (только чтение: реестр кэшируется
            и отдаётся нескольким потребителям, мутация отравила бы процесс).

    """

    role: str
    prompt: str
    fields: Mapping[str, FieldSpec]


def load_schemas(root: Path = REPO_ROOT) -> Mapping[str, RoleSchema]:
    """Прочитать `prompts/schemas.yaml` (без кэша: честное чтение с диска).

    Args:
        root: Корень репозитория.

    Returns:
        Неизменяемое отображение «роль → схема ответа». Свежее чтение каждый
        раз: для повторных проверок есть `load_schemas_cached`.

    Raises:
        ValueError: Файл отсутствует или структура неверна.
    """
    path = root / SCHEMAS_YAML
    if not path.is_file():
        raise ValueError(f"нет файла схем: {SCHEMAS_YAML}")
    raw: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    roles = raw.get("roles") if isinstance(raw, dict) else None
    if not isinstance(roles, dict):
        raise ValueError(f"{SCHEMAS_YAML}: нет секции roles")

    schemas: dict[str, RoleSchema] = {}
    for role, spec in roles.items():
        if not isinstance(spec, dict):
            raise ValueError(f"{SCHEMAS_YAML}: роль {role!r} — не объект")
        prompt = str(spec.get("prompt") or "")
        fields_raw = spec.get("fields")
        if not prompt or not isinstance(fields_raw, dict):
            raise ValueError(f"{SCHEMAS_YAML}: у роли {role!r} нет prompt/fields")
        fields: dict[str, FieldSpec] = {}
        for name, field in fields_raw.items():
            if not isinstance(field, dict):
                raise ValueError(f"{SCHEMAS_YAML}: {role}.{name} — не объект")
            items = field.get("items")
            fields[str(name)] = FieldSpec(
                name=str(name),
                type=str(field.get("type") or ""),
                required=bool(field.get("required", True)),
                items=str(items) if items else None,
            )
        schemas[str(role)] = RoleSchema(
            role=str(role), prompt=prompt, fields=MappingProxyType(fields)
        )
    return MappingProxyType(schemas)


@lru_cache(maxsize=8)
def _schemas_by_fingerprint(root: str, fingerprint: tuple[int, int]) -> Mapping[str, RoleSchema]:
    """Разобрать схемы один раз на (путь, отпечаток файла).

    Args:
        root: Абсолютный путь корня репозитория (часть ключа кэша).
        fingerprint: `(mtime_ns, размер)` файла схем — тоже часть ключа: при
            правке YAML отпечаток меняется, и разбор выполняется заново.

    Returns:
        Неизменяемое отображение «роль → схема ответа».
    """
    return load_schemas(Path(root))


def load_schemas_cached(root: Path = REPO_ROOT) -> Mapping[str, RoleSchema]:
    """Прочитать схемы с идемпотентным кэшем по отпечатку файла.

    Зачем кэш с ключом, а не `maxsize=1`. Реестр читают несколько потребителей
    одного процесса (pytest, мост `role_schema`, `make check-schemas`), и каждый
    разбор YAML стоит ~5.6 мс. `maxsize=1` без ключа игнорирует `root` (чужой
    чекаут молча получал бы схемы репозитория) и никогда не инвалидируется
    (долгоживущий процесс проверял бы старый файл). Ключ — путь и отпечаток
    файла: одинаковое содержимое даёт тот же объект, правка — новый разбор.
    Стоимость ключа — один `stat` (микросекунды).

    Args:
        root: Корень репозитория.

    Returns:
        Неизменяемое отображение «роль → схема ответа».

    Raises:
        ValueError: Файл отсутствует или структура неверна.
    """
    path = root / SCHEMAS_YAML
    if not path.is_file():
        raise ValueError(f"нет файла схем: {SCHEMAS_YAML}")
    stat = path.stat()
    return _schemas_by_fingerprint(str(root.resolve()), (stat.st_mtime_ns, stat.st_size))


def _default_schemas() -> Mapping[str, RoleSchema]:
    """Схемы репозитория по умолчанию (кэш по отпечатку файла)."""
    return load_schemas_cached(REPO_ROOT)


def _type_of(value: object) -> str:
    """Определить тип значения для сверки со схемой.

    Args:
        value: Значение из JSON-объекта.

    Returns:
        `string`, `number`, `boolean`, `object`, `array` или `null`.
    """
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return "null"


def extract_example_schema(path: Path) -> dict[str, Any] | None:
    """Извлечь JSON-пример формата ответа из промпта.

    Args:
        path: Путь к промпту роли или субагента.

    Returns:
        Разобранный объект или None, если блока нет / он не JSON.
    """
    match = _FORMAT_BLOCK_RE.search(path.read_text(encoding="utf-8"))
    if match is None:
        return None
    try:
        parsed = json.loads(match.group(1))
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _array_item_problems(label: str, value: object, expected: str) -> list[str]:
    """Проверить однородность элементов массива.

    Args:
        label: Имя поля для сообщения.
        value: Значение поля (ожидается массив).
        expected: Ожидаемый тип элементов.

    Returns:
        Список проблем (пустой, если элементы нужного типа).
    """
    if not isinstance(value, list):
        return []
    wrong = sorted({_type_of(item) for item in value if _type_of(item) != expected})
    if not wrong:
        return []
    return [f"{label}: элементы массива {wrong}, схема ждёт {expected}"]


def check_prompt_matches_schema(schema: RoleSchema, root: Path = REPO_ROOT) -> list[str]:
    """Сверить JSON-пример промпта с машинно-читаемой схемой.

    Args:
        schema: Схема роли.
        root: Корень репозитория.

    Returns:
        Список проблем (пустой, если пример и схема совпадают).
    """
    path = root / schema.prompt
    if not path.is_file():
        return [f"{schema.role}: нет промпта {schema.prompt}"]
    example = extract_example_schema(path)
    if example is None:
        return [f"{schema.prompt}: нет валидного JSON-блока «Формат ответа/вывода»"]

    problems: list[str] = []
    for name, field in schema.fields.items():
        if name not in example:
            problems.append(
                f"{schema.role}.{name}: поле схемы отсутствует в JSON-примере промпта"
            )
            continue
        actual = _type_of(example[name])
        if actual != field.type:
            problems.append(
                f"{schema.role}.{name}: в промпте {actual}, в схеме {field.type}"
            )
            continue
        if field.items is not None:
            problems.extend(
                _array_item_problems(f"{schema.role}.{name}", example[name], field.items)
            )
    for name in example:
        if name not in schema.fields:
            problems.append(
                f"{schema.role}.{name}: поле есть в промпте, но не объявлено в схеме"
            )
    return problems


def validate_role_payload(
    role: str,
    payload: dict[str, Any],
    schemas: Mapping[str, RoleSchema] | None = None,
) -> list[str]:
    """Проверить ответ модели по схеме роли.

    Args:
        role: Значение `role` из контракта кейса.
        payload: Разобранный JSON-ответ.
        schemas: Реестр схем (по умолчанию — репозиторный).

    Returns:
        Список проблем (пустой, если ответ соответствует схеме).
    """
    registry = schemas if schemas is not None else _default_schemas()
    schema = registry.get(role)
    if schema is None:
        return [f"роль {role!r}: нет машинно-читаемой схемы в {SCHEMAS_YAML.as_posix()}"]

    problems: list[str] = []
    for name, field in schema.fields.items():
        if name not in payload:
            if field.required:
                problems.append(f"{role}.{name}: обязательное поле отсутствует")
            continue
        actual = _type_of(payload[name])
        if actual != field.type:
            problems.append(f"{role}.{name}: тип {actual}, схема ждёт {field.type}")
            continue
        if field.items is not None:
            problems.extend(_array_item_problems(f"{role}.{name}", payload[name], field.items))
    return problems


def case_contract_problems(
    contracts: list[dict[str, Any]], schemas: Mapping[str, RoleSchema]
) -> list[str]:
    """Проверить, что `expected_fields` кейсов — поля верхнего уровня схемы.

    Args:
        contracts: Контракты eval-кейсов.
        schemas: Реестр схем.

    Returns:
        Список проблем (пустой, если дрейфа нет).
    """
    problems: list[str] = []
    for contract in contracts:
        case_id = str(contract.get("id") or "?")
        role = str(contract.get("role") or "")
        schema = schemas.get(role)
        if schema is None:
            problems.append(f"{case_id}: роль {role!r} без схемы в {SCHEMAS_YAML.as_posix()}")
            continue
        expected = contract.get("expected_fields") or []
        if not isinstance(expected, list):
            problems.append(f"{case_id}: expected_fields — не массив")
            continue
        for field in expected:
            if str(field) not in schema.fields:
                problems.append(
                    f"{case_id}: expected_fields содержит {field!r}, которого нет в "
                    f"схеме {role} (вложенное поле? ссылайтесь на верхнеуровневое)"
                )
    return problems


def check_eval_contracts(
    root: Path = REPO_ROOT, schemas: Mapping[str, RoleSchema] | None = None
) -> list[str]:
    """Прочитать eval-кейсы и сверить их контракты со схемами.

    Args:
        root: Корень репозитория.
        schemas: Реестр схем (по умолчанию — кэшированный `root`).

    Returns:
        Список проблем (пустой, если дрейфа нет).
    """
    path = root / CASES_FILE
    if not path.is_file():
        return [f"нет файла кейсов {CASES_FILE.as_posix()}"]
    registry = schemas if schemas is not None else load_schemas_cached(root)

    problems: list[str] = []
    contracts: list[dict[str, Any]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            problems.append(f"{CASES_FILE.name}:{number}: невалидный JSON ({exc})")
            continue
        raw = (row.get("vars") or {}).get("contract") if isinstance(row, dict) else None
        try:
            contract = json.loads(raw) if isinstance(raw, str) else raw
        except json.JSONDecodeError as exc:
            problems.append(f"{CASES_FILE.name}:{number}: contract — невалидный JSON ({exc})")
            continue
        if not isinstance(contract, dict):
            problems.append(f"{CASES_FILE.name}:{number}: contract — не объект")
            continue
        contracts.append(contract)
    problems.extend(case_contract_problems(contracts, registry))
    return problems


def _uncovered_prompts(root: Path, schemas: Mapping[str, RoleSchema]) -> list[str]:
    """Найти промпты с форматом ответа, для которых нет схемы.

    Новая роль не должна появляться без контракта: иначе её ответ снова
    проверяется только глазами и `expected_fields`.

    Args:
        root: Корень репозитория.
        schemas: Реестр схем.

    Returns:
        Список проблем (пустой, если все промпты покрыты).
    """
    covered = {schema.prompt for schema in schemas.values()}
    problems: list[str] = []
    candidates = [
        *(root / "prompts" / "roles").glob("*.md"),
        root / "prompts" / "orchestrator.md",
        *(root / "subagents").glob("*.md"),
    ]
    for path in sorted(candidates):
        if not path.is_file() or extract_example_schema(path) is None:
            continue
        relative = path.relative_to(root).as_posix()
        if relative not in covered:
            problems.append(
                f"{relative}: есть JSON-формат ответа, но нет схемы в "
                f"{SCHEMAS_YAML.as_posix()}"
            )
    return problems


def check_all(root: Path = REPO_ROOT) -> list[str]:
    """Проверить схемы, промпты и eval-контракты целиком.

    Args:
        root: Корень репозитория.

    Returns:
        Список проблем (пустой, если контракт согласован).
    """
    schemas = load_schemas_cached(root)
    problems: list[str] = _uncovered_prompts(root, schemas)
    for schema in schemas.values():
        for name, field in schema.fields.items():
            if field.type not in ALLOWED_TYPES:
                problems.append(f"{schema.role}.{name}: недопустимый тип {field.type!r}")
            if field.items is not None and field.items not in ALLOWED_TYPES:
                problems.append(f"{schema.role}.{name}: недопустимый items {field.items!r}")
        problems.extend(check_prompt_matches_schema(schema, root))
    problems.extend(check_eval_contracts(root, schemas))
    return problems
