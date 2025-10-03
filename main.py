import argparse
import asyncio
import json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from transcript_loader import load_and_filter_transcripts, load_transcript_content
from fact_extractor import extract_facts_from_transcript
from fact_merger import merge_facts
from utils import logger

async def extract_facts_parallel(transcript_paths: list[Path], max_workers: int = 5) -> list:
    """
    Extract facts from transcripts in parallel using ThreadPoolExecutor.
    """
    all_facts = []
    
    def extract_single(path):
        content = load_transcript_content(path)
        return extract_facts_from_transcript(path, content)
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(extract_single, path) for path in transcript_paths]
        for future in futures:
            facts = future.result()
            all_facts.extend(facts)
            logger.info(f"Extracted {len(facts)} facts from one transcript")
    
    return all_facts

def output_results(merged_facts: list, output_file: str):
    """
    Output merged facts to JSON and Markdown.
    """
    # JSON
    with open(f"{output_file}.json", 'w') as f:
        json.dump(merged_facts, f, indent=2)
    
    # Markdown
    with open(f"{output_file}.md", 'w') as f:
        f.write("# Merged Tesla Facts\n\n")
        for fact in merged_facts:
            f.write(f"## {fact['one_liner']}\n\n")
            f.write(f"{fact['quote']}\n\n")
            f.write(f"Source: {fact['source_file']}\n\n")
            f.write("---\n\n")
    
    # Per fact Markdown
    for fact in merged_facts:
        with open(f"facts/{fact['id']}.md", 'w') as f:
            f.write(f"# Fact: {fact['one_liner']}\n\n")
            f.write(f"**Quote:** {fact['quote']}\n\n")
            f.write(f"**Speaker:** {fact.get('speaker', 'Unknown')}\n\n")
            f.write(f"**Timestamp:** {fact.get('timestamp', '')}\n\n")
            f.write(f"**Source:** {fact['source_file']}\n\n")
            f.write(f"**Context:** {fact.get('context', '')}\n\n")
            f.write(f"**Tags:** {', '.join(fact.get('tags', []))}\n\n")
            f.write(f"**Key Metrics:** {', '.join(fact.get('key_metrics', []))}\n\n")
            f.write(f"**Themes:** {', '.join(fact.get('themes', []))}\n\n")
            f.write(f"**Narrative Potential:** {fact.get('narrative_potential', '')}\n\n")
            f.write(f"**Example Type:** {fact.get('example_type', '')}\n\n")
            f.write(f"**Related Ideas:** {', '.join(fact.get('related_ideas', []))}\n\n")

def main():
    parser = argparse.ArgumentParser(description="Tesla Facts Extraction and Merging")
    parser.add_argument("input_dir", help="Directory containing transcript files")
    parser.add_argument("--output", default="merged_facts", help="Output file prefix")
    parser.add_argument("--max_workers", type=int, default=5, help="Max parallel workers")
    args = parser.parse_args()
    
    logger.info("Starting Tesla Facts Extraction")
    
    # Load and filter transcripts
    valid_transcripts = load_and_filter_transcripts(args.input_dir)
    logger.info(f"Found {len(valid_transcripts)} valid transcripts")
    
    # Extract facts in parallel
    all_facts = asyncio.run(extract_facts_parallel(valid_transcripts, args.max_workers))
    logger.info(f"Extracted {len(all_facts)} total facts")
    
    # Merge facts
    merged_facts = merge_facts(all_facts)
    logger.info(f"Merged into {len(merged_facts)} facts")
    
    # Output
    Path("facts").mkdir(exist_ok=True)
    output_results(merged_facts, args.output)
    
    logger.info("Completed")

if __name__ == "__main__":
    main()
