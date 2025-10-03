import os
import json
from typing import List, Tuple
from utils import call_llm, logger, parse_json_response

def load_transcript(file_path: str) -> str:
    """Load transcript content from file."""
    if file_path.endswith('.txt'):
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    elif file_path.endswith('.json'):
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            # Assume JSON structure has 'text' or similar; adjust if needed
            if 'text' in data:
                return data['text']
            elif 'segments' in data:
                return ' '.join([seg.get('text', '') for seg in data['segments']])
            else:
                # Fallback to stringifying
                return json.dumps(data)
    elif file_path.endswith('.srt'):
        # Parse SRT format
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        # Simple SRT parsing: remove timestamps
        lines = content.split('\n')
        text_lines = [line for line in lines if not line.isdigit() and '-->' not in line and line.strip()]
        return ' '.join(text_lines)
    else:
        raise ValueError(f"Unsupported file type: {file_path}")

def heuristic_filter(content: str) -> bool:
    """Heuristic filter for Tesla-related content."""
    keywords = ["Tesla", "Elon Musk", "Agile", "Innovation", "Speed of Innovation"]
    return any(keyword.lower() in content.lower() for keyword in keywords)

async def llm_relevance_check(content: str) -> Tuple[bool, str]:
    """LLM-based relevance check."""
    prompt = f"""Is this transcript primarily about Agile or Speed of Innovation? Respond with a JSON object: {{"relevant": true/false, "reason": "brief explanation"}}.

Transcript: {content[:2000]}..."""  # Truncate for context
    response = await call_llm(prompt)
    parsed = await parse_json_response(response)
    return parsed.get('relevant', False), parsed.get('reason', 'No reason')

def get_transcript_files(directory: str) -> List[str]:
    """Get list of transcript files, preferring those with timestamps."""
    files = []
    for file in os.listdir(directory):
        if file.endswith(('.txt', '.json', '.srt')) and not file.startswith('.'):
            files.append(os.path.join(directory, file))
    # Sort by modification time, newest first (prefer "timestamps")
    files.sort(key=lambda x: os.path.getmtime(x), reverse=True)
    return files

async def filter_transcripts(directory: str) -> List[Tuple[str, str]]:
    """Load and filter transcripts."""
    valid_transcripts = []
    files = get_transcript_files(directory)
    for file_path in files:
        try:
            content = load_transcript(file_path)
            if not heuristic_filter(content):
                logger.info(f"Skipped {file_path}: heuristic filter")
                continue
            relevant, reason = await llm_relevance_check(content)
            if relevant:
                valid_transcripts.append((file_path, content))
                logger.info(f"Accepted {file_path}")
            else:
                logger.info(f"Skipped {file_path}: {reason}")
        except Exception as e:
            logger.error(f"Error processing {file_path}: {e}")
    return valid_transcripts
