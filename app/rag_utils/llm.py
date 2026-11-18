"""Shared Groq configuration for the whole app.

Set GROQ_API_KEY in the project's .env file. GROQ_MODEL is optional.
"""
import os

from dotenv import load_dotenv
from groq import Groq

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

if not GROQ_API_KEY:
    raise RuntimeError("GROQ_API_KEY is not set. Add it to the .env file in the project root.")

client = Groq(api_key=GROQ_API_KEY)


def chat_completion(prompt: str, temperature: float = 0) -> str:
    """Send a single user prompt to Groq and return the reply text."""
    response = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature,
    )
    return response.choices[0].message.content.strip()
