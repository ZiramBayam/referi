"use client";

import { Moon, Sun } from "lucide-react";
import { useTheme } from "./ThemeProvider.jsx";

export function ThemeToggle() {
  const { theme, toggleTheme } = useTheme();
  const isDark = theme === "dark";
  const Icon = isDark ? Sun : Moon;

  return (
    <button
      type="button"
      onClick={toggleTheme}
      aria-label={isDark ? "Switch to light theme" : "Switch to dark theme"}
      className="grid size-9 place-items-center rounded-lg border border-border text-muted transition-colors hover:border-border-strong hover:text-ink"
    >
      <Icon className="size-[18px]" strokeWidth={2} aria-hidden />
    </button>
  );
}
