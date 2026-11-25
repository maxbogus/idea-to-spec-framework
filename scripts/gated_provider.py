"""Провайдер eval с код-гейтом: пустая идея не доходит до модели.

Зачем. `promptfoo` не умеет отменять вызов провайдера по результату
трансформа, поэтому отсечь пустой вход «до LLM» можно только в самом
провайдере. Этот скрипт — exec-провайдер: он получает от promptfoo
`(prompt, options, context)`, как это делает `scripts/mock_provider.py`.

Логика:
- вход пустой → печатаем детерминированный ответ из
  `idea_to_spec.input_gate` и **не обращаемся к модели**;
- вход непустой → сами вызываем Ollama (тот же HTTP API, что и
  провайдер `ollama:chat`) и печатаем её ответ.

Причина, по которой гейт нужен именно в коде: кейс `NEG-01-empty-idea`
падал на всех семи измеренных моделях (3B–12B, разные семейства) — на
пустом входе модель начинала прогон и писала артефакты. Значит, это не
задача модели, а входная ошибка.

Запуск (promptfoo вызывает так сам):
    exec:python3 ../scripts/gated_provider.py
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

from idea_to_spec.input_gate import gate_input  # noqa: E402

#: Адрес Ollama (тот же, что у провайдера `ollama:chat`).
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")


def _load_context(raw: str) -> dict[str, Any]:
    """Разобрать JSON-аргумент context.

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


def _call_ollama(prompt: str, options: dict[str, Any]) -> str:
    """Вызвать Ollama и вернуть текст ответа.

    Args:
        prompt: Текст запроса.
        options: Настройки провайдера (модель, параметры генерации).

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

    body: dict[str, Any] = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "options": {
            "temperature": _param("temperature", 0),
            "num_predict": _param("num_predict", 3500, "max_tokens"),
            "top_p": _param("top_p", 1),
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


def main() -> int:
    """Точка входа exec-провайдера.

    Returns:
        Всегда 0 — ответ печатается в stdout.
    """
    prompt = sys.argv[1] if len(sys.argv) > 1 else ""
    options = _options(sys.argv[2] if len(sys.argv) > 2 else "{}")
    context = _load_context(sys.argv[3] if len(sys.argv) > 3 else "{}")
    vars_block = _vars(context)
    contract = _contract(vars_block)

    gated = gate_input(_input_text(vars_block, contract))
    if gated is not None:
        print(gated["answer"])
        return 0

    print(_call_ollama(prompt, options))
    return 0


if __name__ == "__main__":
    sys.exit(main())
