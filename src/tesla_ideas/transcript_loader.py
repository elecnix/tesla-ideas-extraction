"""Module for loading and filtering transcript files."""

import asyncio
import hashlib
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

def calculate_file_hash(file_path: Path) -> str:
    """Calculate SHA-256 hash of a file's content.
    
    Args:
        file_path: Path to the file
        
    Returns:
        str: SHA-256 hash of the file content
    """
    hasher = hashlib.sha256()
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(4096), b''):
            hasher.update(chunk)
    return hasher.hexdigest()

async def is_relevant_transcript(content: str, llm_client) -> Tuple[bool, str]:
    """Check if the transcript content is relevant using a two-step process.
    
    First checks for keywords, then verifies with LLM if keywords are found.
    
    Args:
        content: Transcript content as string
        llm_client: LLM client for relevance verification
        
    Returns:
        Tuple of (is_relevant, reason)
    """
    # First pass: quick keyword check
    keywords = ["tesla", "elon musk", "agile", "innovation", "gigafactory", "cybertruck"]
    content_lower = content.lower()
    
    if not any(keyword in content_lower for keyword in keywords):
        return False, "No relevant keywords found"
    
    # Second pass: LLM verification
    prompt = """
    Determine if this transcript is primarily about Agile at Tesla or Speed of Innovation.
    
    Transcript:
    {}
    
    Respond with a JSON object containing:
    - "relevant": boolean indicating if the transcript is relevant
    - "reason": brief explanation (1-2 sentences)
    """.format(content[:4000])  # Limit context length
    
    try:
        response = await llm_client._make_request(
            "POST",
            "/chat/completions",
            json={
                "model": llm_client.model,
                "messages": [{"role": "user", "content": prompt}],
                "response_format": {"type": "json_object"},
                "temperature": 0.1,
                "max_tokens": 200
            }
        )
        
        # Parse response
        result = json.loads(response['choices'][0]['message']['content'])
        return result.get('relevant', False), result.get('reason', 'No reason provided')
        
    except Exception as e:
        logging.warning(f"LLM relevance check failed: {str(e)}")
        # Fall back to keyword-only if LLM check fails
        return True, "Keyword match found but LLM verification failed"

async def load_transcript(file_path: Path, llm_client) -> Tuple[Optional[Dict], Optional[str]]:
    """Load and validate a transcript file with LLM-based relevance checking.
    
    Args:
        file_path: Path to the transcript file
        llm_client: LLM client for relevance checking
        
    Returns:
        Tuple containing (content_dict, error_message). content_dict contains the parsed content
        if successful, None otherwise. error_message is None if successful.
    """
    try:
        content = file_path.read_text(encoding='utf-8')
        
        # Check relevance
        is_relevant, reason = await is_relevant_transcript(content, llm_client)
        if not is_relevant:
            return None, f"Skipping non-relevant transcript ({reason}): {file_path}"
            
        # Calculate hash for caching
        file_hash = calculate_file_hash(file_path)
        
        return {
            'file_path': str(file_path),
            'content': content,
            'file_hash': file_hash,
            'file_name': file_path.name,
            'relevance_reason': reason
        }, None
        
    except Exception as e:
        return None, f"Error loading {file_path}: {str(e)}"

async def discover_transcripts(directory: str, llm_client, max_workers: int = 5) -> List[Dict]:
    """Discover and load all transcript files in the given directory with parallel processing.
    
    Args:
        directory: Path to directory containing transcript files
        llm_client: LLM client for relevance checking
        max_workers: Maximum number of concurrent transcript loads
        
    Returns:
        List of transcript dictionaries with content and metadata
    """
    directory_path = Path(directory)
    if not directory_path.exists() or not directory_path.is_dir():
        raise ValueError(f"Directory not found: {directory}")
    
    # Find all candidate files
    file_paths = []
    for ext in ['.txt', '.json']:
        file_paths.extend(list(directory_path.glob(f'**/*{ext}')))
    
    # Process files in parallel
    transcripts = []
    skipped = 0
    
    async def process_file(file_path):
        nonlocal skipped
        try:
            transcript, error = await load_transcript(file_path, llm_client)
            if error:
                logging.info(error)
                skipped += 1
                return None
            return transcript
        except Exception as e:
            logging.error(f"Error processing {file_path}: {str(e)}")
            skipped += 1
            return None
    
    # Process files in batches to limit concurrency
    for i in range(0, len(file_paths), max_workers):
        batch = file_paths[i:i + max_workers]
        tasks = [process_file(fp) for fp in batch]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for result in results:
            if isinstance(result, dict):
                transcripts.append(result)
    
    logging.info(f"Loaded {len(transcripts)} transcripts, skipped {skipped} files.")
    return transcripts
