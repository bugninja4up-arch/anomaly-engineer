"""LLM provider adapter and evidence-aware conversational agent."""

from __future__ import annotations

import json
import os
from typing import Any, Callable
from urllib.parse import urlsplit

from tools import TOOL_SCHEMAS, execute_tool


class AIProvider:
    """OpenAI-compatible adapter for OpenAI, DeepSeek, and Ollama."""

    SUPPORTED_PROVIDERS = {"openai", "deepseek", "ollama"}

    def __init__(self, name: str, settings: dict[str, Any]) -> None:
        self.name = name.lower()
        if self.name not in self.SUPPORTED_PROVIDERS:
            raise ValueError(
                f"Unsupported provider {name!r}; choose OpenAI, DeepSeek, or Ollama."
            )
        self.base_url = str(settings.get("base_url", "")).strip() or None
        self.api_key = self._resolve_api_key(settings.get("api_key", ""))
        self.model = str(settings.get("model", "")).strip()
        if not self.model:
            raise ValueError(f"A model must be configured for provider {self.name!r}.")
        self._client: Any | None = None

    @staticmethod
    def _resolve_api_key(value: Any) -> str:
        key = str(value or "").strip()
        if key.startswith("${") and key.endswith("}"):
            env_name = key[2:-1]
            return os.environ.get(env_name, "")
        return key

    def _get_client(self) -> Any:
        if self._client is None:
            try:
                from openai import OpenAI
            except ImportError as exc:
                raise RuntimeError(
                    "The OpenAI Python package is required. Install it with: "
                    "python -m pip install openai"
                ) from exc
            options: dict[str, Any] = {"api_key": self.api_key or "ollama"}
            if self.base_url:
                options["base_url"] = self.base_url
            self._client = OpenAI(**options)
        return self._client

    def complete(self, messages: list[dict[str, Any]]) -> Any:
        """Ask the configured compatible chat-completions endpoint."""
        return self._get_client().chat.completions.create(
            model=self.model,
            messages=messages,
            tools=TOOL_SCHEMAS,
            tool_choice="auto",
        )


ApprovalCallback = Callable[[str, dict[str, Any]], bool]


class Agent:
    """Conversational agent limited to declared tools and configured scope."""

    SYSTEM_PROMPT = """You are Anomaly-Engineer, an evidence-driven security research assistant.
Use only the registered Python tools; never request or execute shell commands.
The currently registered request tool is a mock and cannot send network traffic.
Only discuss or plan testing for explicitly configured in-scope targets. Do not
claim that a test, scan, request, or vulnerability was performed or confirmed
unless the available tool actually did so. Clearly distinguish hypotheses from
evidence, state uncertainty, and ask for human approval before testing or any
other high-impact action. Loading a skill file is read-only and needs no approval.
Give concise explanations and summaries, not hidden chain-of-thought. Do not
invent evidence, findings, or authorization.
"""

    def __init__(
        self,
        provider: AIProvider,
        db_manager: Any,
        scope: dict[str, Any] | None = None,
        approval_callback: ApprovalCallback | None = None,
        max_tool_rounds: int = 5,
    ) -> None:
        self.provider = provider
        self.db_manager = db_manager
        self.scope = scope or {}
        self.approval_callback = approval_callback
        self.max_tool_rounds = max(1, int(max_tool_rounds))
        self.history: list[dict[str, Any]] = []

    @staticmethod
    def _normalize_url(url: str) -> str:
        parts = urlsplit(url.strip())
        if parts.scheme not in {"http", "https"} or not parts.hostname:
            return ""
        return url.strip().rstrip("/")

    def _is_in_scope(self, url: str) -> bool:
        normalized = self._normalize_url(url)
        if not normalized:
            return False

        allowed_urls = self.scope.get("allowed_urls", []) or []
        for allowed_url in allowed_urls:
            if normalized == self._normalize_url(str(allowed_url)):
                return True

        hostname = (urlsplit(normalized).hostname or "").lower().rstrip(".")
        allowed_domains = self.scope.get("allowed_domains", []) or []
        for domain_entry in allowed_domains:
            candidate = str(domain_entry).strip().lower()
            if "://" in candidate:
                candidate = (urlsplit(candidate).hostname or "").lower()
            candidate = candidate.lstrip("*.").rstrip(".")
            if candidate and (hostname == candidate or hostname.endswith("." + candidate)):
                return True
        return False

    def _dispatch_tool(self, name: str, raw_arguments: str) -> str:
        try:
            arguments = json.loads(raw_arguments)
        except json.JSONDecodeError as exc:
            return json.dumps({"error": f"Invalid tool argument JSON: {exc}"})
        if not isinstance(arguments, dict):
            return json.dumps({"error": "Tool arguments must be a JSON object."})

        if name == "load_skill":
            return execute_tool(name, arguments)

        if name != "mutate_and_fuzz_request":
            return json.dumps({"error": f"Unknown tool: {name}"})
        url = arguments.get("url")
        if not isinstance(url, str) or not self._is_in_scope(url):
            return json.dumps(
                {
                    "status": "blocked",
                    "executed": False,
                    "message": "Target is not in the explicitly configured scope.",
                }
            )
        if self.approval_callback is None or not self.approval_callback(name, arguments):
            return json.dumps(
                {"status": "not_approved", "executed": False, "message": "Tool call was not approved."}
            )
        return execute_tool(name, arguments)

    def respond(self, user_prompt: str) -> str:
        """Answer one user turn, handling only the declared function tools."""
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self.SYSTEM_PROMPT}
        ]
        saved_context = self.db_manager.recent_context()
        if saved_context:
            messages.append(
                {
                    "role": "system",
                    "content": "Use this saved context as historical notes, not as proof of current authorization:\n"
                    + saved_context,
                }
            )
        messages.extend(self.history)
        messages.append({"role": "user", "content": user_prompt})

        final_text = ""
        for _ in range(self.max_tool_rounds):
            completion = self.provider.complete(messages)
            assistant_message = completion.choices[0].message
            tool_calls = assistant_message.tool_calls or []
            if not tool_calls:
                final_text = assistant_message.content or "(لم يُرجع النموذج نصًا.)"
                break

            messages.append(assistant_message.model_dump(exclude_none=True))
            for call in tool_calls:
                result = self._dispatch_tool(
                    call.function.name, call.function.arguments
                )
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": result,
                    }
                )
        else:
            final_text = "توقفت بعد بلوغ الحد الأقصى لجولات استدعاء الأدوات."

        self.history.extend(
            [
                {"role": "user", "content": user_prompt},
                {"role": "assistant", "content": final_text},
            ]
        )
        self.db_manager.add_interaction(request=user_prompt, response=final_text)
        return final_text
