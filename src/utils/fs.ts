import { createHash } from "node:crypto";
import fs from "node:fs";
import fsp from "fs-extra";
import path from "node:path";
import { pipeline } from "node:stream/promises";
import { Readable } from "node:stream";
import { fileURLToPath } from "node:url";

export async function readFileIfExists(filePath: string): Promise<string | null> {
  try {
    return await fsp.readFile(filePath, "utf-8");
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") {
      return null;
    }
    throw error;
  }
}

export async function writeFileAtomic(filePath: string, content: string): Promise<void> {
  const tempPath = `${filePath}.tmp-${Date.now()}`;
  await fsp.ensureDir(path.dirname(filePath));
  await fsp.writeFile(tempPath, content, "utf-8");
  await fsp.rename(tempPath, filePath);
}

export async function hashFile(filePath: string): Promise<string> {
  const hash = createHash("sha256");
  const stream = fs.createReadStream(filePath);
  stream.on("data", (chunk) => hash.update(chunk));
  await new Promise<void>((resolve, reject) => {
    stream.on("end", () => resolve());
    stream.on("error", (err) => reject(err));
  });
  return hash.digest("hex");
}

export async function hashString(content: string): Promise<string> {
  return createHash("sha256").update(content).digest("hex");
}

export async function streamToString(stream: Readable): Promise<string> {
  const chunks: Buffer[] = [];
  for await (const chunk of stream) {
    chunks.push(typeof chunk === "string" ? Buffer.from(chunk) : chunk);
  }
  return Buffer.concat(chunks).toString("utf-8");
}

export function resolveRelativePath(baseUrl: string, relative: string): string {
  const basePath = fileURLToPath(baseUrl);
  const dir = path.dirname(basePath);
  return path.resolve(dir, relative);
}

export async function copyFile(src: string, dest: string): Promise<void> {
  await fsp.ensureDir(path.dirname(dest));
  await pipeline(fs.createReadStream(src), fs.createWriteStream(dest));
}
