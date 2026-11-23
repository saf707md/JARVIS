import logging
import queue
import re
import threading
import tkinter as tk
from tkinter import messagebox

DOT = "\u25cf"

EXIT_WORDS = (
    "exit", "quit", "bye", "goodbye", "goodbye jarvis", "bye jarvis",
    "exit jarvis", "quit jarvis", "close", "close jarvis", "shut down", "shut down jarvis",
)

BG = "#0a1018"
PANEL = "#101a26"
CYAN = "#4dd0ff"
TEXT = "#d6e6f2"
DIM = "#6b7f90"
GREEN = "#3ddc84"
RED = "#ff5c5c"
AMBER = "#ffb84d"

LOG_COLORS = {
    "[AGENT]": CYAN,
    "[TOOL]": GREEN,
    "[SECURITY]": AMBER,
    "[RAG]": "#c792ea",
    "[MEMORY]": "#ffe66d",
    "[LLM]": DIM,
    "[TTS]": DIM,
    "[STT]": DIM,
    "[VOICE]": DIM,
    "[ROUTINE]": GREEN,
    "[UNDO]": AMBER,
    "[SUGGEST]": "#c792ea",
    "[REMINDER]": AMBER,
    "[HOTKEY]": CYAN,
}

REMINDER_CHECK_MS = 15 * 1000  # look for due reminders every 15 seconds

