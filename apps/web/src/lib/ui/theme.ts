export type Theme = "system" | "light" | "dark";
export const THEME_KEY = "paddletrainer.theme.v1";
let memoryTheme: Theme | null = null;
export function validTheme(value: unknown): value is Theme {
  return value === "system" || value === "light" || value === "dark";
}
export function readTheme(): Theme {
  if (memoryTheme) return memoryTheme;
  if (typeof window === "undefined") return "dark";
  try {
    const saved = localStorage.getItem(THEME_KEY);
    return validTheme(saved) ? saved : "dark";
  } catch {
    return "dark";
  }
}
export function resolvedTheme(mode: Theme, systemDark: boolean) {
  return mode === "system" ? (systemDark ? "dark" : "light") : mode;
}
function apply() {
  const resolved = resolvedTheme(
    readTheme(),
    window.matchMedia("(prefers-color-scheme: dark)").matches,
  );
  document.documentElement.dataset.theme = resolved;
  document.documentElement.style.colorScheme = resolved;
}
export function setTheme(mode: Theme) {
  memoryTheme = mode;
  try {
    localStorage.setItem(THEME_KEY, mode);
  } catch {
    /* Current-tab choice still works. */
  }
  apply();
  window.dispatchEvent(new Event("paddletrainer:theme"));
}
export function subscribeTheme(callback: () => void) {
  const media = window.matchMedia("(prefers-color-scheme: dark)");
  const update = () => {
    apply();
    callback();
  };
  const stored = (event: StorageEvent) => {
    if (event.key === THEME_KEY || event.key === null) {
      memoryTheme = null;
      update();
    }
  };
  window.addEventListener("paddletrainer:theme", update);
  window.addEventListener("storage", stored);
  media.addEventListener("change", update);
  apply();
  return () => {
    window.removeEventListener("paddletrainer:theme", update);
    window.removeEventListener("storage", stored);
    media.removeEventListener("change", update);
  };
}
// Fixed script; only the validated local preference influences the chosen token.
export const themeBootstrap = `(function(){try{var m=localStorage.getItem('${THEME_KEY}');if(m!=='light'&&m!=='dark'&&m!=='system')m='dark';var t=m==='system'?(matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light'):m;document.documentElement.dataset.theme=t;document.documentElement.style.colorScheme=t;}catch(e){document.documentElement.dataset.theme='dark';}})();`;
