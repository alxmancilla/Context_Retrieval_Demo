from typing import Any

from core.providers.chat.base import ChatProvider
from core.providers.chat.grove import GroveChatProvider
from core.providers.chat.openai import OpenAIChatProvider


def create_chat_provider(settings: Any) -> ChatProvider:
    if settings.chat_provider == "openai":
        return OpenAIChatProvider(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            model=settings.openai_model,
            timeout_seconds=settings.openai_timeout_seconds,
            max_retries=settings.openai_max_retries,
        )
    return GroveChatProvider(
        api_key=settings.grove_api_key,
        base_url=settings.grove_base_url,
        model=settings.grove_model,
        timeout_seconds=settings.grove_timeout_seconds,
        max_retries=settings.grove_max_retries,
    )


__all__ = [
    "ChatProvider",
    "GroveChatProvider",
    "OpenAIChatProvider",
    "create_chat_provider",
]
