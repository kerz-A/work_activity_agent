# ADR 0001 — LangGraph для оркестрации пайплайна

**Status**: Accepted
**Date**: 2026-04-25

## Context

Нужен фреймворк для оркестрации многошагового AI-пайплайна (8 узлов: Collector → ImageRedaction → Vision → Classifier → Relevance → Timeline → Scoring → Reports). Состояние должно сериализоваться (для resume после падения на дорогих vision-вызовах).

## Decision

Используем **LangGraph** (`langgraph` + `langgraph-checkpoint-sqlite`).

## Альтернативы

| Вариант | Почему не выбран |
|---|---|
| Claude Agent SDK | Натив для Claude, но менее гибкий для DAG; привязка к одному провайдеру |
| Собственный pipeline на asyncio | Больше boilerplate; нет встроенного checkpointing/observability |
| Celery + FastAPI | Distributed task queue избыточен для MVP; нет state-machine из коробки |

## Consequences

- ➕ State-machine с явными переходами и checkpointing
- ➕ Хорошая интеграция с LangSmith для трассировки
- ➕ Pydantic state из коробки
- ➖ Зависимость от LangChain экосистемы (но используем минимально, только LangGraph core)
- ➖ Дополнительная кривая обучения для тех кто не работал
