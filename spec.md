# Software Requirements Specification (SRS): Tesla Ideas Extraction and Merging System

## 1. Overview
This system processes text transcripts of podcasts/videos about Tesla operations (e.g., Agile at Tesla, Speed of Innovation). It extracts ideas from each transcript independently, then merges them into a unified list of distinctive ideas. Merging identifies related ideas and links them while keeping each idea standalone for readers to judge relatedness themselves. The original idea is merged as-is, with the merger LLM referencing ideas by ID, and the merging code inserting the idea into the merged anchor idea.

The system must:
- Handle irrelevant transcripts (skip if not Tesla-related).
- Use an LLM (e.g., https://openrouter.ai/x-ai/grok-4-fast:free) sparingly for relevance checking, idea extraction and merging.
- Process transcripts in parallel to improve efficiency.
- Avoid reprocessing transcripts unnecessarily (e.g., via caching or state tracking).
- Handle incremental updates by receiving more transcripts and updating the merged ideas list.
- Output a JSON file with the merged ideas list.
- Output one Markdown file with the merged ideas list.
- Output one Markdown file per idea, with each idea's details, color, and references.

**Assumptions**:
- Transcripts are plain text files or JSON in specified directories. Multiple directories are allowed.
- LLM API keys are provided via environment variables (e.g., `OPENROUTER_API_KEY`) in .env file.
- Total LLM calls should be minimized (e.g., 1 call per transcript for relevance check, variable calls for extraction loop, and batch merging to reduce invocations).
- LLM should be used in structured output mode (e.g., JSON) to ensure consistent and reliable output.

## 2. Functional Requirements

### 2.1 Transcript Input and Filtering
- **Input**: A directory path containing transcript files (e.g., `.txt` files).
- **Filtering**: For each transcript, use a lightweight heuristic (e.g., keyword check: "Tesla", "Elon Musk", "Agile", "Innovation") to skip irrelevant ones. If skipped, log and move to the next.
- **LLM-Based Relevance Check**: For transcripts that pass the heuristic filter, send the full transcript to the LLM with a prompt to confirm relevance to Tesla operations (Agile, innovation speed, etc.).
  - Prompt example: "Is this transcript primarily about Agile at Tesla or Speed of Innovation at Tesla? Respond with 'yes' or 'no'. If 'no', provide a brief reason."
  - LLM response: Structured output (e.g., {"relevant": true/false, "reason": "..."}).
  - If not relevant, skip the transcript and log the reason.
  - This step can benefit from prompt caching when the same transcript is used in subsequent LLM calls for idea extraction.
- **Output**: List of valid transcript files to process.

### 2.2 Idea Extraction (Per Transcript)
- **Process**: For each valid transcript, analyze it in isolation.
  - Initialize an empty list of extracted ideas.
  - In a loop:
    - Send the full transcript to the LLM along with the current list of extracted ideas, prompting to identify any missing ideas related to Tesla operations (Agile, innovation speed, etc.).
    - Prompt example: "Given this transcript: '[transcript]'. And this current list of ideas: [list]. Extract any additional unique ideas not already in the list about Agile at Tesla or Speed of Innovation at Tesla. Describe each idea in a single line. If no additional ideas can be identified, return an empty list."
    - LLM response: Structured output (e.g., JSON array of strings, one per new idea).
    - Add the new ideas to the list.
    - Repeat the loop until the number of new ideas added in the last iteration is 1 or fewer, or the total number of extracted ideas reaches at least 15.
  - After the loop, assign each idea a UUID and store additional details like contextual details, line number, and timestamp if available.
- **Parallelism**: Process multiple transcripts concurrently using asyncio or ThreadPoolExecutor to handle I/O-bound LLM calls. The global list of ideas should be shared and updated in real-time.
- **Cost Efficiency**: Cache extracted ideas per transcript (e.g., in a JSON file) to avoid reprocessing if the script restarts. Use a hash of the transcript content as a cache key.
- **Resilience**: Implement retry logic for LLM calls (e.g., infinite retries with exponential backoff). The script should be restartable and continue from where it left off.
- **Output**: For each transcript, the final list of unique ideas (short descriptions) with UUIDs and contextual details. The list should be stored in a JSON file.

### 2.3 Idea Merging
- **Anchor-Based Classification**: Treat each extracted idea as an "anchor." For each anchor:
  - Provide the anchor to the LLM along with the current global list of merged ideas, each identified by a unique ID.
  - Prompt the LLM to decide whether to create a new idea (if no exact match), merge into one or more existing ideas, or both (create new and merge into existing ones).
  - The LLM output should only reference existing ideas by their ID, without modifying the original idea text.
  - When merging, the code will insert the anchor idea as-is into the target merged idea, preserving the standalone nature of each idea while allowing readers to judge relatedness independently.
  - Prompt example: "Given this anchor idea: '[anchor]'. And this list of existing ideas: [{'id': '1', 'description': '...'}, ...]. Classify: Create a new idea, merge into existing ideas, or both. Output in JSON with IDs."
  - LLM response: Structured output (e.g., {"action": "new", "idea": "..."}, {"action": "merge", "merges": [{"target_id": "1"}]}, or {"action": "both", "new_idea": "...", "merges": [{"target_id": "1"}]}).
  - The LLM should not itself generate UUIDs.
- **Process Flow**:
  - Start with an empty global list.
  - Iterate through all extracted ideas (from all transcripts).
  - For each anchor, invoke LLM to classify against the current global list.
  - Update the global list: Add new ideas or merge anchors into existing ones by inserting the anchor idea into the target idea's structure.
- **Merging Logic**: If merging, insert the full anchor idea (description, UUID, contextual details) as a sub-element or reference in the target idea, allowing each idea to remain standalone while linked.
- **Parallelism**: Batch anchors into groups (e.g., 10-20 per LLM call) to reduce invocations. Use async for concurrent LLM calls if API supports it. All operations of the pipeline should be parallelized, meaning they can all run massively in parallel: loading transcripts, extracting ideas, and merging. Merging too should be parallelized, and we accept that two identical ideas might be created concurrently.

### 2.4 Output and Logging
- **Final Output**: Save the merged list to a JSON file (e.g., `merged_ideas.json`).
- **Logging**: Use Python's logging module to track progress (e.g., transcripts processed, ideas extracted, merges performed). Log skipped transcripts and LLM call counts for cost monitoring.
- **Error Handling**: Retry failed LLM calls with exponential backoff. Skip malformed transcripts or ideas, recording them as errors that can be retried automatically when restarting the script, allowing the user to fix the issue and continue processing.

## 3. Non-Functional Requirements
- **Performance**: Process 10-50 transcripts in <30 minutes (depending on LLM latency). Parallelism for 5-10 concurrent LLM calls.
- **Security**: No API keys in code; load from env vars. Use HTTPS for API calls.
- **Usability**: Command-line interface with arguments for input directory, output file, and LLM model selection.
- **Maintainability**: Modular code (e.g., separate modules for extraction, merging, utils). Unit tests for key functions. Integration test with sample transcripts and true LLM calls.

## 4. Architecture
- **Modules**:
  - `transcript_loader.py`: Load and filter transcripts.
  - `idea_extractor.py`: LLM-based extraction per transcript.
  - `idea_merger.py`: LLM-based merging.
  - `main.py`: Orchestrate the process (parallel processing, caching).
  - `utils.py`: Helpers for caching, logging, LLM calls.
- **Data Flow**:
  1. Load/filter transcripts.
  2. Extract ideas in parallel (cached).
  3. Merge ideas sequentially or batched (to maintain global list state).
  4. Output merged JSON.
- **Dependencies**: `openai` for LLM, `asyncio` for parallelism, `hashlib` for caching.

## 5. Implementation Notes
- **LLM Selection**: Default to OpenRouter grok-4-fast:free for speed and cost.
- **Prompt Engineering**: Refine prompts based on initial tests to ensure single-line ideas and accurate merging.
- **Testing**: Include sample transcripts and expected outputs. Mock LLM for unit tests.
- **Cost Monitoring**: Track total tokens used per run.
- **Edge Cases**: Empty transcripts, no ideas, LLM failures, overlapping ideas that shouldn't merge.
- **Architectural decisions**: During the implementation, track architectural decisions in a separate file (e.g., `arch_decisions.md`).

This spec provides a complete blueprint. Review it, and let me know any changes before implementation. If needed, I can start coding based on this once approved.
