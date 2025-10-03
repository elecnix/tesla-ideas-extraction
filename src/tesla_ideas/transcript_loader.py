import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from loguru import logger
from pydantic import BaseModel

from .models import TranscriptInfo, TranscriptStatus
from .utils import get_content_hash, is_tesla_related


class TranscriptSegment(BaseModel):
    """Represents a segment of transcript with metadata."""
    text: str
    start_time: Optional[float] = None  # seconds
    duration: Optional[float] = None
    speaker: Optional[str] = None
    line_number: Optional[int] = None


class TranscriptLoader:
    """Handles loading and filtering of transcript files."""
    
    def __init__(self, transcripts_dir: str):
        """Initialize with the directory containing transcript files.
        
        Args:
            transcripts_dir: Path to the directory containing transcript files
        """
        self.transcripts_dir = Path(transcripts_dir)
        self.supported_extensions = {'.json', '.txt'}
        self.client = None  # Will be initialized when needed
        self._transcript_cache: Dict[str, List[TranscriptSegment]] = {}
    
    def get_transcript_segments(self, transcript_id: str) -> List[TranscriptSegment]:
        """Get transcript content as segments with metadata."""
        if transcript_id in self._transcript_cache:
            return self._transcript_cache[transcript_id]
            
        file_path = self._find_transcript_file(transcript_id)
        if not file_path:
            return []
            
        segments = self._load_segments(file_path)
        self._transcript_cache[transcript_id] = segments
        return segments
    
    def _find_transcript_file(self, transcript_id: str) -> Optional[Path]:
        """Find the transcript file for the given ID."""
        for ext in self.supported_extensions:
            candidate = self.transcripts_dir / f"{transcript_id}{ext}"
            if candidate.exists():
                return candidate
        return None
    
    def _load_segments(self, file_path: Path) -> List[TranscriptSegment]:
        """Load transcript as segments."""
        if file_path.suffix == '.json':
            return self._load_json_segments(file_path)
        elif file_path.suffix == '.txt':
            return self._load_text_segments(file_path)
        return []
    
    def _load_json_segments(self, file_path: Path) -> List[TranscriptSegment]:
        """Load JSON transcript with segments."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
            segments = []
            if isinstance(data, dict) and 'segments' in data:
                for i, seg in enumerate(data['segments']):
                    if isinstance(seg, dict) and 'text' in seg:
                        segment = TranscriptSegment(
                            text=seg['text'].strip(),
                            start_time=seg.get('start'),
                            duration=seg.get('duration'),
                            speaker=seg.get('speaker'),
                            line_number=i + 1
                        )
                        segments.append(segment)
            return segments
        except Exception as e:
            logger.warning(f"Failed to load JSON segments from {file_path}: {e}")
            return []
    
    def _load_text_segments(self, file_path: Path) -> List[TranscriptSegment]:
        """Load text transcript as segments (one per line)."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                
            segments = []
            for i, line in enumerate(lines, 1):
                text = line.strip()
                if text:
                    segment = TranscriptSegment(
                        text=text,
                        line_number=i
                    )
                    segments.append(segment)
            return segments
        except Exception as e:
            logger.warning(f"Failed to load text segments from {file_path}: {e}")
            return []
    
    def find_transcript_files(self) -> List[Path]:
        """Find all supported transcript files in the directory.
        
        Returns:
            List of Path objects for found transcript files
        """
        if not self.transcripts_dir.exists() or not self.transcripts_dir.is_dir():
            logger.error(f"Transcripts directory not found: {self.transcripts_dir}")
            return []
            
        files = []
        for ext in self.supported_extensions:
            files.extend(self.transcripts_dir.glob(f'*{ext}'))
        
        # Filter out files that have both .json and .txt versions (prefer .json)
        file_stems = {f.stem for f in files}
        filtered_files = []
        
        for file in files:
            if file.suffix == '.json' or f"{file.stem}.json" not in file_stems:
                filtered_files.append(file)
        
        logger.info(f"Found {len(filtered_files)} transcript files")
        return filtered_files
    
    def load_transcript_content(self, file_path: Path) -> Tuple[Optional[str], Optional[str]]:
        """Load content from a transcript file.
        
        Args:
            file_path: Path to the transcript file
            
        Returns:
            Tuple of (content, error_message). content is None if there was an error.
        """
        try:
            if file_path.suffix == '.json':
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    # Handle different possible JSON structures
                    if isinstance(data, dict):
                        if 'text' in data:
                            content = data['text']
                        elif 'transcript' in data:
                            content = data['transcript']
                        elif 'segments' in data and isinstance(data['segments'], list):
                            # Concatenate all segment texts
                            content = ' '.join(
                                segment.get('text', '') 
                                for segment in data['segments'] 
                                if isinstance(segment, dict)
                            )
                        else:
                            # Try to find the first string value
                            content = next((v for v in data.values() if isinstance(v, str)), "")
                    else:
                        content = str(data)
            else:  # .txt
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
            
            return content, None
            
        except Exception as e:
            error_msg = f"Error loading transcript {file_path}: {str(e)}"
            logger.error(error_msg)
            return None, error_msg
    
    def process_transcript(self, file_path: Path) -> Optional[TranscriptInfo]:
        """Process a single transcript file.
        
        Args:
            file_path: Path to the transcript file
        Returns:
            TranscriptInfo if the file was processed successfully, None otherwise
        """
        transcript_id = file_path.stem
        logger.info(f"Processing transcript: {transcript_id}")

        # Load content
        content, error = self.load_transcript_content(file_path)
        processed_timestamp = datetime.fromtimestamp(file_path.stat().st_mtime)

        if error or content is None:
            return TranscriptInfo(
                transcript_id=transcript_id,
                file_path=str(file_path),
                content_hash="",
                status=TranscriptStatus.FAILED,
                error=error or "Failed to load content",
                processed_at=processed_timestamp
            )

        # Check if content is related to Tesla
        if not is_tesla_related(content):
            logger.info(f"Skipping non-Tesla related transcript: {transcript_id}")
            return TranscriptInfo(
                transcript_id=transcript_id,
                file_path=str(file_path),
                content_hash=get_content_hash(content),
                status=TranscriptStatus.SKIPPED,
                processed_at=processed_timestamp
            )

        # Create transcript info
        return TranscriptInfo(
            transcript_id=transcript_id,
            file_path=str(file_path),
            content_hash=get_content_hash(content),
            status=TranscriptStatus.PENDING,
            processed_at=processed_timestamp
        )
    
    def get_transcripts(self) -> Dict[str, TranscriptInfo]:
        """Get all transcripts in the directory.
        
{{ ... }}
            Dictionary mapping transcript IDs to TranscriptInfo objects
        """
        transcript_files = self.find_transcript_files()
        transcripts = {}
        
        for file_path in transcript_files:
            transcript_info = self.process_transcript(file_path)
            if transcript_info:
                transcripts[transcript_info.transcript_id] = transcript_info
        
        return transcripts
    
    def get_transcript_content(self, transcript_id: str) -> Optional[str]:
        """Get the content of a specific transcript.
        
        Args:
            transcript_id: ID of the transcript to get content for
            
        Returns:
            Transcript content as a string, or None if not found
        """
        # First try to find the file with any supported extension
        for ext in self.supported_extensions:
            file_path = self.transcripts_dir / f"{transcript_id}{ext}"
            if file_path.exists():
                content, _ = self.load_transcript_content(file_path)
                return content
        return None
