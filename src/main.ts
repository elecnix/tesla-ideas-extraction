#!/usr/bin/env node
import process from "node:process";
import { Command } from "commander";
import dotenv from "dotenv";
import { loadConfig } from "./config.js";
import { runPipeline } from "./orchestrator/pipeline.js";
import { logger } from "./utils/logger.js";

dotenv.config();

const program = new Command();

program
  .name("tesla-ideas-pipeline")
  .description("Extract and merge Tesla operational ideas from transcripts")
  .option("-t, --transcripts <dir>", "Directory containing transcripts")
  .option("-c, --cache <dir>", "Directory to store extraction cache files")
  .option("-o, --output <dir>", "Directory where outputs will be written")
  .option("-m, --model <name>", "LLM model identifier")
  .option("--parallel-extract <number>", "Maximum parallel LLM extractions", parseInteger)
  .option("--parallel-merge <number>", "Maximum parallel LLM merge requests", parseInteger)
  .option(
    "--formats <list>",
    "Comma separated list of allowed transcript formats (e.g., json,txt)"
  )
  .option("--reset-cache", "Force cache invalidation before running");

program.parse();

function parseInteger(value: string): number | undefined {
  const parsed = Number.parseInt(value, 10);
  return Number.isNaN(parsed) ? undefined : parsed;
}

const options = program.opts<{
  transcripts?: string;
  cache?: string;
  output?: string;
  model?: string;
  parallelExtract?: number;
  parallelMerge?: number;
  formats?: string;
  resetCache?: boolean;
}>();

const transcriptFormats = options.formats
  ? options.formats
      .split(",")
      .map((entry) => entry.trim().toLowerCase())
      .filter(Boolean)
  : undefined;

(async () => {
  try {
    const config = loadConfig({
      transcriptsDir: options.transcripts,
      cacheDir: options.cache,
      outputDir: options.output,
      model: options.model,
      maxParallelExtractions: options.parallelExtract,
      maxParallelMerges: options.parallelMerge,
      transcriptFormats,
      forceCacheReset: options.resetCache,
    });

    await runPipeline({
      config,
      apiKey: process.env.OPENROUTER_API_KEY,
    });
  } catch (error) {
    logger.error({ err: error }, "Pipeline failed");
    process.exitCode = 1;
  }
})();
