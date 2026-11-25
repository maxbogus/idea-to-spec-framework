"""Структурные проверки контракта: семантика вместо лексики.

Историческая причина. Кейс `DISC-01-no-solution-as-need` требовал
`must_contain: ["потребност"]` — то есть буквального слова «потребность».
Проверялось это семь лет модели разных семейств и размеров (3B–12B):
все они описывали потребность правильно — в `jobs_to_be_done[].want`
(«Получить награду за покупку», «получать премии за покупки»), но ни одна
не написала слово «потребность». Провал оказался свойством ассерта, а не
модели: лексическое требование навязывало формулировку вместо смысла.

Правильный критерий кейса — структурный: потребность отделена от решения.
Проверяется, что ответ содержит потребность (как текст желания в
`jobs_to_be_done[].want` или в `as_is`/`to_be`) и что решение не выдано за
потребность (решение упомянуто не в поле потребности, а в `as_is`/`to_be`
либо помечено как гипотеза/допущение).

Проверки:
1. Потребность не пуста: `jobs_to_be_done[].want` или `to_be` непусты.
2. Решение не выдано за потребность: если решение упомянуто в
   `jobs_to_be_done[].want`, оно помечено как гипотеза или допущение.
"""

from __future__ import annotations

from idea_to_spec.semantic_check import (
    check_needs_separated as needs_separated,
)
from idea_to_spec.semantic_check import run_semantic_check

#: Слова, которыми в ответе называют гипотезу о решении.
_HYPOTHESIS_MARKERS = ("допущени", "гипотез", "предположен", "вариант решения")

#: Технологии и решения, неразличимые по форме. Кейс проверяет, что решение
#: отделено от потребности, поэтому сам термин в ответе допустим — важен
#: контекст, в котором он назван.
_SOLUTION_HINTS = (
    "блокчейн",
    "blockchain",
    "postgresql",
    "mysql",
    "redis",
    "kafka",
    "docker",
    "kubernetes",
    "микросервис",
    "nosql",
    "mongodb",
    "graphql",
)


def needs_are_present(output: str) -> list[str]:
    """Проверить структурный критерий по тексту ответа.

    Args:
        output: Текст ответа модели.

    Returns:
        Список проблем (пустой, если критерий выполнен).
    """
    return run_semantic_check("needs_separated", output)


#: Ответ, который реально дала qwen3:8b на кейс DISC-01 (из отчёта
#: docs/evaluation/eval-qwen3-8b.json): потребность описана правильно,
#: слово «потребность» не употреблено ни разу.
REAL_QWEN3_ANSWER = """{
  "personas": [{"id": "P-1", "name": "Клиент", "context": "B2C"}],
  "contour": "B2C",
  "jobs_to_be_done": [
    {"id": "J-1", "persona": "P-1", "when": "После совершения покупки",
     "want": "Получить награду за покупку",
     "so_that": "Увеличить лояльность к бренду"}
  ],
  "as_is": "Текущая система лояльности использует традиционные карты и баллы.",
  "to_be": "Система лояльности на блокчейне с начислением баллов.",
  "business_requirements": [
    {"id": "BR-1", "text": "Реализовать систему лояльности на блокчейне",
     "source": "допущение", "status": "draft", "owner": "business-analyst"}
  ]
}"""

#: Ответ, где решение выдано за потребность.
SOLUTION_AS_NEED = """{
  "personas": [{"id": "P-1", "name": "Клиент"}],
  "jobs_to_be_done": [
    {"id": "J-1", "persona": "P-1", "when": "всегда",
     "want": "Нужен блокчейн для программы лояльности"}
  ],
  "as_is": "Карты и баллы.",
  "to_be": "Блокчейн."
}"""

#: Ответ, где решение помечено как гипотеза — это допустимо.
SOLUTION_AS_HYPOTHESIS = """{
  "personas": [{"id": "P-1", "name": "Клиент"}],
  "jobs_to_be_done": [
    {"id": "J-1", "persona": "P-1", "when": "после покупки",
     "want": "Получить награду (гипотеза: реализация на блокчейне)"}
  ],
  "as_is": "Карты.",
  "to_be": "Программа лояльности."
}"""


def test_real_qwen3_answer_passes_semantic_check() -> None:
    """Ответ реальной модели проходит структурную проверку."""
    assert needs_are_present(REAL_QWEN3_ANSWER) == []


def test_lexical_requirement_would_fail_on_same_answer() -> None:
    """Тот же ответ не проходит лексическое требование — причина правки."""
    assert "потребност" not in REAL_QWEN3_ANSWER.lower()


def test_solution_as_need_is_rejected() -> None:
    """Решение, выданное за потребность, отвергается."""
    problems = needs_are_present(SOLUTION_AS_NEED)
    assert problems, "решение как потребность должно отвергаться"
    assert "блокчейн" in problems[0]


def test_solution_marked_as_hypothesis_is_accepted() -> None:
    """Решение с явной пометкой «гипотеза» допускается."""
    assert needs_are_present(SOLUTION_AS_HYPOTHESIS) == []


def test_empty_need_is_rejected() -> None:
    """Отсутствие выраженной потребности — проблема."""
    payload = {
        "jobs_to_be_done": [{"id": "J-1", "want": ""}],
        "as_is": "",
        "to_be": "",
    }
    problems = needs_separated(payload, "")
    assert problems
    assert "потребность не выражена" in problems[0]


def test_non_json_answer_reported() -> None:
    """Не-JSON ответ помечается проблемой разбора."""
    problems = needs_are_present("просто текст без JSON")
    assert problems == ["ответ не разобран как JSON (проверка needs_separated)"]
