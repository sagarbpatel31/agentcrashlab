import { defineAgent, defineDynamic } from "eve";
import { createOpenAI } from "@ai-sdk/openai";
import { createOpenAICompatible } from "@ai-sdk/openai-compatible";

export default defineAgent({
  defaultTools: false,
  model: defineDynamic((ctx) => {
    const attributes = ctx.session.auth.current?.attributes || {};
    const provider = String(attributes.provider || "meta");
    const model = String(
      attributes.model || process.env.META_MODEL || "muse-spark-1.3",
    );
    if (provider === "meta") {
      if (!process.env.MODEL_API_KEY)
        throw new Error("Meta Model API key is not configured");
      return {
        model: createOpenAI({
          baseURL: "https://api.meta.ai/v1",
          apiKey: process.env.MODEL_API_KEY,
        }).responses(model),
        modelContextWindowTokens: 1048576,
      };
    }
    const key =
      provider === "baseten"
        ? process.env.BASETEN_API_KEY
        : provider === "fireworks"
          ? process.env.FIREWORKS_API_KEY
          : undefined;
    if (!key) throw new Error("The selected provider is not configured");
    return {
      model: createOpenAICompatible({
        name: provider,
        baseURL:
          provider === "baseten"
            ? "https://inference.baseten.co/v1"
            : "https://api.fireworks.ai/inference/v1",
        apiKey: key,
      })(model),
      modelContextWindowTokens: 131072,
    };
  }),
  limits: {
    sessionUsage: ({ total }) =>
      total.inputTokens >= 100000 || total.outputTokens >= 16000,
  },
});
