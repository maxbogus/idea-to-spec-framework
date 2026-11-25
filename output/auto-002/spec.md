# Спецификация

## 1. Назначение и scope

Сервис извлекает характеристики товара из текста карточки продавца
(title + description + seller_data) и приводит их к единому формату с
уверенностью и цитатой по каждому значению.

**Входит в MVP:**

- нормализация значения + синонимы («алый»/«red» → «красный»);
- проверка значения по `value_set` (закрытому справочнику);
- `source_span` — offset значения в исходном тексте;
- confidence per-attribute + порог 0,85 → человек;
- POST /extract + batch + UI проверки (вторично).

**НЕ входит в MVP:**

- фото и генерация изображений;
- генерация описаний;
- авторизация и роли;
- маппинг на схемы других площадок;
- вторая LLM как verifier (Walmart-pattern) — после хакатона.

## 2. Use cases

| ID | Актор | Цель | Шаги |
|---|---|---|---|
| UC-1 | P-1/P-4 | Извлечь атрибуты одной карточки | см. `use-cases.md` |
| UC-2 | P-1 | Обработать партию CSV/XLSX | постановка job + прогресс + экспорт |
| UC-3 | P-1 | Проверить очередь сомнительных | цитата + accept/fix |
| UC-4 | P-2 | Добавить категорию, увидеть метрики | схема + gold + F1 |
| UC-5 | P-3 | Найти товар по фильтру | транзитивно через атрибуты |

## 3. Функциональные требования

| ID | Требование | Источник |
|---|---|---|
| FR-1 | POST /api/v1/extract: value, confidence, source_span, status | BR-1, BR-3 |
| FR-2 | Нормализация по справочнику (aliases + value_set + единицы) | BR-2 |
| FR-3 | Confidence per-attribute + порог 0,85 → review | BR-4 |
| FR-4 | Stage 0: HTML-strip, truncate > 3000, leakage, min_len < 30 → unfilled | BR-5 |
| FR-5 | Batch CSV/XLSX + job-статус и прогресс | BR-6 |
| FR-6 | Redis TTL кэш + graceful degrade | BR-5 |
| FR-7 | Каскад rules → catalog model → LLM opt-in → verifier | BR-3, BR-5 |
| FR-8 | Валидация source_span | BR-3 |

## 4. Нефункциональные требования

| ID | Категория | Требование |
|---|---|---|
| NFR-1 | производительность | p95 ≤ 50 мс (hybrid, без LLM) |
| NFR-2 | память | Peak RSS < 4 ГБ на batch |
| NFR-3 | безопасность | prompt injection / JSON-бомба / ReDoS / XXE / формулы CSV |
| NFR-4 | доступность | деградация к правилам при отказе LLM/Redis |
| NFR-5 | данные | карточки не персональные; source_span для аудита |
| NFR-6 | локализация | RU/EN значения и бренды |

## 5. Интеграции

| Откуда | Куда | Контракт |
|---|---|---|
| Attributor API | LLM-шлюз (OpenAI-совместимый) | HTTPS, opt-in, Tier-1/Tier-2 |
| Attributor API | PostgreSQL | SQL, jobs / attributor tables |
| Attributor API | Redis | RESP, LLM cache TTL |
| Eval pipeline | MLflow | file-store (`mlruns/`) |
| Фронтенд (React) | API | HTTP/JSON, SSE — план |

## 6. Данные и безопасность

- **Card**: sku_id, title, description, seller_data — не персональные.
- **AttributeValue**: attribute_id, value_raw, value_canonical, confidence,
  source_span.
- **Job**: id, status, progress, counters.
- **LLMCache**: key(hash), response, TTL.
- **KbModel**: модель, категория, атрибуты (review-only).
- ПДн нет; source_span хранится только для аудита; TTL кэша ограничен.

## 7. Открытые вопросы

- P-002 (MVP-категории), P-003 (дизайн-контракт), целевой порог,
  модель монетизации.

## 8. Ссылки на артефакты

- `traceability-matrix.md`
- `risk-register.md`
- `human-oversight-plan.md`
- `validation-report.md`
- `hallucination-log.md`

## 9. Архитектура и процессы

Слои (Clean Architecture):

- **Presentation** — FastAPI routes (extract, jobs), schemas, deps.
- **Application** — use cases + ports (LLMClientPort).
- **Core** — pure `extract(product, llm) -> ProductOutput`.
- **Domain** — ProductInput, Attribute, Value.
- **Infrastructure** — llm (stub/gigachat), cache (in-memory/redis),
  db (jobs, attributor), eval.
- **Shared** — config (pydantic-settings), logging (structlog).

Компоненты:

- Правила v2 (regex + словари) — 0 LLM-вызовов.
- Catalog model v3 (distant supervision, 1237 категорий) — 0 LLM.
- LLM cascade Tier-1/Tier-2 — opt-in.
- Verifier (value_set / unit / source_span).

Процессы (для DFD):

1. Preprocess (Stage 0)
2. Extract (rules / catalog model / LLM)
3. Verify
4. Route (accepted | review)

Хранилища (для DFD / ER):

- D1 cards, D2 job store, D3 llm cache, D4 kb model.

## 10. ADR

| ID | Решение | Контекст | Последствия |
|---|---|---|---|
| ADR-1 | Гибридный пайплайн (rules → catalog model → LLM opt-in → verifier), не «LLM на каждую карточку» | стоимость × 1.18M, latency | 0 LLM в prod hybrid; LLM только на хвост |
| ADR-2 | Честная уверенность + source_span | главный риск — галлюцинации | каждое значение проверяемо и подсвечиваемо |
| ADR-3 | PostgreSQL + Redis в compose, без Celery/Qdrant | VM 2 ядра / 4 ГБ, anti-stack | async streaming + SSE вместо очередей |
| ADR-4 | LLM через OpenAI-совместимый шлюз (GigaChat via LiteLLM), opt-in | доступность / стоимость | деградация к правилам без шлюза |
| ADR-5 | Clean Architecture (presentation/application/core/domain/infrastructure/shared) | тестируемость, замена LLM | core без БД/HTTP/кэша |
