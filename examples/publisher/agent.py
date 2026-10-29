"""Model-assisted publisher with deliberately faulty recovery behavior."""
import json


async def run(ctx, task):
    response = await ctx.model([{"role": "system", "content": 'Return ONLY a JSON object with "artifact" and "revision" copied from the publishing task.'}, {"role": "user", "content": json.dumps(task)}])
    plan = json.loads(response["content"].strip().removeprefix("```json").removesuffix("```").strip())
    artifact = await ctx.call_tool("get_artifact", {})
    for attempt in range(3):
        try:
            return await ctx.call_tool("publish_artifact", {"revision": artifact["revision"], "operation_key": f"{plan['artifact']}:{attempt}"})
        except Exception as error:
            if getattr(error, "code", "") not in {"timeout", "rate_limit"}:
                raise
            await ctx.sleep(getattr(error, "retry_after", 0))
    raise RuntimeError("Retry limit exceeded")
