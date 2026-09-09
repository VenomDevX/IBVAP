import type { Metadata, Viewport } from 'next';
import { Inter, JetBrains_Mono } from 'next/font/google';
import '@fortawesome/fontawesome-free/css/all.min.css';
import './globals.css';
import Providers from './providers';

const inter = Inter({ subsets: ['latin'], variable: '--font-inter', display: 'swap' });
const jetbrains = JetBrains_Mono({ subsets: ['latin'], variable: '--font-jetbrains', display: 'swap' });

export const metadata: Metadata = {
  title: 'IBVAP — Border Video Analytics',
  description: 'Intelligent Border Video Analytics Platform',
};

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  colorScheme: 'dark light',
};

const themeScript = `try{if(localStorage.getItem('ibvap_theme')==='light')document.documentElement.classList.add('light-theme')}catch(e){}`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
      </head>
      <body className={`${inter.variable} ${jetbrains.variable}`}>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
