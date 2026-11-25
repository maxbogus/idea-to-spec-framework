# Функциональные требования

> Выводятся из бизнес-требований. У каждого — источник (BR-*).

| ID | Требование | Источник | Приоритет | Критерий приёмки |
|---|---|---|---|---|
| FR-1 | POST /api/v1/extract принимает {title, description, seller_data} и возвращает per-attribute value, confidence, source_span, status | BR-1, BR-3 | Must | AC-1, AC-3 |
| FR-2 | Нормализация значений по справочнику (aliases + value_set + единицы измерения) | BR-2 | Must | AC-6 |
| FR-3 | Confidence по каждому атрибуту + маршрутизация low-confidence (порог 0,85) в review | BR-4 | Must | AC-4 |
| FR-4 | Stage 0 preprocessing: HTML-strip, truncate > 3000 символов, leakage-filter, description < 30 → unfilled | BR-5 | Must | NFR-1, NFR-2 |
| FR-5 | Batch-обработка партии CSV/XLSX с job-статусом и прогрессом | BR-6 | Should | AC-3 |
| FR-6 | Кэш ответов LLM (Redis TTL) с graceful degradation в in-memory | BR-5 | Should | NFR-4 |
| FR-7 | Каскад: rules v2 → catalog model v3 → LLM (opt-in) → verifier (value_set / unit / source_span) | BR-3, BR-5 | Must | AC-1, AC-2 |
| FR-8 | Извлечение и валидация source_span (границы значения в исходном тексте) | BR-3 | Must | AC-2 |

## Правила

- Требование без источника — гипотеза, а не требование.
- Два разных показателя в одном требовании — разделить.
