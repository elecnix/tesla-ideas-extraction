"""Module for merging similar ideas from different transcripts."""

import asyncio
import logging
import uuid
from typing import Dict, List, Optional, Tuple

from .llm_utils import OpenRouterClient

class IdeaMerger:
    """Merges similar ideas from different transcripts."""
    
    def __init__(self, model: str = "x-ai/grok-4-fast:free"):
        """Initialize the idea merger.
        
        Args:
            model: The LLM model to use for merging.
        """
        self.model = model
    
    async def merge_ideas(
        self,
        ideas: List[Dict],
        batch_size: int = 10,
        max_concurrent: int = 3
    ) -> Tuple[List[Dict], List[str]]:
        """Merge similar ideas using LLM.
        
        Args:
            ideas: List of idea dictionaries to merge.
            batch_size: Number of ideas to process in each LLM call.
            max_concurrent: Maximum number of concurrent LLM calls.
            
        Returns:
            Tuple of (merged_ideas, error_messages)
        """
        if not ideas:
            return [], []
            
        # Start with the first idea
        merged_ideas = [ideas[0]]
        
        # Process remaining ideas in batches
        for i in range(1, len(ideas), batch_size):
            batch = ideas[i:i + batch_size]
            
            # Process current batch
            tasks = [
                self._process_idea(idea, merged_ideas)
                for idea in batch
            ]
            
            # Run tasks with limited concurrency
            batch_results = []
            for j in range(0, len(tasks), max_concurrent):
                current_tasks = tasks[j:j + max_concurrent]
                results = await asyncio.gather(*current_tasks, return_exceptions=True)
                batch_results.extend(results)
            
            # Process results
            for result in batch_results:
                if isinstance(result, Exception):
                    logging.error(f"Error processing idea: {str(result)}")
                    continue
                    
                merged_ideas = self._apply_merge_result(merged_ideas, result)
        
        return merged_ideas, []
    
    async def _process_idea(
        self, 
        idea: Dict, 
        existing_ideas: List[Dict]
    ) -> Dict:
        """Process a single idea against existing merged ideas.
        
        Args:
            idea: The idea to process (must include 'id' and 'content')
            existing_ideas: List of existing merged ideas
            
        Returns:
            Dict containing the original idea and merge result
        """
        async with OpenRouterClient(model=self.model) as llm:
            # Prepare the anchor idea with required fields
            anchor_idea = {
                'id': idea['id'],
                'content': idea['content']
            }
            
            # Get just the essential fields from existing ideas
            existing_for_llm = [
                {'id': e['id'], 'content': e['content']}
                for e in existing_ideas
            ]
            
            # Get merge decision from LLM
            merge_result = await llm.merge_ideas(
                anchor_idea=anchor_idea,
                existing_ideas=existing_for_llm
            )
            
            # Add the full anchor idea to the merge result for reference
            merge_result['anchor_idea'] = idea
            return merge_result
    
    def _apply_merge_result(
        self, 
        merged_ideas: List[Dict],
        merge_result: Dict
    ) -> List[Dict]:
        """Apply merge result to the list of merged ideas.
        
        Args:
            merged_ideas: Current list of merged ideas
            merge_result: Result from _process_idea containing merge instructions
            
        Returns:
            Updated list of merged ideas
        """
        idea = merge_result.get('anchor_idea', {})
        
        # Handle new idea creation
        if merge_result.get('action') in ['new', 'both'] and 'new_idea' in merge_result:
            new_idea = merge_result['new_idea'].copy()
            # Ensure required fields are set
            new_idea.setdefault('sources', [])
            new_idea.setdefault('related_ideas', [])
            
            # Add source from original idea if not present
            if 'sources' in idea and idea['sources']:
                new_idea['sources'].extend(idea['sources'])
            
            merged_ideas.append(new_idea)
        
        # Handle merges with existing ideas
        if merge_result.get('action') in ['merge', 'both'] and 'merges' in merge_result:
            for merge in merge_result['merges']:
                target_id = merge.get('target_id')
                target = next((i for i in merged_ideas if i['id'] == target_id), None)
                
                if target:
                    # Ensure required structures exist
                    if 'related_ideas' not in target:
                        target['related_ideas'] = []
                    
                    # Add the anchor idea as a related idea
                    related_idea = {
                        'id': idea['id'],
                        'content': idea['content'],
                        'relationship': merge.get('relationship', '')
                    }
                    
                    # Add source reference if available
                    if 'sources' in idea:
                        related_idea['sources'] = idea['sources'].copy()
                    
                    target['related_ideas'].append(related_idea)
                    
                    # Add merge metadata
                    if 'merge_history' not in target:
                        target['merge_history'] = []
                        
                    target['merge_history'].append({
                        'merged_from': idea['id'],
                        'merged_at': self._get_current_timestamp()
                    })
        
        return merged_ideas
    
    @staticmethod
    def _get_current_timestamp() -> str:
        """Get current timestamp in ISO format."""
        from datetime import datetime
        return datetime.utcnow().isoformat() + "Z"
