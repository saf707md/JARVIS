import logging
import re
import webbrowser

logger = logging.getLogger("jarvis")

# Friendly names the AI can use. Add more any time.
KNOWN_SITES = {
    "youtube": "https://www.youtube.com",
    "google": "https://www.google.com",
    "gmail": "https://mail.google.com",
    "google drive": "https://drive.google.com",
    "github": "https://github.com",
    "linkedin": "https://www.linkedin.com",
    "wikipedia": "https://www.wikipedia.org",
    "google maps": "https://maps.google.com",
    "google gemini": "https://gemini.google.com",
}


def open_website(site: str) -> str:
    """Open a website in the user's default web browser.

    Args:
        site: A well-known site name such as "youtube", or a web address such as "example.com".
    """
    cleaned = site.strip()
    name = cleaned.lower()

    if name in KNOWN_SITES:
        url = KNOWN_SITES[name]
    else:
        candidate = cleaned
        if not re.match(r"^https?://", candidate, re.IGNORECASE):
            # Accept plain domains like example.com, nothing else
            if re.match(r"^[\w-]+(\.[\w-]+)+(/\S*)?$", candidate):
                candidate = "https://" + candidate
            else:
                return f"Error: I don't know a website called '{site}'."
        url = candidate

    logger.info("[TOOL] Opening website %s", url)
    webbrowser.open(url)
    return f"Opened {url}"
