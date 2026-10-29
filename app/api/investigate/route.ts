import { Client } from "eve/client";
import { z } from "zod";
import { backend, validOrigin } from "@/lib/backend";
export const maxDuration = 180;
const fault = z.object({
  kind: z.enum([
    "timeout_before_write",
    "timeout_after_write",
    "rate_limit",
    "stale_read",
  ]),
  tool: z.string(),
  occurrence: z.number().int().min(1).max(20),
});
const experiments = z.object({
  summary: z.string(),
  scenarios: z
    .array(
      z.object({
        name: z.string(),
        description: z.string(),
        faults: z.array(fault).max(6),
      }),
    )
    .min(1)
    .max(8),
});
const repair = z.object({
  explanation: z.string(),
  files: z
    .array(z.object({ path: z.string(), content: z.string() }))
    .min(1)
    .max(5),
});

export async function POST(request: Request) {
  if (!validOrigin(request))
    return Response.json(
      { error: "Only local same-origin requests are accepted" },
      { status: 403 },
    );
  let session:
    | Awaited<ReturnType<Client["sessions"]["create"]>>["session"]
    | undefined;
  try {
    const body = z
      .object({
        action: z.enum(["design", "repair"]),
        agent_id: z.string().regex(/^[a-zA-Z0-9_-]+$/),
        run_id: z.string().uuid().optional(),
        provider: z.enum(["meta", "baseten", "fireworks"]),
        model: z.string().min(1).max(150),
      })
      .parse(await request.json());
    const config = await backend("bootstrap");
    if (
      !config.providers.find(
        (p: { id: string; configured: boolean }) => p.id === body.provider,
      )?.configured
    )
      return Response.json(
        {
          error:
            "Add the selected provider's API key to .env.local and restart the app.",
        },
        { status: 400 },
      );
    if (
      body.action === "repair" &&
      (!body.run_id ||
        config.repairs.filter(
          (r: { run_id: string }) => r.run_id === body.run_id,
        ).length >= 3)
    )
      return Response.json(
        {
          error: "Choose a failing run with fewer than three repair attempts.",
        },
        { status: 400 },
      );
    const client = new Client({
      baseUrl: new URL(request.url).origin,
      auth: { bearer: process.env.ACL_INTERNAL_TOKEN! },
      headers: { "x-acl-provider": body.provider, "x-acl-model": body.model },
    });
    const outputSchema = z.toJSONSchema(
      body.action === "design" ? experiments : repair,
    );
    const response = await client.sessions.create({
      message:
        body.action === "design"
          ? `Inspect agent ${body.agent_id} and design failure experiments from its implementation. Return the requested structured result.`
          : `Inspect failure ${body.run_id} and agent ${body.agent_id}. Propose a general repair for its actual cause; preserve the task and model call. Return the requested structured result.`,
      outputSchema,
    });
    session = response.session;
    const abort = () => {
      void session?.cancel().catch(() => {});
    };
    request.signal.addEventListener("abort", abort, { once: true });
    const deadline = setTimeout(abort, 150000);
    let result;
    const usage = {
      model_calls: 0,
      input_tokens: 0,
      output_tokens: 0,
      cost_usd: null as number | null,
    };
    try {
      for await (const event of response.delivery.stream({
        signal: request.signal,
      })) {
        if (event.type === "usage.recorded") {
          usage.model_calls += 1;
          usage.input_tokens += event.data.usage.inputTokens;
          usage.output_tokens += event.data.usage.outputTokens;
          if (event.data.usage.costUsd !== undefined)
            usage.cost_usd = (usage.cost_usd ?? 0) + event.data.usage.costUsd;
        }
      }
      result = await response.delivery.result({ signal: request.signal });
    } finally {
      clearTimeout(deadline);
      request.signal.removeEventListener("abort", abort);
    }
    if (result.status !== "completed" || !result.data)
      throw new Error(
        result.error?.message ||
          "Investigator did not produce a completed structured result",
      );
    if (body.action === "design")
      return Response.json(
        await backend("investigations", {
          agent_id: body.agent_id,
          ...experiments.parse(result.data),
          provenance: "live eve investigator",
          provider: body.provider,
          model: body.model,
          usage,
          session_id: response.session.state.sessionId,
        }),
      );
    const candidate = repair.parse(result.data);
    const files = Object.fromEntries(
      candidate.files.map((file) => [file.path, file.content]),
    );
    return Response.json(
      await backend("repairs", {
        run_id: body.run_id,
        files,
        explanation: candidate.explanation,
        provenance: `live eve investigator · ${body.provider}/${body.model}`,
        usage: { ...usage, session_id: response.session.state.sessionId },
      }),
    );
  } catch (error) {
    return Response.json(
      {
        error: error instanceof Error ? error.message : "Investigation failed",
      },
      { status: 400 },
    );
  }
}
