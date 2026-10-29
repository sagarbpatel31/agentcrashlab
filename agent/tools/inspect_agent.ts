import { defineTool } from "eve/tools";
import { z } from "zod";
import { backend } from "../../lib/backend";
export default defineTool({
  description:
    "Read an agent's source, manifest, tool contracts and expected outcomes.",
  inputSchema: z.object({ agent_id: z.string().regex(/^[a-zA-Z0-9_-]+$/) }),
  execute: ({ agent_id }) => backend(`agents/${agent_id}`),
});
