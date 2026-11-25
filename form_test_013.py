#!/usr/bin/env python3
"""Browser Use form-fill test with independent verification.

Configuration precedence: CLI flag > environment variable (.env) > default.
Exit codes: 0 verified success, 1 task failed or unverified, 2 configuration error.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, Field

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def _ensure_display() -> None:
    """WSLg/X11 often exists even when the invoking shell has no DISPLAY exported."""
    if os.getenv("DISPLAY"):
        return
    sockets = sorted(Path("/tmp/.X11-unix").glob("X[0-9]*"))
    if sockets:
        os.environ["DISPLAY"] = ":" + sockets[0].name[1:].split(".")[0]


def _display_available() -> bool:
    display = os.getenv("DISPLAY")
    if display:
        if not display.startswith(":"):
            return True
        number = display[1:].split(".")[0]
        if Path(f"/tmp/.X11-unix/X{number}").exists():
            return True
    wayland = os.getenv("WAYLAND_DISPLAY")
    if wayland:
        runtime = Path(os.getenv("XDG_RUNTIME_DIR", "/run/user/1000"))
        if (runtime / wayland).exists():
            return True
    return False


_ensure_display()

# Browser Use reads event timeouts from the environment. Set before importing it.
_START_TIMEOUT = os.getenv("BROWSER_START_TIMEOUT", "90")
os.environ.setdefault("TIMEOUT_BrowserStartEvent", _START_TIMEOUT)
os.environ.setdefault("TIMEOUT_BrowserLaunchEvent", _START_TIMEOUT)

from browser_use import Agent, BrowserProfile, Tools  # noqa: E402
from browser_use.llm import ChatGroq  # noqa: E402

TASK_TEMPLATE = """\
Open: {url}

Complete this small browser automation task.

1. Inspect the page and identify the text input named '{field}'.
2. Fill it with exactly the text between the markers (markers excluded):
   >>>{text}<<<
3. Read the field's current value back using the evaluate action, with JavaScript that returns the element's live .value property (document.getElementsByName('{field}')[0].value). Do not use find_elements, which reads the HTML attribute and does not reflect typed text.
4. Compare the read-back value with the requested text, character for character.
5. Finish with the done action, returning a structured report:
   - success: true only if the read-back value equals the requested text exactly
   - observed_value: the exact value read back from the field (null if unreadable)
   - notes: one short sentence on anything unexpected

