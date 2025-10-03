#!/usr/bin/env python3
"""Main entry point for the Tesla Ideas Extractor."""

import argparse
import asyncio
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

# Add the project root to the Python path
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Local imports
try:
    from tesla_ideas import __version__
    from tesla_ideas.idea_extractor import IdeaExtractor
    from tesla_ideas.idea_merger import IdeaMerger
    from tesla_ideas.llm_utils import OpenRouterClient
    from tesla_ideas.output_utils import (
        save_ideas_to_json,
        save_ideas_to_markdown,
        save_individual_idea_pages
    )
    from tesla_ideas.transcript_loader import discover_transcripts
except ImportError as e:
    logging.error(f"Failed to import required modules: {e}")
    raise

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('tesla_ideas.log')
    ]
)
logger = logging.getLogger(__name__)

async def process_transcripts(
    input_dirs: List[str],
    output_dir: str,
    cache_dir: str,
    model: str,
    batch_size: int,
    max_concurrent: int,
    skip_extraction: bool = False,
    skip_merging: bool = False
) -> Tuple[List[Dict], List[str]]:
    """Process transcripts and extract/merge ideas.
    
    Args:
        input_dirs: List of directories containing transcript files.
        output_dir: Directory to save output files.
        cache_dir: Directory for caching extracted ideas.
        model: LLM model to use.
        batch_size: Number of ideas to process in each LLM call.
        max_concurrent: Maximum number of concurrent LLM calls.
        skip_extraction: Skip the extraction step and use cached data if available.
        skip_merging: Skip the merging step.
        
    Returns:
        Tuple of (merged_ideas, error_messages)
    """
    # Ensure output and cache directories exist
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    cache_path = Path(cache_dir)
    cache_path.mkdir(parents=True, exist_ok=True)
    
    # Initialize LLM client for transcript loading
    llm_client = OpenRouterClient(model=model)
    
    # Initialize components
    extractor = IdeaExtractor(cache_dir=str(cache_path), model=model)
    merger = IdeaMerger(model=model)
    
    # Load and process transcripts
    all_transcripts = []
    for input_dir in input_dirs:
        try:
            # Discover and load transcripts with LLM-based relevance checking
            async with llm_client:
                transcripts = await discover_transcripts(
                    input_dir,
                    llm_client=llm_client,
                    max_workers=max_concurrent
                )
            all_transcripts.extend(transcripts)
            logger.info(f"Found {len(transcripts)} relevant transcripts in {input_dir}")
        except Exception as e:
            logger.error(f"Error processing directory {input_dir}: {e}")
    
    if not all_transcripts:
        logger.warning("No relevant transcripts found in the specified directories.")
        return [], ["No relevant transcripts found"]
    
    # Extract ideas
    if skip_extraction:
        logger.info("Skipping extraction (using cached data if available)")
        extracted_ideas = []
        for transcript in all_transcripts:
            cached_ideas = extractor._load_cached_ideas(transcript['file_hash'])
            if cached_ideas:
                extracted_ideas.extend(cached_ideas)
        logger.info(f"Loaded {len(extracted_ideas)} ideas from cache")
    else:
        logger.info(f"Extracting ideas from {len(all_transcripts)} transcripts...")
        
        # Add processing timestamp to each transcript
        processed_at = datetime.utcnow().isoformat() + "Z"
        for transcript in all_transcripts:
            transcript['processed_at'] = processed_at
        
        extracted_ideas, extract_errors = await extractor.extract_ideas_from_transcripts(
            all_transcripts,
            max_concurrent=max_concurrent
        )
        
        if extract_errors:
            logger.warning(f"Encountered {len(extract_errors)} errors during extraction")
            for error in extract_errors:
                logger.debug(f"Extraction error: {error}")
        
        logger.info(f"Extracted {len(extracted_ideas)} ideas from transcripts")
    
    if not extracted_ideas:
        return [], ["No ideas were extracted from the transcripts"]
    
    # Save extracted ideas before merging
    extracted_output = output_path / "extracted_ideas.json"
    with open(extracted_output, 'w', encoding='utf-8') as f:
        json.dump(extracted_ideas, f, indent=2, ensure_ascii=False)
    logger.info(f"Saved extracted ideas to {extracted_output}")
    
    # Merge ideas
    if skip_merging:
        logger.info("Skipping merging (using extracted ideas as-is)")
        merged_ideas = extracted_ideas
    else:
        logger.info(f"Merging {len(extracted_ideas)} ideas...")
        merged_ideas, merge_errors = await merger.merge_ideas(
            extracted_ideas,
            batch_size=batch_size,
            max_concurrent=max_concurrent
        )
        
        if merge_errors:
            logger.warning(f"Encountered {len(merge_errors)} errors during merging")
            for error in merge_errors:
                logger.debug(f"Merge error: {error}")
        
        logger.info(f"Merged {len(extracted_ideas)} ideas into {len(merged_ideas)} unique ideas")
    
    # Save results
    save_ideas_to_json(merged_ideas, output_path / "merged_ideas.json")
    save_ideas_to_markdown(merged_ideas, output_path / "merged_ideas.md")
    save_individual_idea_pages(merged_ideas, output_path / "ideas")
    
    return merged_ideas, []

def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Extract and merge ideas from Tesla-related transcripts.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    
    parser.add_argument(
        'input_dirs',
        nargs='+',
        help='One or more directories containing transcript files'
    )
    
    parser.add_argument(
        '--output-dir',
        default='./output',
        help='Directory to save output files'
    )
    
    parser.add_argument(
        '--cache-dir',
        default='.cache/tesla_ideas',
        help='Directory for caching extracted ideas'
    )
    
    parser.add_argument(
        '--model',
        default='x-ai/grok-4-fast:free',
        help='LLM model to use for extraction and merging'
    )
    
    parser.add_argument(
        '--batch-size',
        type=int,
        default=10,
        help='Number of ideas to process in each LLM call'
    )
    
    parser.add_argument(
        '--max-concurrent',
        type=int,
        default=5,
        help='Maximum number of concurrent LLM calls'
    )
    
    parser.add_argument(
        '--skip-extraction',
        action='store_true',
        help='Skip extraction and use cached data if available'
    )
    
    parser.add_argument(
        '--skip-merging',
        action='store_true',
        help='Skip the merging step and output extracted ideas as-is'
    )
    
    parser.add_argument(
        '--version',
        action='version',
        version=f'%(prog)s {__version__}'
    )
    
    return parser.parse_args()

async def async_main():
    """Async entry point."""
    args = parse_args()
    
    # Check for required environment variables
    if not os.getenv('OPENROUTER_API_KEY'):
        logger.error("Error: OPENROUTER_API_KEY environment variable not set")
        sys.exit(1)
    
    logger.info(f"Starting Tesla Ideas Extractor v{__version__}")
    logger.info(f"Input directories: {', '.join(args.input_dirs)}")
    logger.info(f"Output directory: {args.output_dir}")
    logger.info(f"Using model: {args.model}")
    
    try:
        merged_ideas, errors = await process_transcripts(
            input_dirs=args.input_dirs,
            output_dir=args.output_dir,
            cache_dir=args.cache_dir,
            model=args.model,
            batch_size=args.batch_size,
            max_concurrent=args.max_concurrent,
            skip_extraction=args.skip_extraction,
            skip_merging=args.skip_merging
        )
        
        if errors:
            logger.warning(f"Completed with {len(errors)} warnings/errors")
        else:
            logger.info("Completed successfully")
            
        return 0
        
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        return 1

def main():
    """Main entry point."""
    return asyncio.run(async_main())

if __name__ == "__main__":
    sys.exit(main())
