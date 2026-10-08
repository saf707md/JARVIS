import logging

import requests

logger = logging.getLogger("jarvis")

# Open-Meteo weather codes -> plain English
WEATHER_CODES = {
    0: "clear sky", 1: "mainly clear", 2: "partly cloudy", 3: "overcast",
    45: "foggy", 48: "foggy", 51: "light drizzle", 53: "drizzle", 55: "heavy drizzle",
    61: "light rain", 63: "rain", 65: "heavy rain", 71: "light snow", 73: "snow",
    75: "heavy snow", 80: "light showers", 81: "showers", 82: "heavy showers",
    95: "thunderstorm", 96: "thunderstorm with hail", 99: "thunderstorm with hail",
}


def get_weather(city: str) -> str:
    """Get the current weather for a city.

    Args:
        city: The name of the city, for example "London" or "Mumbai".
    """
    try:
        geo = requests.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": city, "count": 1, "language": "en", "format": "json"},
            timeout=10,
        )
        geo.raise_for_status()
        results = geo.json().get("results")
        if not results:
            return f"Error: I couldn't find a place called '{city}'."
        place = results[0]

        weather = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": place["latitude"],
                "longitude": place["longitude"],
                "current": "temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,wind_speed_10m",
                "timezone": "auto",
            },
            timeout=10,
        )
        weather.raise_for_status()
        current = weather.json()["current"]

        description = WEATHER_CODES.get(current.get("weather_code"), "unknown conditions")
        return (
            f"{place['name']}, {place.get('country', '')}: {description}, "
            f"{current['temperature_2m']} degrees Celsius "
            f"(feels like {current['apparent_temperature']}), "
            f"humidity {current['relative_humidity_2m']} percent, "
            f"wind {current['wind_speed_10m']} km/h."
        )
    except requests.RequestException as error:
        logger.error("[TOOL] Weather request failed: %s", error)
        return "Error: I couldn't reach the weather service right now."
