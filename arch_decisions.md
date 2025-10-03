# Architectural Decisions

## LLM Selection
- Used OpenRouter's xAI Grok-4-fast:free for cost efficiency and speed.
- API compatible with OpenAI client.

## Parallelism
- Transcripts processed in parallel using asyncio.gather.
- Merging uses a lock to maintain global list state, but accepts potential duplicates.

## Caching
- Extracted ideas cached per transcript using content hash.
- No caching for merging to keep it simple.

## Error Handling
- Retry logic with exponential backoff for LLM calls.
- Skip malformed data with logging.

## Data Structures
- Merged ideas stored as dict of id to {description, anchors}.
- Anchors are the original extracted ideas.

## Dependencies
- Minimal: openai, python-dotenv.
