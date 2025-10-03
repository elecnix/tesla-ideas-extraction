from typing import Dict, List, Optional, Tuple
from pydantic import BaseModel, Field
from datetime import datetime
from uuid import uuid4
from enum import Enum


class IdeaSource(BaseModel):
    """Represents the source of an idea (e.g., a transcript)."""
    transcript_id: str
    content_hash: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    metadata: Dict[str, str] = Field(default_factory=dict)


class IdeaContent(BaseModel):
    """Represents the content of an idea with its source information."""
    text: str
    source: IdeaSource
    context: Optional[Dict[str, str]] = None


class DetailedIdea(BaseModel):
    """Detailed idea with comprehensive metadata for book writing."""
    id: str = Field(default_factory=lambda: str(uuid4()))
    quote: str
    speaker: Optional[str] = None
    timestamp: Optional[str] = None  # HH:MM:SS format
    source_file: str
    context: Optional[str] = None  # Surrounding sentences
    tags: List[str] = Field(default_factory=list)
    line_number: Optional[int] = None
    frequency: int = 1
    metrics: Optional[Dict[str, str]] = None  # Key metrics or data points
    emotional_tone: Optional[str] = None
    emphasis: Optional[str] = None
    related_ideas: List[str] = Field(default_factory=list)  # IDs of related ideas


class Idea(BaseModel):
    """Represents a unique idea with its variations and sources."""
    id: str = Field(default_factory=lambda: str(uuid4()))
    anchor_text: str
    variations: List[IdeaContent] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    metadata: Dict[str, str] = Field(default_factory=dict)

    def add_variation(self, content: IdeaContent) -> None:
        """Add a new variation to this idea."""
        self.variations.append(content)
        self.updated_at = datetime.utcnow()


class TranscriptStatus(str, Enum):
    """Status of a transcript processing."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class TranscriptInfo(BaseModel):
    """Metadata about a transcript file."""
    transcript_id: str
    file_path: str
    content_hash: str
    status: TranscriptStatus = TranscriptStatus.PENDING
    processed_at: Optional[datetime] = None
    error: Optional[str] = None
    idea_count: int = 0


class ProcessingState(BaseModel):
    """Tracks the processing state of all transcripts."""
    processed_transcripts: Dict[str, TranscriptInfo] = Field(default_factory=dict)
    ideas: Dict[str, Idea] = Field(default_factory=dict)
    stats: Dict[str, int] = Field(default_factory=dict)

    def register_transcript(self, transcript: TranscriptInfo) -> Tuple[TranscriptInfo, bool]:
        """Register or update transcript metadata in state.

        Returns:
            Tuple of (stored transcript info, content_changed flag).
        """
        existing = self.processed_transcripts.get(transcript.transcript_id)
        content_changed = False

        if existing:
            if existing.content_hash != transcript.content_hash:
                content_changed = True
                existing.content_hash = transcript.content_hash
                existing.status = TranscriptStatus.PENDING
                existing.idea_count = 0
                existing.error = None

            existing.file_path = transcript.file_path
            existing.processed_at = transcript.processed_at

            if transcript.status == TranscriptStatus.SKIPPED:
                existing.status = TranscriptStatus.SKIPPED
                existing.idea_count = 0
                existing.error = transcript.error

            return existing, content_changed

        self.processed_transcripts[transcript.transcript_id] = transcript
        if transcript.status == TranscriptStatus.SKIPPED:
            return transcript, False
        return transcript, True

    def should_process_transcript(self, transcript: TranscriptInfo) -> bool:
        """Determine if the transcript needs processing."""
        stored, content_changed = self.register_transcript(transcript)

        if stored.status == TranscriptStatus.SKIPPED:
            return False

        if content_changed:
            return True

        if stored.status in {TranscriptStatus.PENDING, TranscriptStatus.PROCESSING, TranscriptStatus.FAILED}:
            return True

        return stored.status != TranscriptStatus.COMPLETED

    def update_transcript_status(
        self, 
        transcript_id: str, 
        status: TranscriptStatus,
        error: Optional[str] = None,
        idea_count: Optional[int] = None
    ) -> None:
        """Update the status of a transcript."""
        info = self.processed_transcripts.get(transcript_id)
        if not info:
            info = TranscriptInfo(
                transcript_id=transcript_id,
                file_path="",
                content_hash="",
                status=status,
                processed_at=datetime.utcnow()
            )
            self.processed_transcripts[transcript_id] = info

        info.status = status
        info.processed_at = datetime.utcnow()

        if error is not None:
            info.error = error or None
        elif status == TranscriptStatus.COMPLETED:
            info.error = None

        if idea_count is not None:
            info.idea_count = idea_count

        if status == TranscriptStatus.COMPLETED:
            self.stats["total_transcripts_completed"] = sum(
                1 for transcript in self.processed_transcripts.values()
                if transcript.status == TranscriptStatus.COMPLETED
            )

    def add_idea(self, idea: Idea) -> None:
        """Add a new idea to the state."""
        self.ideas[idea.id] = idea
        self.stats["total_ideas"] = len(self.ideas)

    def get_idea_by_anchor(self, anchor_text: str) -> Optional[Idea]:
        """Find an idea by its anchor text."""
        for idea in self.ideas.values():
            if idea.anchor_text.lower() == anchor_text.lower():
                return idea
        return None
