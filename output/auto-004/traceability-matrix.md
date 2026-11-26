# Traceability Matrix

> Связь: бизнес-цель → требование → спецификация → критерий приёмки →
> тест/компонент → задача → коммит/тест → статус. Требование без адресата и
> без задачи — недозрелое.

| Бизнес-цель | Требование | Спецификация | Критерий приёмки | Тест / компонент | Задача (T-*) | Коммит / тест | Статус |
|---|---|---|---|---|---|---|---|
| G-1 | BR-1 / FR-1 | §3 | AC-1 | scripts/idea_to_spec/input_gate.py | T-1 | tests/test_input_gate.py | implemented |
| G-1 | BR-1 / FR-2 | §3 | AC-2 | scripts/scaffold-run.sh, templates/ | T-2 | tests/test_scaffold_matches_start.py | implemented |
| G-1, G-2 | BR-2, BR-9 / FR-3 | §3 | AC-3 | scripts/check_run.py | T-3 | tests/test_run_consistency.py | implemented |
| G-1 | BR-2, BR-9 / FR-4 | §3 | AC-4 | scripts/check_run.py | T-4 | tests/test_run_consistency.py | implemented |
| G-2 | BR-3 / FR-5 | §3 | AC-5 | scripts/check_run.py (частично), prompts/gate-checklists.md | T-5 | нет теста: разрыв v0.3 | draft |
| G-2 | BR-4 / FR-6 | §3 | AC-6 | prompts/orchestrator.md, eval/cases/roles.jsonl | T-6 | tests/test_eval_contract.py | approved |
| G-2 | BR-5 / FR-7 | §3 | AC-7 | subagents/fact-check.md, scripts/check_run.py | T-7 | tests/test_run_consistency.py | implemented |
| G-2 | BR-6 / FR-8 | §3 | AC-8 | templates/open-questions.md, scripts/check_run.py | T-8 | tests/test_run_consistency.py | implemented |
| G-3 | BR-7 / FR-9 | §3 | AC-9 | scripts/make_eval_config.py, Makefile | T-9 | tests/test_make_eval_config.py | implemented |
| G-3 | BR-7 / FR-10 | §3 | AC-10 | Makefile §eval, eval/cases/roles.jsonl | T-10 | tests/test_eval_contract.py | implemented |
| G-4 | BR-8 / FR-11 | §3 | AC-11 | idea_to_spec_framework.py | T-11 | tests/test_connect.py | implemented |
| G-4 | BR-8 / FR-12 | §3 | AC-12 | idea_to_spec_framework.py | T-12 | tests/test_export.py | implemented |
| G-2 | BR-10, BR-9 / FR-13 | §3 | AC-13 | scripts/check_artifact_policy.py | T-13 | tests/test_artifact_policy.py | draft |
| G-2 | BR-5, BR-10 / FR-14 | §3 | AC-14 | промпты ролей (нет изоляции) | T-14 | нет теста: разрыв v0.3 | draft |
| G-3 | BR-7, BR-3 / FR-15 | §3 | AC-15 | Makefile, scripts/session_analytics.py | T-15 | нет теста: разрыв v0.3 | draft |
| G-1 | BR-2, BR-6 / FR-16 | §3 | AC-16 | scripts/check_run.py (нет diff) | T-16 | нет теста: разрыв v0.3 | draft |

## Покрытие по BR

- BR-1 → FR-1, FR-2
- BR-2 → FR-2, FR-3, FR-4, FR-16
- BR-3 → FR-5, FR-15
- BR-4 → FR-6
- BR-5 → FR-7, FR-14
- BR-6 → FR-8, FR-16
- BR-7 → FR-9, FR-10, FR-15
- BR-8 → FR-11, FR-12
- BR-9 → FR-3, FR-4, FR-13
- BR-10 → FR-13, FR-14

## Проверка полноты

- [x] у каждого требования есть бизнес-цель
- [x] у каждого требования есть критерий приёмки
- [x] у каждого требования есть адресат (компонент или явный разрыв)
- [x] у каждого требования есть задача (`T-*`) и статус покрытия
- [ ] шесть требований в статусе `draft` — сознательно, до ответов Q-4 и Q-5
