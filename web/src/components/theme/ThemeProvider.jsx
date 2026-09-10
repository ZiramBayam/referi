"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";

const STORAGE_KEY = "referi-theme";

const ThemeContext = createContext({ theme: "dark", toggleTheme: () => {} });

/** @param {{ children: any }} props */
export function ThemeProvider({ children }) {
  const [theme, setTheme] = useState("dark");

  // Sinkron dari data-theme yang SUDAH dipasang skrip anti-FOUC di <html>.
  useEffect(() => {
    const current = document.documentElement.getAttribute("data-theme") || "dark";
    setTheme(current);
  }, []);

  const toggleTheme = useCallback(() => {
    setTheme((prev) => {
      const next = prev === "dark" ? "light" : "dark";
      const el = document.documentElement;
      el.classList.add("theme-anim");
      el.setAttribute("data-theme", next);
      try {
        localStorage.setItem(STORAGE_KEY, next);
      } catch {}
      window.setTimeout(() => el.classList.remove("theme-anim"), 340);
      return next;
    });
  }, []);

  return <ThemeContext.Provider value={{ theme, toggleTheme }}>{children}</ThemeContext.Provider>;
}

export function useTheme() {
  return useContext(ThemeContext);
}

/**
 * Dijalankan SEBELUM cat pertama: menetapkan tema (?theme di URL menang, lalu
 * localStorage, lalu preferensi sistem). Tanpa ini halaman berkedip putih→gelap.
 */
export const themeInitScript = `(function(){try{var p=new URLSearchParams(location.search).get('theme');var t=(p==='light'||p==='dark')?p:localStorage.getItem('${STORAGE_KEY}');if(t!=='light'&&t!=='dark'){t=window.matchMedia('(prefers-color-scheme: light)').matches?'light':'dark';}if(p==='light'||p==='dark'){try{localStorage.setItem('${STORAGE_KEY}',t);}catch(e){}}document.documentElement.setAttribute('data-theme',t);}catch(e){document.documentElement.setAttribute('data-theme','dark');}})();`;
