"""Utilities for interacting with LLM APIs."""

import json
import logging
import os
import time
from typing import Any, Dict, List, Optional, Union
import httpx
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class LLMError(Exception):
    """Custom exception for LLM-related errors."""
    pass

class OpenRouterClient:
    """Client for interacting with OpenRouter API."""
    
    BASE_URL = "https://openrouter.ai/api/v1"
    
    def __init__(self, api_key: Optional[str] = None, model: str = "x-ai/grok-4-fast:free"):
        """Initialize the OpenRouter client.
        
        Args:
            api_key: OpenRouter API key. If not provided, will try to get from OPENROUTER_API_KEY env var.
            model: Model to use for completions.
        """
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY")
        if not self.api_key:
            raise ValueError("OpenRouter API key not provided and OPENROUTER_API_KEY not set in environment")
        
        self.model = model
        self.client = httpx.AsyncClient(
            base_url=self.BASE_URL,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://github.com/yourusername/tesla-ideas",
                "X-Title": "Tesla Ideas Extractor"
            },
            timeout=60.0
        )
        
        # Rate limiting and retry settings
        self.max_retries = 5
        self.initial_delay = 1.0
        self.max_delay = 60.0
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
    
    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()
    
    async def _make_request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        """Make an HTTP request with retry logic."""
        delay = self.initial_delay
        last_error = None
        
        for attempt in range(self.max_retries):
            try:
                response = await self.client.request(method, endpoint, **kwargs)
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:  # Rate limited
                    retry_after = float(e.response.headers.get('retry-after', delay))
                    logging.warning(f"Rate limited. Retrying after {retry_after} seconds...")
                    await asyncio.sleep(retry_after)
                    continue
                last_error = f"HTTP error: {e.response.status_code} - {e.response.text}"
            except (httpx.RequestError, json.JSONDecodeError) as e:
                last_error = str(e)
            
            if attempt < self.max_retries - 1:
                await asyncio.sleep(delay)
                delay = min(delay * 2, self.max_delay)
        
        raise LLMError(f"Failed after {self.max_retries} attempts. Last error: {last_error}")
    
    async def extract_ideas(self, transcript_content: str) -> List[str]:
        """Extract ideas from a transcript.
        
        Args:
            transcript_content: The content of the transcript.
            
        Returns:
            List of extracted ideas as strings.
        """
        prompt = f"""Extract all unique ideas from this transcript about Agile at Tesla or Speed of Innovation at Tesla. 
Describe each idea in a single line. Ignore unrelated content.

Transcript:
{transcript_content}

Format the response as a JSON array of strings, one per idea."""
        
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "response_format": {"type": "json_object"},
            "max_tokens": 2000
        }
        
        try:
            response = await self._make_request("POST", "/chat/completions", json=payload)
            
            # Extract the content from the response
            content = response['choices'][0]['message']['content']
            
            # Parse the JSON content
            try:
                result = json.loads(content)
                if isinstance(result, dict):
                    # If the model returns an object with an 'ideas' key
                    if 'ideas' in result and isinstance(result['ideas'], list):
                        return result['ideas']
                    # If the model returns an object with a single array
                    elif len(result) == 1 and isinstance(next(iter(result.values())), list):
                        return next(iter(result.values()))
                elif isinstance(result, list):
                    return result
                
                logging.warning(f"Unexpected response format: {content}")
                return []
                
            except json.JSONDecodeError as e:
                logging.error(f"Failed to parse LLM response: {content}")
                return []
                
        except Exception as e:
            logging.error(f"Error extracting ideas: {str(e)}")
            return []
    
    async def merge_ideas(self, anchor_idea: Dict, existing_ideas: List[Dict]) -> Dict:
        """Merge an anchor idea with existing ideas.
        
        Args:
            anchor_idea: The new idea to merge (dict with 'id' and 'content').
            existing_ideas: List of existing ideas with their metadata.
            
        Returns:
            Dict with merge results in the format:
            {
                "action": "new" | "merge" | "both",
                "new_idea": {idea object} (if action is 'new' or 'both'),
                "merges": [
                    {"target_id": "id_of_target_idea"}
                ]
            }
        """
        # Prepare the existing ideas for the prompt
        existing_ideas_list = [
            f"ID: {idea['id']}\n{idea['content']}"
            for idea in existing_ideas
        ]
        
        prompt = f"""Given this anchor idea:
{json.dumps(anchor_idea, indent=2)}

And this list of existing ideas (each with ID and content):
{json.dumps(existing_ideas_list, indent=2)}

Classify the anchor idea into one of these categories:
1. "new" - Create a new idea (if no exact match exists)
2. "merge" - Merge into one or more existing ideas (if it's a variation or adds context)
3. "both" - Create a new idea AND merge into existing ones

For merging, only reference existing ideas by their ID. The anchor idea will be inserted as-is into the target idea.

Respond with a JSON object in this exact format:
{{
  "action": "new" | "merge" | "both",
  "new_idea": {{"id": "new-uuid", "content": "..."}},  // Only if action is "new" or "both"
  "merges": [
    {{"target_id": "existing-idea-id"}}  // Only if action is "merge" or "both"
  ]
}}

Example responses:
1. New idea: {{"action": "new", "new_idea": {{"id": "new-uuid", "content": "..."}}}}
2. Merge into existing: {{"action": "merge", "merges": [{{"target_id": "123"}}]}}
3. Both: {{"action": "both", "new_idea": {{"id": "new-uuid", "content": "..."}}, "merges": [{{"target_id": "123"}}]}}"""

        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "response_format": {"type": "json_object"},
            "temperature": 0.1,  # Lower temperature for more deterministic merging
            "max_tokens": 2000
        }
        
        try:
            response = await self._make_request("POST", "/chat/completions", json=payload)
            content = response['choices'][0]['message']['content']
            
            # Parse the JSON content
            try:
                result = json.loads(content)
                return result
            except json.JSONDecodeError:
                logging.error(f"Failed to parse merge response: {content}")
                return {"action": "new", "new_idea": anchor_idea, "merges": []}
                
        except Exception as e:
            logging.error(f"Error merging ideas: {str(e)}")
            return {"action": "new", "new_idea": anchor_idea, "merges": []}
