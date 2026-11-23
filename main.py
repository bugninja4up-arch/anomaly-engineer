"""CLI entry point for Anomaly-Engineer."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError as exc:
    raise SystemExit(
        "PyYAML is required. Install dependencies with: "
        "python -m pip install openai PyYAML"
    ) from exc

from agent import AIProvider, Agent
from db_manager import DBManager


PROJECT_DIR = Path(__file__).resolve().parent


def load_config(path: Path = PROJECT_DIR / "config.yaml") -> dict[str, Any]:
    """Load the YAML configuration file."""
    with path.open("r", encoding="utf-8") as config_file:
        data = yaml.safe_load(config_file) or {}
    if not isinstance(data, dict):
        raise ValueError("The top-level YAML configuration must be a mapping.")
    return data


def approve_tool_call(name: str, arguments: dict[str, Any]) -> bool:
    """Require explicit confirmation before every tool invocation."""
    print("\nطلب الوكيل استدعاء أداة:")
    print(f"  الأداة: {name}")
    for key, value in arguments.items():
        print(f"  {key}: {value}")
    print("  ملاحظة: الأداة الحالية تجريبية ولا ترسل طلبات شبكة.")
    try:
        answer = input("الموافقة على هذا الاستدعاء؟ [y/N]: ").strip().lower()
    except EOFError:
        return False
    return answer in {"y", "yes"}


def main() -> int:
    try:
        config = load_config()
        provider_name = str(config.get("provider", "openai")).lower()
        provider_settings = config.get("providers", {}).get(provider_name, {})
        if not isinstance(provider_settings, dict):
            raise ValueError(f"Invalid settings for provider {provider_name!r}.")

        database_value = Path(str(config.get("database", "evidence.db")))
        database_path = database_value if database_value.is_absolute() else PROJECT_DIR / database_value
        db_manager = DBManager(database_path)
        db_manager.initialize()

        provider = AIProvider(provider_name, provider_settings)
        agent = Agent(
            provider=provider,
            db_manager=db_manager,
            scope=config.get("scope", {}),
            approval_callback=approve_tool_call,
        )
    except (OSError, ValueError, TypeError) as exc:
        print(f"تعذر تهيئة Anomaly-Engineer: {exc}", file=sys.stderr)
        return 1

    print("Anomaly-Engineer — اكتب exit أو quit للخروج.")
    while True:
        try:
            prompt = input("\nأنت> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nإلى اللقاء.")
            break
        if not prompt:
            continue
        if prompt.lower() in {"exit", "quit"}:
            print("إلى اللقاء.")
            break
        try:
            print(f"\nAnomaly-Engineer> {agent.respond(prompt)}")
        except Exception as exc:  # Keep the REPL alive after provider/tool errors.
            print(f"تعذر إكمال الطلب: {exc}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
