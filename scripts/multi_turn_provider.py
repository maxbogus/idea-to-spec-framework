"""Многоходовый exec-провайдер: настоящий диалог вместо одного хода.

Зачем. Измерено (F023): `scripts/gated_provider.py` отправляет ровно одно
сообщение (`messages: [{role: user, content: prompt}]`), поэтому кейсы
режимов `chat` и `hybrid` проверяли один ход в режиме диалога, а не сам
диалог. Не покрыты: второй ход, реакция на ответ заказчика (факт с
источником «ответ заказчика»), критерий остановки диалога и развилка в
`hybrid`.

Этот провайдер закрывает разрыв:

1. сам вызывает Ollama (тот же HTTP API, что у `ollama:chat`), но по ходам;
2. берёт вопрос из ответа модели, находит в сценарии кейса пару
   «вопрос → ответ» и формирует следующий запрос С ИСТОРИЕЙ;
3. накапливает ходы, пока сценарий не кончится.

Сценарий лежит в контракте кейса (`eval/cases/roles.jsonl`):

    "dialogue": {
      "turns": [
        {"question_contains": "срок хранения", "answer": "12 месяцев (ответ заказчика)"}
      ]
    }

Кейс без сценария (`dialogue` отсутствует) обрабатывается как обычный
одноходовый вызов: провайдер не ломает существующий набор.

Запуск (promptfoo вызывает так сам):
    exec:python3 ../scripts/multi_turn_provider.py
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

#: Скрипт запускается из `scripts/`, пакет `idea_to_spec` лежит рядом.
#: Путь добавляется до импорта — иначе модуль не найдётся при запуске
#: exec-провайдера из другого каталога.
_SCRIPTS_DIR = str(Path(__file__).resolve().parent)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from idea_to_spec.multi_turn import (  # noqa: E402
    DialogueTurn,
    build_history,
    run_turns,
)

#: Адрес Ollama (тот же, что у провайдера `ollama:chat`).
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")


def _load_json(raw: str) -> dict[str, Any]:
    """Разобрать JSON-аргумент.

    Args:
        raw: Строка с JSON.

    Returns:
        Словарь (пустой, если разбор не удался).
    """
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _vars(context: dict[str, Any]) -> dict[str, Any]:
    """Извлечь переменные тест-кейса.

    Args:
        context: Разобранный context.

    Returns:
        Словарь переменных (пустой, если их нет).
    """
    vars_block = context.get("vars")
    return vars_block if isinstance(vars_block, dict) else {}


def _contract(vars_block: dict[str, Any]) -> dict[str, Any]:
    """Извлечь контракт кейса из переменной `contract`.

    Args:
        vars_block: Переменные тест-кейса.

    Returns:
        Словарь контракта (пустой, если контракт не передан).
    """
    raw = vars_block.get("contract")
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str) or not raw.strip():
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _scenario(contract: dict[str, Any]) -> dict[str, Any]:
    """Извлечь сценарий диалога из контракта кейса.

    Args:
        contract: Контракт кейса.

    Returns:
        Блок `dialogue` (пустой, если сценария нет).
    """
    raw = contract.get("dialogue")
    return raw if isinstance(raw, dict) else {}


def _input_text(vars_block: dict[str, Any], contract: dict[str, Any]) -> str:
    """Получить вход кейса.

    Args:
        vars_block: Переменные тест-кейса.
        contract: Контракт кейса.

    Returns:
        Текст входа (пустая строка, если входа нет).
    """
    return str(contract.get("input") or vars_block.get("input") or "")


def _options(raw: str) -> dict[str, Any]:
    """Разобрать JSON-аргумент options.

    Args:
        raw: Строка с JSON.

    Returns:
        Словарь настроек (пустой, если разбор не удался).
    """
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _call_ollama(
    prompt: str, options: dict[str, Any], history: list[dict[str, str]] | None = None
) -> str:
    """Вызвать Ollama и вернуть текст ответа.

    Args:
        prompt: Текст запроса (промпт роли с входом).
        options: Настройки провайдера (модель, параметры генерации).
        history: История переписки (пустая на первом ходе).

    Returns:
        Текст ответа модели.

    Raises:
        RuntimeError: Если Ollama недоступна или ответил ошибкой.
    """
    raw_config = options.get("config")
    config: dict[str, Any] = raw_config if isinstance(raw_config, dict) else {}
    model = str(config.get("model") or os.environ.get("OLLAMA_MODEL", "qwen3:8b"))

    # Параметры генерации лежат в config напрямую (temperature, num_predict,
    # top_p) — так их пишет eval/promptfooconfig.yaml. Ключ `generation`
    # тоже поддерживается: там имена другие (max_tokens).
    raw_generation = config.get("generation")
    generation: dict[str, Any] = raw_generation if isinstance(raw_generation, dict) else {}

    def _param(name: str, fallback: Any, alias: str | None = None) -> Any:
        if name in config:
            return config[name]
        if alias is not None and alias in generation:
            return generation[alias]
        return fallback

    messages: list[dict[str, str]] = []
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": prompt})

    body: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {
            "temperature": _param("temperature", 0),
            "num_predict": _param("num_predict", 3500, "max_tokens"),
            "top_p": _param("top_p", 1),
            # Контекст задаётся явно: иначе Ollama берёт 4096 и вытесняет
            # начало промпта при генерации (замер 2026-11-26).
            "num_ctx": _param("num_ctx", 16384),
        },
    }
    if "think" in config:
        body["think"] = config["think"]

    request = urllib.request.Request(
        f"{OLLAMA_URL}/api/chat",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=600) as response:
            payload = json.loads(response.read())
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Ollama недоступна на {OLLAMA_URL}: {exc}") from exc
    message = payload.get("message") or {}
    return str(message.get("content") or "")


def run_dialogue(
    prompt: str,
    options: dict[str, Any],
    scenario: dict[str, Any],
    mode: str = "",
    input_text: str = "",
) -> tuple[str, list[DialogueTurn]]:
    """Провести диалог по сценарию и вернуть последний ответ роли.

    Логика ходов — общая с mock-провайдером (`idea_to_spec.multi_turn.run_turns`),
    чтобы `eval-mock` воспроизводил ровно то, что проверяет реальный прогон.

    Args:
        prompt: Текст запроса (промпт роли с входом).
        options: Настройки провайдера.
        scenario: Блок `dialogue` контракта кейса.
        mode: Режим прогона.
        input_text: Исходный вход кейса.

    Returns:
        Последний ответ роли и список состоявшихся ходов.
    """
    return run_turns(
        prompt,
        scenario,
        lambda current_prompt, turns: _call_ollama(current_prompt, options, build_history(turns)),
        mode=mode,
        input_text=input_text,
    )


def main() -> int:
    """Точка входа exec-провайдера.

    Returns:
        Всегда 0 — ответ печатается в stdout.
    """
    prompt = sys.argv[1] if len(sys.argv) > 1 else ""
    options = _options(sys.argv[2] if len(sys.argv) > 2 else "{}")
    context = _load_json(sys.argv[3] if len(sys.argv) > 3 else "{}")
    vars_block = _vars(context)
    contract = _contract(vars_block)
    scenario = _scenario(contract)

    if not scenario:
        # Кейс без сценария — обычный одноходовый вызов.
        print(_call_ollama(prompt, options))
        return 0

    output, _turns = run_dialogue(
        prompt,
        options,
        scenario,
        mode=str(contract.get("mode") or ""),
        input_text=_input_text(vars_block, contract),
    )
    print(output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
