import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";

const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin"],
  display: "swap",
});

export const metadata: Metadata = {
  title: "Command Center Electoral 2024",
  description: "Sistema Operativo de Inteligencia Electoral",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="es"
      className={`${inter.variable} h-full antialiased`}
      suppressHydrationWarning
    >
      {/* FIX CRÍTICO: Blindaje del MetadataWrapper contra inyecciones de extensiones */}
      <head suppressHydrationWarning />
      <body
        className={`${inter.className} min-h-full flex flex-col bg-gray-950`}
        suppressHydrationWarning
      >
        {/* Envoltura extra para bloquear inyecciones de extensiones a nivel de body */}
        <div suppressHydrationWarning className="w-full h-full flex-1 flex">
          {children}
        </div>
      </body>
    </html>
  );
}
