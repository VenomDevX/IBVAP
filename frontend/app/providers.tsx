'use client';

import type { ReactNode } from 'react';
import { ThemeProvider } from '@/src/context/ThemeContext';
import { AuthProvider } from '@/src/context/AuthContext';

export default function Providers({ children }: { children: ReactNode }) {
  return (
    <ThemeProvider>
      <AuthProvider>{children}</AuthProvider>
    </ThemeProvider>
  );
}
