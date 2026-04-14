"use client";
import React, { useMemo, useState } from "react";
import DeckGL from "@deck.gl/react";
import { MVTLayer } from "@deck.gl/geo-layers";
import { Map } from "react-map-gl/maplibre";
import "maplibre-gl/dist/maplibre-gl.css";
import type { PickingInfo } from "@deck.gl/core";
import { Search, PieChart } from "lucide-react";

const MAP_STYLE = "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json";

const INITIAL_VIEW_STATE = {
  longitude: -102.5528,
  latitude: 23.6345,
  zoom: 5,
  pitch: 45,
  bearing: 0,
};

type HoverObject = {
  id_entidad?: number | string;
  seccion?: number | string;
  total_votos_calculados?: number;
  votos_desglosados?: unknown;
};

type HoverInfo = PickingInfo<HoverObject> & {
  object?: HoverObject;
  x: number;
  y: number;
};

type MVTFeature = {
  properties?: {
    votos_desglosados?: Record<string, number | string> | string;
    total_votos_calculados?: number | string;
  };
};

export default function CommandCenter() {
  const [query, setQuery] = useState("");
  const [hoverInfo, setHoverInfo] = useState<HoverInfo | null>(null);

  const layers = useMemo(
    () => [
      new MVTLayer({
        id: "resultados-presidencia-mvt",
        data: "http://localhost:8000/api/v1/mapa/tiles/presidencia/{z}/{x}/{y}",
        minZoom: 0,
        maxZoom: 14,
        getFillColor: (feature: MVTFeature) => {
          const rawVotes = feature.properties?.votos_desglosados;
          const votos =
            typeof rawVotes === "object" && rawVotes !== null
              ? (rawVotes as Record<string, number | string>)
              : {};
          const keys = Object.keys(votos);
          if (keys.length === 0) return [45, 212, 191, 100];
          const maxParty = keys.reduce((a, b) => {
            const va = Number(votos[a] ?? 0);
            const vb = Number(votos[b] ?? 0);
            return va > vb ? a : b;
          }, keys[0] || "");

          if (maxParty.includes("MORENA")) return [115, 32, 39, 210];
          if (maxParty.includes("PAN")) return [0, 85, 184, 210];
          if (maxParty.includes("PRI")) return [0, 149, 59, 210];
          if (maxParty.includes("MC")) return [242, 115, 32, 210];
          return [45, 212, 191, 100];
        },
        getElevation: (feature: MVTFeature) =>
          Number(feature.properties?.total_votos_calculados ?? 0) * 5,
        extruded: true,
        wireframe: true,
        pickable: true,
        autoHighlight: true,
        highlightColor: [255, 255, 255, 120],
        onHover: (info: PickingInfo<HoverObject>) => setHoverInfo(info as HoverInfo),
      }),
    ],
    []
  );

  return (
    <div className="relative w-full h-screen bg-gray-950 overflow-hidden text-slate-200">
      <div className="absolute inset-0 z-0">
        <DeckGL initialViewState={INITIAL_VIEW_STATE} controller={true} layers={layers}>
          <Map mapStyle={MAP_STYLE} />
        </DeckGL>
      </div>

      {hoverInfo?.object && (
        <div
          className="absolute z-50 bg-gray-900/90 backdrop-blur-md border border-gray-700/50 p-3 rounded-lg shadow-2xl pointer-events-none text-sm"
          style={{ left: hoverInfo.x + 15, top: hoverInfo.y + 15 }}
        >
          <div className="font-bold text-teal-400 mb-1 border-b border-gray-700 pb-1">
            Entidad: {hoverInfo.object.id_entidad} | Seccion: {hoverInfo.object.seccion}
          </div>
          <div className="text-gray-300">
            Total Votos: <span className="text-white font-bold">{hoverInfo.object.total_votos_calculados}</span>
          </div>
          <div className="mt-2 text-xs text-gray-400 max-w-xs break-words">
            {typeof hoverInfo.object.votos_desglosados === "string"
              ? `${hoverInfo.object.votos_desglosados.substring(0, 100)}...`
              : `${JSON.stringify(hoverInfo.object.votos_desglosados ?? {}).substring(0, 100)}...`}
          </div>
        </div>
      )}

      <div className="absolute top-6 left-6 z-10 w-96">
        <div className="bg-gray-900/80 backdrop-blur-md border border-gray-700/50 rounded-2xl p-4 shadow-2xl">
          <div className="flex items-center bg-gray-950 rounded-xl px-3 py-2 border border-gray-800 focus-within:border-teal-500 transition-colors">
            <Search className="w-5 h-5 text-teal-400 mr-2" />
            <input
              type="text"
              className="bg-transparent w-full outline-none text-sm placeholder-gray-500 text-white"
              placeholder="Ej: Analisis seccional en Uruapan..."
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </div>
        </div>
      </div>

      <div className="absolute top-6 right-6 z-10">
        <div className="bg-gray-900/80 backdrop-blur-md border border-gray-700/50 rounded-2xl p-3 shadow-2xl flex items-center gap-2">
          <PieChart className="w-4 h-4 text-teal-400" />
          <span className="text-xs text-gray-300">MVT + PostGIS Online</span>
        </div>
      </div>
    </div>
  );
}
