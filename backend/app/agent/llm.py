"""The two kinds of model call the agent makes, over Groq's OpenAI-compatible
API: a tool-calling turn (chat) and a strict-JSON answer (json). Tests swap in
a scripted object with the same two methods."""

from dataclasses import dataclass

import openai
from pydantic import BaseModel

from app.config import settings
from app.services.tailoring import GROQ_BASE_URL, strict_json_schema


@dataclass
class Call:
    id: str
    name: str
    arguments: str  # JSON text, as the model wrote it


@dataclass
class Reply:
    content: str
    tool_calls: list[Call]

    def as_message(self) -> dict:
        message = {"role": "assistant", "content": self.content}
        if self.tool_calls:
            message["tool_calls"] = [
                {"id": c.id, "type": "function", "function": {"name": c.name, "arguments": c.arguments}}
                for c in self.tool_calls
            ]
        return message


class GroqLLM:
    def __init__(self, client=None):
        self.client = client or openai.OpenAI(api_key=settings.groq_api_key, base_url=GROQ_BASE_URL)
        self.calls = 0

    def chat(self, messages: list[dict], tools: list[dict]) -> Reply:
        self.calls += 1
        response = self.client.chat.completions.create(
            model=settings.groq_model, messages=messages, tools=tools, tool_choice="auto", max_tokens=2000,
        )
        message = response.choices[0].message
        return Reply(
            content=message.content or "",
            tool_calls=[Call(c.id, c.function.name, c.function.arguments) for c in message.tool_calls or []],
        )

    def json(self, system: str, user: str, schema: type[BaseModel]) -> BaseModel:
        self.calls += 1
        response = self.client.chat.completions.create(
            model=settings.groq_model, max_tokens=2000,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            response_format={"type": "json_schema", "json_schema": {
                "name": schema.__name__.lower(), "strict": True, "schema": strict_json_schema(schema)}},
        )
        return schema.model_validate_json(response.choices[0].message.content)
