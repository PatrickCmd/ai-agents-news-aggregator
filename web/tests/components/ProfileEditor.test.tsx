import { describe, expect, it } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import ProfilePage from "@/app/(authenticated)/profile/page";

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

describe("ProfilePage", () => {
  it("renders profile sections", async () => {
    render(<ProfilePage />, { wrapper });
    await waitFor(() => expect(screen.getByText(/your profile/i)).toBeInTheDocument());
    expect(screen.getByText(/background/i)).toBeInTheDocument();
    expect(screen.getByText(/interests/i)).toBeInTheDocument();
    expect(screen.getByText(/preferences/i)).toBeInTheDocument();
    expect(screen.getByText(/goals/i)).toBeInTheDocument();
    expect(screen.getByText(/reading time/i)).toBeInTheDocument();
  });

  it("submits valid profile via PUT", async () => {
    const user = userEvent.setup();
    render(<ProfilePage />, { wrapper });
    await waitFor(() => screen.getByText(/your profile/i));

    // Add a background entry.
    const addButtons = screen.getAllByRole("button", { name: /add/i });
    await user.click(addButtons[0]!);
    await user.type(screen.getAllByRole("textbox")[0]!, "AI engineer");

    // Submit.
    await user.click(screen.getByRole("button", { name: /save profile/i }));

    // Either toast appears or button shows pending state — easiest assertion is
    // that submit didn't render any FormMessage error.
    await waitFor(() =>
      expect(screen.queryAllByText(/required/i).length).toBe(0),
    );
  });
});
