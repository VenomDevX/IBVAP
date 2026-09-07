import { createContext, useContext, useState, useEffect, type ReactNode } from 'react';

interface ThemeState {
  isLight: boolean;
  toggleTheme: () => void;
}

const ThemeContext = createContext<ThemeState | null>(null);

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [isLight, setIsLight] = useState(() => {
    return localStorage.getItem('ibvap_theme') === 'light';
  });

  useEffect(() => {
    if (isLight) {
      document.documentElement.classList.add('light-theme');
    } else {
      document.documentElement.classList.remove('light-theme');
    }
  }, [isLight]);

  const toggleTheme = () => {
    setIsLight(prev => {
      const next = !prev;
      localStorage.setItem('ibvap_theme', next ? 'light' : 'dark');
      return next;
    });
  };

  return (
    <ThemeContext.Provider value={{ isLight, toggleTheme }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme() {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error('useTheme must be used within ThemeProvider');
  return ctx;
}
