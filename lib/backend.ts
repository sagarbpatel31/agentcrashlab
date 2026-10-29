export async function backend(path: string, body?: unknown) {
  const response = await fetch(`http://127.0.0.1:8765/${path}`, {
    method: body === undefined ? "GET" : "POST",
    headers: {
      Authorization: `Bearer ${process.env.ACL_INTERNAL_TOKEN}`,
      "Content-Type": "application/json",
    },
    body: body === undefined ? undefined : JSON.stringify(body),
    cache: "no-store",
  });
  if (!response.ok)
    throw new Error(
      (await response.json()).error || "Experiment service failed",
    );
  return response.json();
}

export function validOrigin(request: Request) {
  try {
    // Next.js may normalize request.url to localhost; Host retains the address
    // the browser actually used. Reject non-loopback hosts and foreign origins.
    const host = new URL(
      `http://${request.headers.get("host") || new URL(request.url).host}`,
    );
    const origin = request.headers.get("origin");
    return (
      ["127.0.0.1", "localhost"].includes(host.hostname) &&
      (!origin || new URL(origin).host === host.host)
    );
  } catch {
    return false;
  }
}
