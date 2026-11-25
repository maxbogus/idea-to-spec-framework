"""Мост для JS-ассерта promptfoo: структурная проверка ответа.

Зачем. Assert в `eval/promptfooconfig.yaml` — это JavaScript, а проверки
контракта живут в Python (`scripts/idea_to_spec/semantic_check.py`). Чтобы
реальный прогон и pytest смотрели на одно и то же правило, JS вызывает этот
скрипт.

Протокол: на входе — JSON `{"check": "<имя проверки>", "output": "<ответ>",
"mode": "<заданный режим>", "customer_answer": "<ответ заказчика>",
"answered_question": "<отвеченный вопрос>", "scenario_exhausted": true}`,
на выходе — JSON `{"problems": ["...", ...]}`. Пустой список — проверка
выполнена.

Поля контекста диалога необязательны: без них проверки диалога не дают
ложных срабатываний (например, `dialogue_stops_when_answered` без
`scenario_exhausted` молчит).

Запуск (из JS-ассерта promptfoo):
    python3 scripts/semantic_check_bridge.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

#: Скрипт запускается из `scripts/`, пакет `idea_to_spec` лежит рядом.
_SCRIPTS_DIR = str(Path(__file__).resolve().parent)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from idea_to_spec.semantic_check import run_semantic_check  # noqa: E402

#: Ключи контекста, которые передаются в проверку.
CONTEXT_KEYS = ("customer_answer", "answered_question", "scenario_exhausted")


def main() -> int:
    """Прочитать запрос, выполнить проверку, напечатать результат.

    Returns:
        Всегда 0 — результат печатается в stdout.
    """
    raw = sys.stdin.read() if not sys.stdin.isatty() else "{}"
    try:
        request = json.loads(raw)
    except json.JSONDecodeError:
        request = {}
    if not isinstance(request, dict):
        request = {}

    name = str(request.get("check") or "")
    output = str(request.get("output") or "")
    expected_mode = str(request.get("mode") or "")
    context = {key: request[key] for key in CONTEXT_KEYS if key in request}
    problems = run_semantic_check(name, output, expected_mode, **context)
    print(json.dumps({"problems": problems}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
