import { randomUUID } from "node:crypto";
import { Mutex } from "async-mutex";
import pLimit from "p-limit";
import { z } from "zod";
import type { ExtractedIdea, IdeaColor, MergedIdea } from "../domain/types.js";
import { mergeActionSchema } from "../domain/types.js";
import type { OpenRouterClient } from "../clients/openrouter.js";
import { logger } from "../utils/logger.js";
import type { StatsTracker } from "../metrics/stats.js";

const batchResponseSchema = z.object({
  results: z.array(
    mergeActionSchema.extend({
      anchorId: z.string(),
    })
  ),
});

interface PromptExistingIdea {
  id: string;
  title: string;
  description?: string;
  recentColors: string[];
}

interface PromptAnchor {
  id: string;
  summary: string;
  detail?: string | null;
}

export interface IdeaMergerOptions {
  client: OpenRouterClient;
  stats: StatsTracker;
  model: string;
  maxConcurrency: number;
  batchSize?: number;
}

export class IdeaMerger {
  private readonly limit: ReturnType<typeof pLimit>;

  private readonly mutex = new Mutex();

  private readonly mergedIdeas: MergedIdea[] = [];

  private readonly ideaMap = new Map<string, MergedIdea>();

  private readonly batchSize: number;

  constructor(private readonly options: IdeaMergerOptions) {
    this.limit = pLimit(Math.max(1, options.maxConcurrency));
    this.batchSize = options.batchSize ?? 10;
  }

  private static deriveTags(summary: string, detail?: string, existing?: string[]): string[] {
    const base = `${summary} ${detail ?? ""}`.toLowerCase();
    const tags = new Set(existing ?? []);
    if (base.includes("agile") || base.includes("sprint") || base.includes("scrum")) {
      tags.add("agile");
    }
    if (base.includes("innovation") || base.includes("innovate")) {
      tags.add("innovation");
    }
    if (base.includes("factory") || base.includes("manufacturing")) {
      tags.add("manufacturing");
    }
    if (base.includes("leader") || base.includes("leadership")) {
      tags.add("leadership");
    }
    return Array.from(tags);
  }

  private static deriveMetrics(values: (string | undefined)[]): string[] {
    const metrics = new Set<string>();
    for (const value of values) {
      if (!value) continue;
      const matches = value.match(/\b\d+[\d,.]*\b/g);
      if (matches) {
        matches.forEach((match) => metrics.add(match.replace(/[,]/g, "")));
      }
    }
    return Array.from(metrics);
  }

  async merge(anchors: ExtractedIdea[]): Promise<MergedIdea[]> {
    const batches: ExtractedIdea[][] = [];
    for (let i = 0; i < anchors.length; i += this.batchSize) {
      batches.push(anchors.slice(i, i + this.batchSize));
    }

    await Promise.all(batches.map((batch) => this.limit(() => this.processBatch(batch))));

    return this.mutex.runExclusive(() => this.mergedIdeas.map((idea) => JSON.parse(JSON.stringify(idea))));
  }

  private async processBatch(batch: ExtractedIdea[]): Promise<void> {
    if (batch.length === 0) {
      return;
    }

    const anchorsForPrompt = batch.map<PromptAnchor>((anchor) => ({
      id: anchor.id,
      summary: anchor.summary,
      detail: anchor.detail,
    }));

    const existingIdeas = await this.snapshotExistingIdeas();

    await this.options.stats.increment("llmCalls");

    const response = await this.options.client.chat(
      [
        {
          role: "system",
          content:
            "You merge Tesla operational ideas. Decide for each anchor idea whether it should create a new merged idea, add detail (color) to existing merged ideas, or both. Respond strictly with JSON using the provided schema.",
        },
        {
          role: "user",
          content: this.buildPrompt(existingIdeas, anchorsForPrompt),
        },
      ],
      { responseFormat: "json_object", temperature: 0.1 }
    );

    const parsed = batchResponseSchema.safeParse(this.parseJson(response));
    if (!parsed.success) {
      throw new Error(`Failed to parse merge response: ${parsed.error.message}`);
    }

    await this.applyResults(batch, parsed.data.results);
  }

