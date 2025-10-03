import path from "node:path";
import fs from "fs-extra";
import type { AppConfig } from "../config.js";
import { loadTranscripts } from "../transcripts/loader.js";
import { ExtractionCacheStore } from "../storage/extractionCache.js";
import { IdeaExtractor } from "../llm/ideaExtractor.js";
import { IdeaMerger } from "../llm/ideaMerger.js";
import { writeOutputs } from "../output/writer.js";
import { StatsTracker } from "../metrics/stats.js";
import { OpenRouterClient } from "../clients/openrouter.js";
import { logger } from "../utils/logger.js";

export interface PipelineRunOptions {
  config: AppConfig;
  apiKey: string | undefined;
}

export async function runPipeline({ config, apiKey }: PipelineRunOptions): Promise<void> {
  if (!config.transcriptsDir) {
    throw new Error("Transcripts directory must be provided via config or CLI");
  }

  if (!apiKey) {
    throw new Error("OPENROUTER_API_KEY is required to run the pipeline");
  }

  const stats = new StatsTracker();

  const transcriptsDir = path.resolve(config.transcriptsDir);
  const cacheDir = path.resolve(config.cacheDir);
  const outputDir = path.resolve(config.outputDir);

  logger.info(
    {
      transcriptsDir,
      cacheDir,
      outputDir,
      model: config.model,
    },
    "Starting Tesla ideas pipeline"
  );

  await fs.ensureDir(cacheDir);
  await fs.ensureDir(outputDir);

  const allowedFormats = config.transcriptFormats
    .map((format) => format.toLowerCase())
    .filter((format): format is "json" | "txt" => format === "json" || format === "txt");

  const cacheStore = new ExtractionCacheStore(cacheDir);

  if (config.forceCacheReset) {
    logger.warn("Force cache reset requested; clearing extraction cache directory");
    await cacheStore.clearAll();
  }

  const { transcripts, totalFiles, skipped } = await loadTranscripts({
    transcriptsDir,
    logger,
    allowedFormats: allowedFormats.length > 0 ? allowedFormats : undefined,
  });

  await stats.set("transcriptsTotal", totalFiles);
  await stats.set("transcriptsSkipped", skipped.length);

  if (transcripts.length === 0) {
    logger.warn({ totalFiles, skipped: skipped.length }, "No relevant transcripts to process");
    const snapshot = await stats.snapshot();
    await writeOutputs({ ideas: [], outputDir, stats: snapshot });
    return;
  }

  const client = new OpenRouterClient(apiKey, config.llmBaseUrl, config.model);
  const extractor = new IdeaExtractor({
    client,
    cacheStore,
    maxConcurrency: config.maxParallelExtractions,
    model: config.model,
    stats,
  });

  const ideas = await extractor.extract(transcripts);

  const merger = new IdeaMerger({
    client,
    stats,
    model: config.model,
    maxConcurrency: config.maxParallelMerges,
  });

  const mergedIdeas = await merger.merge(ideas);

  const finalStats = await stats.snapshot();
  logger.info({ stats: finalStats, ideas: mergedIdeas.length }, "Pipeline complete");

  await writeOutputs({ ideas: mergedIdeas, outputDir, stats: finalStats });
}
