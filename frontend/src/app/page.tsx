"use client";
import React, { useState, useCallback } from "react";
import DeckGL from "@deck.gl/react";
import { GeoJsonLayer } from "@deck.gl/layers";
import { Map } from "react-map-gl/maplibre";
import "maplibre-gl/dist/maplibre-gl.css";
import { Search, Layers, PieChart, Activity, MapPin, ChevronRight } from "lucide-react";

// Estilo de mapa oscuro para estética analítica
const MAP_STYLE =
  "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json";

const INITIAL_VIEW_STATE = {
  longitude: -102.5528, // Centro geográfico de México
  latitude: 23.6345,
  zoom: 4.5,
  pitch: 45, // Inclinación para efecto 3D
  bearing: 0,
};

const PARTIDOS = [
  { nombre: "MORENA", pct: 35.9, bgClass: "bg-[#b91c1c]", wClass: "w-[35.9%]" },
  { nombre: "PAN", pct: 28.2, bgClass: "bg-[#1d4ed8]", wClass: "w-[28.2%]" },
  { nombre: "PRI", pct: 13.4, bgClass: "bg-[#15803d]", wClass: "w-[13.4%]" },
  { nombre: "MC", pct: 10.1, bgClass: "bg-[#f97316]", wClass: "w-[10.1%]" },
  { nombre: "Otros", pct: 12.4, bgClass: "bg-[#6b7280]", wClass: "w-[12.4%]" },
];

