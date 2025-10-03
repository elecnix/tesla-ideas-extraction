import path from "node:path";
import { fileURLToPath } from "node:url";
import { z } from "zod";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const configSchema = z.object({
  transcriptsDir: z.string(),
  cacheDir: z.string().default(path.join(__dirname, "../cache")),
  outputDir: z.string().default(path.join(__dirname, "../outputs")),
  model: z.string().default("x-ai/grok-4-fast:free"),
  maxParallelExtractions: z.number().int().positive().default(5),
  maxParallelMerges: z.number().int().positive().default(3),
  llmBaseUrl: z.string().default("https://openrouter.ai/api/v1"),
  transcriptFormats: z.array(z.string()).default(["json", "txt"]),
  forceCacheReset: z.boolean().default(false),
});

export type AppConfig = z.infer<typeof configSchema>;

export function loadConfig(overrides: Partial<AppConfig> = {}): AppConfig {
  const forceCacheResetEnv = process.env.FORCE_CACHE_RESET;

  const merged = {
    transcriptsDir: process.env.TRANSCRIPTS_DIR ?? overrides.transcriptsDir,
    cacheDir: process.env.CACHE_DIR ?? overrides.cacheDir,
    outputDir: process.env.OUTPUT_DIR ?? overrides.outputDir,
    model: process.env.LLM_MODEL ?? overrides.model,
    llmBaseUrl: process.env.LLM_BASE_URL ?? overrides.llmBaseUrl,
    maxParallelExtractions:
      process.env.MAX_PARALLEL_EXTRACTIONS !== undefined
        ? Number(process.env.MAX_PARALLEL_EXTRACTIONS)
        : overrides.maxParallelExtractions,
    maxParallelMerges:
      process.env.MAX_PARALLEL_MERGES !== undefined
        ? Number(process.env.MAX_PARALLEL_MERGES)
        : overrides.maxParallelMerges,
    transcriptFormats:
      overrides.transcriptFormats ?? ["json", "txt"],
    forceCacheReset:
      forceCacheResetEnv !== undefined
        ? forceCacheResetEnv.trim().toLowerCase() === "true" || forceCacheResetEnv === "1"
        : overrides.forceCacheReset,
  } satisfies Partial<AppConfig>;

  const parsed = configSchema.safeParse(merged);
  if (!parsed.success) {
    throw new Error(`Invalid configuration: ${parsed.error.message}`);
  }

  return parsed.data;
}
