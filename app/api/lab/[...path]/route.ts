import { validOrigin } from "@/lib/backend";
export const dynamic = "force-dynamic";

async function proxy(
  request: Request,
  { params }: { params: Promise<{ path: string[] }> },
) {
  if (!validOrigin(request))
    return Response.json(
      { error: "Only same-origin local requests are accepted" },
      { status: 403 },
    );
  const { path } = await params;
  if (path.some((part) => !/^[a-zA-Z0-9_-]+$/.test(part)))
    return Response.json({ error: "Invalid path" }, { status: 400 });
  try {
    const response = await fetch(
      `http://127.0.0.1:8765/${path.join("/")}${new URL(request.url).search}`,
      {
        method: request.method,
        headers: {
          Authorization: `Bearer ${process.env.ACL_INTERNAL_TOKEN}`,
          "Content-Type": "application/json",
        },
        body: request.method === "GET" ? undefined : await request.text(),
        cache: "no-store",
        signal: request.signal,
      },
    );
    return new Response(response.body, {
      status: response.status,
      headers: {
        "Content-Type":
          response.headers.get("Content-Type") || "application/json",
        ...(response.headers.has("Content-Disposition")
          ? {
              "Content-Disposition": response.headers.get(
                "Content-Disposition",
              )!,
            }
          : {}),
      },
    });
  } catch {
    return Response.json(
      {
        error:
          "Experiment engine is unavailable. Start the app with npm run dev.",
      },
      { status: 503 },
    );
  }
}
export { proxy as GET, proxy as POST };
