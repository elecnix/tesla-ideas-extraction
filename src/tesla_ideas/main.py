#!/usr/bin/env python3
"""
Main module for processing Tesla-related transcripts and extracting/merging ideas.
"""
import asyncio
import json
import os
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dotenv import load_dotenv
from loguru import logger

from . import __version__
from .idea_extractor import IdeaExtractor
from .models import ProcessingState, TranscriptInfo
from .transcript_loader import TranscriptLoader
from .utils import (
    CACHE_VERSION,
    load_or_initialize_cache,
    save_to_cache,
)

# Configure logger
logger.remove()
logger.add(
    "tesla_ideas.log",
    rotation="10 MB",
    retention="7 days",
    level="INFO",
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
)
logger.add(
    lambda msg: print(msg, end=""),
    level="INFO",
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
)

# Constants
CACHE_FILE = Path("data/cache/processing_state.json")
OUTPUT_DIR = Path("data/output")

class TeslaIdeasProcessor:
    """Main class for processing transcripts and managing the idea extraction workflow."""
    
    def __init__(
        self,
        transcripts_dir: str,
        output_dir: str = "data/output",
        cache_file: str = "data/cache/processing_state.json",
        model: str = "gpt-4",
        batch_size: int = 5,
        max_workers: int = 3
    ):
        """Initialize the processor.
        
        Args:
            transcripts_dir: Directory containing transcript files
            output_dir: Directory for output files
            cache_file: Path to cache file for processing state
            model: LLM model to use
            batch_size: Number of transcripts to process in parallel
            max_workers: Maximum number of concurrent workers
        """
        self.transcripts_dir = Path(transcripts_dir)
        self.output_dir = Path(output_dir)
        self.cache_file = Path(cache_file)
        self.model = model
        self.batch_size = batch_size
        self.max_workers = max_workers
        self.cache_version = CACHE_VERSION
        
        # Create output directories
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.cache_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Initialize components
        self.transcript_loader = TranscriptLoader(self.transcripts_dir)
        self.idea_extractor = IdeaExtractor(model=model)
        
        # Load or initialize processing state
        self.state = load_or_initialize_cache(
            self.cache_file,
            ProcessingState()
        )
    
    async def process_transcripts(self) -> None:
        """Process all transcripts and extract/merge ideas."""
        logger.info("Starting transcript processing")
        start_time = time.time()
        
        try:
            # Find and process new transcripts
            transcripts = self.transcript_loader.get_transcripts()
            new_transcripts = [
                t for t in transcripts.values()
                if t.transcript_id not in self.state.processed_transcripts
                and t.status != "skipped"
            ]
            
            if not new_transcripts:
                logger.info("No new transcripts to process")
                return
            
            logger.info(f"Found {len(new_transcripts)} new transcripts to process")
            
            # Process transcripts in batches
            for i in range(0, len(new_transcripts), self.batch_size):
                batch = new_transcripts[i:i + self.batch_size]
                logger.info(f"Processing batch {i//self.batch_size + 1}/{(len(new_transcripts)-1)//self.batch_size + 1}")
                
                # Process batch concurrently
                tasks = [self._process_transcript(t) for t in batch]
                results = await asyncio.gather(*tasks, return_exceptions=True)
                
                # Handle results
                for transcript, result in zip(batch, results):
                    if isinstance(result, Exception):
                        logger.error(f"Error processing {transcript.transcript_id}: {result}")
                        self.state.update_transcript_status(
                            transcript.transcript_id,
                            "failed",
                            str(result)
                        )
                    elif result:
                        self.state.update_transcript_status(
                            transcript.transcript_id,
                            "completed",
                            idea_count=len(result)
                        )
                
                # Save progress after each batch
                self._save_state()
            
            # Save final state and outputs
            self._save_outputs()
            
            # Print summary
            duration = time.time() - start_time
            logger.info(f"Processing completed in {duration:.1f} seconds")
            logger.info(f"Total transcripts processed: {len(self.state.processed_transcripts)}")
            
        except Exception as e:
            logger.error(f"Error during processing: {e}", exc_info=True)
            raise
    
    async def _process_transcript(
        self,
        transcript: TranscriptInfo
    ) -> List[Dict]:
        """Process a single transcript and return extracted ideas."""
        try:
            # Update status
            self.state.update_transcript_status(transcript.transcript_id, "processing")
            
            # Load transcript content
            content = self.transcript_loader.get_transcript_content(transcript.transcript_id)
            if not content:
                raise ValueError(f"Failed to load content for {transcript.transcript_id}")
            
            # Check relevance with LLM
            relevance_cache_key = f"v{self.cache_version}:relevance:{transcript.transcript_id}:{transcript.content_hash}"
            cached_relevance = self.idea_extractor.cache.get(relevance_cache_key)
            
            if cached_relevance:
                is_relevant, reason = cached_relevance["relevant"], cached_relevance["reason"]
            else:
                is_relevant, reason = await self.idea_extractor.check_relevance(content)
                # Cache the result
                self.idea_extractor.cache[relevance_cache_key] = {
                    "relevant": is_relevant,
                    "reason": reason
                }
            
            if not is_relevant:
                logger.info(f"Transcript {transcript.transcript_id} is not relevant: {reason}")
                self.state.update_transcript_status(
                    transcript.transcript_id,
                    "skipped",
                    f"Not relevant: {reason}"
                )
                return []
            
            # Extract ideas
            result = await self.idea_extractor.extract_ideas(
                transcript_id=transcript.transcript_id,
                content=content,
                content_hash=transcript.content_hash
            )
            
            # Convert to detailed idea objects
            segments = self.transcript_loader.get_transcript_segments(transcript.transcript_id)
            detailed_ideas = self.idea_extractor.to_detailed_ideas(result, transcript, segments)
            
            # Save detailed ideas to JSON file
            output_file = self.output_dir / f"{transcript.transcript_id}_ideas.json"
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump([idea.dict() for idea in detailed_ideas], f, indent=2, ensure_ascii=False)
            
            logger.info(f"Extracted {len(detailed_ideas)} detailed ideas from {transcript.transcript_id}")
            return detailed_ideas
            
        except Exception as e:
            logger.error(f"Error processing transcript {transcript.transcript_id}: {e}")
            self.state.update_transcript_status(
                transcript.transcript_id,
                "failed",
                str(e)
            )
            raise
    
    def _save_state(self) -> None:
        """Save the current processing state to cache."""
        try:
            save_to_cache(
                self.cache_file,
                self.state.model_dump()
            )
        except Exception as e:
            logger.error(f"Error saving state: {e}")
    
    def _save_outputs(self) -> None:
        """Save the final outputs to files."""
        try:
            # Save all ideas as JSON
            ideas_file = self.output_dir / "all_ideas.json"
            with open(ideas_file, "w") as f:
                json.dump(
                    [idea.model_dump() for idea in self.state.ideas.values()],
                    f,
                    indent=2,
                    default=str
                )
            
            # Save all ideas as Markdown
            md_file = self.output_dir / "all_ideas.md"
            with open(md_file, "w") as f:
                f.write("# Tesla Ideas\n\n")
                for idea in self.state.ideas.values():
                    f.write(f"## {idea.anchor_text}\n\n")
                    for i, variation in enumerate(idea.variations, 1):
                        f.write(f"### Variation {i}\n")
                        f.write(f"**Source:** {variation.source.transcript_id}\n")
                        f.write(f"**Context:** {variation.context.get('context', '')}\n")
                        if variation.context.get('tags'):
                            f.write(f"**Tags:** {variation.context['tags']}\n")
                        f.write("\n---\n\n")
                    f.write("\n")
            
            # Save individual idea files
            ideas_dir = self.output_dir / "ideas"
            ideas_dir.mkdir(exist_ok=True)
            
            for idea_id, idea in self.state.ideas.items():
                idea_file = ideas_dir / f"{idea_id}.md"
                with open(idea_file, "w") as f:
                    f.write(f"# {idea.anchor_text}\n\n")
                    f.write(f"*ID:* {idea_id}\n")
                    f.write(f"*Created:* {idea.created_at}\n")
                    f.write(f"*Updated:* {idea.updated_at}\n\n")
                    
                    f.write("## Variations\n\n")
                    for i, variation in enumerate(idea.variations, 1):
                        f.write(f"### Variation {i}\n")
                        f.write(f"**Source:** {variation.source.transcript_id}\n")
                        f.write(f"**Context:** {variation.context.get('context', '')}\n")
                        if variation.context.get('tags'):
                            f.write(f"**Tags:** {variation.context['tags']}\n")
                        f.write(f"\n{variation.text}\n\n")
                        f.write("---\n\n")
            
            logger.info(f"Saved outputs to {self.output_dir}")
            
        except Exception as e:
            logger.error(f"Error saving outputs: {e}")
            raise


async def main():
    """Main entry point."""
    # Load environment variables
    load_dotenv()
    
    # Check for required environment variables
    if not os.getenv("OPENROUTER_API_KEY"):
        logger.error("OPENROUTER_API_KEY environment variable is required")
        return
    
    # Get transcripts directory from command line or use default
    import sys
    transcripts_dir = sys.argv[1] if len(sys.argv) > 1 else "/home/nicolas/Source/tesla-joe-justice-attempts/v2/data/transcripts"
    
    # Initialize and run the processor
    processor = TeslaIdeasProcessor(
        transcripts_dir=transcripts_dir,
        output_dir="data/output",
        cache_file="data/cache/processing_state.json",
        model="x-ai/grok-4-fast:free",
        batch_size=3,
        max_workers=2
    )
    
    try:
        await processor.process_transcripts()
    except KeyboardInterrupt:
        logger.info("Processing interrupted by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
    finally:
        # Ensure state is saved even on error
        processor._save_state()


if __name__ == "__main__":
    asyncio.run(main())
