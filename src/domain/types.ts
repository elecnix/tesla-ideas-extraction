import { z } from "zod";

export const transcriptFormatSchema = z.union([
  z.literal("json"),
  z.literal("txt"),
]);

export type TranscriptFormat = z.infer<typeof transcriptFormatSchema>;

export const transcriptSegmentSchema = z.object({
  start: z.number().nonnegative().optional(),
  duration: z.number().nonnegative().optional(),
  text: z.string(),
});

export type TranscriptSegment = z.infer<typeof transcriptSegmentSchema>;

export const transcriptSchema = z.object({
  id: z.string(),
  path: z.string(),
  hash: z.string(),
  language: z.string().optional(),
  format: transcriptFormatSchema,
  content: z.string(),
  segments: z.array(transcriptSegmentSchema).optional(),
});

export type Transcript = z.infer<typeof transcriptSchema>;

export const ideaContextSchema = z.object({
  before: z.string().optional(),
  after: z.string().optional(),
});

export const extractedIdeaSchema = z.object({
  id: z.string(),
  summary: z.string(),
  detail: z.string().optional(),
  transcriptId: z.string(),
  transcriptHash: z.string(),
  location: z.object({
    start: z.number().nonnegative().optional(),
    duration: z.number().nonnegative().optional(),
    line: z.number().int().nonnegative().optional(),
  }).optional(),
  quote: z.string(),
  speaker: z.string().optional(),
  timestamp: z.string().optional(),
  sourceFile: z.string(),
  context: z.string().optional(),
  contextWindow: ideaContextSchema.optional(),
  tags: z.array(z.string()).optional(),
  metrics: z.array(z.string()).optional(),
  tone: z.string().optional(),
  relatedSummaries: z.array(z.string()).optional(),
  frequency: z.number().int().nonnegative().optional(),
  references: z.array(
    z.object({
      type: z.literal("segment"),
      start: z.number().nonnegative().optional(),
      duration: z.number().nonnegative().optional(),
      text: z.string().optional(),
    })
  ).optional(),
});

export type ExtractedIdea = z.infer<typeof extractedIdeaSchema>;

export const ideaColorSchema = z.object({
  id: z.string(),
  ideaId: z.string(),
  summary: z.string(),
  sourceTranscriptId: z.string(),
  transcriptHash: z.string(),
  sourceIdeaId: z.string(),
  reference: z.object({
    start: z.number().nonnegative().optional(),
    duration: z.number().nonnegative().optional(),
    line: z.number().int().nonnegative().optional(),
  }).optional(),
  quote: z.string(),
  speaker: z.string().optional(),
  timestamp: z.string().optional(),
  sourceFile: z.string(),
  context: z.string().optional(),
  contextWindow: ideaContextSchema.optional(),
  tags: z.array(z.string()).optional(),
  metrics: z.array(z.string()).optional(),
  tone: z.string().optional(),
  text: z.string().optional(),
  relatedSummaries: z.array(z.string()).optional(),
});

export type IdeaColor = z.infer<typeof ideaColorSchema>;

export const mergedIdeaSchema = z.object({
  id: z.string(),
  title: z.string(),
  anchors: z.array(z.string()),
  description: z.string().optional(),
  colors: z.array(ideaColorSchema),
});

export type MergedIdea = z.infer<typeof mergedIdeaSchema>;

export const relevanceResultSchema = z.object({
  relevant: z.boolean(),
  reason: z.string(),
  checkedAt: z.string(),
  model: z.string(),
});

export type RelevanceResult = z.infer<typeof relevanceResultSchema>;

export const EXTRACTION_CACHE_VERSION = "iterative_v2";

export const extractionCacheSchema = z.object({
  cacheVersion: z.string(),
  transcriptId: z.string(),
  transcriptHash: z.string(),
  generatedAt: z.string(),
  model: z.string(),
  iterations: z.number().int().nonnegative(),
  ideas: z.array(extractedIdeaSchema),
  relevance: relevanceResultSchema.optional(),
});

export type ExtractionCache = z.infer<typeof extractionCacheSchema>;

export const mergeActionSchema = z.object({
  action: z.union([
    z.literal("new"),
    z.literal("merge"),
    z.literal("both"),
  ]),
  newIdea: z
    .object({
      title: z.string(),
      description: z.string().optional(),
    })
    .optional(),
  merges: z
    .array(
      z.object({
        targetId: z.string(),
      })
    )
    .optional(),
});

export type MergeAction = z.infer<typeof mergeActionSchema>;

export interface PipelineStatistics {
  transcriptsTotal: number;
  transcriptsSkipped: number;
  transcriptsProcessed: number;
  ideasExtracted: number;
  cacheHits: number;
  llmCalls: number;
}
