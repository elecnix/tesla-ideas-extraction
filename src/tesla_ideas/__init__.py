"""
Tesla Ideas Extractor

A tool for extracting and merging ideas from Tesla-related transcripts.
"""

__version__ = "0.1.0"

from .main import TeslaIdeasProcessor
from .models import Idea, IdeaContent, IdeaSource, ProcessingState, TranscriptInfo
from .transcript_loader import TranscriptLoader
from .idea_extractor import IdeaExtractor
from .idea_merger import IdeaMerger

__all__ = [
    "TeslaIdeasProcessor",
    "Idea",
    "IdeaContent",
    "IdeaSource",
    "ProcessingState",
    "TranscriptInfo",
    "TranscriptLoader",
    "IdeaExtractor",
    "IdeaMerger",
]
