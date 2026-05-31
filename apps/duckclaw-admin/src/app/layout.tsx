import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";

import { ThemeProvider } from '@/components/shared/ThemeProvider';
import { AuthProvider } from '@/components/auth/AuthProvider';

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "DuckClaw Admin",
  description: "Consola de configuración DuckClaw — plantillas, Telegram, DuckDB y runtime",
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
