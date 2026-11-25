#!/usr/bin/env python3
"""Tkinter GUI for the browser agent. Reuses settings from agent.py."""

import asyncio
import logging
import os
import queue
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import ttk, scrolledtext

try:
    from browser_use import BrowserProfile  # noqa: F401
except ImportError:
    _venv_root = Path(__file__).resolve().parent / ".venv-01314"
    _venv_python = _venv_root / "bin" / "python"
    if _venv_python.is_file() and Path(sys.prefix).resolve() != _venv_root.resolve():
        os.execv(str(_venv_python), [str(_venv_python), str(Path(__file__).resolve()), *sys.argv[1:]])
    raise

import agent as cfg  # loads .env, RULES, build_profile, defaults
from browser_use import Agent
from browser_use.llm import ChatGroq

MODELS = [
    "qwen/qwen3.8-27b",
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
]


class QueueHandler(logging.Handler):
    def __init__(self, q):
        super().__init__()
        self.q = q

    def emit(self, record):
        self.q.put(self.format(record))


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Browser Agent")
        self.geometry("820x620")
        self.q = queue.Queue()
        self.agent = None
        self.loop = None
        self.running = False

        h = QueueHandler(self.q)
        h.setFormatter(logging.Formatter("%(message)s"))
        lg = logging.getLogger("browser_use")
        lg.addHandler(h)
        lg.setLevel(logging.INFO)

        self._build_ui()
        self.after(100, self._poll)

    def _build_ui(self):
        pad = {"padx": 8, "pady": 4}

        ttk.Label(self, text="Task").pack(anchor="w", **pad)
        self.task_box = tk.Text(self, height=4, wrap="word")
        self.task_box.pack(fill="x", **pad)
        self.task_box.bind("<Control-Return>", lambda e: (self.start(), "break")[1])

        opts = ttk.Frame(self)
        opts.pack(fill="x", **pad)

        ttk.Label(opts, text="Model").grid(row=0, column=0, sticky="w")
        self.model = ttk.Combobox(opts, values=MODELS, width=28)
        self.model.set(cfg.DEFAULT_MODEL)
        self.model.grid(row=0, column=1, padx=6)

        ttk.Label(opts, text="Max steps").grid(row=0, column=2, padx=(12, 0))
        self.steps = tk.IntVar(value=20)
        ttk.Spinbox(opts, from_=1, to=100, textvariable=self.steps, width=5).grid(row=0, column=3, padx=6)

        self.headless = tk.BooleanVar(value=False)
        self.deliberate = tk.BooleanVar(value=False)
        ttk.Checkbutton(opts, text="Headless", variable=self.headless).grid(row=0, column=4, padx=8)
        ttk.Checkbutton(opts, text="Deliberate", variable=self.deliberate).grid(row=0, column=5)

        btns = ttk.Frame(self)
        btns.pack(fill="x", **pad)
        self.run_btn = ttk.Button(btns, text="Run (Ctrl+Enter)", command=self.start)
        self.run_btn.pack(side="left")
        self.stop_btn = ttk.Button(btns, text="Stop", command=self.stop, state="disabled")
        self.stop_btn.pack(side="left", padx=6)
        ttk.Button(btns, text="Clear log", command=self._clear).pack(side="left")
        self.status = ttk.Label(btns, text="Idle")
        self.status.pack(side="right")

        ttk.Label(self, text="Log").pack(anchor="w", **pad)
        self.log = scrolledtext.ScrolledText(self, height=16, state="disabled", wrap="word")
        self.log.pack(fill="both", expand=True, **pad)

        ttk.Label(self, text="Final result").pack(anchor="w", **pad)
        self.result = scrolledtext.ScrolledText(self, height=8, state="disabled", wrap="word")
        self.result.pack(fill="both", expand=True, **pad)

    # ---------- UI helpers ----------
    def _append(self, widget, text):
        widget.configure(state="normal")
        widget.insert("end", text + "\n")
        widget.see("end")
        widget.configure(state="disabled")

    def _clear(self):
        for w in (self.log, self.result):
            w.configure(state="normal")
            w.delete("1.0", "end")
            w.configure(state="disabled")

    def _set_running(self, running):
        self.running = running
        self.run_btn.configure(state="disabled" if running else "normal")
        self.stop_btn.configure(state="normal" if running else "disabled")
        self.status.configure(text="Running..." if running else "Idle")

    def _poll(self):
        try:
            while True:
                kind, text = self.q.get_nowait() if isinstance(self.q.queue[0], tuple) else ("log", self.q.get_nowait())
                if kind == "result":
                    self._append(self.result, text)
                elif kind == "done":
                    self._set_running(False)
                else:
                    self._append(self.log, text)
        except (queue.Empty, IndexError):
            pass
        self.after(100, self._poll)

    # ---------- actions ----------
    def start(self):
        if self.running:
            return
        task = self.task_box.get("1.0", "end").strip()
        if not task:
            self.status.configure(text="Enter a task first")
            return
        if not cfg.os.getenv("GROQ_API_KEY"):
            self._append(self.log, "Error: GROQ_API_KEY missing from .env")
            return
        self._clear()
        self._set_running(True)
        opts = dict(
            task=task,
            model=self.model.get().strip(),
            steps=int(self.steps.get()),
            headless=self.headless.get(),
            deliberate=self.deliberate.get(),
        )
        threading.Thread(target=lambda: asyncio.run(self._run(**opts)), daemon=True).start()

    def stop(self):
        if self.agent and self.loop:
            self.loop.call_soon_threadsafe(self.agent.stop)
            self.status.configure(text="Stopping...")

    async def _run(self, task, model, steps, headless, deliberate):
        self.loop = asyncio.get_running_loop()
        try:
            fb = cfg.DEFAULT_FALLBACK
            fallback = ChatGroq(model=fb) if fb and fb != model else None
            self.agent = Agent(
                task=task,
                llm=ChatGroq(model=model),
                fallback_llm=fallback,
                browser_profile=cfg.build_profile(headless),
                extend_system_message=cfg.RULES,
                use_vision=False,
                include_attributes=["name", "type", "role", "aria-label", "placeholder"],
                max_clickable_elements_length=4000,
                max_history_items=6,
                flash_mode=not deliberate,
                max_actions_per_step=3,
                max_failures=3,
                step_timeout=120,
                use_judge=False,
            )
            history = await self.agent.run(max_steps=steps)
            result = history.final_result() or "No result produced."
            self.q.put(("result", result))
            self.q.put(("log", f"Steps: {history.number_of_steps()}  "
                               f"Duration: {history.total_duration_seconds():.1f}s"))
        except Exception as exc:
            self.q.put(("log", f"ERROR: {type(exc).__name__}: {exc}"))
        finally:
            try:
                await self.agent.close()
            except Exception:
                pass
            self.agent = None
            self.q.put(("done", ""))


if __name__ == "__main__":
    App().mainloop()
