"""Utilities for outputting merged ideas to various formats."""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional

def save_ideas_to_json(ideas: List[Dict], output_path: str) -> None:
    """Save ideas to a JSON file.
    
    Args:
        ideas: List of idea dictionaries to save.
        output_path: Path to the output JSON file.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump({
                'ideas': ideas,
                'count': len(ideas),
                'generated_at': _get_current_timestamp()
            }, f, indent=2, ensure_ascii=False)
        logging.info(f"Saved {len(ideas)} ideas to {output_path}")
    except IOError as e:
        logging.error(f"Failed to save ideas to {output_path}: {e}")

def save_ideas_to_markdown(ideas: List[Dict], output_path: str) -> None:
    """Save ideas to a Markdown file.
    
    Args:
        ideas: List of idea dictionaries to save.
        output_path: Path to the output Markdown file.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(f"# Tesla Ideas\n\n")
            f.write(f"*Generated on {_get_current_timestamp()}*\n\n")
            f.write(f"Total ideas: {len(ideas)}\n\n")
            
            for i, idea in enumerate(ideas, 1):
                f.write(f"## {i}. {idea['content']}\n\n")
                
                # Add related ideas if available
                if 'related_ideas' in idea and idea['related_ideas']:
                    f.write("### Related Ideas\n")
                    for related in idea['related_ideas']:
                        # Only include the relationship text if it exists
                        if 'relationship' in related and related['relationship']:
                            f.write(f"- {related['relationship']}  \n")
                        else:
                            f.write(f"- {related.get('content', 'Related idea')}  \n")
                    f.write("\n")
                
                # Add sources
                if 'sources' in idea and idea['sources']:
                    f.write("### Sources\n")
                    for source in idea['sources']:
                        fname = source.get('file_name', 'Unknown')
                        fhash = source.get('file_hash', '')[:8]
                        f.write(f"- {fname} ({fhash})  \n")
                    f.write("\n")
                
                f.write("---\n\n")
                
        logging.info(f"Saved {len(ideas)} ideas to {output_path}")
    except IOError as e:
        logging.error(f"Failed to save ideas to {output_path}: {e}")

def save_individual_idea_pages(ideas: List[Dict], output_dir: str) -> None:
    """Save each idea to its own Markdown file.
    
    Args:
        ideas: List of idea dictionaries to save.
        output_dir: Directory to save individual idea files.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    for i, idea in enumerate(ideas, 1):
        try:
            # Create a filename from the idea content (first few words)
            safe_content = "".join(
                c if c.isalnum() or c in ' -_' else '_' 
                for c in idea['content'][:50]
            ).strip('_')
            filename = f"{i:03d}_{safe_content}.md"
            filepath = output_dir / filename
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(f"# {idea['content']}\n\n")
                f.write(f"*ID: {idea['id']}*  \n")
                f.write(f"*Generated on {_get_current_timestamp()}*\n\n")
                
                # Add content (if we have more than just the title)
                if 'details' in idea and idea['details']:
                    f.write(f"{idea['details']}\n\n")
                
                # Add related ideas if available
                if 'related_ideas' in idea and idea['related_ideas']:
                    f.write("## Related Ideas\n")
                    for related in idea['related_ideas']:
                        # Only include the relationship text if it exists
                        if 'relationship' in related and related['relationship']:
                            f.write(f"- {related['relationship']}  \n")
                        else:
                            f.write(f"- {related.get('content', 'Related idea')}  \n")
                    f.write("\n")
                
                # Add sources
                if 'sources' in idea and idea['sources']:
                    f.write("## Sources\n")
                    for source in idea['sources']:
                        fname = source.get('file_name', 'Unknown')
                        fpath = source.get('file_path', '')
                        fhash = source.get('file_hash', '')[:8]
                        f.write(f"- **{fname}**  \n")
                        f.write(f"  - Path: {fpath}  \n")
                        f.write(f"  - Hash: {fhash}  \n")
                        if 'extracted_at' in source:
                            f.write(f"  - Extracted: {source['extracted_at']}  \n")
                        f.write("\n")
                
        except Exception as e:
            logging.error(f"Failed to save idea {i} to {filename}: {e}")
    
    logging.info(f"Saved {len(ideas)} individual idea files to {output_dir}")

def _get_current_timestamp() -> str:
    """Get current timestamp in a readable format."""
    from datetime import datetime
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S %Z")
