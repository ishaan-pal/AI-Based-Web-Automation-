
import os
import asyncio
from pathlib import Path

from dotenv import load_dotenv
from browser_use import Agent, BrowserProfile
from browser_use.llm import ChatGroq

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

if not os.getenv("GROQ_API_KEY"):
    raise RuntimeError("GROQ_API_KEY missing from .env")

FORM_URL = (
    "https://docs.google.com/forms/d/e/"
    "1FAIpQLSfO5kmlSalS2hu8zRdzZZPFqNR8GhUjdd-Z976oiKZ65vBIFw/"
    "viewform"
)

TASK = """
Open the Google Form:

""" + FORM_URL + """

Fill it using the following TEST DATA:

Full Name: Test User
Event Email Address: test.user@example.com
Semester: Semester 1
Branch: Computer Engineering
Roll Number: TEST-0001
Which events would you like to participate in?: Quiz Competition
Dietary Preferences: None

Instructions:

1. Inspect the form and identify each question by its visible label.
2. Fill all five text/selection fields using the supplied values.
3. For the event question, select Quiz Competition only.
4. For dietary preferences, select None.
5. Verify the answers after filling them.
6. Report any field that could not be filled or verified.

IMPORTANT:
- Actually interact with the browser.
- Do not invent additional answers.
- Do not click Submit.
- Do not click Clear form.
- Do not sign into Google.
- Stop after filling and verifying the answers.
"""

async def main():

    chrome = os.getenv("BROWSER_EXECUTABLE_PATH")

    profile_options = {
        "headless": False,
        "user_data_dir": str(BASE_DIR / "google-form-profile"),
        "enable_default_extensions": False,
        "keep_alive": True,
    }

    if chrome:
        profile_options["executable_path"] = chrome

    profile = BrowserProfile(**profile_options)

    agent = Agent(
        task=TASK,
        llm=ChatGroq(model="openai/gpt-oss-120b"),
        browser_profile=profile,

        # Reduce the size of Groq requests
        use_vision=False,
        include_attributes=[
            "name",
            "type",
            "role",
            "aria-label",
            "placeholder",
            "value",
        ],
        max_clickable_elements_length=5000,
        max_history_items=6,

        # Simple form task: avoid unnecessary planning
        flash_mode=True,
        enable_planning=False,
        use_judge=False,

        max_actions_per_step=5,
        max_failures=1,
        step_timeout=90,
    )

    try:
        print("Starting Google Form automation...")
        history = await agent.run(max_steps=12)

        print("\n========== AGENT RESULT ==========")
        print(history.final_result())

        print("\nInspect the browser before closing it.")

        input("Press ENTER when you have inspected the form...")

    except Exception as exc:
        print(f"\nAGENT ERROR: {type(exc).__name__}: {exc}")

    finally:
        await agent.close()

if __name__ == "__main__":
    asyncio.run(main())
