from collections.abc import Iterator
from typing import Protocol, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class ChatProvider(Protocol):
    def invoke(self, system: str, user: str) -> str: ...

    def stream(self, system: str, user: str) -> Iterator[str]: ...

    def invoke_typed(self, system: str, user: str, schema: type[T]) -> T: ...
