# J.A.R.V.I.S - Just A Rather Very Intelligent System

A cloud-based personal AI assistant for Windows. JARVIS understands typed or spoken requests,
decides which approved tool to use, searches the web and your own documents, remembers facts
between sessions, and controls the computer through a safe permission system.

No GPU is needed: the language model runs in the cloud (Google Gemini free tier).

## Features
- Voice conversation (speech-to-text and a natural neural voice, with the built-in Windows voice as fallback)
- Cloud LLM brain with tool calling (agent behaviour, multi-step)
- Persistent memory in SQLite
- RAG over your own PDF, PPTX, DOCX, TXT and MD files (ChromaDB, local embeddings)
- Web and news search, weather, calculator, system information
- Safe computer actions: open approved apps and websites, find and read files, screenshots
- Three-level security model with confirmation prompts
- Dark desktop interface with status lights and a live activity panel

## Architecture
User -> Interface -> Orchestrator -> Cloud LLM
                          |-> Security layer -> Tool layer (calculator, search, files, apps...)
                          |-> Memory (SQLite)
                          |-> RAG (ChromaDB)
                          |-> Voice (STT / TTS)

The LLM never executes anything. It can only REQUEST a tool from a fixed registry. The
orchestrator checks the request with the security layer and runs the approved Python function.

## Security model
- Level 1 (automatic): calculate, search, weather, read allowed files, open whitelisted apps and
  websites, memory, document search, screenshot.
- Level 2 (asks the user first): create_note (and any future action that changes files).
- Level 3 (never runs): shell commands, deleting files, installing software, passwords, system settings.
Other protections: application whitelist, website validator, allowed folders for file access,
blocked sensitive file names (.env, password, secret...), calculator without eval, tool round limit.

## Setup (Windows)
1. Install Python 3.10 or newer.
2. In the project folder:
   python -m venv venv
   .\venv\Scripts\Activate.ps1
   pip install -r requirements.txt
3. Create a .env file (never commit it):
   GEMINI_API_KEY=your_key_here
   GEMINI_MODEL=gemini-3.5-flash-lite
   Optional voice settings:
   JARVIS_TTS=edge                 (natural voice, needs internet; "offline" = built-in Windows voice)
   JARVIS_VOICE=en-GB-RyanNeural   (other voices: en-IN-PrabhatNeural, en-US-GuyNeural, en-GB-SoniaNeural)
   JARVIS_VOICE_RATE=+5%
   JARVIS_WAKE_WORD=on             ("Hey JARVIS"; off = SPEAK button only)
   JARVIS_WAKE_THRESHOLD=0.5       (raise to 0.6-0.7 if it wakes by mistake, lower to 0.3-0.4 if it misses you)
4. Put documents in knowledge\ (any sub-folders), then run: python -m rag.ingest
5. Check everything: python health_check.py
6. Start JARVIS: double-click start_jarvis.bat (or: python -m ui.app)

## Project structure
core/       orchestrator, LLM wrapper, prompts, logging setup
voice/      speech_to_text.py, text_to_speech.py
memory/     SQLite database and memory manager
rag/        document loader, chunking, vector store, ingest, retriever
tools/      calculator, browser, applications, filesystem, system, weather, web_search, screenshot, registry
security/   permission levels
ui/         Tkinter interface
knowledge/  your documents      notes/  notes JARVIS creates      logs/  jarvis.log

## Adding a new tool
1. Write a Python function with type hints and a clear docstring in tools/.
2. Add it to the _TOOLS dictionary in tools/registry.py with a permission level (1, 2 or 3).

## Limitations
- Free-tier cloud services have rate limits and may be busy at times.
- Speech recognition uses Google's free web service, so audio is sent to Google.
- Web search uses unofficial free search libraries and can occasionally return nothing.
- Scanned (image-only) PDFs cannot be read yet.
- Text sent to Gemini on the free tier may be used by Google to improve its products.

## Future scope
Vision and camera input, calendar and email, smart-home control,
mobile app, multiple specialised agents, better voices.
