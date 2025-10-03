# Software Requirements Specification (SRS): Tesla Facts Extraction and Merging System

## 1. Overview
This system processes text transcripts of podcasts/videos about Tesla operations and work environment (e.g., Agile at Tesla, Speed of Innovation, company culture). It extracts facts and their supporting sources from each transcript independently, then merges them into a unified list of distinctive facts. Merging identifies related facts and links them while keeping each fact standalone for readers to judge relatedness themselves. The original fact is merged as-is, with the merger LLM referencing facts by ID, and the merging code inserting the fact into the merged anchor fact.

The system must:
- Handle irrelevant transcripts (skip if not Tesla-related).
- Use an LLM (e.g., https://openrouter.ai/x-ai/grok-4-fast:free) sparingly for relevance checking, fact extraction and merging.
- Process transcripts in parallel to improve efficiency.
- Avoid reprocessing transcripts unnecessarily (e.g., via caching or state tracking).
- Handle incremental updates by receiving more transcripts and updating the merged facts list.
- Output a JSON file with the merged facts list.
- Output one Markdown file with the merged facts list.
- Output one Markdown file per fact, with each fact's details, color, and references.

**Assumptions**:
- Transcripts are plain text (.txt), JSON (.json), or SRT (.srt) files in specified directories. Multiple directories are allowed. If multiple files share the same basename, prefer those with timestamps.
- LLM API keys are provided via environment variables (e.g., `OPENROUTER_API_KEY`) in .env file.
- Total LLM calls should be minimized (e.g., 1 call per transcript for relevance check, variable calls for extraction loop, and batch merging to reduce invocations).
- LLM should be used in structured output mode (e.g., JSON) to ensure consistent and reliable output.
## 2. Functional Requirements

### 2.1 Transcript Input and Filtering
- **Input**: A directory path containing transcript files (e.g., `.txt`, `.json`, or `.srt` files).
- **Filtering**: For each transcript, use a lightweight heuristic (e.g., keyword check: "Tesla", "Elon Musk", "Agile", "Innovation", "work environment", "company culture") to skip irrelevant ones. If skipped, log and move to the next.
- **LLMBased Relevance Check**: For transcripts that pass the heuristic filter, send the full transcript to the LLM with a prompt to confirm relevance to Tesla operations and work environment (Agile, innovation speed, etc.).
  - Prompt example: "Is this transcript primarily about Tesla's work environment, including Agile at Tesla or Speed of Innovation at Tesla? Respond with 'yes' or 'no'. If 'no', provide a brief reason."
  - LLM response: Structured output (e.g., {"relevant": true/false, "reason": "..."}).
  - If not relevant, skip the transcript and log the reason.
  - This step can benefit from prompt caching when the same transcript is used in subsequent LLM calls for fact extraction.
- **Output**: List of valid transcript files to process.
### 2.2 Fact Extraction (Per Transcript)
- **Process**: For each valid transcript, analyze it in isolation.
  - Initialize an empty list of extracted facts.
  - In a loop:
    - Send the full transcript to the LLM along with the current list of extracted facts, prompting to identify any missing facts related to Tesla operations and work environment (Agile, innovation speed, etc.).
    - Prompt example: "Given this transcript: '[transcript]'. And this current list of facts: [list]. Extract any additional unique facts not already in the list about Tesla's work environment, including Agile at Tesla or Speed of Innovation at Tesla. Describe each fact in a single line. If no additional facts can be identified, return an empty list."
    - LLM response: Structured output (e.g., JSON array of strings, one per new fact).
    - Add the new facts to the list.
    - Repeat the loop until the number of new facts added in the last iteration is 1 or fewer, or the total number of extracted facts reaches at least 15.
  - After the loop, assign each fact a UUID and store additional details like contextual details, line number, and timestamp if available.
- **Parallelism**: Process multiple transcripts concurrently using asyncio or ThreadPoolExecutor to handle I/O-bound LLM calls. The global list of facts should be shared and updated in real-time.
- **Cost Efficiency**: Cache extracted facts per transcript (e.g., in a JSON file) to avoid reprocessing if the script restarts. Use a hash of the transcript content as a cache key.
- **Resilience**: Implement retry logic for LLM calls (e.g., infinite retries with exponential backoff). The script should be restartable and continue from where it left off.
- **Output**: For each transcript, the final list of unique facts with UUIDs and detailed contextual information. Each fact should be stored in a structured JSON format to support book writing and raw material extraction, including the following fields:
  - `quote`: The original text of the fact.
  - `speaker`: Speaker identification if available.
  - `timestamp`: Timestamp from subtitles or transcription sources (e.g., "HH:MM:SS"), not the current processing time.
  - `source_file`: Name of the source file.
  - `context`: Surrounding sentences before and after the quote.
  - `tags`: Automatically generated tags related to work environment, Agile principles, innovation, etc.
  
  Example JSON structure per fact:
  ```json
  {
    "quote": "Original text",
    "speaker": "If available",
    "timestamp": "HH:MM:SS",
    "source_file": "filename.txt",
    "context": "Surrounding sentences",
    "tags": ["agile", "innovation", "tesla"],
  }
  ```
  Additionally, capture full quotes with timestamps, maintain speaker identification, include surrounding context, add video timestamps for reference, include source file and line numbers, track fact frequency across sources, automatically tag with work environment aspects, Agile principles, identify key metrics or data points, capture emotional tone and emphasis, and find related facts during extraction or merging phases.

### 2.3 Fact Merging
- **Anchor-Based Classification**: Treat each extracted fact as an "anchor." For each anchor:
  - Provide the anchor to the LLM along with the current global list of merged facts, each identified by a unique ID.
  - Prompt the LLM to decide whether to create a new fact (if no exact match), merge into one or more existing facts, or both (create new and merge into existing ones).
  - The LLM output should only reference existing facts by their ID, without modifying the original fact text.
  - When merging, the code will insert the anchor fact as-is into the target merged fact, preserving the standalone nature of each fact while allowing readers to judge relatedness independently.
  - Prompt example: "Given this anchor fact: '[anchor]'. And this list of existing facts: [{'id': '1', 'description': '...'}, ...]. Classify: Create a new fact, merge into existing facts, or both. Output in JSON with IDs."
  - LLM response: Structured output (e.g., {"action": "new", "fact": "..."}, {"action": "merge", "merges": [{"target_id": "1"}]}, or {"action": "both", "new_fact": "...", "merges": [{"target_id": "1"}]}).
  - The LLM should not itself generate UUIDs.
- **Process Flow**:
  - Start with an empty global list.
  - Iterate through all extracted facts (from all transcripts).
  - For each anchor, invoke LLM to classify against the current global list.
  - Update the global list: Add new facts or merge anchors into existing ones by inserting the anchor fact into the target fact's structure.
- **Merging Logic**: If merging, insert the full anchor fact (description, UUID, contextual details) as a sub-element or reference in the target fact, allowing each fact to remain standalone while linked.
- **Parallelism**: Batch anchors into groups (e.g., 10-20 per LLM call) to reduce invocations. Use async for concurrent LLM calls if API supports it. All operations of the pipeline should be parallelized, meaning they can all run massively in parallel: loading transcripts, extracting facts, and merging. Merging too should be parallelized, and we accept that two identical facts might be created concurrently.

### 2.4 Output and Logging
- **Final Output**: Save the merged list to a JSON file (e.g., `merged_facts.json`).
- **Logging**: Use Python's logging module to track progress (e.g., transcripts processed, facts extracted, merges performed). Log skipped transcripts and LLM call counts for cost monitoring.
- **Error Handling**: Retry failed LLM calls with exponential backoff. Skip malformed transcripts or facts, recording them as errors that can be retried automatically when restarting the script, allowing the user to fix the issue and continue processing.

## 3. Non-Functional Requirements
- **Performance**: Process 10-50 transcripts in <30 minutes (depending on LLM latency). Parallelism for 5-10 concurrent LLM calls.
- **Security**: No API keys in code; load from env vars. Use HTTPS for API calls.
- **Usability**: Command-line interface with arguments for input directory, output file, and LLM model selection.
- **Maintainability**: Modular code (e.g., separate modules for extraction, merging, utils). Unit tests for key functions. Integration test with sample transcripts and true LLM calls.

## 4. Architecture
- **Modules**:
  - `transcript_loader.py`: Load and filter transcripts.
  - `fact_extractor.py`: LLM-based extraction per transcript.
  - `fact_merger.py`: LLM-based merging.
  - `main.py`: Orchestrate the process (parallel processing, caching).
  - `utils.py`: Helpers for caching, logging, LLM calls.
- **Data Flow**:
  1. Load/filter transcripts.
  2. Extract facts in parallel (cached).
  3. Merge facts sequentially or batched (to maintain global list state).
  4. Output merged JSON.
- **Dependencies**: `openai` for LLM, `asyncio` for parallelism, `hashlib` for caching.

## 5. Implementation Notes
- **LLM Selection**: Default to OpenRouter grok-4-fast:free for speed and cost.
- **Prompt Engineering**: Refine prompts based on initial tests to ensure single-line facts and accurate merging.
- **Testing**: Include sample transcripts and expected outputs. Mock LLM for unit tests.
- **Cost Monitoring**: Track total tokens used per run.
- **Edge Cases**: Empty transcripts, no facts, LLM failures, overlapping facts that shouldn't merge.
- **Handling Spec Updates**: Implementations must support versioning for cached data to handle changes in processing logic (e.g., new extraction loops, relevance checks, or merging rules). Include a version identifier (e.g., spec version or hash of key prompts/methods) in cache metadata. When deploying updates, check cache versions; if outdated, re-run affected steps (e.g., relevance validation, fact extraction, merging) for cached transcripts. Provide a command-line flag to force full cache invalidation and reprocessing for major changes. Log version mismatches to track reprocessing needs and ensure the merged facts list remains consistent.
- **Handling Long Transcripts**: To avoid truncation due to LLM context limits, if a transcript exceeds the model's input limit, split it into overlapping chunks (e.g., 80% overlap) and process each chunk for fact extraction, then deduplicate the extracted facts across chunks.
- **Architectural decisions**: During the implementation, track architectural decisions in a separate file (e.g., `arch_decisions.md`).

This spec provides a complete blueprint. Review it, and let me know any changes before implementation. If needed, I can start coding based on this once approved.
