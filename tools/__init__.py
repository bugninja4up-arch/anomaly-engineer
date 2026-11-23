"""Tool schemas and safe dispatch for the agent."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "mutate_and_fuzz_request",
            "description": (
                "Mock-only placeholder for the future request mutation tool. "
                "This implementation does not send requests or perform fuzzing."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "Target URL."},
                    "method": {"type": "string", "description": "HTTP method."},
                    "payload_json": {
                        "type": "string",
                        "description": "Request payload represented as JSON text.",
                    },
                },
                "required": ["url", "method", "payload_json"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "load_skill",
            "description": "Read a Markdown skill from the project's skills directory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "skill_name": {
                        "type": "string",
                        "description": "Skill filename with or without the .md suffix.",
                    }
                },
                "required": ["skill_name"],
                "additionalProperties": False,
            },
        },
    },
]


def mutate_and_fuzz_request(
    url: str, method: str, payload_json: str
) -> dict[str, Any]:
    """Return a mock result; no network request or mutation is performed."""
    return {
        "status": "not_implemented",
        "executed": False,
        "message": "Mock only: no request was sent and no fuzzing was performed.",
        "input": {"url": url, "method": method, "payload_json": payload_json},
    }


def load_skill(skill_name: str) -> dict[str, Any]:
    """Read one Markdown skill, rejecting paths and names outside the skills folder."""
    name = skill_name.strip()
    stem = name[:-3] if name.endswith(".md") else name
    if not re.fullmatch(r"[A-Za-z0-9_-]+", stem):
        return {"error": "Skill name must be a simple Markdown filename."}

    skills_dir = (Path(__file__).resolve().parent.parent / "skills").resolve()
    skill_path = (skills_dir / f"{stem}.md").resolve()
    if skill_path.parent != skills_dir or not skill_path.is_file():
        return {"error": f"Skill not found: {stem}.md"}
    return {"skill_name": f"{stem}.md", "content": skill_path.read_text(encoding="utf-8")}


def execute_tool(name: str, arguments: str | dict[str, Any]) -> str:
    """Dispatch only explicitly defined Python tools and serialize the result."""
    if isinstance(arguments, str):
        try:
            parsed = json.loads(arguments)
        except json.JSONDecodeError as exc:
            return json.dumps({"error": f"Invalid tool argument JSON: {exc}"})
    else:
        parsed = arguments

    if not isinstance(parsed, dict):
        return json.dumps({"error": "Tool arguments must be a JSON object."})

    if name == "load_skill":
        if set(parsed) != {"skill_name"} or not isinstance(parsed.get("skill_name"), str):
            return json.dumps({"error": "Expected exactly one string field: skill_name."})
        result = load_skill(parsed["skill_name"])
        return json.dumps(result, ensure_ascii=False)

    if name == "mutate_and_fuzz_request":
        required = {"url", "method", "payload_json"}
        if set(parsed) != required or not all(
            isinstance(parsed.get(field), str) for field in required
        ):
            return json.dumps(
                {"error": "Expected exactly three string fields: url, method, payload_json."}
            )
        result = mutate_and_fuzz_request(
            url=parsed["url"],
            method=parsed["method"],
            payload_json=parsed["payload_json"],
        )
        return json.dumps(result, ensure_ascii=False)

    return json.dumps({"error": f"Unknown tool: {name}"})
