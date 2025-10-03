"""Module for extracting ideas from transcripts using LLM."""

import asyncio
import json
import logging
import uuid
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .llm_utils import OpenRouterClient

class IdeaExtractor:
    """Extracts ideas from transcripts using LLM."""
    
    def __init__(self, cache_dir: Optional[str] = None, model: str = "x-ai/grok-4-fast:free"):
        """Initialize the idea extractor.
        
        Args:
            cache_dir: Directory to cache extracted ideas. If None, no caching is used.
            model: The LLM model to use for extraction.
        """
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self.model = model
        
        if self.cache_dir:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
    
    def _get_cache_path(self, file_hash: str) -> Optional[Path]:
        """Get the cache file path for a given transcript hash."""
        if not self.cache_dir:
            return None
        return self.cache_dir / f"{file_hash}.json"
    
    def _load_cached_ideas(self, file_hash: str) -> Optional[List[Dict]]:
        """Load cached ideas for a transcript with version checking.
        
        Returns:
            List of ideas if cache is valid, None otherwise
        """
        if not self.cache_dir:
            return None
            
        cache_file = self._get_cache_path(file_hash)
        if not cache_file or not cache_file.exists():
            return None
            
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)
            
            # Check cache version
            if not isinstance(cache_data, dict) or 'version' not in cache_data:
                logging.info(f"Old cache format found for {file_hash}, regenerating...")
                return None
                
            if cache_data['version'] != '3.0':  # Updated version for new format
                logging.info(f"Cache version mismatch for {file_hash}, regenerating...")
                return None
                
            ideas = cache_data.get('ideas', [])
            
            # Migrate old format to new format if needed
            migrated_ideas = []
            for idea in ideas:
                if 'content' in idea and 'quote' not in idea:
                    # Migrate from old format to new format
                    migrated_idea = {
                        'id': idea.get('id', str(uuid.uuid4())),
                        'quote': idea['content'],
                        'speaker': None,
                        'timestamp': None,
                        'context': '',
                        'tags': [],
                        'source_file': idea.get('sources', [{}])[0].get('file_name'),
                        'sources': idea.get('sources', [])
                    }
                    migrated_ideas.append(migrated_idea)
                else:
                    migrated_ideas.append(idea)
                    
            return migrated_ideas
            
        except (json.JSONDecodeError, IOError, AttributeError) as e:
            logging.warning(f"Failed to load cache file {cache_file}: {e}")
            return None
    
    def _save_ideas_to_cache(self, file_hash: str, ideas: List[Dict]) -> None:
        """Save extracted ideas to cache with versioning."""
        if not self.cache_dir:
            return
            
        cache_file = self._get_cache_path(file_hash)
        try:
            cache_data = {
                'version': '3.0',  # Updated version for new format
                'extracted_at': self._get_current_timestamp(),
                'ideas': ideas
            }
            
            # Ensure directory exists
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            
            # Write with atomic replacement
            temp_file = cache_file.with_suffix('.tmp')
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, indent=2, ensure_ascii=False)
            temp_file.replace(cache_file)  # Atomic replace
            
        except Exception as e:
            logging.warning(f"Failed to save cache file {cache_file}: {e}")
            # Clean up temp file if it exists
            if 'temp_file' in locals() and temp_file.exists():
                try:
                    temp_file.unlink()
                except (OSError, PermissionError) as unlink_error:
                    logging.warning(f"Failed to clean up temp file {temp_file}: {unlink_error}")
    
    async def _extract_ideas_from_content(
        self, 
        transcript_content: str, 
        file_metadata: Dict
    ) -> List[Dict]:
        """Extract ideas from transcript content using LLM with iterative extraction.
        
        Implements an iterative loop to extract ideas until no new unique ideas are found
        or a maximum number of iterations is reached.
        """
        max_iterations = 5
        min_ideas = 15
        all_ideas = []
        seen_ideas = set()
        
        async with OpenRouterClient(model=self.model) as llm:
            for iteration in range(max_iterations):
                # Prepare the prompt with current ideas to avoid duplicates
                previous_ideas = "\n".join(f"- {idea['quote']}" for idea in all_ideas)
                
                # Build the prompt with proper string formatting
                prompt_parts = [
                    "Extract unique ideas about Agile at Tesla or Speed of Innovation from this transcript.",
                    "For each idea, include the following information:",
                    "1. The exact quote (quote)",
                    "2. Speaker if available (speaker)",
                    "3. Timestamp if available (timestamp)",
                    "4. The surrounding context (context)",
                    "5. Relevant tags (tags) from: agile, innovation, tesla, engineering, management, culture, productivity",
                    "",
                    "Transcript (truncated if too long):",
                    transcript_content,
                    ""
                ]
                
                if all_ideas:
                    prompt_parts.extend([
                        "Already extracted ideas (do not repeat these):",
                        previous_ideas,
                        ""
                    ])
                    
                prompt_parts.extend([
                    "Extract only new, unique ideas not already listed above.",
                    "Format the response as a JSON array of objects, with each object containing:",
                    "{\n  \"quote\": \"exact quote\",\n  \"speaker\": \"speaker name or null\",\n  \"timestamp\": \"HH:MM:SS or null\",\n  \"context\": \"surrounding sentences\",\n  \"tags\": [\"tag1\", \"tag2\"]\n}"
                ])
                
                prompt = "\n".join(p.strip() for p in prompt_parts)
                
                # Get new ideas from LLM
                try:
                    idea_texts = await llm._make_request(
                        "POST",
                        "/chat/completions",
                        json={
                            "model": self.model,
                            "messages": [{"role": "user", "content": prompt}],
                            "response_format": {"type": "json_object"},
                            "temperature": 0.7,
                            "max_tokens": 2000
                        }
                    )
                    
                    # Parse response
                    content = idea_texts['choices'][0]['message']['content']
                    try:
                        result = json.loads(content)
                        if isinstance(result, dict) and 'ideas' in result and isinstance(result['ideas'], list):
                            new_ideas = [idea for idea in result['ideas'] if isinstance(idea, dict) and 'quote' in idea]
                        elif isinstance(result, list):
                            new_ideas = [idea for idea in result if isinstance(idea, dict) and 'quote' in idea]
                        else:
                            new_ideas = []
                    except (json.JSONDecodeError, AttributeError, TypeError) as e:
                        logging.warning(f"Failed to parse LLM response: {e}\nContent: {content}")
                        new_ideas = []
                    
                    # Add only truly new ideas
                    added_count = 0
                    for idea_data in new_ideas:
                        quote = idea_data.get('quote', '').strip()
                        if not quote:
                            continue
                            
                        # Simple deduplication
                        normalized = quote.lower().strip()
                        if normalized not in seen_ideas and len(normalized) > 10:  # Minimum length
                            idea_id = str(uuid.uuid4())
                            idea = {
                                'id': idea_id,
                                'quote': quote,
                                'speaker': idea_data.get('speaker'),
                                'timestamp': idea_data.get('timestamp'),
                                'context': idea_data.get('context', ''),
                                'tags': idea_data.get('tags', []),
                                'source_file': file_metadata.get('file_name'),
                                'sources': [{
                                    'file_path': file_metadata.get('file_path'),
                                    'file_name': file_metadata.get('file_name'),
                                    'file_hash': file_metadata.get('file_hash'),
                                    'extracted_at': file_metadata.get('processed_at'),
                                    'extraction_iteration': iteration + 1
                                }]
                            }
                            
                            # Ensure tags is a list
                            if not isinstance(idea['tags'], list):
                                idea['tags'] = [tag.strip() for tag in str(idea['tags']).split(',') if tag.strip()]
                            
                            all_ideas.append(idea)
                            seen_ideas.add(normalized)
                            added_count += 1
                    
                    logging.info(f"Iteration {iteration + 1}: Added {added_count} new ideas")
                    
                    # Stop if we're not finding many new ideas or have enough
                    if (added_count <= 1 and len(all_ideas) >= 3) or len(all_ideas) >= min_ideas:
                        break
                        
                except Exception as e:
                    logging.error(f"Error in extraction iteration {iteration + 1}: {str(e)}", exc_info=True)
                    if iteration == 0:
                        raise  # Only fail if first iteration fails
                    break
        
        logging.info(f"Extracted {len(all_ideas)} total ideas from transcript")
        return all_ideas
    
    async def extract_ideas_from_transcript(
        self, 
        transcript: Dict
    ) -> Tuple[List[Dict], List[str]]:
        """Extract ideas from a single transcript.
        
        Args:
            transcript: Transcript dictionary with 'content' and 'file_hash' keys.
            
        Returns:
            Tuple of (extracted_ideas, error_messages)
        """
        file_hash = transcript.get('file_hash')
        if not file_hash:
            return [], ["Transcript missing file_hash"]
        
        # Check cache first
        cached_ideas = self._load_cached_ideas(file_hash)
        if cached_ideas is not None:
            return cached_ideas, []
        
        # Add processing timestamp
        transcript['processed_at'] = self._get_current_timestamp()
        
        try:
            # Extract ideas using LLM
            ideas = await self._extract_ideas_from_content(
                transcript['content'],
                transcript
            )
            
            # Cache the results
            if self.cache_dir:
                self._save_ideas_to_cache(file_hash, ideas)
            
            return ideas, []
            
        except Exception as e:
            error_msg = f"Error extracting ideas from {transcript.get('file_name', 'unknown')}: {str(e)}"
            logging.error(error_msg, exc_info=True)
            return [], [error_msg]
    
    async def extract_ideas_from_transcripts(
        self, 
        transcripts: List[Dict],
        max_concurrent: int = 5
    ) -> Tuple[List[Dict], List[str]]:
        """Extract ideas from multiple transcripts in parallel.
        
        Args:
            transcripts: List of transcript dictionaries.
            max_concurrent: Maximum number of concurrent extractions.
            
        Returns:
            Tuple of (all_extracted_ideas, all_errors)
        """
        all_ideas = []
        all_errors = []
        
        # Process transcripts in batches to control concurrency
        for i in range(0, len(transcripts), max_concurrent):
            batch = transcripts[i:i + max_concurrent]
            
            # Create tasks for the current batch
            tasks = [
                self.extract_ideas_from_transcript(transcript)
                for transcript in batch
            ]
            
            # Run tasks concurrently
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Process results
            for result in results:
                if isinstance(result, Exception):
                    all_errors.append(str(result))
                    continue
                    
                ideas, errors = result
                all_ideas.extend(ideas)
                all_errors.extend(errors)
        
        return all_ideas, all_errors
    
    @staticmethod
    def _get_current_timestamp() -> str:
        """Get current timestamp in ISO format."""
        from datetime import datetime
        return datetime.utcnow().isoformat() + "Z"
