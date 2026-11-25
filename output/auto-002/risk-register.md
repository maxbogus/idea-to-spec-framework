# Risk Register

> Риск = Likelihood × Impact. Шкала: low / med / high.

| ID | Риск | Likelihood | Impact | Risk | Владелец | Мера контроля |
|---|---|---|---|---|---|---|
| R-1 | Галлюцинация LLM (выдуманное значение) | med | high | high | ML-команда | source_span + verifier + статус «нет в тексте» |
| R-2 | Стоимость на масштабе 1,18M карточек | med | high | high | PM | гибрид, LLM opt-in, кэш |
| R-3 | Падение качества на новых/редких категориях | high | med | high | ML-команда | общие атрибуты сразу; специфические — на review |
| R-4 | Грязные данные (48.9% HTML, шаблоны продавцов) | high | med | high | SA | Stage 0 preprocessing |
| R-5 | Prompt injection через текст карточки | med | high | high | Architect | sandbox, лимиты, `make test-security` |
| R-6 | Сроки/бюджет хакатона (VM 2 ядра / 4 ГБ) | med | med | med | PM | MVP scope, memory-budget |

## Классификация

- Регуляторный риск (GDPR / AI Act / ГОСТ)
- Риск данных (персональные, утечка)
- Риск интеграций (внешние API, платежи)
- Риск галлюцинаций (непроверенные факты)
- Риск сроков и бюджета
