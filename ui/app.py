"""J.A.R.V.I.S desktop interface (CustomTkinter).

Layout: a sidebar with system status, switches and shortcuts; the conversation as chat
bubbles in the middle; an optional live activity panel on the right.

All slow work (the AI, tools, voice) runs in background threads. Background threads never
touch the window directly: they put events on self.events, and _poll_events handles them
in the window thread every 100 ms.
"""
import logging
import queue
import re
import threading
import time
import tkinter as tk
from datetime import datetime

import customtkinter as ctk

# ---------------- look ----------------
BG = "#0b1220"
SIDEBAR = "#0e1828"
PANEL = "#111c2e"
CARD = "#16233a"
BORDER = "#22324d"
USER_BUBBLE = "#1d5fd1"
JARVIS_BUBBLE = "#182740"
CYAN = "#4dd0ff"
TEXT = "#e3eef8"
DIM = "#7a8ca0"
GREEN = "#3ddc84"
RED = "#ff5c5c"
AMBER = "#ffb84d"
PURPLE = "#c792ea"
FONT = "Segoe UI"
MONO = "Consolas"

LOG_COLORS = {
    "[AGENT]": CYAN, "[TOOL]": GREEN, "[SECURITY]": AMBER, "[RAG]": PURPLE, "[MEMORY]": "#ffe66d",
    "[ROUTINE]": GREEN, "[UNDO]": AMBER, "[SUGGEST]": PURPLE, "[REMINDER]": AMBER, "[HOTKEY]": CYAN,
    "[LLM]": DIM, "[TTS]": DIM, "[STT]": DIM, "[VOICE]": DIM,
}
EXIT_WORDS = (
    "exit", "quit", "bye", "goodbye", "goodbye jarvis", "bye jarvis", "ok bye", "cool bye", "bye bye",
    "exit jarvis", "quit jarvis", "close", "close jarvis", "shut down", "shut down jarvis",
)
SYSTEMS = ("AI", "MEMORY", "DOCUMENTS", "TOOLS", "VOICE")
SYSTEM_NAMES = {"AI": "AI", "MEMORY": "Memory", "DOCUMENTS": "Documents", "TOOLS": "Tools", "VOICE": "Voice"}
MAX_BUBBLES = 150
SUGGEST_EVERY_MS = 20 * 60 * 1000   # look for new habits every 20 minutes
REMINDER_CHECK_MS = 15 * 1000       # look for due reminders every 15 seconds

VOICES = ["en-GB-RyanNeural", "en-GB-SoniaNeural", "en-IN-PrabhatNeural", "en-IN-NeerjaNeural",
          "en-US-GuyNeural", "en-US-JennyNeural"]


def font(size=13, weight="normal", family=FONT):
    return ctk.CTkFont(family=family, size=size, weight=weight)


class QueueHandler(logging.Handler):
    """Sends log lines to the window so they appear in the activity panel."""

    def __init__(self, events):
        super().__init__()
        self.events = events

    def emit(self, record):
        self.events.put(("log", self.format(record), record.levelno))


