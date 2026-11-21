"""Shared test setup: a throw-away database, and light stand-ins for modules that need
Windows, a microphone, the cloud or heavy libraries. The real code under test is untouched."""
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _stub(name, **functions):
    module = types.ModuleType(name)
    for attr, value in functions.items():
        setattr(module, attr, value)
    sys.modules[name] = module


_ok = lambda *a, **k: "ok"  # noqa: E731
_stub("rag.retriever", read_knowledge_document=_ok, reindex_documents=_ok, search_documents=_ok)
_stub("tools.vision", analyze_screen=_ok)
_stub("tools.web_search", web_search=_ok, news_search=_ok)
_stub("tools.screenshot", take_screenshot=_ok)


@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    import memory.database as database
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "jarvis_test.db")
    yield


@pytest.fixture
def fake_desktop(monkeypatch):
    """Replace actions that touch Windows with recorders, and return the record."""
    import tools.registry as registry
    from core import actions

    opened, performed = [], []

    def open_application(app_name: str) -> str:
        opened.append(("app", app_name))
        return f"Opened {app_name}."

    def open_folder(folder_name: str) -> str:
        opened.append(("folder", folder_name))
        return f"Opened the {folder_name} folder."

    def open_website(site: str) -> str:
        opened.append(("site", site))
        return f"Opened https://{site}"

    def search_on_site(site: str, query: str, search_type: str = "any") -> str:
        opened.append(("search", site, query))
        return f"Searched {site} for {query}"

    for name, function in [("open_application", open_application), ("open_folder", open_folder),
                           ("open_website", open_website), ("search_on_site", search_on_site)]:
        monkeypatch.setitem(registry._TOOLS, name, (function, 1))
    monkeypatch.setattr(actions, "_is_running", lambda process: False)
    monkeypatch.setattr(actions, "_perform", lambda undo: performed.append(undo) or f"did {undo['type']}")
    return {"opened": opened, "performed": performed}
