export function Footer() {
  return (
    <footer className="border-t mt-auto">
      <div className="container py-4 text-sm text-muted-foreground text-center">
        Sub-project #5 · v0.6.0 · {process.env.NEXT_PUBLIC_API_URL}
      </div>
    </footer>
  );
}
