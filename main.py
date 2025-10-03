import asyncio
import json
import os
from typing import List, Dict, Any
from transcript_loader import filter_transcripts
from idea_extractor import extract_ideas
from idea_merger import merge_ideas_batch
from utils import logger, merged_ideas

async def process_transcript(file_path: str, content: str):
    """Process a single transcript: extract ideas."""
    ideas = await extract_ideas(content, file_path)
    return ideas

async def main(directory: str):
    """Main orchestration."""
    logger.info("Starting Tesla Ideas Extraction")

    # Filter transcripts
    valid_transcripts = await filter_transcripts(directory)
    logger.info(f"Found {len(valid_transcripts)} valid transcripts")

    # Extract ideas in parallel
    tasks = [process_transcript(fp, content) for fp, content in valid_transcripts]
    extracted_lists = await asyncio.gather(*tasks)
    all_ideas = [idea for sublist in extracted_lists for idea in sublist]
    logger.info(f"Extracted {len(all_ideas)} total ideas")

    # Merge ideas in batches
    batch_size = 10
    for i in range(0, len(all_ideas), batch_size):
        batch = all_ideas[i:i+batch_size]
        await merge_ideas_batch(batch)

    # Output
    output_json(merged_ideas)
    output_markdown(merged_ideas)
    logger.info("Processing complete")

def output_json(ideas: Dict[str, Dict[str, Any]]):
    """Output merged ideas to JSON."""
    with open('merged_ideas.json', 'w') as f:
        json.dump(list(ideas.values()), f, indent=2)

def output_markdown(ideas: Dict[str, Dict[str, Any]]):
    """Output merged ideas to Markdown."""
    with open('merged_ideas.md', 'w') as f:
        f.write("# Merged Tesla Ideas\n\n")
        for idea_id, data in ideas.items():
            f.write(f"## Idea {idea_id}\n")
            f.write(f"{data['description']}\n\n")
            for anchor in data['anchors']:
                f.write(f"- {anchor['quote']} (from {anchor['source_file']})\n")
            f.write("\n")

    # One file per idea
    os.makedirs('ideas', exist_ok=True)
    for idea_id, data in ideas.items():
        with open(f"ideas/{idea_id}.md", 'w') as f:
            f.write(f"# Idea {idea_id}\n\n")
            f.write(f"**Description:** {data['description']}\n\n")
            f.write("**References:**\n")
            for anchor in data['anchors']:
                f.write(f"- {anchor['quote']}\n")
                f.write(f"  - Source: {anchor['source_file']}\n")
                if anchor['speaker']:
                    f.write(f"  - Speaker: {anchor['speaker']}\n")
                if anchor['timestamp']:
                    f.write(f"  - Timestamp: {anchor['timestamp']}\n")
                f.write(f"  - Tags: {', '.join(anchor['tags'])}\n\n")

if __name__ == "__main__":
    import sys
    if len(sys.argv) != 2:
        print("Usage: python main.py <directory>")
        sys.exit(1)
    directory = sys.argv[1]
    asyncio.run(main(directory))
