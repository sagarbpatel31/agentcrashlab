import { eveChannel } from "eve/channels/eve";

export default eveChannel({
  auth: [
    async (request: Request) => {
      if (
        !process.env.ACL_INTERNAL_TOKEN ||
        request.headers.get("authorization") !==
          `Bearer ${process.env.ACL_INTERNAL_TOKEN}`
      )
        return null;
      const provider = request.headers.get("x-acl-provider") || "meta";
      if (!["meta", "baseten", "fireworks"].includes(provider)) return null;
      return {
        authenticator: "agentcrashlab-local",
        principalId: "local-developer",
        principalType: "user" as const,
        attributes: {
          provider,
          model: request.headers.get("x-acl-model") || "muse-spark-1.3",
        },
      };
    },
  ],
});
