import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";

const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin"],
  display: "swap",
});

export const metadata: Metadata = {
  title: "Sistema Operativo Electoral 2024 | Command Center",
  description:
    "Plataforma de inteligencia electoral con mapas GPU (Deck.gl), análisis forense de votos, búsqueda semántica (pgvector) y cartografía GIS del proceso federal 2024.",
  keywords: ["elecciones", "2024", "México", "INE", "MAGAR", "GIS", "análisis electoral"],
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
      <body
        className={`${inter.className} min-h-full flex flex-col bg-gray-950`}
        suppressHydrationWarning
      >
        {children}
      </body>
    </html>
  );
}
