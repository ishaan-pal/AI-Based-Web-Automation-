
import os
from pathlib import Path

from dotenv import load_dotenv
from browser_use import Agent, Browser

BASE_DIR = Path(__file__).resolve().parent

load_dotenv(BASE_DIR / ".env")

if not os.getenv("GROQ_API_KEY"):
    raise RuntimeError("Groq API key is missing.")

# Launch local Chromium
browser = Browser(
    "chromium",
    headless=False,
    user_data_dir=str(BASE_DIR / "browser-profile"),
)

task = """
Open this website:
https://www.selenium.dev/selenium/web/web-form.html

I want to test your ability to interact with a browser.

Perform ONLY these actions:

1. Wait until the page has loaded.
2. Find the text input whose ID is 'my-text'.
3. Enter exactly: Browser Use Test User
4. Read that input's value again.
5. Verify that the value is exactly correct.

IMPORTANT INSTRUCTIONS:

- Use the available DOM/JavaScript inspection helpers.
- Do not repeatedly request the entire accessibility tree.
- Do not print the entire page DOM or accessibility tree.
- Inspect only the target input.
- Actually interact with the browser; do not merely describe what you would do.
- Do not click Submit.
- Do not navigate away.

Report whether the input was successfully filled and verified.
"""

agent = Agent(
    task=task,
    llm="groq:openai/gpt-oss-120b",
    browser=browser,
    workspace=str(BASE_DIR / "workspace"),
    judge=False,
)

print("Launching GPT-OSS 120B browser agent...")

result = agent.run_sync(
    max_steps=12,
    timeout=180,
)

print("\n========== FINAL RESULT ==========")
print(result.final_result())

print("\n========== RUN COMPLETED ==========")
