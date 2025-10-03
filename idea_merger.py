import asyncio
import uuid
from typing import List, Dict, Any
from utils import call_llm, logger, parse_json_response, merged_ideas

merge_lock = asyncio.Lock()

async def merge_ideas_batch(anchors: List[Dict[str, Any]]):
    """Merge a batch of anchors into global merged ideas."""
    async with merge_lock:
        global merged_ideas
        for anchor in anchors:
            await merge_single_anchor(anchor)

async def merge_single_anchor(anchor: Dict[str, Any]):
    """Merge a single anchor."""
    global merged_ideas
    existing_str = '\n'.join([f"{id}: {data['description']}" for id, data in merged_ideas.items()])
    prompt = f"""Given this anchor idea: '{anchor['quote']}'.

And this list of existing ideas:
{existing_str}

Classify: Create a new idea, merge into existing ideas, or both. Output in JSON: {{"action": "new", "idea": "description"}} or {{"action": "merge", "merges": [{{"target_id": "id"}}]}} or {{"action": "both", "new_idea": "desc", "merges": [{{"target_id": "id"}}]}}."""
    response = await call_llm(prompt)
    try:
        action = await parse_json_response(response)
    except Exception as e:
        logger.error(f"Failed to parse merge response: {e}")
        action = {"action": "new", "idea": anchor['quote']}

    if action['action'] == 'new':
        new_id = str(uuid.uuid4())
        merged_ideas[new_id] = {
            "description": action.get('idea', anchor['quote']),
            "anchors": [anchor]
        }
    elif action['action'] == 'merge':
        for merge in action.get('merges', []):
            target_id = merge['target_id']
            if target_id in merged_ideas:
                merged_ideas[target_id]['anchors'].append(anchor)
    elif action['action'] == 'both':
        # Create new
        new_id = str(uuid.uuid4())
        merged_ideas[new_id] = {
            "description": action.get('new_idea', anchor['quote']),
            "anchors": [anchor]
        }
        # Merge
        for merge in action.get('merges', []):
            target_id = merge['target_id']
            if target_id in merged_ideas:
                merged_ideas[target_id]['anchors'].append(anchor)

    logger.info(f"Merged anchor: {anchor['id']} -> {action['action']}")
