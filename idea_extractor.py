# import asyncio
import logging
import json
import uuid
from typing import List, Dict

async def extract_ideas(transcript: Dict, model: str, cache: Dict) -> List[Dict]:
    file_path = transcript['file_path']
    content_hash = hash(transcript['content'])
    cache_key = f'extracted_ideas_{file_path}_{content_hash}'
    if cache_key in cache:
        logging.info(f'Using cached ideas for {file_path}')
        return cache[cache_key]

    ideas = []
    iteration = 0
    while True:
        iteration += 1
        new_ideas = await extract_ideas_iteration(transcript['content'], ideas, model)
        ideas.extend(new_ideas)
        logging.info(f'Iteration {iteration} for {file_path}: Found {len(new_ideas)} new ideas')
        if len(new_ideas) <= 1 or len(ideas) >= 15:
            break

    detailed_ideas = []
    for idea in ideas:
        idea_id = str(uuid.uuid4())
        detailed_idea = {
            'id': idea_id,
            'description': idea,
            'source_file': transcript['file_name'],
            'context': get_context(transcript['content'], idea),
            'tags': extract_tags(idea),
            'timestamp': extract_timestamp(transcript['content'], idea)
        }
        detailed_ideas.append(detailed_idea)

    cache[cache_key] = detailed_ideas
    logging.info(f'Extracted {len(detailed_ideas)} ideas from {file_path}')
    return detailed_ideas

async def extract_ideas_iteration(content: str, current_ideas: List[str], model: str) -> List[str]:
    from utils import make_llm_call
    current_ideas_str = json.dumps(current_ideas) if current_ideas else '[]'
    prompt = f"Given this transcript: '{content}'. And this current list of ideas: {current_ideas_str}. Extract any additional unique ideas not already in the list about innovative concepts, strategies, or practices related to Tesla. Describe each idea in a single line. If no additional ideas can be identified, return an empty list."
    response = await make_llm_call(prompt, model, structured=True)
    logging.info(f'Raw LLM response for idea extraction: {response[:1000]}... (truncated if long)')
    if not response:
        logging.error('Empty response received from LLM for idea extraction')
        return []
    try:
        new_ideas = json.loads(response)
        if isinstance(new_ideas, list):
            logging.info(f'Successfully parsed {len(new_ideas)} new ideas from LLM response')
            return new_ideas
        else:
            logging.error(f'LLM response is not a list: {type(new_ideas)}')
            return []
    except json.JSONDecodeError as e:
        logging.error(f'Failed to parse LLM response for idea extraction: {str(e)}, response: {response[:1000]}... (truncated if long)')
        return []

def get_context(content: str, idea: str) -> str:
    lines = content.split('\n')
    for i, line in enumerate(lines):
        if idea in line:
            start = max(0, i - 2)
            end = min(len(lines), i + 3)
            return ' '.join(lines[start:end])
    return ''

def extract_tags(idea: str) -> List[str]:
    tags = []
    if 'agile' in idea.lower():
        tags.append('agile')
    if 'innovation' in idea.lower():
        tags.append('innovation')
    if 'tesla' in idea.lower():
        tags.append('tesla')
    return tags

def extract_timestamp(content: str, idea: str) -> str:
    # Placeholder for timestamp extraction logic
    return '00:00:00'
