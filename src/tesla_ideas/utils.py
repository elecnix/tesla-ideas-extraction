import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, TypeVar, Union
from uuid import uuid4

import orjson
from loguru import logger
from pydantic import BaseModel

T = TypeVar('T', bound=BaseModel)

CACHE_VERSION = "2.0"  # Updated for iterative extraction and relevance check

def get_content_hash(content: str) -> str:
    """Generate a hash for the given content."""
    return hashlib.md5(content.encode('utf-8')).hexdigest()

def read_json_file(file_path: Union[str, Path]) -> Any:
    """Read and parse a JSON file."""
    with open(file_path, 'rb') as f:
        return orjson.loads(f.read())

def write_json_file(file_path: Union[str, Path], data: Any) -> None:
    """Write data to a JSON file."""
    file_path = Path(file_path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with open(file_path, 'wb') as f:
        f.write(orjson.dumps(data, option=orjson.OPT_INDENT_2 | orjson.OPT_SORT_KEYS))

def load_or_initialize_cache(cache_path: Path, default: T) -> T:
    """Load data from cache or initialize with default if not exists."""
    if cache_path.exists():
        try:
            data = read_json_file(cache_path)
            return default.__class__.model_validate(data)
        except Exception as e:
            logger.warning(f"Error loading cache from {cache_path}: {e}")
    return default

def save_to_cache(cache_path: Path, data: Any) -> None:
    """Save data to cache file."""
    try:
        write_json_file(cache_path, data)
    except Exception as e:
        logger.error(f"Error saving cache to {cache_path}: {e}")

def generate_uuid() -> str:
    """Generate a UUID string."""
    return str(uuid4())

def is_tesla_related(content: str) -> bool:
    """Check if content is related to Tesla based on keywords."""
    keywords = ["tesla", "elon musk", "agile", "innovation", "production", "gigafactory", "cybertruck"]
    content_lower = content.lower()
    return any(keyword in content_lower for keyword in keywords)
