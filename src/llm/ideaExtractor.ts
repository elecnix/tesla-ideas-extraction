import path from "node:path";
import { randomUUID } from "node:crypto";
import { setTimeout as delay } from "node:timers/promises";
import pLimit from "p-limit";
import { z } from "zod";
import type {
  ExtractedIdea,
  Transcript,
  ExtractionCache,
  RelevanceResult,
} from "../domain/types.js";
import { EXTRACTION_CACHE_VERSION } from "../domain/types.js";
import type { ExtractionCacheStore } from "../storage/extractionCache.js";
import { logger } from "../utils/logger.js";
import { extractFirstJsonObject } from "../utils/json.js";
import type { OpenRouterClient } from "../clients/openrouter.js";
import type { StatsTracker } from "../metrics/stats.js";

const relevanceResponseSchema = z.object({
  relevant: z.boolean(),
  reason: z.string().min(1),
});

const iterationLocationSchema = z
  .object({
    line: z.number().int().nonnegative().optional(),
    start: z.number().nonnegative().optional(),
    duration: z.number().nonnegative().optional(),
  })
  .optional();

const iterationReferenceSchema = z.object({
  type: z.literal("segment"),
  start: z.number().nonnegative().optional(),
  duration: z.number().nonnegative().optional(),
  text: z.string().optional(),
});

const extractionIterationSchema = z.object({
  ideas: z
    .array(
      z.object({
        summary: z.string(),
        detail: z.string().optional(),
        quote: z.string(),
        speaker: z.string().optional(),
        timestamp: z.string().optional(),
        context: z
          .object({
            before: z.string().optional(),
            after: z.string().optional(),
          })
          .optional(),
        contextText: z.string().optional(),
        tags: z.array(z.string()).optional(),
        metrics: z.array(z.string()).optional(),
        tone: z.string().optional(),
        relatedSummaries: z.array(z.string()).optional(),
        location: iterationLocationSchema,
        references: z.array(iterationReferenceSchema).optional(),
        frequency: z.number().int().nonnegative().optional(),
      })
    )
    .default([]),
});

export interface IdeaExtractorOptions {
  client: OpenRouterClient;
  cacheStore: ExtractionCacheStore;
  maxConcurrency: number;
  model: string;
  stats: StatsTracker;
  relevanceModel?: string;
}

interface IterationResult {
  newIdeas: ExtractedIdea[];
  totalIdeas: ExtractedIdea[];
  iterations: number;
}

const TAG_KEYWORDS: Record<string, string[]> = {
  agile: ["agile", "scrum", "kanban", "iteration", "sprint"],
  innovation: ["innovation", "innovate", "breakthrough", "r&d"],
  manufacturing: ["factory", "manufacturing", "production", "assembly"],
  leadership: ["leader", "leadership", "management", "executive"],
  metrics: ["kpi", "metric", "%", "ratio", "throughput"],
};

function deriveTags(baseText: string, detail?: string, provided?: string[]): string[] {
  const normalized = `${baseText} ${detail ?? ""}`.toLowerCase();
  const tags = new Set<string>();

  for (const [tag, keywords] of Object.entries(TAG_KEYWORDS)) {
    if (keywords.some((keyword) => normalized.includes(keyword))) {
      tags.add(tag);
    }
  }

  (provided ?? []).forEach((tag) => {
    if (tag.trim()) {
      tags.add(tag.trim().toLowerCase());
    }
  });

  return Array.from(tags);
}

function deriveMetrics(texts: (string | undefined)[]): string[] {
  const metrics = new Set<string>();
  for (const text of texts) {
    if (!text) continue;
    const matches = text.match(/\b\d+[\d,.]*\b/g);
    if (matches) {
      matches.forEach((match) => metrics.add(match.replace(/[,]/g, "")));
    }
  }
  return Array.from(metrics);
}

export class IdeaExtractor {
  private readonly limit: ReturnType<typeof pLimit>;

  constructor(private readonly options: IdeaExtractorOptions) {
    this.limit = pLimit(options.maxConcurrency);
  }

  async extract(transcripts: Transcript[]): Promise<ExtractedIdea[]> {
    const results = await Promise.all(
      transcripts.map((transcript) => this.limit(() => this.processTranscript(transcript)))
    );
    return results.flat();
  }

  private async processTranscript(transcript: Transcript): Promise<ExtractedIdea[]> {
    const { cacheStore, model } = this.options;
    const cached = await cacheStore.read(transcript);

    if (cached && cached.cacheVersion === EXTRACTION_CACHE_VERSION && cached.model === model) {
      await this.options.stats.increment("cacheHits");
      await this.options.stats.increment("transcriptsProcessed");
      await this.options.stats.increment("ideasExtracted", cached.ideas.length);
      return cached.ideas;
    }

    const relevance = await this.ensureRelevance(transcript, cached?.relevance);
    if (!relevance.relevant) {
      await this.options.stats.increment("transcriptsSkipped");
      await cacheStore.write(transcript, {
        cacheVersion: EXTRACTION_CACHE_VERSION,
        transcriptId: transcript.id,
        transcriptHash: transcript.hash,
        generatedAt: new Date().toISOString(),
        model,
        iterations: 0,
        ideas: [],
        relevance,
      });
      return [];
    }

    const { totalIdeas, iterations } = await this.iterativelyExtractIdeas(transcript);

    const cache: ExtractionCache = {
      cacheVersion: EXTRACTION_CACHE_VERSION,
      transcriptId: transcript.id,
      transcriptHash: transcript.hash,
      generatedAt: new Date().toISOString(),
      model,
      iterations,
      ideas: totalIdeas,
      relevance,
    };

    await cacheStore.write(transcript, cache);

    await this.options.stats.increment("transcriptsProcessed");
    await this.options.stats.increment("ideasExtracted", totalIdeas.length);

    return totalIdeas;
  }