  private async applyResults(batch: ExtractedIdea[], results: z.infer<typeof batchResponseSchema>["results"]): Promise<void> {
    await this.mutex.runExclusive(async () => {
      for (const result of results) {
        const anchor = batch.find((item) => item.id === result.anchorId);
        if (!anchor) {
          logger.warn({ anchorId: result.anchorId }, "Merge result referenced unknown anchor");
          continue;
        }

        if (result.action === "new" || result.action === "both") {
          if (!result.newIdea) {
            logger.warn({ anchorId: anchor.id }, "New idea action missing newIdea payload");
          } else {
            const mergedIdea = this.createMergedIdea(anchor, result.newIdea.title, result.newIdea.description);
            this.mergedIdeas.push(mergedIdea);
            this.ideaMap.set(mergedIdea.id, mergedIdea);
          }
        }

        if (result.action === "merge" || result.action === "both") {
          if (!result.merges || result.merges.length === 0) {
            logger.warn({ anchorId: anchor.id }, "Merge action missing target merges");
          } else {
            for (const mergeTarget of result.merges) {
              const targetIdea = this.ideaMap.get(mergeTarget.targetId);
              if (!targetIdea) {
                logger.warn(
                  { anchorId: anchor.id, targetId: mergeTarget.targetId },
                  "Merge action referenced unknown idea"
                );
                continue;
              }

              const color: IdeaColor = {
                id: randomUUID(),
                ideaId: targetIdea.id,
                summary: anchor.summary,
                text: anchor.detail,
                sourceTranscriptId: anchor.transcriptId,
                transcriptHash: anchor.transcriptHash,
                sourceIdeaId: anchor.id,
                reference: anchor.location ?? undefined,
                quote: anchor.quote,
                speaker: anchor.speaker,
                timestamp: anchor.timestamp,
                sourceFile: anchor.sourceFile,
                context: anchor.context,
                contextWindow: anchor.contextWindow,
                tags: IdeaMerger.deriveTags(anchor.summary, anchor.detail, anchor.tags),
                metrics: anchor.metrics ?? IdeaMerger.deriveMetrics([
                  anchor.summary,
                  anchor.detail,
                  anchor.context,
                ]),
                tone: anchor.tone,
                relatedSummaries: anchor.relatedSummaries,
              };

              targetIdea.colors.push(color);

              if (!targetIdea.anchors.includes(anchor.summary)) {
                targetIdea.anchors.push(anchor.summary);
              }
            }
          }
        }
      }
    });
  }

  private createMergedIdea(anchor: ExtractedIdea, title: string, description?: string): MergedIdea {
    const ideaId = randomUUID();
    const color: IdeaColor = {
      id: randomUUID(),
      ideaId,
      summary: anchor.summary,
      text: anchor.detail,
      sourceTranscriptId: anchor.transcriptId,
      transcriptHash: anchor.transcriptHash,
      sourceIdeaId: anchor.id,
      reference: anchor.location ?? undefined,
      quote: anchor.quote,
      speaker: anchor.speaker,
      timestamp: anchor.timestamp,
      sourceFile: anchor.sourceFile,
      context: anchor.context,
      contextWindow: anchor.contextWindow,
      tags: IdeaMerger.deriveTags(anchor.summary, anchor.detail, anchor.tags),
      metrics: anchor.metrics ?? IdeaMerger.deriveMetrics([
        anchor.summary,
        anchor.detail,
        anchor.context,
      ]),
      tone: anchor.tone,
      relatedSummaries: anchor.relatedSummaries,
    };

    return {
      id: ideaId,
      title: title.trim(),
      description: description?.trim(),
      anchors: [anchor.summary],
      colors: [color],
    } satisfies MergedIdea;
  }

  private async snapshotExistingIdeas(): Promise<PromptExistingIdea[]> {
    return this.mutex.runExclusive(() =>
      this.mergedIdeas.map((idea) => ({
        id: idea.id,
        title: idea.title,
        description: idea.description,
        recentColors: idea.colors.slice(-3).map((color) => color.summary),
      }))
    );
  }

  private parseJson(raw: string): unknown {
    try {
      return JSON.parse(raw);
    } catch (error) {
      logger.warn({ raw }, "Merge response was not valid JSON, attempting recovery");
      const match = raw.match(/```json\s*([\s\S]*?)```/i);
      if (match) {
        return JSON.parse(match[1]);
      }
      throw error;
    }
  }

  private buildPrompt(existingIdeas: PromptExistingIdea[], anchors: PromptAnchor[]): string {
    const existingBlock = existingIdeas.length
      ? existingIdeas
          .map((idea) => {
            const colors = idea.recentColors.map((color, index) => `${index + 1}. ${color}`).join("; ");
            return `- id: ${idea.id}\n  title: ${idea.title}\n  description: ${idea.description ?? ""}\n  recent_colors: ${colors}`;
          })
          .join("\n")
      : "None";

    const anchorsBlock = anchors
      .map((anchor) => {
        return `- id: ${anchor.id}\n  summary: ${anchor.summary}\n  detail: ${anchor.detail ?? ""}`;
      })
      .join("\n");

    return `Existing merged ideas:\n${existingBlock}\n\nAnchors to classify:\n${anchorsBlock}\n\nRespond with JSON:\n{\n  "results": [\n    {\n      "anchorId": "<anchor id>",\n      "action": "new" | "merge" | "both",\n      "newIdea": {\n        "title": "...",\n        "description": "optional"\n      },\n      "merges": [\n        {\n          "targetId": "<existing idea id>"\n        }\n      ]\n    }\n  ]\n}\nWhen merging, rely on the anchor's own wording; do not create new paraphrased summaries.`;
  }
}
