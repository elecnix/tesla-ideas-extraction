import os
import hashlib
import json
import logging
import asyncio
from typing import Dict, Any, Optional
from openai import AsyncOpenAI
from dotenv import load_dotenv

load_dotenv()

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# LLM client
client = AsyncOpenAI(
    api_key=os.getenv("OPENROUTER_API_KEY"),
    base_url="https://openrouter.ai/api/v1",
)

MODEL = "x-ai/grok-4-fast:free"

async def call_llm(prompt: str, max_tokens: int = 1000, temperature: float = 0.0) -> str:
    """Call the LLM with retry logic."""
    for attempt in range(10):  # Infinite retries as per spec
        try:
            response = await client.chat.completions.create(
                model=MODEL,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                temperature=temperature,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.warning(f"LLM call failed (attempt {attempt + 1}): {e}")
            await asyncio.sleep(2 ** attempt)  # Exponential backoff
    raise Exception("LLM call failed after all retries")

def get_content_hash(content: str) -> str:
    """Get hash of content for caching."""
    return hashlib.sha256(content.encode()).hexdigest()

def load_cache(cache_file: str) -> Optional[Dict[str, Any]]:
    """Load cache from JSON file."""
    if os.path.exists(cache_file):
        with open(cache_file, 'r') as f:
            return json.load(f)
    return None

def save_cache(cache_file: str, data: Dict[str, Any]):
    """Save cache to JSON file."""
    os.makedirs(os.path.dirname(cache_file), exist_ok=True)
    with open(cache_file, 'w') as f:
        json.dump(data, f, indent=2)

async def parse_json_response(response: str) -> Dict[str, Any]:
    """Parse JSON response from LLM."""
    try:
        # Remove any markdown formatting if present
        response = response.strip()
        if response.startswith('```json'):
            response = response[7:]
        if response.endswith('```'):
            response = response[:-3]
        return json.loads(response.strip())
    except json.JSONDecodeError:
        logger.error(f"Failed to parse JSON response: {response}")
        raise

# Global merged ideas list
merged_ideas: Dict[str, Dict[str, Any]] = {}
