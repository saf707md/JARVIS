import logging

from ddgs import DDGS

logger = logging.getLogger("jarvis")

NO_RESULTS = "I couldn't find any results right now. The search service may be busy."


def web_search(query: str) -> str:
    """Search the web for current or factual information.

    Use this for anything that may have changed recently or that you are not
    certain about: prices, people in current roles, products, events, facts.

    Args:
        query: What to search for, written like a search-engine query.
    """
    try:
        results = DDGS().text(query, max_results=5)
    except Exception as error:
        logger.error("[TOOL] Web search failed: %s", error)
        return "Error: I couldn't access the web service right now."

    if not results:
        return NO_RESULTS

    lines = []
    for item in results:
        title = item.get("title", "")
        body = (item.get("body") or "")[:250]
        url = item.get("href", "")
        lines.append(f"- {title}: {body} ({url})")
    return "\n".join(lines)


def news_search(query: str) -> str:
    """Search recent news articles. Use this for 'latest', 'recent' or 'news' questions.

    Args:
        query: The news topic, for example "generative AI".
    """
    try:
        results = DDGS().news(query=query, max_results=5)
    except Exception as error:
        logger.error("[TOOL] News search failed: %s", error)
        return "Error: I couldn't access the news service right now."

    if not results:
        return NO_RESULTS

    lines = []
    for item in results:
        title = item.get("title", "")
        body = (item.get("body") or "")[:250]
        source = item.get("source", "")
        date = (item.get("date") or "")[:10]
        lines.append(f"- [{date}] {title} ({source}): {body}")
    return "\n".join(lines)
