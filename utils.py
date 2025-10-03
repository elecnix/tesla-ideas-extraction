import os
import json
import logging
from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential
from dotenv import load_dotenv

load_dotenv()  # Load .env file

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Initialize OpenAI client for OpenRouter
client = OpenAI(
    api_key=os.getenv("OPENROUTER_API_KEY"),
    base_url="https://openrouter.ai/api/v1"
)

MODEL = "x-ai/grok-4-fast:free"

@retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=1, min=4, max=60))
def call_llm(prompt: str, structured: bool = False) -> dict:
    """
    Call the LLM with a prompt. If structured, expect JSON response.
    """
    try:
        response_format = {"type": "json_object"} if structured else None
        response = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            response_format=response_format,
            temperature=0.0  # For consistency
        )
        content = response.choices[0].message.content
        if structured:
            return json.loads(content)
        return content
    except Exception as e:
        logger.error(f"LLM call failed: {e}")
        raise
