import os
from dotenv import load_dotenv
from google import genai

# Read the .env file so we can use the key
load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")

if not api_key or api_key == "your_key_here":
    print("ERROR: No real key found. Open .env and paste your key after GEMINI_API_KEY=")
    raise SystemExit(1)

model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
client = genai.Client(api_key=api_key)

try:
    response = client.models.generate_content(
        model=model,
        contents="In one short sentence, introduce yourself as JARVIS, a personal AI assistant.",
    )
    print("MODEL:", model)
    print("REPLY:", response.text)
except Exception as e:
    print("ERROR:", e)