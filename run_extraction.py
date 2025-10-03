#!/usr/bin/env python3
"""
Main script for extracting and merging ideas from all transcripts.
"""
import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv
from loguru import logger

from src.tesla_ideas import TeslaIdeasProcessor

# Configure logger
logger.remove()
logger.add(
    "extraction.log",
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

async def main():
    # Load environment variables
    load_dotenv()
    
    # Check for required environment variables
    if not os.getenv("OPENROUTER_API_KEY"):
        logger.error("ERROR: OPENROUTER_API_KEY environment variable is not set")
        logger.info("Please create a .env file with your OpenRouter API key:")
        logger.info("OPENROUTER_API_KEY=your_api_key_here")
        return
    
    # Path to transcripts directory
    transcripts_dir = "/home/nicolas/Source/tesla-joe-justice-attempts/v2/data/transcripts"
    
    # Create output directories
    output_dir = "data/output"
    cache_file = "data/cache/processing_state.json"
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    Path(cache_file).parent.mkdir(parents=True, exist_ok=True)
    
    # Initialize the processor
    processor = TeslaIdeasProcessor(
        transcripts_dir=transcripts_dir,
        output_dir=output_dir,
        cache_file=cache_file,
        model="x-ai/grok-4-fast:free",
        batch_size=3,    # Process 3 transcripts at a time
        max_workers=2    # Use 2 concurrent workers
    )
    
    try:
        logger.info("Starting full extraction...")
        await processor.process_transcripts()
        
        # Print summary
        logger.info("\n=== Extraction Complete ===")
        logger.info(f"Total transcripts processed: {len(processor.state.processed_transcripts)}")
        logger.info(f"Total unique ideas extracted: {len(processor.state.ideas)}")
        logger.info(f"Results saved to: {output_dir}")
        
    except Exception as e:
        logger.error(f"Error during extraction: {e}", exc_info=True)
    finally:
        # Ensure state is saved even if there's an error
        processor._save_state()

if __name__ == "__main__":
    asyncio.run(main())
