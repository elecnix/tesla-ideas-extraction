import path from "node:path";
import fs from "fs-extra";
import { z } from "zod";
import {
  extractionCacheSchema,
  type ExtractionCache,
  type Transcript,
  EXTRACTION_CACHE_VERSION,
} from "../domain/types.js";

function sanitizeName(input: string): string {
  return input.replace(/[^a-z0-9-_]/gi, "_").slice(0, 120);
}

const cacheFileSchema = extractionCacheSchema;

export class ExtractionCacheStore {
  constructor(private readonly baseDir: string) {}

  private buildFilePath(transcript: Transcript): string {
    const safeId = sanitizeName(transcript.id);
    const key = `${safeId}-${transcript.hash}`;
    return path.join(this.baseDir, `${key}.json`);
  }

  async read(transcript: Transcript): Promise<ExtractionCache | null> {
    const filePath = this.buildFilePath(transcript);
    try {
      const raw = await fs.readFile(filePath, "utf-8");
      const parsed = cacheFileSchema.safeParse(JSON.parse(raw));
      if (!parsed.success) {
        await fs.remove(filePath);
        return null;
      }
      if (
        parsed.data.transcriptHash !== transcript.hash ||
        parsed.data.cacheVersion !== EXTRACTION_CACHE_VERSION
      ) {
        await fs.remove(filePath);
        return null;
      }
      return parsed.data;
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code === "ENOENT") {
        return null;
      }
      throw error;
    }
  }

  async write(transcript: Transcript, cache: ExtractionCache): Promise<void> {
    const filePath = this.buildFilePath(transcript);
    await fs.ensureDir(path.dirname(filePath));
    await fs.writeFile(filePath, JSON.stringify(cache, null, 2), "utf-8");
  }

  async clear(transcript: Transcript): Promise<void> {
    const filePath = this.buildFilePath(transcript);
    await fs.remove(filePath);
  }

  async clearAll(): Promise<void> {
    await fs.emptyDir(this.baseDir);
  }
}
