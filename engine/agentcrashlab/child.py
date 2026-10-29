"""Public adapter bridge. This file is copied into the isolated runner."""
import asyncio
import importlib.util
import json
import sys


class ToolFailure(Exception):
    def __init__(self, error):
        super().__init__(error["message"])
        self.code = error["code"]
        self.retry_after = error.get("retry_after", 0)


class Context:
    async def request(self, kind, **payload):
        print(json.dumps({"kind": kind, **payload}), flush=True)
        line = sys.stdin.readline()
        if not line:
            raise RuntimeError("The experiment controller disconnected")
        response = json.loads(line)
        if "error" in response:
            raise ToolFailure(response["error"])
        return response["result"]

    async def call_tool(self, name, arguments):
        return await self.request("tool", name=name, arguments=arguments)

    async def model(self, messages):
        return await self.request("model", messages=messages)

    async def sleep(self, seconds):
        return await self.request("sleep", seconds=seconds)


async def main():
    request = json.loads(sys.stdin.readline())
    spec = importlib.util.spec_from_file_location("target_agent", request["entrypoint"])
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    result = await module.run(Context(), request["task"])
    print(json.dumps({"kind": "finished", "result": result}), flush=True)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except BaseException as exc:
        print(json.dumps({"kind": "agent_error", "error": f"{type(exc).__name__}: {exc}"}), flush=True)
        sys.exit(1)