class JarvisApp:
    def __init__(self, root):
        self.root = root
        self.events = queue.Queue()
        self.orchestrator = None
        self.busy = False
        self.voice_enabled = True
        self.status_rows = {}
        self.bubbles = []
        self.offered = set()   # suggestions already shown this session
        self.wake = None       # "Hey JARVIS" listener, if available
        self.hotkey = None     # Ctrl+Shift+J text actions, if available
        self.text_menu = None

        self._build_ui()
        self._setup_logging()
        self._begin_work()
        self._set_state("STARTING", AMBER)
        self.root.after(100, self._poll_events)
        self.root.after(SUGGEST_EVERY_MS, self._suggest_tick)
        self.root.after(3000, self._reminder_tick)
        threading.Thread(target=self._startup, daemon=True).start()

    # ================================================================ building the window
    def _build_ui(self):
        self.root.title("J.A.R.V.I.S")
        self.root.geometry("1240x760")
        self.root.minsize(980, 600)
        self.root.configure(fg_color=BG)
        self.root.grid_columnconfigure(1, weight=1)
        self.root.grid_rowconfigure(0, weight=1)
        self._build_sidebar()
        self._build_main()
        self._build_activity()

    def _build_sidebar(self):
        side = ctk.CTkFrame(self.root, width=250, corner_radius=0, fg_color=SIDEBAR)
        side.grid(row=0, column=0, sticky="nsw")
        side.grid_propagate(False)
        side.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(side, text="J.A.R.V.I.S", font=font(28, "bold"), text_color=CYAN).grid(
            row=0, column=0, sticky="w", padx=22, pady=(24, 0))
        ctk.CTkLabel(side, text="Just A Rather Very Intelligent System", font=font(11), text_color=DIM).grid(
            row=1, column=0, sticky="w", padx=22)

        self._section(side, "SYSTEMS", 2)
        box = ctk.CTkFrame(side, fg_color=PANEL, corner_radius=12)
        box.grid(row=3, column=0, sticky="ew", padx=14)
        box.grid_columnconfigure(1, weight=1)
        for index, name in enumerate(SYSTEMS):
            dot = ctk.CTkFrame(box, width=10, height=10, corner_radius=5, fg_color=DIM)
            dot.grid(row=index, column=0, padx=(14, 8), pady=(10 if index == 0 else 4, 10 if index == len(SYSTEMS) - 1 else 4))
            label = ctk.CTkLabel(box, text=SYSTEM_NAMES[name], font=font(13, "bold"), text_color=TEXT, anchor="w")
            label.grid(row=index, column=1, sticky="w")
            detail = ctk.CTkLabel(box, text="starting", font=font(11), text_color=DIM, anchor="e")
            detail.grid(row=index, column=2, sticky="e", padx=(4, 12))
            self.status_rows[name] = (dot, detail)

        self._section(side, "CONTROLS", 4)
        controls = ctk.CTkFrame(side, fg_color="transparent")
        controls.grid(row=5, column=0, sticky="ew", padx=18)
        self.voice_var = ctk.BooleanVar(value=True)
        self.wake_var = ctk.BooleanVar(value=True)
        self.activity_var = ctk.BooleanVar(value=True)
        for row, (text, var, command) in enumerate([
            ("Voice replies", self.voice_var, self._toggle_voice),
            ("Hey JARVIS", self.wake_var, self._toggle_wake),
            ("Activity panel", self.activity_var, self._toggle_activity),
        ]):
            ctk.CTkSwitch(controls, text=text, variable=var, command=command, font=font(13), text_color=TEXT,
                          progress_color=CYAN).grid(row=row, column=0, sticky="w", pady=4)

        self._section(side, "SHORTCUTS", 6)
        shortcuts = ctk.CTkFrame(side, fg_color="transparent")
        shortcuts.grid(row=7, column=0, sticky="ew", padx=14)
        shortcuts.grid_columnconfigure(0, weight=1)
        for row, (text, command) in enumerate([
            ("Routines", self._show_routines),
            ("Reminders", self._show_reminders),
            ("Settings", self._show_settings),
        ]):
            ctk.CTkButton(shortcuts, text=text, command=command, anchor="w", height=34, corner_radius=10,
                          font=font(13), fg_color=PANEL, hover_color=BORDER, text_color=TEXT).grid(
                row=row, column=0, sticky="ew", pady=3)

        side.grid_rowconfigure(8, weight=1)
        self.hint_label = ctk.CTkLabel(side, text="Tip: select text in any app\nand press Ctrl+Shift+J",
                                       font=font(11), text_color=DIM, justify="left")
        self.hint_label.grid(row=9, column=0, sticky="sw", padx=22, pady=18)

    def _section(self, parent, title, row):
        ctk.CTkLabel(parent, text=title, font=font(11, "bold"), text_color=DIM).grid(
            row=row, column=0, sticky="w", padx=22, pady=(22, 6))

    def _build_main(self):
        main = ctk.CTkFrame(self.root, corner_radius=0, fg_color=BG)
        main.grid(row=0, column=1, sticky="nsew")
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(main, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=22, pady=(18, 6))
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(header, text="Conversation", font=font(18, "bold"), text_color=TEXT).grid(row=0, column=0, sticky="w")
        self.state_pill = ctk.CTkLabel(header, text="", font=font(12, "bold"), corner_radius=12, height=28,
                                       fg_color=PANEL, text_color=AMBER, padx=14)
        self.state_pill.grid(row=0, column=1, sticky="e")

        self.chat = ctk.CTkScrollableFrame(main, fg_color=PANEL, corner_radius=16)
        self.chat.grid(row=1, column=0, sticky="nsew", padx=22, pady=6)
        self.chat.grid_columnconfigure(0, weight=1)
        self.chat.bind("<Configure>", lambda event: self._rewrap())

        bar = ctk.CTkFrame(main, fg_color=PANEL, corner_radius=16)
        bar.grid(row=2, column=0, sticky="ew", padx=22, pady=(8, 20))
        bar.grid_columnconfigure(0, weight=1)
        self.entry = ctk.CTkEntry(bar, placeholder_text="Type a message, or say “Hey JARVIS”…",
                                  font=font(14), height=44, border_width=0, fg_color=PANEL, text_color=TEXT)
        self.entry.grid(row=0, column=0, sticky="ew", padx=(14, 6), pady=8)
        self.entry.bind("<Return>", lambda event: self._send())
        self.mic_button = ctk.CTkButton(bar, text="SPEAK", width=92, height=40, corner_radius=12,
                                        font=font(13, "bold"), fg_color=GREEN, hover_color="#2fbf70",
                                        text_color=BG, command=self._listen_clicked)
        self.mic_button.grid(row=0, column=1, padx=4, pady=8)
        self.send_button = ctk.CTkButton(bar, text="SEND", width=92, height=40, corner_radius=12,
                                         font=font(13, "bold"), fg_color=CYAN, hover_color="#38b6e0",
                                         text_color=BG, command=self._send)
        self.send_button.grid(row=0, column=2, padx=(4, 10), pady=8)
        self.entry.focus_set()

    def _build_activity(self):
        self.activity_frame = ctk.CTkFrame(self.root, width=380, corner_radius=0, fg_color=SIDEBAR)
        self.activity_frame.grid(row=0, column=2, sticky="nse")
        self.activity_frame.grid_propagate(False)
        self.activity_frame.grid_rowconfigure(1, weight=1)
        self.activity_frame.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(self.activity_frame, text="System activity", font=font(15, "bold"), text_color=TEXT).grid(
            row=0, column=0, sticky="w", padx=18, pady=(22, 8))
        self.activity = ctk.CTkTextbox(self.activity_frame, fg_color=PANEL, corner_radius=12, wrap="word",
                                       font=font(11, family=MONO), text_color=TEXT)
        self.activity.grid(row=1, column=0, sticky="nsew", padx=14, pady=(0, 20))
        self.activity.configure(state="disabled")

    # ================================================================ chat bubbles
    def _bubble_width(self):
        return max(260, int(self.chat.winfo_width() * 0.68))

    def _add_bubble(self, who, text):
        """who: 'user', 'jarvis' or 'note'."""
        row = ctk.CTkFrame(self.chat, fg_color="transparent")
        row.grid(row=len(self.bubbles), column=0, sticky="ew", padx=10, pady=(6, 2))
        row.grid_columnconfigure(0, weight=1)
        if who == "note":
            label = ctk.CTkLabel(row, text=text, font=font(11), text_color=DIM, wraplength=self._bubble_width())
            label.grid(row=0, column=0)
        else:
            side = "e" if who == "user" else "w"
            stamp = datetime.now().strftime("%I:%M %p").lstrip("0").lower()
            ctk.CTkLabel(row, text=f"{'You' if who == 'user' else 'JARVIS'}  ·  {stamp}", font=font(10),
                         text_color=DIM).grid(row=0, column=0, sticky=side, padx=6)
            label = ctk.CTkLabel(row, text=text, font=font(14), justify="left", anchor="w",
                                 wraplength=self._bubble_width(), corner_radius=14, padx=14, pady=9,
                                 fg_color=USER_BUBBLE if who == "user" else JARVIS_BUBBLE,
                                 text_color="#ffffff" if who == "user" else TEXT)
            label.grid(row=1, column=0, sticky=side)
        self.bubbles.append((row, label))
        if len(self.bubbles) > MAX_BUBBLES:
            old_row, _ = self.bubbles.pop(0)
            old_row.destroy()
        self.root.after(30, self._scroll_to_end)

    def _rewrap(self):
        width = self._bubble_width()
        for _, label in self.bubbles:
            label.configure(wraplength=width)

    def _scroll_to_end(self):
        try:
            self.chat.update_idletasks()
            self.chat._parent_canvas.yview_moveto(1.0)
        except Exception:
            pass

    # ================================================================ small helpers
    def _toggle_voice(self):
        self.voice_enabled = self.voice_var.get()

    def _toggle_activity(self):
        if self.activity_var.get():
            self.activity_frame.grid()
        else:
            self.activity_frame.grid_remove()

    def _toggle_wake(self):
        if self.wake is None:
            return
        if self.wake_var.get() and not self.busy:
            self.wake.resume()
        else:
            self.wake.pause()
        if not self.busy:
            self._end_work()

    def _wake_ready(self):
        return self.wake is not None and self.wake_var.get()

    def _set_state(self, text, color):
        self.state_pill.configure(text=text, text_color=color)

    def _set_status(self, name, detail, color):
        dot, label = self.status_rows[name]
        dot.configure(fg_color=color)
        label.configure(text=detail)

    def _begin_work(self):
        self.busy = True
        if self.wake is not None:
            self.wake.pause()  # free the microphone and never wake on our own voice
        self.send_button.configure(state="disabled")
        self.mic_button.configure(state="disabled")

    def _end_work(self):
        self.busy = False
        if self._wake_ready():
            self.wake.resume()
            self._set_state("READY · say “Hey JARVIS”", GREEN)
        else:
            self._set_state("READY", GREEN)
        self.send_button.configure(state="normal")
        self.mic_button.configure(state="normal")

    # ================================================================ logging
    def _setup_logging(self):
        logger = logging.getLogger("jarvis")
        logger.setLevel(logging.INFO)
        handler = QueueHandler(self.events)
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
        from core.logging_setup import add_file_logging
        add_file_logging(logger)

    def _show_log(self, message, level):
        color = RED if level >= logging.ERROR else TEXT
        for prefix, prefix_color in LOG_COLORS.items():
            if message.startswith(prefix):
                color = RED if level >= logging.ERROR else prefix_color
                break
        tag = f"c{color}"
        self.activity.configure(state="normal")
        self.activity.tag_config(tag, foreground=color)
        self.activity.insert("end", message[:300] + "\n", tag)
        if int(self.activity.index("end-1c").split(".")[0]) > 600:
            self.activity.delete("1.0", "100.0")
        self.activity.configure(state="disabled")
        self.activity.see("end")

    # ================================================================ startup (background thread)
    def _startup(self):
        log = logging.getLogger("jarvis")
        try:
            from core.orchestrator import Orchestrator
            self.orchestrator = Orchestrator(confirm=self._confirm)
            self.events.put(("status", "AI", self.orchestrator.llm.model_name.replace("gemini-", ""), GREEN))
        except Exception as error:
            self.events.put(("status", "AI", "offline", RED))
            log.error("[LLM] Could not start: %s", error)

        try:
            from contextlib import closing
            from memory.database import get_connection
            with closing(get_connection()) as connection:
                count = connection.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
            self.events.put(("status", "MEMORY", f"{count} facts", GREEN))
        except Exception as error:
            self.events.put(("status", "MEMORY", "offline", RED))
            log.error("[MEMORY] Database error: %s", error)

        try:
            from rag.vector_store import get_collection
            chunks = get_collection().count()
            self.events.put(("status", "DOCUMENTS", f"{chunks} chunks" if chunks else "empty", GREEN if chunks else AMBER))
        except Exception as error:
            self.events.put(("status", "DOCUMENTS", "offline", RED))
            log.error("[RAG] Vector store error: %s", error)

        try:
            from tools.registry import get_tool_functions
            self.events.put(("status", "TOOLS", f"{len(get_tool_functions())} tools", GREEN))
        except Exception as error:
            self.events.put(("status", "TOOLS", "offline", RED))
            log.error("[TOOL] Registry error: %s", error)

        try:
            import pyttsx3  # noqa: F401
            import speech_recognition  # noqa: F401
            voice_ok = True
        except Exception as error:
            voice_ok = False
            self.events.put(("status", "VOICE", "offline", RED))
            log.error("[VOICE] Voice libraries missing: %s", error)

        if voice_ok:
            self.events.put(("status", "VOICE", self._start_wake_word(log), GREEN))
        self._start_hotkey(log)

        # Greet before going idle, so the wake word never hears our own voice
        if self.orchestrator is not None and self.voice_enabled:
            self._speak("J.A.R.V.I.S online. At your service, Sir.")
        self.events.put(("ready",))
        self._check_suggestions()

    # ================================================================ wake word
    def _start_wake_word(self, log):
        """Returns the detail text for the VOICE status row."""
        try:
            from voice import wake_word
            if not wake_word.enabled():
                return "push-to-talk"
            listener = wake_word.WakeWordListener(on_wake=lambda: self.events.put(("wake",)))
            listener.pause()      # stays paused until JARVIS is idle
            listener.start()
            self.wake = listener
            return "Hey JARVIS"
        except Exception as error:
            log.warning("[VOICE] Wake word unavailable, use the SPEAK button: %s", error)
            return "push-to-talk"

    def _on_wake(self):
        """Window thread: "Hey JARVIS" was heard."""
        if self.busy or self.orchestrator is None or not self._wake_ready():
            return
        try:
            import winsound
            winsound.MessageBeep(winsound.MB_OK)  # short chime: "I'm listening"
        except Exception:
            pass
        self._listen_clicked()

    def _speak_aside(self, text):
        """Speak something JARVIS starts by itself (reminders, suggestions) without waking itself."""
        paused_here = self.wake is not None and not self.busy
        if paused_here:
            self.wake.pause()
        try:
            self._speak(text)
        finally:
            if paused_here and not self.busy and self._wake_ready():
                self.wake.resume()

    # ================================================================ typed and spoken messages
    def _send(self):
        text = self.entry.get().strip()
        if not text or self.busy or self.orchestrator is None:
            return
        self.entry.delete(0, "end")
        self._add_bubble("user", text)
        self._begin_work()
        threading.Thread(target=self._process, args=(text,), daemon=True).start()

    def _listen_clicked(self):
        if self.busy or self.orchestrator is None:
            return
        self._begin_work()
        self._set_state("LISTENING · speak now", CYAN)
        threading.Thread(target=self._listen_and_process, daemon=True).start()

    def _listen_and_process(self):
        try:
            from voice.speech_to_text import listen
            text = listen()
        except Exception as error:
            logging.getLogger("jarvis").error("[STT] Error: %s", error)
            text = ""
        if not text:
            self._respond("I didn't catch that, Sir.")
            return
        self.events.put(("user_text", text))
        self._process(text)

    def _is_exit(self, text):
        return re.sub(r"[^a-z ]", "", text.lower()).strip() in EXIT_WORDS

    def _process(self, text):
        if self._is_exit(text):
            self._respond("Goodbye, Sir.", quit_after=True)
            return
        self.events.put(("state", "THINKING", AMBER))
        try:
            reply = self.orchestrator.ask(text)
        except Exception as error:
            logging.getLogger("jarvis").error("[AGENT] Unexpected error: %s", error)
            reply = "Sir, something went wrong while processing that request."
        self._respond(reply)

    def _respond(self, reply, quit_after=False):
        self.events.put(("reply", reply))
        if self.voice_enabled:
            self.events.put(("state", "SPEAKING", CYAN))
            self._speak(reply)
        self.events.put(("quit",) if quit_after else ("done",))

    def _speak(self, text):
        try:
            from voice.text_to_speech import speak
            speak(re.sub(r"[*#`_]", "", text))
        except Exception as error:
            logging.getLogger("jarvis").error("[TTS] Error: %s", error)

    # ================================================================ cards (approval, suggestion, lists)
    def _card(self, title, badge, badge_color, lines, approve_text=None, cancel_text="Close", width=460):
        """A centred dialog card. Returns True if approved. Must run in the window thread."""
        result = {"ok": False}
        card = ctk.CTkToplevel(self.root)
        card.title("J.A.R.V.I.S")
        card.configure(fg_color=CARD)
        card.resizable(False, False)
        card.transient(self.root)
        card.attributes("-topmost", True)

        ctk.CTkLabel(card, text=badge, font=font(11, "bold"), text_color=BG, fg_color=badge_color,
                     corner_radius=10, height=24, padx=10).pack(anchor="w", padx=22, pady=(20, 8))
        ctk.CTkLabel(card, text=title, font=font(17, "bold"), text_color=TEXT, justify="left",
                     wraplength=width - 44).pack(anchor="w", padx=22)
        body = ctk.CTkFrame(card, fg_color=PANEL, corner_radius=12)
        body.pack(fill="x", padx=22, pady=14)
        for line in lines:
            numbered = re.match(r"^\s*(\d+)\.\s+(.*)$", line)
            if numbered:
                row = ctk.CTkFrame(body, fg_color="transparent")
                row.pack(fill="x", padx=14, pady=3)
                ctk.CTkLabel(row, text=numbered.group(1), width=24, height=24, corner_radius=12, fg_color=badge_color,
                             text_color=BG, font=font(11, "bold")).pack(side="left", anchor="n")
                ctk.CTkLabel(row, text=numbered.group(2), font=font(13), text_color=TEXT, justify="left",
                             wraplength=width - 110).pack(side="left", padx=10, anchor="w")
            elif line.strip():
                ctk.CTkLabel(body, text=line.strip(), font=font(13), text_color=TEXT, justify="left",
                             wraplength=width - 74).pack(anchor="w", padx=14, pady=4)
        if not any(line.strip() for line in lines):
            ctk.CTkLabel(body, text="Nothing here yet.", font=font(13), text_color=DIM).pack(anchor="w", padx=14, pady=8)

        buttons = ctk.CTkFrame(card, fg_color="transparent")
        buttons.pack(fill="x", padx=22, pady=(0, 20))

        def finish(ok):
            result["ok"] = ok
            card.grab_release()
            card.destroy()

        if approve_text:
            ctk.CTkButton(buttons, text=f"{approve_text}  ↵", command=lambda: finish(True), height=38,
                          corner_radius=10, fg_color=GREEN, hover_color="#2fbf70", text_color=BG,
                          font=font(13, "bold")).pack(side="right")
            card.bind("<Return>", lambda event: finish(True))
        ctk.CTkButton(buttons, text=f"{cancel_text}  Esc", command=lambda: finish(False), height=38, corner_radius=10,
                      fg_color="transparent", border_width=1, border_color=BORDER, hover_color=PANEL,
                      text_color=TEXT, font=font(13)).pack(side="right", padx=(0, 8))
        card.bind("<Escape>", lambda event: finish(False))
        card.protocol("WM_DELETE_WINDOW", lambda: finish(False))

        card.update_idletasks()
        x = self.root.winfo_rootx() + (self.root.winfo_width() - card.winfo_reqwidth()) // 2
        y = self.root.winfo_rooty() + max(40, (self.root.winfo_height() - card.winfo_reqheight()) // 3)
        card.geometry(f"{width}x{card.winfo_reqheight()}+{max(0, x)}+{max(0, y)}")
        card.after(60, card.focus_force)
        card.after(80, card.grab_set)
        self.root.wait_window(card)
        return result["ok"]

    def _confirm(self, description):
        """Level 2 permission prompt. Called from the worker thread; the card runs in the window thread."""
        result = {}
        done = threading.Event()
        self.events.put(("confirm", description, result, done))
        done.wait(timeout=120)
        return result.get("ok", False)

    def _show_confirm(self, description, result, done):
        lines = description.split("\n")
        title = "Sir, I'd like to " + lines[0].rstrip(":") + ("." if len(lines) == 1 else ":")
        result["ok"] = self._card(title, "PERMISSION REQUIRED", AMBER, lines[1:], "Approve", "Cancel")
        done.set()

    def _show_routines(self):
        from tools.routines import all_routines
        lines = [f"{name}: " + ", ".join(step.split(": ", 1)[-1] for step in steps)
                 for name, steps in all_routines().items()]
        self._card("Your routines", "ROUTINES", GREEN,
                   [f"{i}. {line}" for i, line in enumerate(lines, 1)] or ["Say “make a study routine that opens…”"])

    def _show_reminders(self):
        from tools.reminders import list_reminders
        text = list_reminders()
        lines = [line[2:] for line in text.splitlines() if line.startswith("- ")]
        self._card("Upcoming reminders", "REMINDERS", AMBER,
                   [f"{i}. {line}" for i, line in enumerate(lines, 1)] or ["Say “remind me to… at 6pm”"])

    # ================================================================ settings
    def _show_settings(self):
        from core.settings import read_settings, save_settings
        current = read_settings()
        win = ctk.CTkToplevel(self.root)
        win.title("J.A.R.V.I.S — Settings")
        win.configure(fg_color=CARD)
        win.resizable(False, False)
        win.transient(self.root)
        win.attributes("-topmost", True)
        ctk.CTkLabel(win, text="Settings", font=font(20, "bold"), text_color=TEXT).pack(anchor="w", padx=24, pady=(20, 4))
        ctk.CTkLabel(win, text="Saved to your .env file. Your API key is never changed here.", font=font(11),
                     text_color=DIM).pack(anchor="w", padx=24, pady=(0, 10))
        form = ctk.CTkFrame(win, fg_color=PANEL, corner_radius=12)
        form.pack(fill="x", padx=24, pady=6)
        form.grid_columnconfigure(1, weight=1)

        def label(row, text, note=None):
            ctk.CTkLabel(form, text=text, font=font(13), text_color=TEXT).grid(row=row, column=0, sticky="w",
                                                                               padx=16, pady=(12, 0 if note else 12))
            if note:
                ctk.CTkLabel(form, text=note, font=font(10), text_color=DIM).grid(row=row + 1, column=0, sticky="w",
                                                                                 padx=16, pady=(0, 10))

        voice = ctk.StringVar(value=current.get("JARVIS_VOICE", VOICES[0]))
        label(0, "Voice")
        ctk.CTkOptionMenu(form, values=VOICES, variable=voice, width=220, fg_color=CARD, button_color=BORDER).grid(
            row=0, column=1, sticky="e", padx=16)

        natural = ctk.BooleanVar(value=current.get("JARVIS_TTS", "edge") != "offline")
        label(1, "Natural voice", "Off = built-in Windows voice, works offline")
        ctk.CTkSwitch(form, text="", variable=natural, progress_color=CYAN).grid(row=1, column=1, sticky="e", padx=16)

        rate_text = current.get("JARVIS_VOICE_RATE", "+5%")
        rate = ctk.IntVar(value=int(re.sub(r"[^0-9-]", "", rate_text) or 0))
        label(3, "Speaking speed")
        speed = ctk.CTkFrame(form, fg_color="transparent")
        speed.grid(row=3, column=1, sticky="e", padx=16)
        rate_label = ctk.CTkLabel(speed, text="", font=font(12), text_color=DIM, width=48)
        ctk.CTkSlider(speed, from_=-20, to=30, number_of_steps=10, variable=rate, width=170, progress_color=CYAN,
                      command=lambda v: rate_label.configure(text=f"{int(v):+d}%")).pack(side="left")
        rate_label.configure(text=f"{rate.get():+d}%")
        rate_label.pack(side="left", padx=(8, 0))

        sensitivity = ctk.DoubleVar(value=1 - float(current.get("JARVIS_WAKE_THRESHOLD", "0.5") or 0.5))
        label(4, "Wake-word sensitivity", "Higher = easier to trigger, more false wake-ups")
        wake_row = ctk.CTkFrame(form, fg_color="transparent")
        wake_row.grid(row=4, column=1, sticky="e", padx=16)
        sens_label = ctk.CTkLabel(wake_row, text="", font=font(12), text_color=DIM, width=48)
        ctk.CTkSlider(wake_row, from_=0.2, to=0.7, number_of_steps=10, variable=sensitivity, width=170,
                      progress_color=CYAN, command=lambda v: sens_label.configure(text=f"{v:.2f}")).pack(side="left")
        sens_label.configure(text=f"{sensitivity.get():.2f}")
        sens_label.pack(side="left", padx=(8, 0))

        wake_on = ctk.BooleanVar(value=current.get("JARVIS_WAKE_WORD", "on") != "off")
        label(6, "“Hey JARVIS” at start-up")
        ctk.CTkSwitch(form, text="", variable=wake_on, progress_color=CYAN).grid(row=6, column=1, sticky="e", padx=16)

        language = ctk.StringVar(value=current.get("JARVIS_TRANSLATE_TO", "English"))
        label(7, "Translate selected text into")
        ctk.CTkEntry(form, textvariable=language, width=220).grid(row=7, column=1, sticky="e", padx=16)

        hotkey = ctk.StringVar(value=current.get("JARVIS_HOTKEY", "ctrl+shift+j"))
        label(8, "Text-action hotkey", "Takes effect after restarting JARVIS")
        ctk.CTkEntry(form, textvariable=hotkey, width=220).grid(row=8, column=1, sticky="e", padx=16)

        message = ctk.CTkLabel(win, text="", font=font(12), text_color=DIM)
        message.pack(anchor="w", padx=24, pady=(8, 0))

        def save():
            from ui.hotkey import parse_hotkey
            try:
                parse_hotkey(hotkey.get())
            except ValueError as error:
                message.configure(text=f"Hotkey: {error}", text_color=RED)
                return
            threshold = round(1 - sensitivity.get(), 2)
            save_settings({
                "JARVIS_VOICE": voice.get(),
                "JARVIS_TTS": "edge" if natural.get() else "offline",
                "JARVIS_VOICE_RATE": f"{rate.get():+d}%",
                "JARVIS_WAKE_THRESHOLD": str(threshold),
                "JARVIS_WAKE_WORD": "on" if wake_on.get() else "off",
                "JARVIS_TRANSLATE_TO": language.get().strip() or "English",
                "JARVIS_HOTKEY": hotkey.get().strip().lower(),
            })
            if self.wake is not None:
                self.wake.threshold = threshold  # applies immediately
            logging.getLogger("jarvis").info("[VOICE] Settings saved")
            message.configure(text="Saved. Voice and translation changes apply now.", text_color=GREEN)

        def test_voice():
            save()
            threading.Thread(target=self._speak_aside, args=("Good day, Sir. This is how I sound now.",),
                             daemon=True).start()

        buttons = ctk.CTkFrame(win, fg_color="transparent")
        buttons.pack(fill="x", padx=24, pady=(10, 20))
        ctk.CTkButton(buttons, text="Save", command=save, width=110, height=38, corner_radius=10, fg_color=GREEN,
                      hover_color="#2fbf70", text_color=BG, font=font(13, "bold")).pack(side="right")
        ctk.CTkButton(buttons, text="Test voice", command=test_voice, width=110, height=38, corner_radius=10,
                      fg_color=CYAN, hover_color="#38b6e0", text_color=BG, font=font(13, "bold")).pack(side="right", padx=8)
        ctk.CTkButton(buttons, text="Close", command=win.destroy, width=90, height=38, corner_radius=10,
                      fg_color="transparent", border_width=1, border_color=BORDER, text_color=TEXT,
                      font=font(13)).pack(side="right")
        win.bind("<Escape>", lambda event: win.destroy())
        win.update_idletasks()
        x = self.root.winfo_rootx() + (self.root.winfo_width() - win.winfo_reqwidth()) // 2
        y = self.root.winfo_rooty() + 60
        win.geometry(f"+{max(0, x)}+{max(0, y)}")
        win.after(60, win.focus_force)

    # ================================================================ proactive routine suggestions
    def _suggest_tick(self):
        """Runs in the window thread every 20 minutes (Tkinter timers must live here)."""
        threading.Thread(target=self._check_suggestions, daemon=True).start()
        self.root.after(SUGGEST_EVERY_MS, self._suggest_tick)

    def _check_suggestions(self):
        """Runs in a background thread. Offers at most one suggestion per check."""
        try:
            from core.suggestions import describe, find_suggestion
            suggestion = find_suggestion()
        except Exception as error:
            logging.getLogger("jarvis").error("[SUGGEST] Error: %s", error)
            suggestion = None
        if suggestion and suggestion["key"] not in self.offered:
            self.offered.add(suggestion["key"])
            logging.getLogger("jarvis").info("[SUGGEST] Habit found: %s", "; ".join(suggestion["steps"]))
            self.events.put(("suggest", suggestion, describe(suggestion)))

    def _handle_suggestion(self, suggestion, text):
        from core.suggestions import accept, dismiss
        self._add_bubble("jarvis", text)
        if self.voice_enabled and not self.busy:
            threading.Thread(target=self._speak_aside, args=(text,), daemon=True).start()
        hour = suggestion["hour"]
        when = f"{hour % 12 or 12} {'am' if hour < 12 else 'pm'}"
        steps = [f"{i}. {step.split(': ', 1)[-1].replace(' | ', ' → ')}" for i, step in enumerate(suggestion["steps"], 1)]
        title = f"Around {when} you usually do this. Save it as your “{suggestion['name']}” routine?"
        if self._card(title, "SUGGESTION", PURPLE, steps, "Save routine", "Not now"):
            accept(suggestion)
            self._add_bubble("jarvis", f"Done. Say “start {suggestion['name']} routine” any time, Sir.")
        else:
            dismiss(suggestion)
            self._add_bubble("jarvis", "Understood, I won't suggest that again.")

    # ================================================================ reminders
    def _reminder_tick(self):
        """Runs in the window thread; the database check runs in a worker thread."""
        threading.Thread(target=self._check_reminders, daemon=True).start()
        self.root.after(REMINDER_CHECK_MS, self._reminder_tick)

    def _check_reminders(self):
        try:
            from tools.reminders import pop_due_reminders
            due = pop_due_reminders()
        except Exception as error:
            logging.getLogger("jarvis").error("[REMINDER] Error: %s", error)
            return
        for text, due_at, missed in due:
            when = due_at.strftime("%I:%M %p").lstrip("0").lower()
            message = f"Missed reminder from {when}: {text}" if missed else f"Reminder: {text}"
            logging.getLogger("jarvis").info("[REMINDER] %s", message)
            self.events.put(("reminder", message))

    def _announce_reminder(self, message):
        from core.notify import notify
        notify("J.A.R.V.I.S reminder", message)
        self._add_bubble("jarvis", f"⏰  Sir, {message[0].lower() + message[1:]}")
        if self.voice_enabled:
            threading.Thread(target=self._speak_aside, args=(f"Sir, {message}",), daemon=True).start()

    # ================================================================ hotkey text actions
    def _start_hotkey(self, log):
        try:
            from ui.hotkey import GlobalHotkey
            hotkey = GlobalHotkey(on_press=lambda: self.events.put(("hotkey",)))
            if hotkey.start():
                self.hotkey = hotkey
                self.events.put(("hint", f"Tip: select text in any app\nand press {hotkey.name}"))
        except Exception as error:
            log.warning("[HOTKEY] Text actions unavailable: %s", error)

    def _on_hotkey(self):
        """Window thread: the hotkey was pressed in some app."""
        if self.busy or self.orchestrator is None:
            from core.notify import notify
            notify("J.A.R.V.I.S", "I'm busy right now, Sir. Try again in a moment.")
            return
        self._close_text_menu()
        try:
            previous = self.root.clipboard_get()
        except tk.TclError:
            previous = None
        self.root.clipboard_clear()
        logging.getLogger("jarvis").info("[HOTKEY] Copying the selected text")
        vk = self.hotkey.vk

        def copy_then_report():
            from ui.hotkey import send_copy
            send_copy(vk)
            time.sleep(0.3)  # give the app a moment to put its text on the clipboard
            self.events.put(("hotkey_copied", previous))

        threading.Thread(target=copy_then_report, daemon=True).start()

    def _on_selection_copied(self, previous):
        try:
            selected = self.root.clipboard_get()
        except tk.TclError:
            selected = ""
        self.root.clipboard_clear()  # put the user's own clipboard back
        if previous:
            self.root.clipboard_append(previous)
        if not selected.strip():
            from core.notify import notify
            notify("J.A.R.V.I.S", f"Select some text first, then press {self.hotkey.name}.")
            logging.getLogger("jarvis").info("[HOTKEY] No text was selected")
            return
        self._show_text_menu(selected)

    def _show_text_menu(self, selected):
        from core.text_actions import ACTIONS, preview
        menu = ctk.CTkToplevel(self.root)
        menu.overrideredirect(True)
        menu.attributes("-topmost", True)
        menu.configure(fg_color=CARD)
        frame = ctk.CTkFrame(menu, fg_color=CARD, border_width=1, border_color=CYAN, corner_radius=12)
        frame.pack(fill="both", expand=True)
        ctk.CTkLabel(frame, text="J.A.R.V.I.S", font=font(12, "bold"), text_color=CYAN).pack(anchor="w", padx=14, pady=(10, 0))
        ctk.CTkLabel(frame, text=f"“{preview(selected, 44)}”", font=font(11), text_color=DIM,
                     wraplength=260, justify="left").pack(anchor="w", padx=14, pady=(0, 6))
        for number, (key, (label, _)) in enumerate(ACTIONS.items(), 1):
            ctk.CTkButton(frame, text=f"{number}   {label}", anchor="w", height=32, corner_radius=8, font=font(13),
                          fg_color="transparent", hover_color=BORDER, text_color=TEXT,
                          command=lambda k=key: self._choose_text_action(k, selected)).pack(fill="x", padx=8, pady=1)
            menu.bind(str(number), lambda event, k=key: self._choose_text_action(k, selected))
        ctk.CTkButton(frame, text="Esc   Cancel", anchor="w", height=28, corner_radius=8, font=font(12),
                      fg_color="transparent", hover_color=BORDER, text_color=DIM,
                      command=self._close_text_menu).pack(fill="x", padx=8, pady=(2, 10))
        menu.bind("<Escape>", lambda event: self._close_text_menu())
        menu.update_idletasks()
        x, y = self.root.winfo_pointerxy()
        x = min(x + 12, menu.winfo_screenwidth() - menu.winfo_reqwidth() - 8)
        y = min(y + 12, menu.winfo_screenheight() - menu.winfo_reqheight() - 48)
        menu.geometry(f"+{x}+{y}")
        menu.after(60, menu.focus_force)
        self.text_menu = menu
        menu.after(30000, lambda: self.text_menu is menu and self._close_text_menu())

    def _close_text_menu(self):
        if self.text_menu is not None:
            self.text_menu.destroy()
            self.text_menu = None

    def _choose_text_action(self, key, selected):
        from core.text_actions import ACTIONS, build_request, preview
        self._close_text_menu()
        if self.busy or self.orchestrator is None:
            return
        label = ACTIONS[key][0]
        self._add_bubble("user", f"{label}: “{preview(selected)}”")
        logging.getLogger("jarvis").info("[HOTKEY] %s (%d characters)", label, len(selected))
        self._begin_work()
        self._set_state("THINKING", AMBER)

        def work():
            try:
                reply = self.orchestrator.ask(build_request(key, selected))
            except Exception as error:
                logging.getLogger("jarvis").error("[HOTKEY] %s failed: %s", label, error)
                reply = "Sir, something went wrong with that text action."
            self.events.put(("reply", reply))
            self.events.put(("text_result", label, reply))
            if key == "remember" and self.voice_enabled:
                self.events.put(("state", "SPEAKING", CYAN))
                self._speak(reply)
            self.events.put(("done",))

        threading.Thread(target=work, daemon=True).start()

    def _show_text_result(self, label, reply):
        window = ctk.CTkToplevel(self.root)
        window.title(f"J.A.R.V.I.S — {label}")
        window.configure(fg_color=CARD)
        window.attributes("-topmost", True)
        ctk.CTkLabel(window, text=label.upper(), font=font(11, "bold"), text_color=BG, fg_color=CYAN,
                     corner_radius=10, height=24, padx=10).pack(anchor="w", padx=18, pady=(16, 8))
        lines = reply.count("\n") + len(reply) // 64 + 2
        box = ctk.CTkTextbox(window, wrap="word", fg_color=PANEL, corner_radius=12, font=font(13), text_color=TEXT,
                             width=520, height=min(380, max(110, lines * 22)))
        box.insert("1.0", reply)
        box.configure(state="disabled")
        box.pack(fill="both", expand=True, padx=18)
        row = ctk.CTkFrame(window, fg_color="transparent")
        row.pack(fill="x", padx=18, pady=14)

        def copy():
            self.root.clipboard_clear()
            self.root.clipboard_append(reply)
            copy_button.configure(text="Copied ✓")

        copy_button = ctk.CTkButton(row, text="Copy", width=100, height=36, corner_radius=10, fg_color=CYAN,
                                    hover_color="#38b6e0", text_color=BG, font=font(13, "bold"), command=copy)
        copy_button.pack(side="right")
        ctk.CTkButton(row, text="Close", width=90, height=36, corner_radius=10, fg_color="transparent",
                      border_width=1, border_color=BORDER, text_color=TEXT, font=font(13),
                      command=window.destroy).pack(side="right", padx=8)
        window.bind("<Escape>", lambda event: window.destroy())
        x, y = self.root.winfo_pointerxy()
        window.geometry(f"+{max(0, x - 260)}+{max(0, y - 120)}")
        window.after(60, window.focus_force)

    # ================================================================ events from background threads
    def _poll_events(self):
        try:
            while True:
                event = self.events.get_nowait()
                kind = event[0]
                if kind == "log":
                    self._show_log(event[1], event[2])
                elif kind == "status":
                    self._set_status(event[1], event[2], event[3])
                elif kind == "state":
                    self._set_state(event[1], event[2])
                elif kind == "hint":
                    self.hint_label.configure(text=event[1])
                elif kind == "ready":
                    self._end_work()
                    self._add_bubble("jarvis", "At your service, Sir.")
                    restored = getattr(self.orchestrator, "restored_turns", 0)
                    if restored:
                        self._add_bubble("note", f"{restored} earlier messages restored from the last session")
                elif kind == "user_text":
                    self._add_bubble("user", event[1])
                elif kind == "reply":
                    self._add_bubble("jarvis", event[1])
                elif kind == "done":
                    self._end_work()
                elif kind == "quit":
                    if self.wake is not None:
                        self.wake.stop()
                    if self.hotkey is not None:
                        self.hotkey.stop()
                    self.root.destroy()
                    return
                elif kind == "confirm":
                    self._show_confirm(event[1], event[2], event[3])
                elif kind == "suggest":
                    self._handle_suggestion(event[1], event[2])
                elif kind == "reminder":
                    self._announce_reminder(event[1])
                elif kind == "hotkey":
                    self._on_hotkey()
                elif kind == "hotkey_copied":
                    self._on_selection_copied(event[1])
                elif kind == "text_result":
                    self._show_text_result(event[1], event[2])
                elif kind == "wake":
                    self._on_wake()
        except queue.Empty:
            pass
        self.root.after(100, self._poll_events)


def main():
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")
    root = ctk.CTk()
    JarvisApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
