"""Scripted offline publisher with deliberately flawed retry keys."""


async def run(ctx, task):
    artifact = await ctx.call_tool("get_artifact", {})
    for attempt in range(3):
        try:
            return await ctx.call_tool("publish_artifact", {"revision": artifact["revision"], "operation_key": f"publication:{attempt}"})
        except Exception as error:
            if getattr(error, "code", "") not in {"timeout", "rate_limit"}:
                raise
            await ctx.sleep(getattr(error, "retry_after", 0))
    raise RuntimeError("Retry limit exceeded")
