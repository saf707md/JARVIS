import logging
import re
import webbrowser
from urllib.parse import quote

logger = logging.getLogger("jarvis")

# Approved sites and their search addresses. {q} is replaced with the encoded search words.
SEARCH_SITES = {
    "youtube": "https://www.youtube.com/results?search_query={q}",
    "google": "https://www.google.com/search?q={q}",
    "google images": "https://www.google.com/search?tbm=isch&q={q}",
    "google maps": "https://www.google.com/maps/search/{q}",
    "wikipedia": "https://en.wikipedia.org/w/index.php?search={q}",
    "github": "https://github.com/search?q={q}",
    "stack overflow": "https://stackoverflow.com/search?q={q}",
    "reddit": "https://www.reddit.com/search/?q={q}",
    "spotify": "https://open.spotify.com/search/{q}",
    "google scholar": "https://scholar.google.com/scholar?q={q}",
}

ALIASES = {
    "yt": "youtube", "you tube": "youtube", "maps": "google maps", "wiki": "wikipedia",
    "stackoverflow": "stack overflow", "images": "google images", "scholar": "google scholar",
}

# YouTube's own result-type filters
YOUTUBE_FILTERS = {
    "video": "EgIQAQ%3D%3D",
    "channel": "EgIQAg%3D%3D",
    "playlist": "EgIQAw%3D%3D",
}


def search_on_site(site: str, query: str, search_type: str = "any") -> str:
    """Open a website's search results page for a query in the user's browser.

    Use this for requests like "open YouTube and search for X" or "search
    Wikipedia for Y". Supported sites: youtube, google, google images, google
    maps, wikipedia, github, stack overflow, reddit, spotify, google scholar.

    Args:
        site: The site to search, for example "youtube".
        query: The words to search for, without words like "channel" or "search".
        search_type: Only for YouTube: "channel" for channels, "playlist" for playlists, "video" for videos, otherwise "any".
    """
    name = site.strip().lower()
    name = ALIASES.get(name, name)
    template = SEARCH_SITES.get(name)
    if template is None:
        return f"Error: I can't search '{site}'. I can search: {', '.join(sorted(SEARCH_SITES))}."

    cleaned = re.sub(r"[\x00-\x1f]", " ", query).strip()[:200]
    if not cleaned:
        return "Error: please tell me what to search for."

    url = template.replace("{q}", quote(cleaned, safe=""))
    kind = search_type.strip().lower()
    if name == "youtube" and kind in YOUTUBE_FILTERS:
        url += "&sp=" + YOUTUBE_FILTERS[kind]

    logger.info("[TOOL] Opening %s search: %s", name, cleaned)
    webbrowser.open(url)
    label = f"{kind} " if name == "youtube" and kind in YOUTUBE_FILTERS else ""
    return (
        f"Opened {name} {label}search results for '{cleaned}'. "
        "(I only open the results page; I can't click or play anything.)"
    )