SUGGEST_EVERY_MS = 20 * 60 * 1000  # look for new habits every 20 minutes


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
        self.indicators = {}
        self.offered = set()  # suggestions already shown this session
        self.wake = None       # "Hey JARVIS" listener, if available
        self.hotkey = None     # Ctrl+Shift+J text actions, if available
        self.text_menu = None

        self._build_ui()
        self._setup_logging()
        self._begin_work()
        self._set_state("STARTING...", AMBER)
        self.root.after(100, self._poll_events)
        self.root.after(SUGGEST_EVERY_MS, self._suggest_tick)
        self.root.after(3000, self._reminder_tick)
        threading.Thread(target=self._startup, daemon=True).start()

    # ---------- building the window ----------
    def _build_ui(self):
        self.root.title("J.A.R.V.I.S")
        self.root.geometry("1150x720")
        self.root.configure(bg=BG)
        self.root.minsize(900, 560)

        header = tk.Frame(self.root, bg=BG)
        header.pack(fill="x", padx=20, pady=(14, 4))
        left = tk.Frame(header, bg=BG)
        left.pack(side="left")
        tk.Label(left, text="J.A.R.V.I.S", font=("Consolas", 28, "bold"),
                 fg=CYAN, bg=BG).pack(anchor="w")
        tk.Label(left, text="JUST A RATHER VERY INTELLIGENT SYSTEM",
                 font=("Consolas", 9), fg=DIM, bg=BG).pack(anchor="w")
        right = tk.Frame(header, bg=BG)
        right.pack(side="right")
        self.system_label = tk.Label(right, text=f"{DOT} SYSTEM STARTING...",
                                     font=("Consolas", 12, "bold"), fg=AMBER, bg=BG)
        self.system_label.pack(anchor="e")
        self.state_label = tk.Label(right, text="", font=("Consolas", 11), fg=DIM, bg=BG)
        self.state_label.pack(anchor="e")

        bar = tk.Frame(self.root, bg=PANEL)
        bar.pack(fill="x", padx=20, pady=6)
        for name in ("AI", "MEMORY", "RAG", "TOOLS", "VOICE"):
            label = tk.Label(bar, text=f"{name} {DOT} ...", font=("Consolas", 11, "bold"),
                             fg=DIM, bg=PANEL, padx=14, pady=6)
            label.pack(side="left")
            self.indicators[name] = label

        body = tk.Frame(self.root, bg=BG)
        body.pack(fill="both", expand=True, padx=20, pady=6)
        body.columnconfigure(0, weight=3)
        body.columnconfigure(1, weight=2)
        body.rowconfigure(1, weight=1)

        tk.Label(body, text="CONVERSATION", font=("Consolas", 10, "bold"),
                 fg=DIM, bg=BG).grid(row=0, column=0, sticky="w")
        tk.Label(body, text="SYSTEM ACTIVITY", font=("Consolas", 10, "bold"),
                 fg=DIM, bg=BG).grid(row=0, column=1, sticky="w", padx=(10, 0))

        self.chat = self._make_text(body, 1, 0, (0, 0))
        self.chat.tag_config("user", foreground=TEXT)
        self.chat.tag_config("jarvis", foreground=CYAN)
        self.chat.tag_config("dim", foreground=DIM)
        self.activity = self._make_text(body, 1, 1, (10, 0))
        self.activity.config(font=("Consolas", 9))

        entry_row = tk.Frame(self.root, bg=BG)
        entry_row.pack(fill="x", padx=20, pady=(6, 16))
        self.entry = tk.Entry(entry_row, font=("Consolas", 13), bg=PANEL, fg=TEXT,
                              insertbackground=CYAN, relief="flat")
        self.entry.pack(side="left", fill="x", expand=True, ipady=9)
        self.entry.bind("<Return>", lambda event: self._send())
        self.mic_button = tk.Button(entry_row, text="SPEAK", font=("Consolas", 11, "bold"),
                                    bg=GREEN, fg=BG, relief="flat", padx=14,
                                    command=self._listen_clicked)
        self.mic_button.pack(side="left", padx=(8, 0), ipady=4)
        self.send_button = tk.Button(entry_row, text="SEND", font=("Consolas", 11, "bold"),
                                     bg=CYAN, fg=BG, relief="flat", padx=18,
                                     command=self._send)
        self.send_button.pack(side="left", padx=(8, 0), ipady=4)
        self.voice_var = tk.BooleanVar(value=True)
        tk.Checkbutton(entry_row, text="Voice replies", variable=self.voice_var,
                       command=self._toggle_voice, font=("Consolas", 10), fg=TEXT, bg=BG,
                       selectcolor=PANEL, activebackground=BG,
                       activeforeground=TEXT).pack(side="left", padx=(12, 0))
        self.wake_var = tk.BooleanVar(value=True)
        tk.Checkbutton(entry_row, text="Hey JARVIS", variable=self.wake_var,
                       command=self._toggle_wake, font=("Consolas", 10), fg=TEXT, bg=BG,
                       selectcolor=PANEL, activebackground=BG,
                       activeforeground=TEXT).pack(side="left", padx=(8, 0))
        self.entry.focus_set()

    def _make_text(self, parent, row, column, padx):
        frame = tk.Frame(parent, bg=PANEL)
        frame.grid(row=row, column=column, sticky="nsew", padx=padx)
        widget = tk.Text(frame, wrap="word", bg=PANEL, fg=TEXT, font=("Consolas", 11),
                         relief="flat", padx=10, pady=8, state="disabled")
        scroll = tk.Scrollbar(frame, command=widget.yview)
        widget.config(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        widget.pack(side="left", fill="both", expand=True)
        return widget

    def _append(self, widget, text, tag=None):
        widget.config(state="normal")
        widget.insert("end", text + "\n", tag)
        widget.config(state="disabled")
        widget.see("end")

    def _toggle_voice(self):
        self.voice_enabled = self.voice_var.get()

    def _set_state(self, text, color):
        self.state_label.config(text=text, fg=color)

    def _toggle_wake(self):
        if self.wake is None:
            return
        if self.wake_var.get() and not self.busy:
            self.wake.resume()
        else:
            self.wake.pause()

    def _wake_ready(self):
        return self.wake is not None and self.wake_var.get()

    def _begin_work(self):
        self.busy = True
        if self.wake is not None:
            self.wake.pause()  # free the microphone and never wake on our own voice
        self.send_button.config(state="disabled")
        self.mic_button.config(state="disabled")

    def _end_work(self):
        self.busy = False
        if self._wake_ready():
            self.wake.resume()
            self._set_state("READY - say \"Hey JARVIS\"", GREEN)
        else:
            self._set_state("READY", GREEN)
        self.send_button.config(state="normal")
        self.mic_button.config(state="normal")

    # ---------- logging into the activity panel ----------
    def _setup_logging(self):
        logger = logging.getLogger("jarvis")
        logger.setLevel(logging.INFO)
        handler = QueueHandler(self.events)
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
        from core.logging_setup import add_file_logging
        add_file_logging(logger)

    # ---------- startup checks (run in the background) ----------
    def _startup(self):
        log = logging.getLogger("jarvis")
        try:
            from core.orchestrator import Orchestrator
            self.orchestrator = Orchestrator(confirm=self._confirm)
            self.events.put(("status", "AI", "ONLINE", GREEN))
        except Exception as error:
            self.events.put(("status", "AI", "OFFLINE", RED))
            log.error("[LLM] Could not start: %s", error)

        try:
            from contextlib import closing
            from memory.database import get_connection
            with closing(get_connection()) as connection:
                count = connection.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
            self.events.put(("status", "MEMORY", f"ONLINE ({count} facts)", GREEN))
        except Exception as error:
            self.events.put(("status", "MEMORY", "OFFLINE", RED))
            log.error("[MEMORY] Database error: %s", error)

        try:
            from rag.vector_store import get_collection
            chunks = get_collection().count()
            if chunks:
                self.events.put(("status", "RAG", f"ONLINE ({chunks} chunks)", GREEN))
            else:
                self.events.put(("status", "RAG", "EMPTY", AMBER))
        except Exception as error:
            self.events.put(("status", "RAG", "OFFLINE", RED))
            log.error("[RAG] Vector store error: %s", error)

        try:
            from tools.registry import get_tool_functions
            self.events.put(("status", "TOOLS", f"ONLINE ({len(get_tool_functions())})", GREEN))
        except Exception as error:
            self.events.put(("status", "TOOLS", "OFFLINE", RED))
            log.error("[TOOL] Registry error: %s", error)

        try:
            import pyttsx3  # noqa: F401
            import speech_recognition  # noqa: F401
            voice_ok = True
        except Exception as error:
            voice_ok = False
            self.events.put(("status", "VOICE", "OFFLINE", RED))
            log.error("[VOICE] Voice libraries missing: %s", error)

        if voice_ok:
            self.events.put(("status", "VOICE", self._start_wake_word(log), GREEN))
        self._start_hotkey(log)

        # Greet before going idle, so the wake word never hears our own voice
        if self.orchestrator is not None and self.voice_enabled:
            self._speak("J.A.R.V.I.S online. At your service, Sir.")
        self.events.put(("ready",))
        self._check_suggestions()

    # ---------- wake word ----------
    def _start_wake_word(self, log):
        """Returns the text for the VOICE status light."""
        try:
            from voice import wake_word
            if not wake_word.enabled():
                return "ONLINE (wake word off)"
            listener = wake_word.WakeWordListener(on_wake=lambda: self.events.put(("wake",)))
            listener.pause()      # stays paused until JARVIS is idle
            listener.start()
            self.wake = listener
            return "ONLINE (Hey JARVIS)"
        except Exception as error:
            log.warning("[VOICE] Wake word unavailable, use the SPEAK button: %s", error)
            return "ONLINE (push-to-talk)"

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

    # ---------- hotkey text actions ----------
    def _start_hotkey(self, log):
        try:
            from ui.hotkey import GlobalHotkey
            hotkey = GlobalHotkey(on_press=lambda: self.events.put(("hotkey",)))
            if hotkey.start():
                self.hotkey = hotkey
        except Exception as error:
            log.warning("[HOTKEY] Text actions unavailable: %s", error)

    def _on_hotkey(self):
        """Window thread: the hotkey was pressed in some app."""
        log = logging.getLogger("jarvis")
        if self.busy or self.orchestrator is None:
            from core.notify import notify
            notify("J.A.R.V.I.S", "I'm busy right now, Sir. Try again in a moment.")
            return
        if self.text_menu is not None:
            self._close_text_menu()
        try:
            previous = self.root.clipboard_get()
        except tk.TclError:
            previous = None
        self.root.clipboard_clear()
        log.info("[HOTKEY] Copying the selected text")
        vk = self.hotkey.vk

        def copy_then_report():
            from ui.hotkey import send_copy
            send_copy(vk)
            import time
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
        menu = tk.Toplevel(self.root)
        menu.overrideredirect(True)
        menu.attributes("-topmost", True)
        menu.configure(bg=PANEL, highlightthickness=1, highlightbackground=CYAN)
        tk.Label(menu, text="J.A.R.V.I.S", font=("Consolas", 10, "bold"), fg=CYAN, bg=PANEL).pack(anchor="w", padx=10, pady=(8, 0))
        tk.Label(menu, text=f"\u201c{preview(selected, 48)}\u201d", font=("Consolas", 9), fg=DIM, bg=PANEL,
                 wraplength=300, justify="left").pack(anchor="w", padx=10, pady=(2, 6))
        for number, (key, (label, _)) in enumerate(ACTIONS.items(), 1):
            tk.Button(menu, text=f"{number}  {label}", anchor="w", font=("Consolas", 11), fg=TEXT, bg=BG,
                      activebackground=CYAN, activeforeground=BG, relief="flat", padx=10,
                      command=lambda k=key: self._choose_text_action(k, selected)).pack(fill="x", padx=8, pady=1)
            menu.bind(str(number), lambda event, k=key: self._choose_text_action(k, selected))
        tk.Button(menu, text="Esc  Cancel", anchor="w", font=("Consolas", 10), fg=DIM, bg=PANEL, relief="flat",
                  padx=10, command=self._close_text_menu).pack(fill="x", padx=8, pady=(4, 8))
        menu.bind("<Escape>", lambda event: self._close_text_menu())
        menu.update_idletasks()
        x, y = self.root.winfo_pointerxy()
        x = min(x + 12, menu.winfo_screenwidth() - menu.winfo_reqwidth() - 8)
        y = min(y + 12, menu.winfo_screenheight() - menu.winfo_reqheight() - 48)
        menu.geometry(f"+{x}+{y}")
        menu.focus_force()
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
        self._append(self.chat, f"YOU (hotkey): {label} \u2014 \u201c{preview(selected)}\u201d", "user")
        logging.getLogger("jarvis").info("[HOTKEY] %s (%d characters)", label, len(selected))
        self._begin_work()
        self._set_state("THINKING...", AMBER)

        def work():
            try:
                reply = self.orchestrator.ask(build_request(key, selected))
            except Exception as error:
                logging.getLogger("jarvis").error("[HOTKEY] %s failed: %s", label, error)
                reply = "Sir, something went wrong with that text action."
            self.events.put(("reply", reply))
            self.events.put(("text_result", label, reply))
            if key == "remember" and self.voice_enabled:
                self.events.put(("state", "SPEAKING...", CYAN))
                self._speak(reply)
            self.events.put(("done",))

        threading.Thread(target=work, daemon=True).start()

    def _show_text_result(self, label, reply):
        window = tk.Toplevel(self.root)
        window.title(f"J.A.R.V.I.S \u2014 {label}")
        window.configure(bg=BG)
        window.attributes("-topmost", True)
        text = tk.Text(window, wrap="word", bg=PANEL, fg=TEXT, font=("Consolas", 11), relief="flat",
                       padx=10, pady=8, width=60, height=min(18, max(5, reply.count("\n") + len(reply) // 60 + 2)))
        text.insert("1.0", reply)
        text.config(state="disabled")
        text.pack(fill="both", expand=True, padx=10, pady=(10, 6))
        row = tk.Frame(window, bg=BG)
        row.pack(fill="x", padx=10, pady=(0, 10))

        def copy():
            self.root.clipboard_clear()
            self.root.clipboard_append(reply)
            copy_button.config(text="COPIED")

        copy_button = tk.Button(row, text="COPY", font=("Consolas", 10, "bold"), bg=CYAN, fg=BG, relief="flat",
                                padx=14, command=copy)
        copy_button.pack(side="left")
        tk.Button(row, text="CLOSE", font=("Consolas", 10, "bold"), bg=PANEL, fg=TEXT, relief="flat", padx=14,
                  command=window.destroy).pack(side="left", padx=(8, 0))
        window.bind("<Escape>", lambda event: window.destroy())
        x, y = self.root.winfo_pointerxy()
        window.geometry(f"+{max(0, x - 200)}+{max(0, y - 100)}")
        window.focus_force()

    # ---------- reminders ----------
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
        self._append(self.chat, f"JARVIS: Sir, {message[0].lower() + message[1:]}", "jarvis")
        if self.voice_enabled:
            threading.Thread(target=self._speak_aside, args=(f"Sir, {message}",), daemon=True).start()

    # ---------- proactive routine suggestions ----------
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

    def _suggest_tick(self):
        """Runs in the window thread every 20 minutes (Tkinter timers must live here)."""
        threading.Thread(target=self._check_suggestions, daemon=True).start()
        self.root.after(SUGGEST_EVERY_MS, self._suggest_tick)

    def _handle_suggestion(self, suggestion, text):
        from core.suggestions import accept, dismiss
        self._append(self.chat, f"JARVIS: {text}", "jarvis")
        if self.voice_enabled and not self.busy:
            threading.Thread(target=self._speak_aside, args=(text,), daemon=True).start()
        if messagebox.askyesno("J.A.R.V.I.S - Suggestion", f"Sir, {text}"):
            result = accept(suggestion)
            name = suggestion["name"]
            self._append(self.chat, f"JARVIS: Done. Say \"start {name} routine\" any time. ({result})", "jarvis")
        else:
            dismiss(suggestion)
            self._append(self.chat, "JARVIS: Understood, I won't suggest that again.", "jarvis")

    # ---------- typed messages ----------
    def _send(self):
        text = self.entry.get().strip()
        if not text or self.busy or self.orchestrator is None:
            return
        self.entry.delete(0, "end")
        self._append(self.chat, f"YOU: {text}", "user")
        self._begin_work()
        threading.Thread(target=self._process, args=(text,), daemon=True).start()

    # ---------- spoken messages ----------
    def _listen_clicked(self):
        if self.busy or self.orchestrator is None:
            return
        self._begin_work()
        self._set_state("LISTENING... speak now", CYAN)
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

    # ---------- shared processing ----------
    def _is_exit(self, text):
        cleaned = re.sub(r"[^a-z ]", "", text.lower()).strip()
        return cleaned in EXIT_WORDS

    def _process(self, text):
        if self._is_exit(text):
            self._respond("Goodbye, Sir.", quit_after=True)
            return
        self.events.put(("state", "THINKING...", AMBER))
        try:
            reply = self.orchestrator.ask(text)
        except Exception as error:
            logging.getLogger("jarvis").error("[AGENT] Unexpected error: %s", error)
            reply = "Sir, something went wrong while processing that request."
        self._respond(reply)

    def _respond(self, reply, quit_after=False):
        self.events.put(("reply", reply))
        if self.voice_enabled:
            self.events.put(("state", "SPEAKING...", CYAN))
            self._speak(reply)
        if quit_after:
            self.events.put(("quit",))
        else:
            self.events.put(("done",))

    def _speak(self, text):
        try:
            from voice.text_to_speech import speak
            speak(re.sub(r"[*#`_]", "", text))
        except Exception as error:
            logging.getLogger("jarvis").error("[TTS] Error: %s", error)

    # ---------- permission prompt (Level 2) ----------
    def _confirm(self, description):
        """Called from the worker thread; the dialog itself runs in the window thread."""
        result = {}
        done = threading.Event()
        self.events.put(("confirm", description, result, done))
        done.wait(timeout=120)
        return result.get("ok", False)

    # ---------- handling events in the window thread ----------
    def _poll_events(self):
        try:
            while True:
                event = self.events.get_nowait()
                kind = event[0]
                if kind == "log":
                    self._show_log(event[1], event[2])
                elif kind == "status":
                    _, name, text, color = event
                    self.indicators[name].config(text=f"{name} {DOT} {text}", fg=color)
                elif kind == "state":
                    self._set_state(event[1], event[2])
                elif kind == "ready":
                    self.system_label.config(text=f"{DOT} SYSTEM ONLINE", fg=GREEN)
                    self._end_work()
                    self._append(self.chat, "JARVIS: At your service, Sir.", "jarvis")
                    restored = getattr(self.orchestrator, "restored_turns", 0)
                    if restored:
                        self._append(self.chat, f"({restored} earlier messages restored from the last session)", "dim")
                elif kind == "user_text":
                    self._append(self.chat, f"YOU (voice): {event[1]}", "user")
                elif kind == "reply":
                    self._append(self.chat, f"JARVIS: {event[1]}", "jarvis")
                elif kind == "quit":
                    if self.wake is not None:
                        self.wake.stop()
                    if self.hotkey is not None:
                        self.hotkey.stop()
                    self.root.destroy()
                    return
                elif kind == "done":
                    self._end_work()
                elif kind == "hotkey":
                    self._on_hotkey()
                elif kind == "hotkey_copied":
                    self._on_selection_copied(event[1])
                elif kind == "text_result":
                    self._show_text_result(event[1], event[2])
                elif kind == "wake":
                    self._on_wake()
                elif kind == "reminder":
                    self._announce_reminder(event[1])
                elif kind == "suggest":
                    self._handle_suggestion(event[1], event[2])
                elif kind == "confirm":
                    _, description, result, done = event
                    result["ok"] = messagebox.askyesno(
                        "J.A.R.V.I.S - Permission required",
                        f"Sir, I'd like to {description}.\n\nWould you like me to continue?",
                    )
                    done.set()
        except queue.Empty:
            pass
        self.root.after(100, self._poll_events)

    def _show_log(self, message, level):
        color = RED if level >= logging.ERROR else TEXT
        for prefix, prefix_color in LOG_COLORS.items():
            if message.startswith(prefix):
                color = RED if level >= logging.ERROR else prefix_color
                break
        tag = f"c{color}"
        self.activity.tag_config(tag, foreground=color)
        self._append(self.activity, message[:300], tag)


def main():
    root = tk.Tk()
    JarvisApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()



