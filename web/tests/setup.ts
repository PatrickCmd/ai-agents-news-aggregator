import "@testing-library/jest-dom/vitest";
import { vi, afterEach, beforeAll, afterAll } from "vitest";
import { cleanup } from "@testing-library/react";
import { server } from "./mocks/server";

// jsdom polyfill for matchMedia
Object.defineProperty(window, "matchMedia", {
  writable: true,
  value: vi.fn().mockImplementation((query) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })),
});

// Clerk: stub the SDK so tests never hit the real Clerk service.
vi.mock("@clerk/clerk-react", () => ({
  ClerkProvider: ({ children }: { children: React.ReactNode }) => children,
  useAuth: () => ({
    isLoaded: true,
    isSignedIn: true,
    getToken: vi.fn().mockResolvedValue("test-jwt-token"),
  }),
  useUser: () => ({
    user: {
      id: "user_test",
      primaryEmailAddress: { emailAddress: "test@example.com" },
      fullName: "Test User",
    },
  }),
  RedirectToSignIn: () => null,
  UserButton: () => null,
}));

// MSW: intercept all fetches; tests can override with server.use(...).
beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => {
  cleanup();
  server.resetHandlers();
});
afterAll(() => server.close());

// Process env defaults for tests.
process.env.NEXT_PUBLIC_API_URL = "http://localhost:8000";
process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY = "pk_test_dummy";
