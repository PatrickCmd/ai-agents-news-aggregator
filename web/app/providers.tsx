"use client";

import { ClerkProvider } from "@clerk/react";
import { Toaster } from "@/components/ui/sonner";
import { ThemeProvider } from "@/lib/theme";
import { QueryProvider } from "@/lib/queryProvider";
import { Header } from "@/components/layout/Header";
import { Footer } from "@/components/layout/Footer";

/**
 * Client-side provider stack: Clerk → Theme → TanStack Query.
 *
 * Lives separately from `app/layout.tsx` (which is a server component owning
 * `metadata`) to avoid SSR-time `createContext` errors during static export.
 * Pattern: server layout exports metadata; client providers wrap children.
 */
export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <ClerkProvider
      publishableKey={process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY!}
      signInFallbackRedirectUrl="/"
      signUpFallbackRedirectUrl="/"
    >
      <ThemeProvider>
        <QueryProvider>
          <Header />
          <main className="flex-1 container py-6">{children}</main>
          <Footer />
          <Toaster richColors position="top-right" />
        </QueryProvider>
      </ThemeProvider>
    </ClerkProvider>
  );
}
