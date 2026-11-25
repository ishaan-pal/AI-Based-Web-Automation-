# Browser Use Agent

Scripts that drive a real Chromium browser with [browser-use](https://github.com/browser-use/browser-use) and Groq models. All scripts load their configuration from `.env` and, where available, from CLI flags (CLI > environment > default).

## Requirements

- Python 3.12 on Linux, WSL2, or macOS
- A Groq API key
- Internet access (for the Groq API and the target websites)
- A graphical display only if you want to see the browser window. On WSL2 this is WSLg; headless mode works without a display.
- Chromium is downloaded automatically by browser-use on the first launch into `~/.cache/ms-playwright`. Do not use a snap-installed Chromium for CDP automation.

## Setup

1. Clone the repository and change into it:

   ```bash
   git clone https://github.com/ishaan-pal/AI-Based-Web-Automation-.git
   cd AI-Based-Web-Automation-
   ```

2. Create the virtual environment. The directory name `.venv-01314` matters: `gui.py` automatically re-launches itself with that interpreter if it is started from an incompatible environment.

   ```bash
   python3.12 -m venv .venv-01314
   source .venv-01314/bin/activate
   python -m pip install --upgrade pip
   python -m pip install browser-use==0.13.14
   ```

   With `uv` instead:

   ```bash
   uv venv .venv-01314 --python 3.12
   uv pip install browser-use==0.13.14
   ```

3. Create a `.env` file in the project root with your Groq key:

   ```dotenv
   GROQ_API_KEY=gsk_your_key_here
   ```

   `.env` is gitignored; never commit it.

4. Verify the environment:

   ```bash
   python -c "import importlib.metadata as m; print(m.version('browser-use'))"
   ```

   Expected output: `0.13.14`.

## Running

Activate the environment first in every new shell:

```bash
source .venv-01314/bin/activate
```

You can also call `.venv-01314/bin/python` directly without activating.

### GUI (`gui.py`)

```bash
python gui.py
```

Type a task and click **Run** or press **Ctrl+Enter**. The GUI has a model selector, step limit, **Headless** and **Deliberate** checkboxes, **Stop**, and **Clear log**. It requires a working display; if there is none, use the CLI agent with `--headless`.

Starting it with a browser-use 1.x environment (for example `.venv/bin/python gui.py`) is safe: it detects the incompatible `BrowserProfile` import and re-executes itself with `.venv-01314/bin/python`.

### General-purpose CLI agent (`agent.py`)

```bash
python agent.py "Open https://example.com and report the page title"
python agent.py --headless --max-steps 10 "Fill the form on https://example.com/form"
python agent.py --model openai/gpt-oss-20b --fallback-model none "Summarize this page"
```

| Flag | Default | Meaning |
| --- | --- | --- |
| `--model` | `GROQ_MODEL` or `openai/gpt-oss-120b` | Groq model used by the agent |
| `--fallback-model` | `GROQ_FALLBACK_MODEL` or `openai/gpt-oss-20b` | Fallback on failure; `none` disables it |
| `--max-steps` | `20` | Maximum agent steps |
| `--headless` | off | Run Chromium without a window |
| `--deliberate` | off | Normal reasoning instead of flash mode |

The agent refuses purchases, payments, and irreversible submissions, and reports missing information instead of guessing.

### Selenium form test (`form_test_013.py`)

```bash
python form_test_013.py
```

Opens the Selenium test form, fills the `my-text` input, reads the live `.value` back with JavaScript, and independently compares the page state after the agent finishes. It prints `RESULT: PASS` or `RESULT: FAIL`; exit codes are `0` success, `1` failed/unverified, `2` configuration error.

Useful flags:

```bash
python form_test_013.py --url https://example.com/form --field my-text --text "Some text"
python form_test_013.py --headless false --max-steps 10 --history-items 6
python form_test_013.py --flash-mode true --exclude-actions "search,screenshot,extract"
```

`--history-items` must be greater than 5 or omitted; the default is `6`.

### Google Form test (`google_form_test.py`)

```bash
python google_form_test.py
```

Fills a hard-coded Google Form with the dummy values defined at the top of the file. It does not submit the form. After the run it waits at `Press ENTER when you have inspected the form...` so you can inspect the browser before it closes. Edit `FORM_URL` and `TASK` in the file to target a different form.

### Legacy script (`form_test.py`)

`form_test.py` uses the **browser-use 1.0** API (`Browser("chromium", ...)`, `browser=`, `workspace=`). It is not compatible with the 0.13.x environment above. To run it, create a separate environment:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install browser-use==1.0.8 python-dotenv
python form_test.py
```

Do not use this environment for `agent.py`, `gui.py`, `form_test_013.py`, or `google_form_test.py`.

## Configuration reference

All variables can be placed in `.env`. CLI flags override them where supported.

| Variable | Default | Used by | Meaning |
| --- | --- | --- | --- |
| `GROQ_API_KEY` | required | all | Groq API key |
| `GROQ_MODEL` | `openai/gpt-oss-120b` | all | Main model |
| `GROQ_FALLBACK_MODEL` | `openai/gpt-oss-20b` | `agent.py`, `gui.py` | Fallback model; `none` disables |
| `BROWSER_HEADLESS` | `auto` | `form_test_013.py` | `auto`, `true`, or `false`; `auto` detects a usable X/Wayland display |
| `BROWSER_EXECUTABLE_PATH` | unset | `agent.py`, `form_test_013.py`, `google_form_test.py` | Path to a non-snap Chromium/Chrome binary |
| `BROWSER_START_TIMEOUT` | `90` | `form_test_013.py` | Browser launch event timeout in seconds |
| `BROWSER_PROFILE_DIR` | `browser-profile-01314` | `form_test_013.py` | Persistent Chromium profile directory |
| `FORM_URL` | Selenium web-form page | `form_test_013.py` | Target URL |
| `FORM_FIELD` | `my-text` | `form_test_013.py` | Input `name` attribute |
| `FORM_TEXT` | `Browser Use Test User` | `form_test_013.py` | Exact text to type and verify |
| `AGENT_MAX_STEPS` | `10` | `form_test_013.py` | Maximum steps |
| `AGENT_EXCLUDE_ACTIONS` | built-in list | `form_test_013.py` | Comma-separated action names hidden from the model |
| `AGENT_FLASH_MODE` | `true` | `form_test_013.py` | `true` or `false` |
| `AGENT_HISTORY_ITEMS` | `6` | `form_test_013.py` | History items kept in prompts; must be `>5` |

Browser profiles, virtual environments, `__pycache__`, logs, and `.env` are excluded by `.gitignore`.

## Troubleshooting

- **`browser_use.BrowserProfile was removed in browser-use 1.0`** — you are using the wrong venv. Activate `.venv-01314` or reinstall `browser-use==0.13.14`. `gui.py` handles this automatically.
- **`max_history_items must be None or greater than 5`** — use `6` or higher (the defaults already are). Values such as `1` are rejected by browser-use 0.13.x.
- **No Chromium window appears** — check that WSLg/X11 is running and `DISPLAY` is reachable. `form_test_013.py` auto-detects the X socket; otherwise pass `--headless false` explicitly.
- **Chromium dies, tabs detach, or `ConnectionRefusedError` on 127.0.0.1** — the launch flags already disable the sandbox, GPU init, and small `/dev/shm` usage. Avoid snap Chromium; set `BROWSER_EXECUTABLE_PATH` to a normal Chromium/Chrome binary and retry.
- **`413` or `429` from Groq** — reduce `--history-items`, extend `--exclude-actions`, or lower `--max-steps`. These are request-size/rate limits, not browser failures.

## Repository layout

- `agent.py` — general-purpose CLI agent
- `gui.py` — Tkinter front end for `agent.py`
- `form_test_013.py` — single-field form test with independent page verification
- `google_form_test.py` — hard-coded Google Form fill test
- `form_test.py` — legacy browser-use 1.0 example
- `.gitignore` — excludes secrets, environments, browser profiles, and caches
