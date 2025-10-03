import asyncio
import logging
import argparse
# import os
import json
import time
import os
import tempfile
from transcript_loader import load_transcripts
from idea_extractor import extract_ideas
from idea_merger import merge_ideas
from utils import setup_logging, save_cache, track_tokens

async def main():
    parser = argparse.ArgumentParser(description='Tesla ideas Extraction and Merging System')
    parser.add_argument('--input-dir', type=str, required=True, help='Directory containing transcript files')
    parser.add_argument('--output-json', type=str, default='merged_ideas.json', help='Output JSON file for merged ideas')
    parser.add_argument('--output-md', type=str, default='merged_ideas.md', help='Output Markdown file for merged ideas')
    parser.add_argument('--model', type=str, default='anthropic/claude-3-opus-20240229', help='LLM model to use via OpenRouter')
    args = parser.parse_args()

    setup_logging()
    logging.info('Starting Tesla ideas Extraction and Merging System - Debug Mode')

    # Add timestamp to output filenames to prevent overwriting
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    # Use a temporary directory to rule out directory-specific issues
    temp_dir = tempfile.gettempdir()
    output_json = os.path.join(temp_dir, f"merged_ideas_{timestamp}.json")
    output_md = os.path.join(temp_dir, f"merged_ideas_{timestamp}.md")
    logging.info(f'Using timestamped output files in temp directory: {output_json}, {output_md}')

    # Check write permissions in temp directory
    try:
        test_file = os.path.join(temp_dir, f"test_write_{timestamp}.txt")
        with open(test_file, 'w') as f:
            f.write("Test")
        os.remove(test_file)
        logging.info(f'Write permissions confirmed in temp directory: {temp_dir}')
    except Exception as e:
        logging.error(f'Write permission issue in temp directory: {str(e)}')

    # Clear cache to ensure fresh extraction
    cache = {}
    logging.info('Cache cleared to ensure fresh extraction')

    transcripts = await load_transcripts(args.input_dir, cache)
    # Limit to transcript 19 (index 18) for debugging
    transcripts = transcripts[18:19]
    logging.info(f'Processing transcript 19, total {len(transcripts)} transcript for debugging')
    # Bypass relevance filtering to force extraction
    valid_transcripts = transcripts
    logging.info(f'Bypassing relevance filtering, using all transcripts: {len(valid_transcripts)}')
    if valid_transcripts:
        logging.info(f'Forced transcript file for extraction: {valid_transcripts[0].get("file_name", "Unknown")}')
    
    all_ideas = []
    tasks = []
    for transcript in valid_transcripts:
        tasks.append(extract_ideas(transcript, args.model, cache))
    
    results = await asyncio.gather(*tasks)
    for ideas in results:
        all_ideas.extend(ideas)
    logging.info(f'Total ideas extracted: {len(all_ideas)}')

    merged_ideas = await merge_ideas(all_ideas, args.model, cache)
    logging.info(f'Merged ideas content before saving: {json.dumps(merged_ideas, indent=2)}')
    # Print to console as a workaround for file saving issues
    print("=== MERGED IDEAS CONTENT (CONSOLE OUTPUT WORKAROUND) ===")
    print(json.dumps(merged_ideas, indent=2))
    print("=== END OF MERGED IDEAS CONTENT ===")
    
    # Use alternative method to write JSON file
    try:
        json_content = json.dumps(merged_ideas, indent=2)
        with open(output_json, 'w', encoding='utf-8') as f:
            f.write(json_content)
        logging.info(f'Saved merged ideas to {output_json} using alternative method')
        # Add a small delay to ensure file system updates
        time.sleep(2)
        # Verify content after saving
        with open(output_json, 'r', encoding='utf-8') as f:
            saved_content = f.read()
        logging.info(f'Veified content after saving to {output_json}: {saved_content[:500]}... (truncated if long)')
    except Exception as e:
        logging.error(f'Error saving JSON file: {str(e)}')
        # Workaround: Log full content directly as a fallback
        logging.info(f'WORKAROUND - Full merged ideas content: {json.dumps(merged_ideas, indent=2)}')

    # Use alternative method to write MD file
    try:
        md_content = '# Merged Tesla ideas\n\n'
        for idea in merged_ideas:
            md_content += f'## Idea {idea["id"]}\n'
            md_content += f'{idea["description"]}\n\n'
            if 'related_ideas' in idea:
                md_content += '### Related ideas\n'
                for rel_idea in idea['related_ideas']:
                    md_content += f'- {rel_idea["description"]}\n'
        with open(output_md, 'w', encoding='utf-8') as f:
            f.write(md_content)
        logging.info(f'Saved merged ideas markdown to {output_md} using alternative method')
        # Add a small delay to ensure file system updates
        time.sleep(2)
        # Verify content after saving
        with open(output_md, 'r', encoding='utf-8') as f:
            saved_md_content = f.read()
        logging.info(f'Veified content after saving to {output_md}: {saved_md_content[:500]}... (truncated if long)')
    except Exception as e:
        logging.error(f'Error saving MD file: {str(e)}')
        # Workaround: Log full content directly as a fallback
        logging.info(f'WORKAROUND - Full markdown content: {md_content[:2000]}... (truncated if long)')
        # Print to console as a workaround
        print("=== MERGED IDEAS MARKDOWN CONTENT (CONSOLE OUTPUT WORKAROUND) ===")
        print(md_content)
        print("=== END OF MERGED IDEAS MARKDOWN CONTENT ===")

    # List directory to confirm file existence
    try:
        dir_contents = os.listdir(temp_dir)
        logging.info(f'Temp directory contents after saving files (partial list): {dir_contents[:10]}... (truncated if long)')
    except Exception as e:
        logging.error(f'Error listing temp directory: {str(e)}')

    for idea in merged_ideas:
        try:
            idea_file = os.path.join(temp_dir, f'idea_{idea["id"]}.md')
            with open(idea_file, 'w', encoding='utf-8') as f:
                f.write(f'# Idea {idea["id"]}\n\n')
                f.write(f'{idea["description"]}\n\n')
                f.write(f'**Source:** {idea.get("source_file", "Unknown")}\n')
                if 'timestamp' in idea:
                    f.write(f'**Timestamp:** {idea["timestamp"]}\n')
                if 'context' in idea:
                    f.write(f'**Context:** {idea["context"]}\n')
                if 'tags' in idea:
                    f.write(f'**Tags:** {", ".join(idea["tags"])}\n')
            logging.info(f'Saved individual idea file: {idea_file}')
        except Exception as e:
            logging.error(f'Error saving individual idea file for {idea["id"]}: {str(e)}')

    token_count = track_tokens()
    logging.info(f'Total tokens used: {token_count}')
    save_cache(cache)

if __name__ == '__main__':
    asyncio.run(main())