You must actually interact with the browser. Do not merely describe the actions.
Do not submit the form. Do not navigate away. Do not modify other fields.
"""


class FormFillReport(BaseModel):
    success: bool
    observed_value: str | None = None
    notes: str = Field(default="")


# Runs inside the page after the agent finishes. Reads the live .value property,
# not the HTML attribute, and flags other text fields that differ from their defaults.
PROBE_JS = """(name) => {
  const el = document.getElementsByName(name)[0];
  const textLike = ['text', 'password', 'textarea', 'search', 'email', 'url', 'tel', 'number'];
  const edited = [];
  document.querySelectorAll('input, textarea').forEach((n) => {
    const t = (n.type || 'text').toLowerCase();
    if (n === el || !textLike.includes(t)) return;
    if (n.value !== n.defaultValue) edited.push(n.name || n.id || t);
  });
  return JSON.stringify({found: !!el, value: el ? el.value : null, url: location.href, edited: edited});
}"""


# Every registered action adds tokens to every request. Unknown names are ignored.
DEFAULT_EXCLUDED_ACTIONS = (
    "search,search_google,go_back,wait,upload_file,switch,close,extract,screenshot,"
    "dropdown_options,select_dropdown,write_file,replace_file,read_file,find_text,find_elements"
)


@dataclass(frozen=True)
class Config:
    url: str
    field: str
    text: str
    model: str
    max_steps: int
    headless: bool
    profile_dir: Path
    executable_path: str | None
    enable_extensions: bool
    exclude_actions: tuple[str, ...]
    flash_mode: bool
    history_items: int


def _truthy(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _resolve_headless(mode: str) -> bool:
    mode = mode.strip().lower()
    if mode == "auto":
        if sys.platform.startswith("linux"):
            return not _display_available()
        return False
    return _truthy(mode)


def parse_config() -> Config:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--url", default=os.getenv("FORM_URL", "https://www.selenium.dev/selenium/web/web-form.html"))
    p.add_argument("--field", default=os.getenv("FORM_FIELD", "my-text"), help="input 'name' attribute")
    p.add_argument("--text", default=os.getenv("FORM_TEXT", "Browser Use Test User"))
    p.add_argument("--model", default=os.getenv("GROQ_MODEL", "openai/gpt-oss-120b"))
    p.add_argument("--max-steps", type=int, default=int(os.getenv("AGENT_MAX_STEPS", "10")))
    p.add_argument("--headless", default=os.getenv("BROWSER_HEADLESS", "auto"), help="auto | true | false")
    p.add_argument("--profile-dir", default=os.getenv("BROWSER_PROFILE_DIR", str(BASE_DIR / "browser-profile-01314")))
    p.add_argument("--executable", default=os.getenv("BROWSER_EXECUTABLE_PATH"), help="custom Chromium/Chrome binary")
    p.add_argument(
        "--extensions",
        action="store_true",
        default=_truthy(os.getenv("BROWSER_ENABLE_EXTENSIONS", "false")),
        help="enable default extensions (slower first launch)",
    )
    p.add_argument("--exclude-actions", default=os.getenv("AGENT_EXCLUDE_ACTIONS", DEFAULT_EXCLUDED_ACTIONS),
                   help="comma-separated action names to hide from the model")
    p.add_argument("--flash-mode", default=os.getenv("AGENT_FLASH_MODE", "true"), help="true | false")
    p.add_argument("--history-items", type=int, default=int(os.getenv("AGENT_HISTORY_ITEMS", "6")))
    a = p.parse_args()

    if not os.getenv("GROQ_API_KEY"):
        print("Configuration error: GROQ_API_KEY missing (set it in .env).", file=sys.stderr)
        sys.exit(2)
    if a.executable and not Path(a.executable).is_file():
        print(f"Configuration error: executable not found: {a.executable}", file=sys.stderr)
        sys.exit(2)
    if not a.text.strip() or not a.field.strip():
        print("Configuration error: --text and --field must be non-empty.", file=sys.stderr)
        sys.exit(2)

    return Config(
        url=a.url,
        field=a.field,
        text=a.text,
        model=a.model,
        max_steps=a.max_steps,
        headless=_resolve_headless(a.headless),
        profile_dir=Path(a.profile_dir).expanduser().resolve(),
        executable_path=a.executable,
        enable_extensions=a.extensions,
        exclude_actions=tuple(s.strip() for s in a.exclude_actions.split(",") if s.strip()),
        flash_mode=_truthy(a.flash_mode),
        history_items=a.history_items,
    )


def build_agent(cfg: Config) -> Agent:
    profile_kwargs: dict = {
        "headless": cfg.headless,
        "user_data_dir": str(cfg.profile_dir),
        "enable_default_extensions": cfg.enable_extensions,
    }
    if cfg.executable_path:
        profile_kwargs["executable_path"] = cfg.executable_path

    return Agent(
        task=TASK_TEMPLATE.format(url=cfg.url, field=cfg.field, text=cfg.text),
        llm=ChatGroq(model=cfg.model),
        browser_profile=BrowserProfile(**profile_kwargs),
        output_model_schema=FormFillReport,
        use_vision=False,
        max_actions_per_step=3,
        max_failures=3,
        step_timeout=90,
        use_judge=False,
        tools=Tools(exclude_actions=list(cfg.exclude_actions)),
        flash_mode=cfg.flash_mode,
        max_history_items=cfg.history_items,
    )


async def main() -> int:
    cfg = parse_config()
    cfg.profile_dir.mkdir(parents=True, exist_ok=True)

    print(f"Model={cfg.model} | headless={cfg.headless} | display={os.getenv('DISPLAY')} | extensions={cfg.enable_extensions}")
    print(f"Target: {cfg.url} -> input '{cfg.field}'")

    live: dict = {}

    async def capture_live_state(agent: Agent) -> None:
        """After each step; once the agent is done, read the page ourselves."""
        if not agent.history.is_done():
            return
        try:
            page = await agent.browser_session.get_current_page()
            live.update(json.loads(await page.evaluate(PROBE_JS, cfg.field)))
        except Exception as exc:
            live["error"] = f"{type(exc).__name__}: {exc}"

    agent = build_agent(cfg)
    try:
        history = await agent.run(max_steps=cfg.max_steps, on_step_end=capture_live_state)
    except Exception as exc:
        print(f"\nRun failed before completion: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    finally:
        try:
            await agent.close()
        except Exception:
            pass

    report = history.structured_output
    print("\n========== AGENT REPORT (self-reported, not trusted) ==========")
    print(report.model_dump_json(indent=2) if report else f"No structured report. Raw: {history.final_result()}")

    print("\n========== INDEPENDENT PAGE CHECK ==========")
    if "error" in live or not live:
        print(f"Live read failed or never ran: {live.get('error', 'agent did not reach done')}")
        return 1

    value_ok = live.get("found") is True and live.get("value") == cfg.text
    url_ok = live.get("url", "").split("#")[0] == cfg.url.split("#")[0]
    untouched = not live.get("edited")
    print(f"expected value : {cfg.text!r}")
    print(f"live value     : {live.get('value')!r}   -> {'OK' if value_ok else 'MISMATCH'}")
    print(f"url unchanged  : {'OK' if url_ok else 'CHANGED: ' + live.get('url', '?')}")
    print(f"other fields   : {'OK' if untouched else 'EDITED: ' + ', '.join(live['edited'])}")

    if value_ok and not (report and report.success and report.observed_value == cfg.text):
        print("NOTE: the page is correct but the agent's own report disagrees.")

    verified = value_ok and url_ok and untouched
    print(f"\nRESULT: {'PASS' if verified else 'FAIL'}")
    return 0 if verified else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
