import os
from dotenv import load_dotenv

# Read the .env file
load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")

# Backup models, tried in order if the main one is busy or unavailable.
# You can override this in .env with: GEMINI_FALLBACK_MODELS=model1,model2
GEMINI_FALLBACK_MODELS = [
    name.strip()
    for name in os.getenv(
        "GEMINI_FALLBACK_MODELS",
        "gemini-flash-lite-latest,gemini-3.5-flash,gemini-flash-latest",
    ).split(",")
    if name.strip()
]
