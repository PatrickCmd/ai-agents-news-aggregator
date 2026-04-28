import { describe, it, expect, beforeEach } from "vitest";
import { render, act } from "@testing-library/react";
import { ThemeProvider, useTheme } from "@/lib/theme";

function Probe() {
  const { theme, setTheme } = useTheme();
  return (
    <button data-testid="probe" data-theme={theme} onClick={() => setTheme("light")}>
      flip
    </button>
  );
}

describe("ThemeProvider", () => {
  beforeEach(() => {
    document.documentElement.className = "";
    localStorage.clear();
  });

  it("defaults to dark and does not add a class to <html>", () => {
    render(
      <ThemeProvider>
        <Probe />
      </ThemeProvider>,
    );
    expect(document.documentElement.classList.contains("light")).toBe(false);
    expect(document.documentElement.classList.contains("dark")).toBe(false);
  });

  it("adds .light to <html> when setTheme('light') is called", () => {
    const { getByTestId } = render(
      <ThemeProvider>
        <Probe />
      </ThemeProvider>,
    );
    act(() => {
      getByTestId("probe").click();
    });
    expect(document.documentElement.classList.contains("light")).toBe(true);
  });

  it("removes .light when flipping back to dark", () => {
    const { getByTestId, rerender } = render(
      <ThemeProvider>
        <Probe />
      </ThemeProvider>,
    );
    act(() => {
      getByTestId("probe").click();
    });
    expect(document.documentElement.classList.contains("light")).toBe(true);

    function Probe2() {
      const { setTheme } = useTheme();
      return <button data-testid="probe2" onClick={() => setTheme("dark")}>back</button>;
    }
    rerender(
      <ThemeProvider>
        <Probe2 />
      </ThemeProvider>,
    );
    act(() => {
      getByTestId("probe2").click();
    });
    expect(document.documentElement.classList.contains("light")).toBe(false);
  });
});
