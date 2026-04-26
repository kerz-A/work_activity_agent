"""Переиспользуемые pydantic-валидаторы для устойчивости к LLM-выходу.

Маленькие модели (Gemma 4B и т.п.) часто возвращают строку вместо списка строк
или null вместо пустого списка. Эти валидаторы нормализуют такие случаи.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Annotated, Any, TypeVar

from pydantic import BeforeValidator

T = TypeVar("T")


def _to_tuple_of_strings(value: Any) -> tuple[str, ...]:
    """str → (str,), list → tuple, None → (). Любые другие — пробуем привести через iter."""
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,) if value else ()
    if isinstance(value, tuple):
        return tuple(str(v) for v in value)
    if isinstance(value, list):
        return tuple(str(v) for v in value)
    if isinstance(value, Iterable):
        return tuple(str(v) for v in value)
    return (str(value),)


# Type alias для использования: Annotated[tuple[str, ...], FlexibleStringTuple]
FlexibleStringTuple = BeforeValidator(_to_tuple_of_strings)
