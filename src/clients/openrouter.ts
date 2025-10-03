import { setTimeout as delay } from "node:timers/promises";
import { fetch } from "undici";
import { z } from "zod";
import { logger } from "../utils/logger.js";

const openRouterResponseSchema = z.object({
  id: z.string(),
  choices: z.array(
    z.object({
      message: z.object({
        role: z.string(),
        content: z.string(),
      }),
    })
  ),
});

export interface ChatMessage {
  role: "system" | "user" | "assistant";
  content: string;
}

export interface ChatOptions {
  temperature?: number;
  responseFormat?: "json_object" | "text";
}

export class OpenRouterClient {
  constructor(
    private readonly apiKey: string,
    private readonly baseUrl: string,
    private readonly model: string,
    private readonly maxRetries = Infinity,
    private readonly loggerInstance = logger
  ) {}

  async chat(messages: ChatMessage[], options: ChatOptions = {}): Promise<string> {
    if (!this.apiKey) {
      throw new Error("OPENROUTER_API_KEY is required");
    }

    let attempt = 0;
    while (true) {
      attempt += 1;
      try {
        const response = await fetch(`${this.baseUrl}/chat/completions`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${this.apiKey}`,
          },
          body: JSON.stringify({
            model: this.model,
            messages,
            temperature: options.temperature ?? 0.2,
            response_format:
              options.responseFormat === "json_object"
                ? { type: "json_object" }
                : undefined,
          }),
        });

        if (!response.ok) {
          const text = await response.text();
          throw new Error(`OpenRouter error ${response.status}: ${text}`);
        }

        const payload = await response.json();
        const parsed = openRouterResponseSchema.safeParse(payload);
        if (!parsed.success) {
          throw new Error(`Unexpected OpenRouter response: ${parsed.error.message}`);
        }

        const choice = parsed.data.choices[0];
        if (!choice) {
          throw new Error("OpenRouter returned no choices");
        }

        return choice.message.content;
      } catch (error) {
        this.loggerInstance.warn(
          { attempt, error: (error as Error).message },
          "OpenRouter chat failure"
        );

        if (attempt >= this.maxRetries) {
          throw error;
        }

        const waitMs = Math.min(1000 * 2 ** attempt, 30_000);
        await delay(waitMs);
      }
    }
  }
}
