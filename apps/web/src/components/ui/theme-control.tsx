"use client";
import { useSyncExternalStore } from "react";
import { readTheme, setTheme, subscribeTheme } from "@/lib/ui/theme";
import type { Theme } from "@/lib/ui/theme";
import Icon from "./icon";
const modes: {
  value: Theme;
  label: string;
  icon: "monitor" | "sun" | "moon";
}[] = [
  { value: "system", label: "Rendszer", icon: "monitor" },
  { value: "light", label: "Világos", icon: "sun" },
  { value: "dark", label: "Sötét", icon: "moon" },
];
export default function ThemeControl() {
  const selected = useSyncExternalStore(
    subscribeTheme,
    readTheme,
    () => "dark" as Theme,
  );
  return (
    <div
      className="pt-theme-switch"
      role="group"
      aria-label="Megjelenítési téma"
    >
      {modes.map((mode) => (
        <button
          type="button"
          key={mode.value}
          aria-pressed={mode.value === selected}
          onClick={() => setTheme(mode.value)}
          title={mode.label}
        >
          <Icon name={mode.icon} />
          <span>{mode.label}</span>
        </button>
      ))}
    </div>
  );
}