  private async ensureRelevance(
    transcript: Transcript,
    cached?: RelevanceResult
  ): Promise<RelevanceResult> {
    if (cached && cached.model === this.options.relevanceModel) {
      return cached;
    }

    await this.options.stats.increment("llmCalls");

    const response = await this.options.client.chat(
      [
        {
          role: "system",
          content:
            "You are a relevance filter for transcripts about Tesla's agile practices and speed of innovation. Decide if the transcript primarily discusses Tesla operations, agile methodology at Tesla, or innovation speed at Tesla.",
        },
        {
          role: "user",
          content: `Transcript:\n${transcript.content}\n\nRespond in JSON with fields relevant (boolean) and reason (string).`,
        },
      ],
      { responseFormat: "json_object", temperature: 0 }
    );

    const parsed = relevanceResponseSchema.safeParse(this.parseJson(response));
    if (!parsed.success) {
      throw new Error(`Failed to parse relevance response: ${parsed.error.message}`);
    }

    return {
      relevant: parsed.data.relevant,
      reason: parsed.data.reason,
      checkedAt: new Date().toISOString(),
      model: this.options.relevanceModel ?? this.options.model,
    } satisfies RelevanceResult;
  }

  private async iterativelyExtractIdeas(transcript: Transcript): Promise<IterationResult> {
    const maxIterations = 10;
    const ideas: ExtractedIdea[] = [];
    let iterations = 0;

    while (iterations < maxIterations) {
      iterations += 1;
      const prompt = this.buildPrompt(transcript.content, ideas);

      await delay(Math.random() * 200);

      await this.options.stats.increment("llmCalls");
      const raw = await this.options.client.chat(
        [
          {
            role: "system",
            content:
              "You extract new, distinct ideas about Tesla agile and innovation practices. Only output ideas not already listed.",
          },
          {
            role: "user",
            content: prompt,
          },
        ],
        { responseFormat: "json_object", temperature: 0.2 }
      );

      const parsed = extractionIterationSchema.safeParse(this.parseJson(raw));
      if (!parsed.success) {
        throw new Error(`Failed iteration parse: ${parsed.error.message}`);
      }

      const sourceFile = path.basename(transcript.path);

      const newIdeas = parsed.data.ideas
        .map((idea) => {
          const contextWindow = idea.context
            ? {
                before: idea.context.before?.trim() || undefined,
                after: idea.context.after?.trim() || undefined,
              }
            : undefined;

          return {
            id: randomUUID(),
            summary: idea.summary.trim(),
            detail: idea.detail?.trim(),
            transcriptId: transcript.id,
            transcriptHash: transcript.hash,
            quote: idea.quote.trim(),
            speaker: idea.speaker?.trim(),
            timestamp: idea.timestamp?.trim(),
            sourceFile,
            context: idea.context
              ? [idea.context.before, idea.context.after]
                  .filter((part): part is string => Boolean(part && part.trim()))
                  .join("\n") || undefined
              : undefined,
            contextWindow,
            tags: idea.tags?.map((tag) => tag.trim()).filter(Boolean),
            metrics: idea.metrics?.map((metric) => metric.trim()).filter(Boolean),
            tone: idea.tone?.trim(),
            relatedSummaries: idea.relatedSummaries?.map((entry) => entry.trim()).filter(Boolean),
            frequency: idea.frequency,
            location: idea.location,
            references: idea.references?.filter(Boolean),
          } satisfies ExtractedIdea;
        })
        .filter((idea) => !ideas.some((existing) => existing.summary === idea.summary));

      if (newIdeas.length === 0) {
        break;
      }

      ideas.push(...newIdeas);

      if (newIdeas.length <= 1 || ideas.length >= 15) {
        break;
      }
    }

    return {
      newIdeas: ideas,
      totalIdeas: ideas,
      iterations,
    } satisfies IterationResult;
  }

  private parseJson(raw: string): unknown {
    try {
      return JSON.parse(raw);
    } catch (error) {
      const extracted = extractFirstJsonObject(raw);
      if (!extracted) {
        logger.error({ raw }, "Unable to extract JSON payload from LLM response");
        throw error;
      }
      return JSON.parse(extracted);
    }
  }

  private buildPrompt(transcript: string, existingIdeas: ExtractedIdea[]): string {
    const existingList = existingIdeas
      .map((idea, index) => `${index + 1}. ${idea.summary}${idea.detail ? ` — ${idea.detail}` : ""}`)
      .join("\n");

    return `Current extracted ideas:\n${existingList || "None"}\n\nTranscript:\n${transcript}\n\nReturn JSON with\n{\n  "ideas": [\n    {\n      "summary": "concise new idea not already listed",\n      "detail": "optional detail"\n    }\n  ]\n}\nEnsure each idea is distinct and specific. If no new ideas exist, return an empty array.`;
  }
}
