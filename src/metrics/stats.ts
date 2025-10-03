import { Mutex } from "async-mutex";

export interface PipelineStats {
  transcriptsTotal: number;
  transcriptsSkipped: number;
  transcriptsProcessed: number;
  ideasExtracted: number;
  cacheHits: number;
  llmCalls: number;
}

const defaultStats: PipelineStats = {
  transcriptsTotal: 0,
  transcriptsSkipped: 0,
  transcriptsProcessed: 0,
  ideasExtracted: 0,
  cacheHits: 0,
  llmCalls: 0,
};

export class StatsTracker {
  private readonly mutex = new Mutex();

  private readonly stats: PipelineStats = { ...defaultStats };

  async increment<K extends keyof PipelineStats>(key: K, amount = 1): Promise<void> {
    await this.mutex.runExclusive(() => {
      this.stats[key] += amount;
    });
  }

  async set<K extends keyof PipelineStats>(key: K, value: PipelineStats[K]): Promise<void> {
    await this.mutex.runExclusive(() => {
      this.stats[key] = value;
    });
  }

  async snapshot(): Promise<PipelineStats> {
    return this.mutex.runExclusive(() => ({ ...this.stats }));
  }
}
