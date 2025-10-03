import asyncio
import json
import os
from typing import List, Optional, Tuple

import openai
from loguru import logger
from pydantic import BaseModel, Field

from .models import DetailedIdea, TranscriptInfo
from .utils import CACHE_VERSION


class ExtractedIdea(BaseModel):
    """Represents an idea extracted from a transcript."""
    quote: str = Field(..., description="The original quote text")
    context: Optional[str] = Field(None, description="Surrounding context")
    speaker: Optional[str] = Field(None, description="Speaker if identified")
    timestamp: Optional[str] = Field(None, description="Timestamp in HH:MM:SS")
    line_number: Optional[int] = Field(None, description="Line number in source")
    tags: List[str] = Field(default_factory=list, description="Tags for categorization")


class IdeaExtractionResult(BaseModel):
    """Result of the idea extraction process."""
    ideas: List[ExtractedIdea] = Field(default_factory=list)
    transcript_id: str
    content_hash: str


class IdeaExtractor:
    """Handles extraction of ideas from transcripts using an LLM."""
    
    def __init__(self, model: str = "x-ai/grok-4-fast:free", temperature: float = 0.3):
        """Initialize the idea extractor.
        
        Args:
            model: The LLM model to use for extraction
            temperature: Temperature parameter for generation
        """
        self.model = model
        self.temperature = temperature
        self.cache = {}
        self.client = openai.AsyncOpenAI(
            api_key=os.getenv("OPENROUTER_API_KEY"),
            base_url="https://openrouter.ai/api/v1"
        )
    
    async def extract_ideas(
        self,
        transcript_id: str,
        content: str,
        content_hash: str,
        max_retries: int = 3,
        initial_delay: float = 1.0
    ) -> IdeaExtractionResult:
        """Extract ideas from a transcript asynchronously.
        
        Args:
            transcript_id: ID of the transcript
            content: Transcript content
            content_hash: Hash of the transcript content
            
        Returns:
            IdeaExtractionResult containing the extracted ideas
        """
        system_prompt = (
            "You are an expert at extracting meaningful quotes from transcripts about Tesla's operations, Agile practices, innovation, and manufacturing. "
            "Extract full, standalone quotes that contain specific insights, not summaries. "
            "Each quote must be a direct excerpt that makes sense on its own."
        )
        
        delay = initial_delay
        # Check if we have a cached result
        cache_key = f"v{CACHE_VERSION}:extracted_ideas:{transcript_id}:{content_hash}"
        cached_result = self.cache.get(cache_key)
        if cached_result:
            logger.info(f"Using cached result for transcript {transcript_id}")
            return IdeaExtractionResult(**cached_result)
        
        for attempt in range(max_retries):
            try:
                logger.info(f"Extracting ideas from transcript {transcript_id} (attempt {attempt + 1}/{max_retries})")
                
                # Iterative extraction loop
                all_extracted_ideas = []
                iteration = 0
                max_iterations = 10  # Prevent infinite loops
                
                while len(all_extracted_ideas) < 15 and iteration < max_iterations:
                    iteration += 1
                    
                    # Create prompt with current quotes list
                    current_quotes_text = "\n".join(
                        f"{i+1}. {idea.quote}" 
                        for i, idea in enumerate(all_extracted_ideas)
                    ) if all_extracted_ideas else "None yet"
                    
                    iterative_prompt = (
                        "Extract additional unique Tesla-related quotes from this transcript. Focus on operations, Agile practices, innovation, and manufacturing insights.\n\n"
                        "ALREADY EXTRACTED QUOTES (do not repeat these):\n" + current_quotes_text + "\n\n"
                        "Find NEW quotes not in the list above. Each quote must be a complete, standalone excerpt that makes sense on its own, without referencing other quotes or the transcript context.\n\n"
                        "Return ONLY a JSON object:\n"
                        '{"quotes": [{"quote": "full original quote text", "context": "brief surrounding context", "speaker": "speaker name or null", "timestamp": "HH:MM:SS or null", "line_number": 123, "tags": ["tag1", "tag2"]}]}'
                        "\n\nTranscript:\n" + content
                    )
                    
                    response = await self.client.chat.completions.create(
                        model=self.model,
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": iterative_prompt}
                        ],
                        temperature=self.temperature,
                        response_format={"type": "json_object"},
                    )
                    
                    result = response.choices[0].message.content
                    if not result:
                        break
                        
                    # Parse and add new ideas
                    try:
                        parsed = json.loads(result)
                        quotes_data = parsed.get('quotes', [])
                        
                        new_ideas = []
                        for item in quotes_data:
                            if isinstance(item, dict) and 'quote' in item:
                                quote_text = item['quote'].strip()
                                # Check if this quote is already extracted (simple string match)
                                if not any(existing.quote.lower() == quote_text.lower() for existing in all_extracted_ideas):
                                    # Parse line_number safely
                                    line_number = item.get('line_number')
                                    if isinstance(line_number, str):
                                        try:
                                            line_number = int(line_number)
                                        except (ValueError, TypeError):
                                            line_number = None
                                    elif not isinstance(line_number, int):
                                        line_number = None
                                    
                                    # Parse speaker safely
                                    speaker = item.get('speaker')
                                    if speaker and not isinstance(speaker, str):
                                        speaker = None
                                    
                                    # Parse timestamp safely (should be HH:MM:SS format)
                                    timestamp = item.get('timestamp')
                                    if timestamp and not isinstance(timestamp, str):
                                        timestamp = None
                                    elif timestamp and not (isinstance(timestamp, str) and len(timestamp.split(':')) == 3):
                                        # If not in HH:MM:SS format, set to None
                                        timestamp = None
                                    
                                    # Parse tags safely
                                    tags = item.get('tags', [])
                                    if not isinstance(tags, list):
                                        tags = []
                                    else:
                                        tags = [str(tag) for tag in tags if tag]  # Convert to strings and filter empty
                                    
                                    try:
                                        extracted_idea = ExtractedIdea(
                                            quote=quote_text,
                                            context=item.get('context', ''),
                                            speaker=speaker,
                                            timestamp=timestamp,
                                            line_number=line_number,
                                            tags=tags
                                        )
                                        new_ideas.append(extracted_idea)
                                    except Exception as e:
                                        logger.warning(f"Skipping invalid idea: {e}")
                                        continue
                        
                        logger.debug(f"Iteration {iteration}: extracted {len(new_ideas)} new ideas")
                        
                        # Stop if fewer than 2 new ideas added
                        if len(new_ideas) <= 1:
                            break
                            
                        all_extracted_ideas.extend(new_ideas)
                        
                    except json.JSONDecodeError:
                        logger.warning(f"Failed to parse JSON in iteration {iteration}")
                        break
                
                logger.info(f"Extracted {len(all_extracted_ideas)} ideas from transcript {transcript_id} after {iteration} iterations")
                
                return IdeaExtractionResult(
                    ideas=all_extracted_ideas,
                    transcript_id=transcript_id,
                    content_hash=content_hash
                )
                
            except Exception as e:
                if attempt < max_retries - 1:
                    logger.warning(
                        f"Attempt {attempt + 1} failed, retrying in {delay:.1f}s: {str(e)}"
                    )
                    await asyncio.sleep(delay)
                    delay *= 2  # Exponential backoff
                else:
                    logger.error(
                        f"All {max_retries} attempts failed for transcript {transcript_id}: {e}"
                    )
                    # Return an empty result instead of raising an exception to continue processing
                    return IdeaExtractionResult(
                        ideas=[],
                        transcript_id=transcript_id,
                        content_hash=content_hash
                    )
        
        # This should never be reached
        return IdeaExtractionResult(
            ideas=[],
            transcript_id=transcript_id,
            content_hash=content_hash
        )
    async def check_relevance(self, content: str, max_retries: int = 3) -> Tuple[bool, str]:
        """Check if transcript content is relevant to Agile at Tesla or Speed of Innovation.
        
        Args:
            content: Transcript content to check
            max_retries: Maximum retry attempts
            
        Returns:
            Tuple of (is_relevant, reason)
        """
        system_prompt = (
            "You are an expert at evaluating content relevance for Tesla's operations and innovation. "
            "Determine if the provided transcript primarily discusses Agile practices at Tesla or Tesla's speed of innovation. "
            "Be strict: only consider it relevant if it's clearly about these topics at Tesla."
        )
        
        user_prompt = (
            f"Does this transcript primarily discuss Agile practices at Tesla or Tesla's speed of innovation?\n\n"
            f"Respond with JSON: {{\"relevant\": true/false, \"reason\": \"brief explanation\"}}\n\n"
            f"Transcript:\n{content[:2000]}"  # Limit content for efficiency
        )
        
        delay = 1.0
        
        for attempt in range(max_retries):
            try:
                response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    temperature=0.1,
                    response_format={"type": "json_object"},
                )
                
                result = response.choices[0].message.content
                if not result:
                    continue
                    
                data = json.loads(result)
                relevant = data.get("relevant", False)
                reason = data.get("reason", "No reason provided")
                
                return relevant, reason
                
            except Exception as e:
                if attempt < max_retries - 1:
                    await asyncio.sleep(delay)
                    delay *= 2
                else:
                    logger.error(f"Relevance check failed: {e}")
                    return False, f"Check failed: {e}"
        
        return False, "All attempts failed"
    
    def to_detailed_ideas(
        self,
        extraction_result: IdeaExtractionResult,
        transcript_info: TranscriptInfo,
        segments: List
    ) -> List[DetailedIdea]:
        """Convert extracted ideas to DetailedIdea objects.
        
        Args:
            extraction_result: Result from extract_ideas
            transcript_info: Information about the source transcript
            segments: Transcript segments for metadata
            
        Returns:
            List of DetailedIdea objects
        """
        from .models import DetailedIdea
        
        ideas = []
        
        # Create segment lookup by line number or text
        segment_lookup = {}
        for seg in segments:
            if seg.line_number:
                segment_lookup[seg.line_number] = seg
            # Also try text match for fallback
            segment_lookup[seg.text[:100]] = seg
        
        for extracted in extraction_result.ideas:
            # Try to find matching segment for metadata
            segment = None
            if extracted.line_number:
                segment = segment_lookup.get(extracted.line_number)
            if not segment and extracted.quote:
                # Fallback to text matching
                for seg in segments:
                    if extracted.quote in seg.text or seg.text in extracted.quote:
                        segment = seg
                        break
            
            # Convert timestamp from seconds to HH:MM:SS
            timestamp = extracted.timestamp
            if not timestamp and segment and segment.start_time:
                hours = int(segment.start_time // 3600)
                minutes = int((segment.start_time % 3600) // 60)
                seconds = int(segment.start_time % 60)
                timestamp = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
            
            speaker = extracted.speaker or (segment.speaker if segment else None)
            line_number = extracted.line_number or (segment.line_number if segment else None)
            
            # Generate tags if not provided
            tags = extracted.tags or ["tesla", "innovation"]
            
            # Add Agile-related tags if applicable
            if any(word in extracted.quote.lower() for word in ["agile", "sprint", "scrum", "kanban", "lean"]):
                tags.append("agile")
            
            detailed_idea = DetailedIdea(
                quote=extracted.quote,
                speaker=speaker,
                timestamp=timestamp,
                source_file=transcript_info.file_path,
                context=extracted.context,
                tags=list(set(tags)),  # Remove duplicates
                line_number=line_number,
                metrics={},  # Could be populated with data points
                emotional_tone=None,  # Could be analyzed
                emphasis=None  # Could be analyzed
            )
            ideas.append(detailed_idea)
        
        return ideas
