import { ExternalLinkIcon } from "lucide-react";

interface Props {
  videoId: string;
  title: string;
}

export function YouTubePreview({ videoId, title }: Props) {
  return (
    <div className="space-y-2">
      <div className="aspect-video w-full overflow-hidden rounded-md border border-[var(--rule)] bg-black">
        <iframe
          title={title}
          src={`https://www.youtube-nocookie.com/embed/${videoId}`}
          loading="lazy"
          allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
          allowFullScreen
          className="h-full w-full"
        />
      </div>
      <a
        href={`https://youtu.be/${videoId}`}
        target="_blank"
        rel="noopener noreferrer"
        className="inline-flex items-center gap-1 font-mono text-xs uppercase tracking-[0.14em] text-[var(--ink-dim)] hover:text-[var(--ink)] transition-colors"
      >
        <ExternalLinkIcon className="h-3 w-3" />
        Open on YouTube
      </a>
    </div>
  );
}
