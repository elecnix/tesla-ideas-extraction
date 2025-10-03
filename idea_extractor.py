import uuid
from typing import List, Dict, Any
from utils import call_llm, logger, parse_json_response, get_content_hash, load_cache, save_cache
import os

CACHE_DIR = 'cache/ideas'

async def extract_ideas(transcript_content: str, source_file: str) -> List[Dict[str, Any]]:
    """Extract ideas from a single transcript."""
    cache_key = get_content_hash(transcript_content)
    cache_file = os.path.join(CACHE_DIR, f"{cache_key}.json")
    cache = load_cache(cache_file)
    if cache:
        logger.info(f"Loaded cached ideas for {source_file}")
        return cache['ideas']

    ideas = []
    iteration = 0
    while len(ideas) < 15:
        current_ideas_str = '\n'.join([f"- {idea}" for idea in ideas])
        prompt = f"""Given this transcript: '{transcript_content[:4000]}...'  # Truncate for context

And this current list of extracted ideas:
{current_ideas_str}

Extract any additional unique ideas not already in the list about Agile or Speed of Innovation. Describe each idea in a single line. If no additional ideas can be identified, return an empty list.

Respond with a JSON array of strings, e.g., ["idea1", "idea2"]."""
        response = await call_llm(prompt)
        try:
            new_ideas = await parse_json_response(response)
            if not isinstance(new_ideas, list):
                new_ideas = []
        except Exception as e:
            logger.error(f"Failed to parse extraction response: {e}")
            new_ideas = []
        if len(new_ideas) <= 1:
            break
        ideas.extend(new_ideas)
        iteration += 1
        if iteration > 10:  # Safety
            break

    # Assign UUIDs and details
    detailed_ideas = []
    for idea in ideas:
        detailed_ideas.append({
            "id": str(uuid.uuid4()),
            "quote": idea,
            "speaker": None,  # Not available
            "timestamp": None,
            "source_file": source_file,
            "context": "",  # Placeholder
            "tags": ["agile", "innovation", "tesla"]  # Auto-generated
        })

    # Cache
    save_cache(cache_file, {"ideas": detailed_ideas, "version": "1.0"})

    logger.info(f"Extracted {len(detailed_ideas)} ideas from {source_file}")
    return detailed_ideas
