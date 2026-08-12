import os

import pytest
from pydantic import BaseModel, Field

from core.providers.chat import GroveChatProvider
from core.settings import get_settings

pytestmark = [
    pytest.mark.integration,
    pytest.mark.grove_live,
    pytest.mark.skipif(
        os.getenv("RUN_LIVE_INTEGRATION") != "1",
        reason="set RUN_LIVE_INTEGRATION=1",
    ),
]


class Probe(BaseModel):
    status: str = Field(pattern="^ok$")


def _provider() -> GroveChatProvider:
    settings = get_settings()
    return GroveChatProvider(
        api_key=settings.grove_api_key,
        base_url=settings.grove_base_url,
        model=settings.grove_model,
        timeout_seconds=settings.grove_timeout_seconds,
        max_retries=settings.grove_max_retries,
    )


def test_grove_typed_and_streaming_shapes_are_live():
    provider = _provider()
    typed = provider.invoke_typed(
        "Follow the requested output schema exactly.",
        "Return status equal to ok.",
        Probe,
    )
    tokens = list(provider.stream("Answer concisely.", "Reply with the single word ok."))
    assert typed.status == "ok"
    assert tokens
    assert "".join(tokens).strip()