export default function CommandCenter() {
  const [query, setQuery] = useState("");
  const [selectedInfo, setSelectedInfo] = useState<Record<string, unknown> | null>(null);
  const [viewState, setViewState] = useState(INITIAL_VIEW_STATE);

  const layers = [
    new GeoJsonLayer({
      id: "distritos-layer",
      data: null as unknown as string, // Endpoint futuro: /api/v1/mapa/distritos
      filled: true,
      extruded: true,
      getFillColor: [45, 212, 191, 150],
      getElevation: 100,
      pickable: true,
      onHover: (info: any) => {
        if (info && info.object) setSelectedInfo(info.object as Record<string, unknown>);
        else setSelectedInfo(null);
      },
    }),
  ];

  const handleSearch = useCallback(
    (e: React.FormEvent) => {
      e.preventDefault();
      // Futuro: llamar /api/v1/buscar con pgvector semántico
      console.log("Búsqueda semántica:", query);
    },
    [query]
  );

  return (
    <div className="relative w-full h-screen bg-gray-950 overflow-hidden text-slate-200 font-sans">
      {/* ══════════════════════════════════════════
          MAPA BASE DECK.GL (GPU-rendered)
      ══════════════════════════════════════════ */}
      <div className="absolute inset-0 z-0">
        <DeckGL
          viewState={viewState}
          onViewStateChange={({ viewState: vs }) => setViewState(vs as typeof INITIAL_VIEW_STATE)}
          controller={true}
          layers={layers}
        >
          <Map mapStyle={MAP_STYLE} />
        </DeckGL>
      </div>

      {/* ══════════════════════════════════════════
          HEADER — Título del sistema
      ══════════════════════════════════════════ */}
      <header className="absolute top-0 left-0 right-0 z-20 flex items-center justify-between px-6 py-3 bg-gradient-to-b from-gray-950/90 to-transparent">
        <div className="flex items-center gap-3">
          <div className="w-2 h-2 rounded-full bg-teal-400 animate-pulse" />
          <span className="text-xs font-bold tracking-[0.3em] text-gray-400 uppercase">
            Sistema Operativo Electoral
          </span>
          <span className="text-xs px-2 py-0.5 bg-teal-500/20 text-teal-300 rounded-full border border-teal-500/30">
            2024
          </span>
        </div>
        <div className="flex items-center gap-2 text-xs text-gray-500">
          <Activity className="w-3 h-3 text-green-400" />
          <span>PostGIS · pgvector · NLP — Online</span>
        </div>
      </header>

      {/* ══════════════════════════════════════════
          OMNIBOX — Buscador Semántico
      ══════════════════════════════════════════ */}
      <div className="absolute top-16 left-6 z-10 w-96">
        <form onSubmit={handleSearch}>
          <div className="bg-gray-900/80 backdrop-blur-md border border-gray-700/50 rounded-2xl p-4 shadow-2xl">
            <div className="flex items-center bg-gray-950/80 rounded-xl px-3 py-2.5 border border-gray-800 focus-within:border-teal-500/50 transition-colors">
              <Search className="w-4 h-4 text-teal-400 mr-2 flex-shrink-0" />
              <input
                id="omnibox-search"
                type="text"
                className="bg-transparent w-full outline-none text-sm placeholder-gray-600 text-gray-200"
                placeholder="¿Dónde ganó MORENA en Michoacán?"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
              />
              {query && (
                <button type="submit" className="ml-2 flex-shrink-0" title="Buscar" aria-label="Buscar">
                  <ChevronRight className="w-4 h-4 text-teal-400" />
                </button>
              )}
            </div>
            <p className="text-[10px] text-gray-600 mt-2 pl-1">
              Motor semántico pgvector · Análisis forense 2024
            </p>
          </div>
        </form>

        {/* Mini-leyenda de partidos */}
        <div className="mt-3 bg-gray-900/70 backdrop-blur-md border border-gray-700/40 rounded-xl p-3 shadow-xl">
          <div className="flex items-center gap-1.5 mb-2">
            <Layers className="w-3 h-3 text-gray-500" />
            <span className="text-[10px] font-semibold tracking-widest text-gray-500 uppercase">
              Distribución Nacional
            </span>
          </div>
          <div className="space-y-1.5">
            {PARTIDOS.map((p) => (
              <div key={p.nombre} className="flex items-center gap-2">
                <div
                  className={`w-2 h-2 rounded-full flex-shrink-0 ${p.bgClass}`}
                />
                <span className="text-xs text-gray-400 w-16">{p.nombre}</span>
                <div className="flex-1 bg-gray-800 rounded-full h-1.5">
                  <div
                    className={`h-1.5 rounded-full ${p.wClass} ${p.bgClass}`}
                  />
                </div>
                <span className="text-[10px] text-gray-500 w-8 text-right">
                  {p.pct}%
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* ══════════════════════════════════════════
          PANEL ANALÍTICO DERECHO
      ══════════════════════════════════════════ */}
      <div className="absolute top-16 right-6 z-10 w-80 bottom-6">
        <div className="bg-gray-900/80 backdrop-blur-md border border-gray-700/50 rounded-2xl p-5 shadow-2xl h-full flex flex-col">
          {/* Header del panel */}
          <h2 className="text-xs font-bold tracking-widest text-gray-400 uppercase flex items-center gap-2 mb-5">
            <PieChart className="w-3.5 h-3.5" />
            Inteligencia Electoral
          </h2>

          {selectedInfo ? (
            <div className="flex-1 space-y-3">
              <div className="bg-gray-800/50 rounded-xl p-3 border border-gray-700/40">
                <div className="flex items-center gap-2 mb-2">
                  <MapPin className="w-3 h-3 text-teal-400" />
                  <span className="text-xs font-semibold text-teal-300">
                    Distrito Seleccionado
                  </span>
                </div>
                <pre className="text-[10px] text-gray-400 overflow-auto max-h-40">
                  {JSON.stringify(selectedInfo, null, 2)}
                </pre>
              </div>
            </div>
          ) : (
            <div className="flex-1 flex flex-col items-center justify-center gap-4">
              <div className="border border-dashed border-gray-700 rounded-xl w-full flex-1 flex flex-col items-center justify-center p-6">
                <MapPin className="w-8 h-8 text-gray-700 mb-3" />
                <p className="text-gray-600 text-xs text-center leading-relaxed">
                  Haz clic en un polígono (Distrito / Sección) para ver el
                  análisis forense de los votos de 2024.
                </p>
              </div>

              {/* Stats placeholder */}
              <div className="w-full space-y-2">
                {["Distritos Federales", "Secciones Electorales", "Casillas"].map(
                  (label, i) => (
                    <div
                      key={label}
                      className="flex items-center justify-between bg-gray-800/40 rounded-lg px-3 py-2 border border-gray-700/30"
                    >
                      <span className="text-[10px] text-gray-500">{label}</span>
                      <span className="text-xs font-bold text-gray-300">
                        {["300", "68,278", "170,000+"][i]}
                      </span>
                    </div>
                  )
                )}
              </div>
            </div>
          )}

          {/* Footer estado */}
          <div className="mt-4 pt-3 border-t border-gray-800 flex items-center justify-between">
            <span className="text-[9px] text-gray-600 uppercase tracking-wider">
              INE · MAGAR · 2024
            </span>
            <div className="flex items-center gap-1.5">
              <div className="w-1.5 h-1.5 rounded-full bg-green-500 animate-pulse" />
              <span className="text-[9px] text-gray-600">API Online</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
