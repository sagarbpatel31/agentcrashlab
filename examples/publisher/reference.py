"""Handwritten reference publisher; not an AI-generated repair."""


async def run(ctx, task):
    for attempt in range(3):
        artifact = await ctx.call_tool("get_artifact", {})
        if artifact["revision"] == task["revision"]:
            break
    else:
        raise RuntimeError("Requested revision could not be confirmed")
    for attempt in range(3):
        try:
            return await ctx.call_tool("publish_artifact", {"revision": task["revision"], "operation_key": f"publish:{task['artifact']}:{task['revision']}"})
        except Exception as error:
            if getattr(error, "code", "") not in {"timeout", "rate_limit"}:
                raise
            await ctx.sleep(getattr(error, "retry_after", 0))
    raise RuntimeError("Retry limit exceeded")
