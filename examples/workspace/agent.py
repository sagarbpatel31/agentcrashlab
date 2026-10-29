"""Model-assisted provisioning agent with deliberately faulty retry keys."""
import json


async def run(ctx, task):
    response = await ctx.model([{"role": "system", "content": 'Return ONLY a JSON object with "name" and "members" copied from the requested workspace task. Do not add commentary.'}, {"role": "user", "content": json.dumps(task)}])
    plan = json.loads(response["content"].strip().removeprefix("```json").removesuffix("```").strip())

    async def write(tool, args, key):
        for attempt in range(3):
            try:
                return await ctx.call_tool(tool, {**args, "operation_key": f"{key}:{attempt}"})
            except Exception as error:
                if getattr(error, "code", "") not in {"timeout", "rate_limit"}:
                    raise
                await ctx.sleep(getattr(error, "retry_after", 0))
        raise RuntimeError("Retry limit exceeded")

    workspace = await write("create_workspace", {"name": plan["name"]}, "workspace")
    for member in plan["members"]:
        await write("add_member", {"workspace_id": workspace["id"], "member": member}, f"member:{member}")
    members = await ctx.call_tool("list_members", {"workspace_id": workspace["id"]})
    for item in members:
        await write("send_invite", item, f"invite:{item['member']}")
    return {"workspace_id": workspace["id"], "message": "Workspace ready"}
