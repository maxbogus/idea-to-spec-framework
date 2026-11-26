"""Проверки того, что промпт роли реально собирается из файлов-источников.

Историческая причина файла: промпт роли мог не попасть в eval-запрос
(transformVars не подключён, файл роли не найден), и модель получала голый
вход без роли и правил. Метрики на таком прогоне недостоверны.

Проверки ниже фиксируют инвариант: каждая переменная шаблона производится
трансформом, а тексты роли и правил доходят до промпта.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from idea_to_spec.paths import EVAL_CASES_FILE, EVAL_DIR

#: Регулярки блоков `{% if <имя> %}` и подстановок `{{ <имя> }}`.
IF_BLOCK_RE = re.compile(r"\{%\s*if\s+([A-Za-z_][A-Za-z0-9_]*)\s*%\}")
VAR_RE = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")

#: Имена переменных, которые шаблон реального прогона читает из трансформа.
#:
#: `guide` больше нет: гайд оркестратора не подключается к запросу — измерено
#: на eval-прогоне, что с гайдом модель отвечала по гайду, а не по формату
#: своей роли (чужие ключи вместо полей ответа). Рабочие части гайда
#: (триггеры режима, критерии выбора режима) перенесены в промпт роли.
EXPECTED_TEMPLATE_VARS = {"role_prompt", "rules", "input", "mode", "role"}


def _template_vars(config_path: Path) -> set[str]:
    """Собрать имена переменных, читаемых шаблоном промпта.

    Args:
        config_path: Путь к YAML-конфигу promptfoo.

    Returns:
        Множество имён из блоков `{% if ... %}` и подстановок `{{ ... }}`.
    """
    text = config_path.read_text(encoding="utf-8")
    return set(IF_BLOCK_RE.findall(text)) | set(VAR_RE.findall(text))


def _load_cases() -> list[dict[str, Any]]:
    """Загрузить кейсы eval-набора с распакованным контрактом.

    Returns:
        Список контрактов кейсов.
    """
    cases: list[dict[str, Any]] = []
    for line in EVAL_CASES_FILE.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        cases.append(json.loads(json.loads(line)["vars"]["contract"]))
    return cases


CASES = _load_cases()
CASE_IDS = [str(case["id"]) for case in CASES]


def _transform() -> Any:
    """Загрузить функцию трансформа promptfoo.

    Returns:
        Функция `transform_vars`, собирающая переменные промпта.
    """
    import sys

    sys.path.insert(0, str(EVAL_DIR.parent / "scripts"))
    from promptfoo_transform import transform_vars

    return transform_vars


def _produce(case: dict[str, Any]) -> dict[str, Any]:
    """Прогнать трансформ на одном кейсе.

    Args:
        case: Контракт кейса.

    Returns:
        Словарь переменных, которые получит шаблон промпта.
    """
    transform_vars = _transform()
    produced: dict[str, Any] = transform_vars(
        {"id": case["id"], "contract": json.dumps(case, ensure_ascii=False)}
    )
    return produced


@pytest.mark.parametrize("config_name", ["promptfooconfig.yaml", "promptfooconfig.mock.yaml"])
def test_config_declares_transform_vars(config_name: str) -> None:
    """Оба конфига promptfoo подключают трансформ переменных."""
    config = (EVAL_DIR / config_name).read_text(encoding="utf-8")
    assert "transformVars" in config, (
        f"{config_name}: не подключён transformVars — промпт роли не попадёт в запрос"
    )
    assert "promptfoo_transform" in config, (
        f"{config_name}: transformVars должен ссылаться на promptfoo_transform"
    )


def test_real_config_template_vars_match_expectation() -> None:
    """Шаблон реального прогона читает ровно перечисленные переменные.

    Защищает от молчаливого расхождения: если в шаблон добавят новую
    переменную, тест потребует её и в списке, и в наборе кейсов.
    """
    assert _template_vars(EVAL_DIR / "promptfooconfig.yaml") == EXPECTED_TEMPLATE_VARS


@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
def test_transform_produces_declared_vars(case: dict[str, Any]) -> None:
    """Трансформ не выдаёт переменных, которых нет в шаблоне."""
    unknown = set(_produce(case)) - EXPECTED_TEMPLATE_VARS
    assert not unknown, f"{case['id']}: трансформ произвёл неизвестные переменные: {unknown}"


def test_every_template_var_is_produced_by_some_case() -> None:
    """Каждая переменная шаблона произведена хотя бы одним кейсом.

    Главный инвариант: раньше промпт роли и вход могли не доходить до
    запроса, и ни один тест этого не замечал.
    """
    produced: set[str] = set()
    for case in CASES:
        produced |= set(_produce(case))
    missing = EXPECTED_TEMPLATE_VARS - produced
    assert not missing, f"Переменные шаблона, которые не производит ни один кейс: {sorted(missing)}"


def test_guide_is_not_delivered_to_any_role() -> None:
    """Гайд оркестратора не подключается к запросу ни одной роли.

    Регрессия: гайд в промпте оркестратора перетягивал модель на ответ по
    гайду — вместо полей своей роли появлялись чужие ключи. Измерено: с
    гайдом 0 из 5 кейсов оркестратора, без гайда — все пять с полным
    набором полей.
    """
    for case in CASES:
        assert "guide" not in _produce(case), f"кейс {case['id']} получил гайд"

    guide = (Path(EVAL_DIR.parent) / "prompts" / "orchestrator-guide.md").read_text(
        encoding="utf-8"
    )
    assert "Триггеры режима" in guide, "гайд должен остаться справочником"
    orchestrator = (Path(EVAL_DIR.parent) / "prompts" / "orchestrator.md").read_text(
        encoding="utf-8"
    )
    assert "Триггеры режима" in orchestrator, (
        "рабочие части гайда должны быть в промпте оркестратора"
    )


def test_role_prompt_is_delivered() -> None:
    """Промпт роли доходит до переменных шаблона.

    Проверяется по маркерам из файлов `prompts/roles/product-manager.md` и
    `prompts/orchestrator.md`: если файл не прочитан, маркеров не будет.
    """
    pm = next(case for case in CASES if case["role"] == "product-manager")
    assert "Product Manager" in str(_produce(pm).get("role_prompt", ""))

    orchestrator = next(case for case in CASES if case["role"] == "orchestrator")
    assert "оркестратор" in str(_produce(orchestrator).get("role_prompt", "")).lower()


def test_rules_are_delivered() -> None:
    """Общие правила из `prompts/rules.md` доходят до промпта."""
    case = CASES[0]
    assert "Факт без источника" in str(_produce(case).get("rules", ""))


def test_every_case_role_has_a_prompt_file() -> None:
    """У каждой роли из набора есть файл промпта, и он попадает в запрос.

    Регрессия, найденная при добавлении критика: `transform_vars` молча
    опускал `role_prompt`, если файла роли нет. Кейс при этом «проходил»
    на mock-провайдере, а реальная модель получала запрос без роли и без
    формата ответа — то есть измерение было недостоверным.
    """
    for case in CASES:
        produced = _produce(case)
        assert produced.get("role_prompt"), f"{case['id']}: промпт роли не подключён"


def test_unknown_role_fails_loudly() -> None:
    """Неизвестная роль — ошибка, а не прогон без промпта роли."""
    transform_vars = _transform()
    contract = json.dumps({"role": "no-such-role", "input": "идея", "mode": "auto"})
    with pytest.raises(FileNotFoundError):
        transform_vars({"id": "X-01", "contract": contract})


def test_input_and_mode_are_delivered() -> None:
    """Вход и режим кейса доходят до промпта без искажений.

    Для роли гейта вход дополняется блоком «гейт + чеклист»: чеклист — предмет
    проверки, поэтому он приходит во входе, а не в промпте роли. Исходный текст
    артефактов обязан сохраниться без изменений.
    """
    for case in CASES:
        produced = _produce(case)
        delivered = str(produced.get("input", ""))
        if case["role"] == "gate-reviewer":
            assert delivered.startswith(f"ГЕЙТ: {case['gate']}"), (
                f"{case['id']}: нет блока гейта во входе"
            )
            assert case["input"] in delivered, f"{case['id']}: артефакты не дошли"
        else:
            assert delivered == case["input"], f"{case['id']}: вход не дошёл"
        assert produced.get("mode") == case["mode"], f"{case['id']}: режим не дошёл"
