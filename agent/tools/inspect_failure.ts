import { defineTool } from "eve/tools";
import { z } from "zod";
import { backend } from "../../lib/backend";
export default defineTool({
  description:
    "Read the frozen evidence of a failed experiment: calls, observations, committed effects and assertions.",
  inputSchema: z.object({ run_id: z.string().uuid() }),
  execute: ({ run_id }) => backend(`runs/${run_id}`),
});
