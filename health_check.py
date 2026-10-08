import importlib
import sys

passed = 0
failed = 0


def check(name, function):
    global passed, failed
    try:
        detail = function()
        print(f"[PASS] {name}" + (f" - {detail}" if detail else ""))
        passed += 1
    except Exception as error:
        print(f"[FAIL] {name} - {error}")
        failed += 1


def python_version():
    return sys.version.split()[0]


def api_key():
    import config
    if not config.GEMINI_API_KEY or config.GEMINI_API_KEY == "your_key_here":
        raise RuntimeError("no real GEMINI_API_KEY in .env")
    return f"key found, model {config.GEMINI_MODEL}"


def packages():
    names = ["google.genai", "dotenv", "pyttsx3", "speech_recognition", "pyaudio", "chromadb",
             "pypdf", "pptx", "docx", "requests", "psutil", "ddgs", "PIL", "tkinter"]
    missing = []
    for name in names:
        try:
            importlib.import_module(name)
        except Exception:
            missing.append(name)
    if missing:
        raise RuntimeError("missing: " + ", ".join(missing))
    return f"{len(names)} packages found"


def memory_database():
    from contextlib import closing
    from memory.database import get_connection
    with closing(get_connection()) as connection:
        count = connection.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
    return f"{count} stored facts"


def document_index():
    from rag.vector_store import get_collection
    count = get_collection().count()
    if count == 0:
        raise RuntimeError("no documents indexed - run: python -m rag.ingest")
    return f"{count} chunks indexed"


def microphone():
    import speech_recognition as sr
    devices = sr.Microphone.list_microphone_names()
    if not devices:
        raise RuntimeError("no microphone found")
    return f"{len(devices)} audio input devices"


def speaker_voice():
    import pyttsx3
    voices = pyttsx3.init().getProperty("voices")
    if not voices:
        raise RuntimeError("no Windows voices found")
    return f"{len(voices)} voices available"


def internet():
    import requests
    response = requests.get(
        "https://geocoding-api.open-meteo.com/v1/search?name=London&count=1", timeout=8
    )
    response.raise_for_status()
    return "online"


def tool_registry():
    from tools.registry import get_tool_functions
    functions = get_tool_functions()
    without_docs = [f.__name__ for f in functions if not f.__doc__]
    if without_docs:
        raise RuntimeError("tools without descriptions: " + ", ".join(without_docs))
    return f"{len(functions)} tools registered"


def security_tests():
    from tools.registry import run_tool

    unknown = run_tool("run_shell", {"command": "dir"})
    if not unknown.startswith("Error"):
        raise RuntimeError("an unknown tool was not rejected")

    declined = run_tool("create_note", {"filename": "health check", "content": "x"},
                        confirm=lambda description: False)
    if "declined" not in declined:
        raise RuntimeError("a Level 2 action ran without approval")

    secret = run_tool("read_text_file", {"path": ".env"})
    if not secret.startswith("Error"):
        raise RuntimeError(".env could be read")

    app = run_tool("open_application", {"app_name": "powershell"})
    if not app.startswith("Error"):
        raise RuntimeError("an unapproved application could be opened")

    return "unknown tool, Level 2 decline, .env read and unapproved app were all blocked"


def calculator():
    from tools.calculator import calculate
    if calculate("25 * 40") != "1000":
        raise RuntimeError("wrong result")
    try:
        calculate("__import__('os').system('dir')")
    except Exception:
        return "25 * 40 = 1000, code injection rejected"
    raise RuntimeError("calculator accepted code")


def cloud_llm():
    from core.llm import JarvisLLM
    response = JarvisLLM().send("Reply with the single word: ready")
    if response is None:
        raise RuntimeError("no response (service busy or rate limited - wait a minute and retry)")
    return "AI replied: " + (response.text or "").strip()[:40]


print("J.A.R.V.I.S HEALTH CHECK\n")
check("Python version", python_version)
check("API key and model", api_key)
check("Required packages", packages)
check("Memory database", memory_database)
check("Document index (RAG)", document_index)
check("Microphone", microphone)
check("Speaker voice", speaker_voice)
check("Internet connection", internet)
check("Tool registry", tool_registry)
check("Calculator safety", calculator)
check("Security layer", security_tests)
check("Cloud LLM (1 API call)", cloud_llm)
print(f"\nResult: {passed} passed, {failed} failed")
