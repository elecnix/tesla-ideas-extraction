import asyncio
import json
import os
from typing import Dict, List, Optional, Tuple

from loguru import logger
from pydantic import BaseModel, Field

from .models import Idea, IdeaContent, ProcessingState
from .utils import generate_uuid


class MergeDecision(BaseModel):
    """Represents a decision to merge or create a new idea."""
    action: str = Field(..., description="One of: 'new', 'merge'")
    merge_targets: List[Dict] = Field(default_factory=list, description="List of target ideas to merge into")


class IdeaMerger:
    """Handles merging of similar ideas using an LLM."""
    
    def __init__(self, model: str = "gpt-4", temperature: float = 0.2):
        """Initialize the idea merger.
        
        Args:
            model: The LLM model to use for merging decisions
            temperature: Temperature parameter for generation
        """
        self.model = model
        self.temperature = temperature
        self.client = None
        
    async def initialize(self):
        """Initialize the OpenAI client asynchronously."""
        import openai
        self.client = openai.AsyncOpenAI(
            api_key=os.getenv("OPENROUTER_API_KEY"),
            base_url="https://openrouter.ai/api/v1"
        )
    
    async def should_merge(
        self,
        anchor_idea: str,
        existing_ideas: List[Tuple[str, str]],
        max_retries: int = 3,
        initial_delay: float = 1.0
    ) -> MergeDecision:
        """Determine if a new idea should be merged with existing ones.
        
        Args:
            anchor_idea: The new idea to potentially merge
            existing_ideas: List of (idea_id, idea_text) for existing ideas
            max_retries: Maximum number of retry attempts
            initial_delay: Initial delay between retries in seconds
            
        Returns:
            MergeDecision with the merge decision
        """
        if not self.client:
            await self.initialize()
            
        system_prompt = """You are an expert at analyzing and organizing ideas. Your task is to determine 
        if a new idea should be merged with existing ones or treated as a new, distinct idea.
        
        Consider the following when making your decision:
        1. Are the core concepts and meaning of the ideas the same or very similar?
        2. Do they describe the same practice, principle, or insight?
        3. Are the differences only in wording or minor details?
        
        If the new idea is substantially different from all existing ones, it should be a new idea.
        If it's similar to one or more existing ideas, it should be merged with them.
        """
        
        existing_ideas_text = "\n".join(
            f"{i+1}. {idea_text} (ID: {idea_id[:8]}...)" 
            for i, (idea_id, idea_text) in enumerate(existing_ideas)
        )
        
        user_prompt = f"""New idea to evaluate:
        {anchor_idea}
        
        Existing ideas:
        {existing_ideas_text}
        
        Decide if this new idea should be:
        1. A new distinct idea (if it's substantially different from all existing ones)
        2. Merged with one or more existing ideas (if it's similar to existing ones)
        
        If merging, provide the ID(s) of the idea(s) to merge it with.
        
        Respond with a JSON object:
        {{
            "action": "new" | "merge",
            "merge_targets": [                 // Only if action is "merge"
                {{ "id": "...", "reason": "..." }},
                ...
            ]
        }}
        """
        
        delay = initial_delay
        last_error = None
        
        for attempt in range(max_retries):
            try:
                response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    temperature=self.temperature,
                    response_format={"type": "json_object"},
                )
                
                # Parse the response
                result = response.choices[0].message.content
                if not result:
                    raise ValueError("Empty response from model")
                
                # Parse and validate the response
                try:
                    data = json.loads(result)
                    return MergeDecision(**data)
                except (json.JSONDecodeError, ValueError) as e:
                    logger.error(f"Failed to parse merge decision: {e}")
                    logger.debug(f"Response content: {result}")
                    raise ValueError(f"Invalid merge decision format: {e}")
                
            except Exception as e:
                last_error = e
                if attempt < max_retries - 1:
                    logger.warning(
                        f"Merge decision attempt {attempt + 1} failed, retrying in {delay:.1f}s: {str(e)}"
                    )
                    await asyncio.sleep(delay)
                    delay *= 2  # Exponential backoff
                else:
                    logger.error(
                        f"All {max_retries} merge decision attempts failed"
                    )
                    # Default to creating a new idea on failure
                    return MergeDecision(action="new")
        
        # This should never be reached due to the return in the loop
        return MergeDecision(action="new")
    
    async def merge_ideas(
        self,
        state: ProcessingState,
        new_ideas: List[Idea],
        batch_size: int = 10,
        max_workers: int = 5
    ) -> ProcessingState:
        """Merge new ideas into the existing state.
        
        Args:
            state: Current processing state
            new_ideas: List of new ideas to merge
            batch_size: Number of ideas to process in parallel
            max_workers: Maximum number of concurrent workers
            
        Returns:
            Updated processing state
        """
        if not new_ideas:
            return state
            
        # Process ideas in batches to avoid overwhelming the API
        for i in range(0, len(new_ideas), batch_size):
            batch = new_ideas[i:i + batch_size]
            
            # Process batch with limited concurrency
            semaphore = asyncio.Semaphore(max_workers)
            
            async def process_idea(idea: Idea) -> None:
                async with semaphore:
                    await self._process_single_idea(state, idea)
            
            # Process the batch concurrently
            await asyncio.gather(*[process_idea(idea) for idea in batch])
            
            logger.info(f"Processed batch {i//batch_size + 1}/{(len(new_ideas)-1)//batch_size + 1}")
        
        return state
    
    async def _process_single_idea(
        self,
        state: ProcessingState,
        new_idea: Idea
    ) -> None:
        """Process a single new idea and merge it into the state."""
        if not new_idea.variations:
            return
            
        # Get the anchor text from the first variation
        anchor_text = new_idea.anchor_text
        
        # Get existing ideas for comparison (limit to most recent N for efficiency)
        existing_ideas = [
            (idea_id, idea.anchor_text)
            for idea_id, idea in list(state.ideas.items())[-100:]  # Only check last 100 ideas
        ]
        
        if not existing_ideas:
            # First idea, just add it
            state.add_idea(new_idea)
            return
            
        # Get merge decision from LLM
        decision = await self.should_merge(anchor_text, existing_ideas)
        
        if decision.action == "new":
            # Create a new idea with original anchor text
            state.add_idea(new_idea)
        
        elif decision.action == "merge" and decision.merge_targets:
            # Merge with existing ideas
            merged = False
            for target in decision.merge_targets:
                target_id = target.get("id")
                if not target_id:
                    continue
                    
                # Find the target idea (check full ID or prefix)
                target_idea = None
                for idea_id, idea in state.ideas.items():
                    if idea_id.startswith(target_id) or target_id in idea_id:
                        target_idea = idea
                        break
                
                if target_idea:
                    # Add all variations from the new idea to the target
                    for variation in new_idea.variations:
                        target_idea.add_variation(variation)
                    merged = True
                    
            # If no valid targets found, create as new idea
            if not merged:
                state.add_idea(new_idea)
        
        else:
            # Default to creating a new idea
            state.add_idea(new_idea)
