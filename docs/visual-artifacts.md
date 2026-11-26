# Визуальные артефакты: каталог, паки, DoR

> Операционный документ фреймворка. Отвечает на три вопроса: какая диаграмма
> что показывает, чем она отличается от «просто картинки», и когда её
> отсутствие — дефект спецификации. Источник статусов — первоисточники
> (OMG, IEEE, c4model.com), а не книги и не блоги.

## 1. Принцип: диаграмма — производная

Диаграмма строится из тех же ID, что и требования: `J-*` из `jtbd.md`,
`UC-*` из `use-cases.md`, данные из `spec.md §6`, компоненты из §9, жизненные
циклы из §18. Узел, которого нет в артефакте, — придуман; такая диаграмма
не строится. Поэтому «диаграмма как код»: источник — `.mmd`, `.png` только
рендер (`make render`), `.drawio`/`.vsdx` источником не считаются.

## 2. Статусы

| Статус | Значение | Пример |
|---|---|---|
| `standard` | формальная спецификация | BPMN 2.0.2, DMN 1.6, UML 2.5.1 |
| `de-facto` | стандарт рынка без формального статуса | C4 (модель, не стандарт) |
| `practice` | практика без единой нотации | Event Storming, DDD-карты |
| `opinion` | спорная рекомендация | «80% покрытия диаграммами» |
| `reference` | документируем, но не генерируем | ArchiMate, SysML, Wardley |

## 3. Матрица: артефакт → нотация → пак → владелец

| Артефакт | Нотация | Пак | Владелец | Статус |
|---|---|---|---|---|
| Use case | `usecase-beta` | base | SA | practice |
| Sequence | `sequenceDiagram` | base | SA | standard (UML) |
| ER | `erDiagram` | base | SA | practice |
| DFD L0–L3 | `flowchart` | extended | SA | practice (ГОСТ 2.701 / ISO 5807) |
| C4 C1–C4 | `C4Context`…`C4Deployment` | extended | Architect | de-facto |
| BPMN | `flowchart` + XML | extended | SA | standard |
| Activity | `flowchart` | extended | Architect | standard (UML) |
| Gantt | `gantt` | extended | PM | practice |
| Жизненные циклы | `stateDiagram-v2` | behavior | SA | standard (UML) |
| Карта доменов | `flowchart` + subgraphs | domain | SA | practice (DDD) |
| Event Storming | `flowchart` + classDef | domain | SA | practice |
| DMN (приближение) | `flowchart` | process | BA/SA | standard (с оговоркой) |
| SIPOC | `flowchart LR` | process | BA | practice |
| Service blueprint | `flowchart` + subgraphs | ux | Designer | practice |
| Data lineage | `flowchart LR` | data | SA | practice |
| RAG pipeline | `flowchart` + subgraphs | ai | SA | practice |
| Vector schema | `erDiagram` | ai | SA | practice |
| Agent workflow | `stateDiagram-v2` | ai | Architect | practice |
| Prompt flow | `flowchart LR` | ai | Architect | practice |
| Feedback loop | `flowchart LR` | ai | Architect | practice |
| Network topology | `flowchart` + subgraphs | infra | Architect | practice |
| IaC | `flowchart LR` | infra | Architect | practice |
| C4 Code | `classDiagram` | architecture | Architect | optional |

Источники разделов — `templates/spec-template.md` §11–§18; §6 и §9 питают
базовый и расширенный уровни.

## 4. Паки

| Пак | Диаграммы | Когда включать |
|---|---|---|
| `behavior` | `state` | у сущности есть статусы и правила переходов |
| `domain` | `domain-map`, `event-storming` | система делится на контексты; события важнее сущностей |
| `process` | `dmn`, `sipoc` | правила ветвятся; нужно зафиксировать границы процесса |
| `ux` | `service-blueprint` | у сервиса есть frontstage/backstage |
| `data` | `data-lineage` | данные проходят обработку, есть PII |
| `ai` | `rag-pipeline`, `vector-schema`, `agent-workflow`, `prompt-flow`, `feedback-loop` | есть LLM, RAG, агент или eval |
| `infra` | `network-topology`, `iac` | есть развёртывание и зоны доверия |
| `architecture` | `c4-code` | критичное ядро требует диаграммы классов |

Включение только явное: `make scaffold RUN=<id> PACKS="data,ai"`.
`full` паков не добавляет; `all` = base + extended + все паки.

## 5. DoR: профили

| Профиль | Что требуется |
|---|---|
| `base` | use case, sequence, C4 C1–C2 |
| `full` | base + ER, DFD L0–L3, C4 C3–C4, BPMN (`.mmd` + `.bpmn`), activity, gantt |
| `startup` | base + ER + `state` |
| `enterprise` | full + behavior, domain, process, data, architecture |
| `ai` | full + behavior, data, ai |
| `china` | как enterprise (региональные требования — в чек-листах) |

Проверка: `make check-dor RUN=<id> PROFILE=<profile>` — по умолчанию
report-only; `STRICT=1` роняет гейт. Профиль `auto` выводится из состава
файлов: есть расширенные — требуется полный набор.

## 6. Инструменты

| Инструмент | Роль |
|---|---|
| Mermaid + `mmdc >= 12.0.0` | основной рендер; детерминированный конфиг `templates/mermaid-config.json` |
| PlantUML | reference-only нотации (Wardley, ArchiMate, Communication) |
| Structurizr | C4 как модель, когда нужна генерация нескольких представлений |
| Camunda Modeler | канонический BPMN/DMN XML |
| Draw.io | допустим как рабочий инструмент, но XML — не источник истины в прогоне |

## 7. Reference-only

Не генерируются фреймворком и не входят в DoR: Wardley Map, Business Model
Canvas, ArchiMate, SysML, Communication Diagram, network topology с
вендорными иконками, IaC-визуал, DMN XML. Причина — либо нет честной
Mermaid-нотации, либо формат является таблицей/контрактом, а не диаграммой.
Подробности и альтернативы — `skills/diagram-generation/references/diagram-catalog.md`.

## 8. Связь со стандартами

- IEEE 1016 (SDD): описывает структуру описания проекта, DFD не предписывает;
  статус документа — Inactive-Reserved, поэтому ссылка справочная.
- OMG BPMN 2.0.2, DMN 1.6, UML 2.5.1, SysML 2.0 — формальные нотации.
- C4 — модель описания архитектуры (c4model.com), не стандарт.
- TOGAF/ArchiMate, DDD/Event Storming — методологии; во фреймворке берутся
  только те представления, которые выводятся из артефактов.

Маппинг на SDLC/PDLC и региональные нормы — `standards-mapping.md`.

> Статусы проверены 2026-11-26 по первоисточникам. Перед публикацией
> внешних материалов номера версий перепроверить: BPMN 2.0.2, DMN 1.6,
> UML 2.5.1, SysML 2.0.
