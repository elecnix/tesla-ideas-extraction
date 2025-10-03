import path from "node:path";
import fs from "fs-extra";
import type { MergedIdea } from "../domain/types.js";
import type { PipelineStats } from "../metrics/stats.js";

function slugify(input: string): string {
  return input
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 120) || "idea";
}

function buildIdeaMarkdown(idea: MergedIdea): string {
  const colors = idea.colors
    .map((color) => {
      const lines = [
        `- **Source Transcript**: ${color.sourceTranscriptId}`,
        `- **Summary**: ${color.summary}`,
      ];
      if (color.text) {
        lines.push(`- **Detail**: ${color.text}`);
      }
      lines.push(`- **Reference Idea**: ${color.sourceIdeaId}`);
      return lines.join("\n");
    })
    .join("\n\n");

  const anchorsBlock = idea.anchors.map((anchor) => `- ${anchor}`).join("\n");

  return `# ${idea.title}

${idea.description ?? ""}

## Anchors
${anchorsBlock}

## Color Contributions
${colors || "No additional color yet."}
`;
}

function buildMergedMarkdown(ideas: MergedIdea[], stats: PipelineStats): string {
  const list = ideas
    .map((idea, index) => `### ${index + 1}. ${idea.title}
- Anchors: ${idea.anchors.length}
- Colors: ${idea.colors.length}
- Description: ${idea.description ?? "(none)"}
`)
    .join("\n");

  return `# Tesla Merged Ideas

- Total Ideas: ${ideas.length}
- Transcripts Processed: ${stats.transcriptsProcessed}
- Transcripts Skipped: ${stats.transcriptsSkipped}
- Ideas Extracted: ${stats.ideasExtracted}
- Cache Hits: ${stats.cacheHits}
- LLM Calls: ${stats.llmCalls}

${list}`;
}

export interface WriteOutputsOptions {
  ideas: MergedIdea[];
  outputDir: string;
  stats: PipelineStats;
}

export async function writeOutputs({ ideas, outputDir, stats }: WriteOutputsOptions): Promise<void> {
  const ideasDir = path.join(outputDir, "ideas");
  await fs.emptyDir(ideasDir);

  const jsonFile = path.join(outputDir, "merged_ideas.json");
  await fs.writeJson(
    jsonFile,
    {
      generatedAt: new Date().toISOString(),
      totalIdeas: ideas.length,
      stats,
      ideas,
    },
    { spaces: 2 }
  );

  const markdownAll = path.join(outputDir, "merged_ideas.md");
  await fs.writeFile(markdownAll, buildMergedMarkdown(ideas, stats), "utf-8");

  for (const idea of ideas) {
    const slug = slugify(idea.title);
    const filePath = path.join(ideasDir, `${slug}.md`);
    await fs.writeFile(filePath, buildIdeaMarkdown(idea), "utf-8");
  }
}
