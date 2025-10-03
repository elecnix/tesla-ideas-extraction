import json
import uuid
from typing import List, Dict, Any
from utils import call_llm, logger

def merge_facts(all_facts: List[Dict]) -> List[Dict]:
    """
    Merge facts into a unified list.
    Use anchor-based classification.
    """
    merged_facts = []  # List of merged fact groups, but since standalone, perhaps list of facts with links
    
    for anchor in all_facts:
        # For simplicity, batch anchors, but here process one by one for now
        existing_ids = [f['id'] for f in merged_facts]
        existing_descriptions = [f.get('quote', f['one_liner']) for f in merged_facts]
        
        prompt = f"""Given this anchor fact: '{anchor['quote']}' (ID: {anchor['id']})

And this list of existing facts: {json.dumps([{'id': mid, 'description': desc} for mid, desc in zip(existing_ids, existing_descriptions)])}

Classify: Create a new fact, merge into existing facts, or both. Also, identify any thematic connections, contradictions, or evolutionary patterns.

Respond with JSON: {"action": "new|merge|both", "new_fact": "...", "merges": [{"target_id": "id", "synthesis": "..."}]}

If merge, reference by ID."""
        
        response = call_llm(prompt, structured=True)
        action = response.get('action', 'new')
        
        if action == 'new':
            merged_facts.append(anchor)
        elif action == 'merge':
            for merge in response.get('merges', []):
                target_id = merge['target_id']
                # Find target and append anchor to it, e.g., add to related_ideas or something
                for fact in merged_facts:
                    if fact['id'] == target_id:
                        fact['related_ideas'].append(anchor['id'])
                        # Perhaps update other fields, but keep standalone
                        break
        elif action == 'both':
            # Add new fact
            new_fact = response.get('new_fact', anchor['quote'])
            new_anchor = anchor.copy()
            new_anchor['quote'] = new_fact
            new_anchor['id'] = str(uuid.uuid4())  # Need import
            merged_facts.append(new_anchor)
            # And merge
            for merge in response.get('merges', []):
                target_id = merge['target_id']
                for fact in merged_facts:
                    if fact['id'] == target_id:
                        fact['related_ideas'].append(anchor['id'])
                        break
        
        logger.info(f"Processed anchor {anchor['id']}: {action}")
    
    return merged_facts
