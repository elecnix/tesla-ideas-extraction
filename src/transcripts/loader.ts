import { promises as fsPromises, Dirent } from "node:fs";
import path from "node:path";
import type { Logger } from "pino";
import { z } from "zod";
import type { Transcript } from "../domain/types.js";
import { hashString } from "../utils/fs.js";
import { logger } from "../utils/logger.js";

const transcriptJsonSchema = z.object({
  video_id: z.string(),
  source: z.string().optional(),
  lang: z.string().nullable().optional(),
  segments: z
    .array(
      z.object({
        start: z.number().nonnegative().optional(),
        duration: z.number().nonnegative().optional(),
        text: z.string(),
      })
    )
    .optional(),
});

type TranscriptJson = z.infer<typeof transcriptJsonSchema>;

export interface LoadTranscriptsOptions {
  transcriptsDir: string;
  logger?: Logger;
  allowedFormats?: ("json" | "txt")[];
  keywords?: string[];
  followSymlinks?: boolean;
}

export interface LoadTranscriptsResult {
  transcripts: Transcript[];
  totalFiles: number;
  skipped: { path: string; reason: string }[];
}

const DEFAULT_KEYWORDS = [
  "tesla",
  "elon",
  "agile",
  "innovation",
  "joe justice",
  "gigafactory",
  "speed",
  "factory",
  "manufacturing",
];

function containsKeyword(content: string, keywords: string[]): boolean {
  const lowerContent = content.toLowerCase();
  return keywords.some((keyword) => lowerContent.includes(keyword));
}

async function* walkDirectory(
  dir: string,
  followSymlinks: boolean
): AsyncGenerator<{ path: string; dirent: Dirent }> {
  const entries = await fsPromises.readdir(dir, { withFileTypes: true });

  for (const dirent of entries) {
    const fullPath = path.join(dir, dirent.name);

    if (dirent.isDirectory()) {
      yield* walkDirectory(fullPath, followSymlinks);
      continue;
    }

    if (dirent.isSymbolicLink()) {
      if (!followSymlinks) {
        continue;
      }
      try {
        const stats = await fsPromises.stat(fullPath);
        if (stats.isDirectory()) {
          yield* walkDirectory(fullPath, followSymlinks);
          continue;
        }
        if (!stats.isFile()) {
          continue;
        }
      } catch {
        continue;
      }
    }

    if (dirent.isFile()) {
      yield { path: fullPath, dirent };
    }
  }
}

function detectFormat(filePath: string): "json" | "txt" | null {
  const ext = path.extname(filePath).toLowerCase();
  if (ext === ".json") return "json";
  if (ext === ".txt") return "txt";
  return null;
}

async function readTranscriptJson(filePath: string): Promise<Transcript> {
  const raw = await fsPromises.readFile(filePath, "utf-8");
  const parsed = transcriptJsonSchema.safeParse(JSON.parse(raw));
  if (!parsed.success) {
    throw new Error(`Invalid transcript JSON at ${filePath}: ${parsed.error.message}`);
  }

  const segments = (parsed.data.segments ?? []) as NonNullable<TranscriptJson["segments"]>;
  const combinedText = segments.map((segment) => segment.text).join("\n");
  const hashSource = combinedText.length > 0 ? combinedText : raw;
  const hash = await hashString(hashSource);

  return {
    id: parsed.data.video_id,
    path: filePath,
    hash,
    language: parsed.data.lang ?? undefined,
    format: "json",
    content: combinedText.length > 0 ? combinedText : raw,
    segments,
  } satisfies Transcript;
}

async function readTranscriptText(filePath: string): Promise<Transcript> {
  const content = await fsPromises.readFile(filePath, "utf-8");
  const hash = await hashString(content);
  const id = path.basename(filePath, path.extname(filePath));

  return {
    id,
    path: filePath,
    hash,
    format: "txt",
    content,
  } satisfies Transcript;
}

export async function loadTranscripts({
  transcriptsDir,
  logger: providedLogger,
  allowedFormats = ["json", "txt"],
  keywords = DEFAULT_KEYWORDS,
  followSymlinks = false,
}: LoadTranscriptsOptions): Promise<LoadTranscriptsResult> {
  const log = providedLogger ?? logger;
  const transcripts: Transcript[] = [];
  const skipped: { path: string; reason: string }[] = [];
  let totalFiles = 0;

  for await (const { path: filePath } of walkDirectory(transcriptsDir, followSymlinks)) {
    totalFiles += 1;

    const format = detectFormat(filePath);
    if (!format || !allowedFormats.includes(format)) {
      skipped.push({ path: filePath, reason: "unsupported_format" });
      log.debug({ file: filePath }, "Skipping transcript due to unsupported format");
      continue;
    }

    try {
      const transcript =
        format === "json"
          ? await readTranscriptJson(filePath)
          : await readTranscriptText(filePath);

      if (!containsKeyword(transcript.content, keywords)) {
        skipped.push({ path: filePath, reason: "heuristic_irrelevant" });
        log.debug({ transcript: transcript.id }, "Skipping transcript due to heuristic irrelevance");
        continue;
      }

      transcripts.push(transcript);
    } catch (error) {
      skipped.push({ path: filePath, reason: "error" });
      log.error({ error, file: filePath }, "Failed to load transcript");
    }
  }

  log.info(
    { totalFiles, processed: transcripts.length, skipped: skipped.length },
    "Transcript loading complete"
  );

  return { transcripts, totalFiles, skipped };
}
