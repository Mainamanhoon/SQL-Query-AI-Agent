"""Provider-neutral model interface and an OpenAI-compatible HTTP adapter."""

from typing import List, Protocol

import httpx
from langchain_core.messages import BaseMessage


class ModelUnavailableError(RuntimeError):
    """The configured model cannot currently serve a request."""


class LanguageModel(Protocol):
    """Small dependency-injection contract implemented by real and test models."""

    async def complete(self, messages: List[BaseMessage], json_output: bool = False) -> str:
        """Return model text for messages, optionally requiring a JSON object.

        Args:
            messages: System policy and conversation messages.
            json_output: Whether the output must be a JSON object.

        Returns:
            Model-generated text. Implementations may make network requests.
        """
        ...


class HTTPChatModel:
    """Call a configured chat-completions endpoint without coupling nodes to a vendor."""

    def __init__(self, client: httpx.AsyncClient, api_key: str, base_url: str, model: str) -> None:
        """Store injected transport and provider settings without making requests.

        Args:
            client: Lifecycle-managed HTTP client with a configured timeout.
            api_key: Server-only provider credential.
            base_url: OpenAI-compatible API base URL.
            model: Provider-specific model identifier.
        """
        self.client = client
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model

    async def complete(self, messages: List[BaseMessage], json_output: bool = False) -> str:
        """Request a bounded completion, keeping provider errors and credentials private.

        Args:
            messages: Policy and conversational messages to send to the model.
            json_output: Request JSON-object response mode when true.

        Returns:
            Assistant text from the provider.

        Raises:
            ModelUnavailableError: Configuration, transport, or response is invalid.

        Side Effects:
            Sends messages and schema to the configured external provider.
        """
        if not self.api_key or not self.model:
            raise ModelUnavailableError(
                "Set LLM_API_KEY and LLM_MODEL on the backend to enable chat."
            )
        roles = {"system": "system", "human": "user", "ai": "assistant"}
        payload = {
            "model": self.model,
            "messages": [
                {"role": roles[message.type], "content": message.content} for message in messages
            ],
            "max_tokens": 1800,
        }
        if json_output:
            payload["response_format"] = {"type": "json_object"}
        try:
            response = await self.client.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {self.api_key}"},
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            if not isinstance(content, str) or not content.strip() or len(content) > 16000:
                raise ValueError("Invalid model response.")
            return content.strip()
        except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError) as error:
            raise ModelUnavailableError(
                "The language model is unavailable. Check its configuration and try again."
            ) from error
