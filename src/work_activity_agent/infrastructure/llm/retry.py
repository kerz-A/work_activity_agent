"""Retry-обёртки для LLM-вызовов через tenacity."""

from __future__ import annotations

import logging

from tenacity import (
    AsyncRetrying,
    RetryError,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger(__name__)


def build_async_retrying(
    max_attempts: int = 3,
    min_wait_s: float = 1.0,
    max_wait_s: float = 30.0,
    retry_on: tuple[type[BaseException], ...] = (Exception,),
) -> AsyncRetrying:
    """Сконфигурированный AsyncRetrying для LLM-вызовов.

    Использование:
        retrying = build_async_retrying()
        async for attempt in retrying:
            with attempt:
                result = await llm_call()
    """
    return AsyncRetrying(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=min_wait_s, max=max_wait_s),
        retry=retry_if_exception_type(retry_on),
        reraise=True,
    )


__all__ = ["RetryError", "build_async_retrying"]
