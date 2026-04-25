# ADR 0002 — LiteLLM как абстракция над LLM провайдерами

**Status**: Accepted
**Date**: 2026-04-25

## Context

Нужен единый интерфейс к Vision и text LLM с возможностью смены провайдера через конфиг. Anthropic/OpenAI/локальные модели должны быть взаимозаменяемы.

## Decision

Используем **LiteLLM** как универсальный SDK.

## Альтернативы

| Вариант | Почему не выбран |
|---|---|
| Только Anthropic SDK | Привязка к одному провайдеру; нет fallback'ов |
| Только OpenAI SDK | То же самое |
| Гибрид: локальный OCR + LLM | Сложнее, два пайплайна обработки |

## Consequences

- ➕ Смена провайдера через `configs/models.yaml` (alias → real model name)
- ➕ Из коробки: structured output (`response_format=json_schema`), cost tracking, retry hooks
- ➕ Поддержка десятков провайдеров — легко расширить (Vertex, Bedrock, Azure)
- ➖ Дополнительный слой абстракции — иногда сложнее дебажить
- ➖ Зависимость от темпа развития LiteLLM (мелкие вещи могут отставать от нативных SDK)
