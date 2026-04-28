const YT_HOSTS = new Set([
  "youtube.com",
  "www.youtube.com",
  "m.youtube.com",
  "youtu.be",
  "www.youtu.be",
]);

const ID_RE = /^[A-Za-z0-9_-]{11}$/;

export function youtubeIdFromUrl(url: string): string | null {
  if (!url) return null;
  let parsed: URL;
  try {
    parsed = new URL(url);
  } catch {
    return null;
  }
  if (!YT_HOSTS.has(parsed.hostname)) return null;

  // youtu.be/<id>[?t=...]
  if (parsed.hostname === "youtu.be" || parsed.hostname === "www.youtu.be") {
    const id = parsed.pathname.slice(1).split("/")[0] ?? "";
    return ID_RE.test(id) ? id : null;
  }

  // youtube.com/watch?v=<id>
  if (parsed.pathname === "/watch") {
    const id = parsed.searchParams.get("v");
    return id && ID_RE.test(id) ? id : null;
  }

  // youtube.com/shorts/<id> or /embed/<id>
  const m = parsed.pathname.match(/^\/(?:shorts|embed)\/([^/?]+)/);
  const candidate = m?.[1] ?? "";
  if (candidate && ID_RE.test(candidate)) return candidate;

  return null;
}
