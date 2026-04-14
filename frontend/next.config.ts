import type { NextConfig } from "next";
import path from "path";

const nextConfig: NextConfig = {
  // Aseguramos que Turbopack no se confunda con lockfiles en directorios superiores.
  turbopack: {
    root: path.resolve(__dirname),
  },
  // Compatibilidad defensiva para configuraciones heredadas.
  experimental: {
    turbo: {
      root: "./",
    },
  },
};

export default nextConfig;
