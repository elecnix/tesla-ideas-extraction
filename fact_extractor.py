import hashlib
import json
import uuid
from pathlib import Path
from typing import List, Dict, Any
from utils import call_llm, logger

def hash_content(content: str) -> str:
    """Hash the transcript content for caching."""
    return hashlib.sha256(content.encode('utf-8')).hexdigest()

def load_cached_facts(transcript_path: Path, content_hash: str) -> List[Dict]:
    """Load cached facts for a transcript."""
    cache_dir = Path("cache")
    cache_dir.mkdir(exist_ok=True)
    cache_file = cache_dir / f"{transcript_path.stem}_{content_hash}.json"
    if cache_file.exists():
        with open(cache_file, 'r') as f:
            return json.load(f)
    return []

def save_cached_facts(transcript_path: Path, content_hash: str, facts: List[Dict]):
    """Save facts to cache."""
    cache_dir = Path("cache")
    cache_dir.mkdir(exist_ok=True)
    cache_file = cache_dir / f"{transcript_path.stem}_{content_hash}.json"
    with open(cache_file, 'w') as f:
        json.dump(facts, f, indent=2)

def extract_facts_from_transcript(transcript_path: Path, content: str) -> List[Dict]:
    """
    Extract facts from a single transcript.
    Use caching to avoid reprocessing.
    """
    content_hash = hash_content(content)
    cached = load_cached_facts(transcript_path, content_hash)
    if cached:
        logger.info(f"Loaded cached facts for {transcript_path}")
        return cached
    
    facts = []
    iteration = 0
    max_iterations = 10  # Safety limit
    min_new_facts = 1  # Stop if less than this
    
    while len(facts) < 15 and iteration < max_iterations:
        existing_facts_str = json.dumps([f['one_liner'] for f in facts])
        prompt = f"""Given this transcript: '{content[:4000]}...'  # Truncate for context

And this current list of extracted facts: {existing_facts_str}

Extract any additional unique facts not already in the list about Tesla's work environment, including Agile at Tesla or Speed of Innovation at Tesla. For each fact, provide a 2-4 sentence passage that includes context and narrative flow, suitable for book material. Include full quotes, examples, and surrounding context. If no additional facts can be identified, return an empty list.

Respond with a JSON array of objects, each with 'passage'.

Example: [{"passage": "Full quote here."}]"""
        
        response = call_llm(prompt, structured=True)
        new_facts_data = response if isinstance(response, list) else []
        
        new_facts = []
        for item in new_facts_data:
            if 'passage' in item:
                fact = {
                    "id": str(uuid.uuid4()),
                    "one_liner": item['passage'][:100] + "...",  # Approximate
                    "quote": item['passage'],
                    "speaker": "",  # To be filled if available
                    "timestamp": "",  # To be filled
                    "source_file": str(transcript_path),
                    "context": "",  # To be filled
                    "tags": ["tesla", "agile", "innovation"],  # Placeholder
                    "key_metrics": [],  # Placeholder
                    "themes": ["leadership"],  # Placeholder
                    "narrative_potential": "",  # Placeholder
                    "example_type": "success_story",  # Placeholder
                    "related_ideas": []  # Placeholder
                }
                new_facts.append(fact)
        
        facts.extend(new_facts)
        logger.info(f"Iteration {iteration}: added {len(new_facts)} facts, total {len(facts)}")
        
        if len(new_facts) <= min_new_facts:
            break
        iteration += 1
    
    # Here we could enrich with more details, but for now, save as is
    save_cached_facts(transcript_path, content_hash, facts)
    return facts
