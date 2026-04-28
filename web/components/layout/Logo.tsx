import Link from "next/link";

export function Logo({ as = "link" }: { as?: "link" | "static" } = {}) {
  const inner = (
    <span className="font-display text-xl font-semibold leading-none tracking-tight">
      digest<span className="text-primary">.</span>
    </span>
  );
  if (as === "static") return inner;
  return (
    <Link href="/" aria-label="digest. — go to home" className="inline-block">
      {inner}
    </Link>
  );
}
