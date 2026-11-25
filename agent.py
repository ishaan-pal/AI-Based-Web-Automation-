#!/usr/bin/env python3
"""General-purpose autonomous browser agent (browser-use + Groq)."""

import os
import sys
import asyncio
import argparse
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")
os.environ.setdefault("ANONYMIZED_TELEMETRY", "false")  # must be set before import

from browser_use import Agent, BrowserProfile
from browser_use.llm import ChatGroq

DEFAULT_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
DEFAULT_FALLBACK = os.getenv("GROQ_FALLBACK_MODEL", "openai/gpt-oss-20b")

RULES = """
OPERATING RULES:
- Inspect actual page contents before acting.
- Verify important actions before reporting success.
- Never invent information or claim success without checking the result.
- Never make purchases, payments or irreversible submissions.
- If essential information is missing, stop and say what is missing in your final answer.
"""


def parse_args():
    p = argparse.ArgumentParser(description="Autonomous AI browser agent")
    p.add_argument("task", nargs="+", help="Browser task in natural language")
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument("--fallback-model", default=DEFAULT_FALLBACK,
                   help="Used when the main model fails (e.g. rate limit). 'none' disables.")
    p.add_argument("--max-steps", type=int, default=20)
    p.add_argument("--headless", action="store_true")
    p.add_argument("--deliberate", action="store_true",
                   help="Normal reasoning instead of flash mode")
    return p.parse_args()


def build_profile(headless: bool) -> BrowserProfile:
    opts = {
        "headless": headless,
        "user_data_dir": str(BASE_DIR / "agent-profile"),
        "enable_default_extensions": False,
        "chromium_sandbox": False,
        "args": ["--disable-dev-shm-usage", "--disable-gpu", "--no-first-run"],
    }
    chrome = os.getenv("BROWSER_EXECUTABLE_PATH")
    if chrome:
        if not Path(chrome).is_file():
            raise FileNotFoundError(f"Chromium executable not found: {chrome}")
        opts["executable_path"] = chrome
    return BrowserProfile(**opts)


async def run(args) -> int:
    if not os.getenv("GROQ_API_KEY"):
        print("Error: GROQ_API_KEY missing from .env", file=sys.stderr)
        return 2

    task = " ".join(args.task)

    use_fallback = args.fallback_model.lower() != "none" and args.fallback_model != args.model
    fallback = ChatGroq(model=args.fallback_model) if use_fallback else None

    agent = Agent(
        task=task,
        llm=ChatGroq(model=args.model),
        fallback_llm=fallback,
        browser_profile=build_profile(args.headless),
        extend_system_message=RULES,  # rules go in system prompt, not the task text

        # Keep context small for Groq free-tier limits.
        use_vision=False,
        include_attributes=["name", "type", "role", "aria-label", "placeholder"],
        max_clickable_elements_length=4000,
        max_history_items=6,

        flash_mode=not args.deliberate,
        max_actions_per_step=3,
        max_failures=3,
        step_timeout=120,
        use_judge=False,
    )

    print("=" * 40)
    print(" AUTONOMOUS BROWSER AGENT")
    print("=" * 40)
    print(f"Model:    {args.model}")
    print(f"Fallback: {args.fallback_model if use_fallback else 'none'}")
    print(f"Task:     {task}")
    print("=" * 40 + "\n")

    code = 0
    try:
        history = await agent.run(max_steps=args.max_steps)

        print("\n========== FINAL RESULT ==========\n")
        result = history.final_result()
        if result:
            print(result)
        else:
            print("No result produced.")
            errors = [e for e in history.errors() if e]
            if errors:
                print("Last error:", str(errors[-1])[:500])
            code = 1

        print("\n========== SUMMARY ==========")
        print("Steps:    ", history.number_of_steps())
        print(f"Duration:  {history.total_duration_seconds():.1f}s")
        print("Success:  ", history.is_successful())
    except KeyboardInterrupt:
        print("\nInterrupted by user.")
        code = 130
    except Exception as exc:
        print(f"\nAGENT ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        code = 1
    finally:
        try:
            await agent.close()
        except Exception:
            pass
    return code


def main():
    try:
        sys.exit(asyncio.run(run(parse_args())))
    except KeyboardInterrupt:
        sys.exit(130)
    except Exception as exc:
        print(f"Startup error: {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()