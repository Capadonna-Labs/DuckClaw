import type { Metadata, Viewport } from "next";
import { Inter } from "next/font/google";
import "./globals.css";

import { ThemeProvider } from '@/components/shared/ThemeProvider';
import { AuthProvider } from '@/components/auth/AuthProvider';

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "DuckClaw Admin",
  description: "Consola de configuración DuckClaw — agentes, skills, DuckDB y runtime",
};

/** Evita el salto del chrome en iOS Safari; el teclado redimensiona el layout. */
export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  viewportFit: 'cover',
  interactiveWidget: 'resizes-content',
  themeColor: [
    { media: '(prefers-color-scheme: light)', color: '#ffffff' },
    { media: '(prefers-color-scheme: dark)', color: '#161B22' },
  ],
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="es">
      <body
        className={`${inter.className} font-sans antialiased bg-gov-gray-50 text-gov-gray-900 transition-colors duration-300 dark:bg-dark-bg dark:text-dark-text`}
      >
        <ThemeProvider>
          <AuthProvider>{children}</AuthProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
