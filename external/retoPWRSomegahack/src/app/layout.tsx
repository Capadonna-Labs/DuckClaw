import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";

import { ThemeProvider } from '@/components/shared/ThemeProvider';

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "CRM PQRSD · Alcaldía de Medellín",
  description: "Sistema de Gestión de PQRSDs del Distrito de Medellín",
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
          {children}
        </ThemeProvider>
      </body>
    </html>
  );
}
