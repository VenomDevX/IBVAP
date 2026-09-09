'use client';

import { createContext, useContext, useState, useEffect, type ReactNode } from 'react';

interface ThemeState {
  isLight: boolean;
  toggleTheme: () => void;
  setTheme: (light: boolean) => void;
}

const ThemeContext = createContext<ThemeState | null>(null);
const STORAGE_KEY = 'ibvap_theme';

function readInitial(): boolean {
  if (typeof document !== 'undefined') {
    return document.documentElement.classList.contains('light-theme');
  }
  return false;
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [isLight, setIsLight] = useState<boolean>(readInitial);

  useEffect(() => {
    document.documentElement.classList.toggle('light-theme', isLight);
    try {
      localStorage.setItem(STORAGE_KEY, isLight ? 'light' : 'dark');
    } catch {
      /* private mode / storage disabled — theme still applies for this session */
    }
  }, [isLight]);

  const value: ThemeState = {
    isLight,
    toggleTheme: () => setIsLight(v => !v),
    setTheme: setIsLight,
  };

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme() {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error('useTheme must be used within ThemeProvider');
  return ctx;
}
