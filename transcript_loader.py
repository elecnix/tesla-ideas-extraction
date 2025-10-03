import os
import json
from pathlib import Path
from typing import List
from utils import call_llm, logger

def load_transcript_content(file_path: Path) -> str:
    """
    Load content from a transcript file.
    Supports .txt, .json, .srt.
    For .json, assume it's a list of segments or direct text.
    """
    if file_path.suffix == '.txt':
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    elif file_path.suffix == '.json':
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            if isinstance(data, dict) and 'text' in data:
                return data['text']
            elif isinstance(data, list):
                # Assume list of dicts with 'text' or just strings
                return ' '.join(item.get('text', str(item)) for item in data)
            else:
                return str(data)
    elif file_path.suffix == '.srt':
        # Simple SRT parser: ignore timestamps, extract text
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            text_lines = [line.strip() for line in lines if not line.strip().isdigit() and '-->' not in line and line.strip()]
            return ' '.join(text_lines)
    else:
        raise ValueError(f"Unsupported file type: {file_path.suffix}")

def heuristic_filter(content: str) -> bool:
    """
    Heuristic filter for Tesla-related content.
    """
    keywords = ["Tesla", "Elon Musk", "Agile", "Innovation", "work environment", "company culture"]
    return any(keyword.lower() in content.lower() for keyword in keywords)

def llm_relevance_check(content: str) -> bool:
    """
    LLM check for relevance to Tesla operations and work environment.
    """
    prompt = f"""Is this transcript primarily about Tesla's work environment, including Agile at Tesla or Speed of Innovation at Tesla? Respond with a JSON object: {{"relevant": true/false, "reason": "brief reason"}}.

Transcript: {content[:2000]}..."""  # Truncate for context limit
    response = call_llm(prompt, structured=True)
    relevant = response.get('relevant', False)
    if not relevant:
        reason = response.get('reason', 'No reason provided')
        logger.info(f"Skipped transcript: {reason}")
    return relevant

def load_and_filter_transcripts(directory: str) -> List[Path]:
    """
    Load and filter transcripts from the directory.
    Prefer files with timestamps in basename.
    """
    dir_path = Path(directory)
    files = list(dir_path.glob("*.txt")) + list(dir_path.glob("*.json")) + list(dir_path.glob("*.srt"))
    
    # Group by basename (without extension)
    grouped = {}
    for f in files:
        base = f.stem
        if base not in grouped:
            grouped[base] = []
        grouped[base].append(f)
    
    # For each group, prefer the one with timestamp (assuming format like id-timestamp.ext)
    valid_files = []
    for base, file_list in grouped.items():
        # Sort by modification time descending (newer first), but since names have timestamps, maybe sort by name
        file_list.sort(key=lambda x: x.stat().st_mtime, reverse=True)
        chosen = file_list[0]  # Pick the first, assuming it's the latest
        valid_files.append(chosen)
    
    # Now filter each
    filtered = []
    for file_path in valid_files:
        try:
            content = load_transcript_content(file_path)
            if not content.strip():
                logger.info(f"Skipped empty transcript: {file_path}")
                continue
            if not heuristic_filter(content):
                logger.info(f"Skipped by heuristic: {file_path}")
                continue
            if llm_relevance_check(content):
                filtered.append(file_path)
                logger.info(f"Accepted transcript: {file_path}")
            else:
                logger.info(f"Skipped by LLM: {file_path}")
        except Exception as e:
            logger.error(f"Error loading {file_path}: {e}")
    
    return filtered
