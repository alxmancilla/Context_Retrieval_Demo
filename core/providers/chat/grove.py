import json
from typing import TypeVar

from openai import OpenAI
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class GroveChatProvider:
    """OpenAI-wire client for Azure Grove using Grove's api-key header."""

    def __init__(
        self, *, api_key: str, base_url: str, model: str,
        timeout_seconds: float = 60.0, max_retries: int = 2,
    ) -> None:
        self.model = model
        self.client = OpenAI(
            api_key="grove-header-auth",
            base_url=base_url.rstrip("/"),
            default_headers={"api-key": api_key},
            timeout=timeout_seconds,
            max_retries=max_retries,
        )

    def invoke(self, system: str, user: str) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return response.choices[0].message.content or ""

    def stream(self, system: str, user: str):
        events = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            stream=True,
        )
        for event in events:
            if event.choices and event.choices[0].delta.content:
                yield event.choices[0].delta.content

    def invoke_typed(self, system: str, user: str, schema: type[T]) -> T:
        prompt = (
            f"{user}\n\nReturn JSON only, matching this schema:\n"
            f"{json.dumps(schema.model_json_schema())}"
        )
        raw = self.invoke(system, prompt)
        start, end = raw.find("{"), raw.rfind("}")
        if start < 0 or end < start:
            raise ValueError("Grove response did not contain a JSON object")
        return schema.model_validate_json(raw[start : end + 1])
