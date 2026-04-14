"use client";
import React, { useEffect, useMemo, useState } from "react";
import DeckGL from "@deck.gl/react";
import { MVTLayer } from "@deck.gl/geo-layers";
import { Map } from "react-map-gl/maplibre";
import "maplibre-gl/dist/maplibre-gl.css";
import type { PickingInfo } from "@deck.gl/core";
import { AlertCircle, PieChart, RotateCcw, Search } from "lucide-react";

const MAP_STYLE = "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json";

const INITIAL_VIEW_STATE = {
  longitude: -102.5528,
  latitude: 23.6345,
  zoom: 4.5,
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

type ViewState = typeof INITIAL_VIEW_STATE & {
  transitionDuration?: number;
};

export default function CommandCenter() {
  const [isMounted, setIsMounted] = useState(false);
  const [query, setQuery] = useState("");
  const [hoverInfo, setHoverInfo] = useState<HoverInfo | null>(null);
  const [viewState, setViewState] = useState<ViewState>(INITIAL_VIEW_STATE);
  const [activeElection, setActiveElection] = useState("PRESIDENCIA");
  const [activeEntidadFilter, setActiveEntidadFilter] = useState<number | null>(null);
  const [notification, setNotification] = useState<string | null>(null);

  useEffect(() => {
    setIsMounted(true);
  }, []);

  const handleSearch = async (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" && query.trim() !== "") {
      setNotification(null);
      try {
        const res = await fetch(
          `http://localhost:8000/api/v1/search/intent?q=${encodeURIComponent(query)}`
        );
        const data: {
          bbox?: number[];
          cargo_inferido?: string | null;
          entidad_id?: number | null;
          warning?: string | null;
        } = await res.json();

        if (data.warning) {
          setNotification(data.warning);
        }

        if (Array.isArray(data.bbox) && data.bbox.length === 4) {
          const longitude = (data.bbox[0] + data.bbox[2]) / 2;
          const latitude = (data.bbox[1] + data.bbox[3]) / 2;

          setViewState((prev) => ({
            ...prev,
            longitude,
            latitude,
            zoom: 7.5,
            transitionDuration: 2500,
          }));
        }

        if (data.entidad_id) {
          setActiveEntidadFilter(data.entidad_id);
        }
        if (data.cargo_inferido) {
          setActiveElection(data.cargo_inferido);
        }
      } catch (error) {
        console.error("Error en motor semantico:", error);
      }
    }
  };

  const handleReset = () => {
    setActiveElection("PRESIDENCIA");
    setActiveEntidadFilter(null);
    setQuery("");
    setNotification(null);
    setViewState({ ...INITIAL_VIEW_STATE, transitionDuration: 2000 });
  };

  const tileUrl = activeEntidadFilter
    ? `http://localhost:8000/api/v1/mapa/tiles/${activeElection}/{z}/{x}/{y}?entidad_filter=${activeEntidadFilter}`
    : `http://localhost:8000/api/v1/mapa/tiles/${activeElection}/{z}/{x}/{y}`;

  const layers = useMemo(
    () => [
      new MVTLayer({
        id: `resultados-mvt-${activeElection}-${activeEntidadFilter ?? "nacional"}`,
        data: tileUrl,
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
    [activeElection, activeEntidadFilter, tileUrl]
  );

  if (!isMounted) {
    return <div className="w-full h-screen bg-gray-950"></div>;
  }

  return (
    <div className="relative w-full h-screen bg-gray-950 overflow-hidden text-slate-200">
      <div className="absolute inset-0 z-0">
        <DeckGL
          viewState={viewState}
          onViewStateChange={({ viewState: nextViewState }) =>
            setViewState(nextViewState as ViewState)
          }
          controller={true}
          layers={layers}
        >
          <Map mapStyle={MAP_STYLE} />
        </DeckGL>
      </div>

      {hoverInfo?.object && (
        <div
          className="absolute z-50 bg-gray-900/90 backdrop-blur-md border border-gray-700/50 p-3 rounded-lg shadow-2xl pointer-events-none text-sm"
          style={{ left: hoverInfo.x + 15, top: hoverInfo.y + 15 }}
        >
          <div className="font-bold text-teal-400 mb-1 border-b border-gray-700 pb-1">
            Entidad: {hoverInfo.object.id_entidad} | Seccion:{" "}
            {hoverInfo.object.seccion ?? (hoverInfo.object as { properties?: { seccion?: number } }).properties?.seccion}
          </div>
          <div className="text-gray-300">
            Total Votos:{" "}
            <span className="text-white font-bold">
              {hoverInfo.object.total_votos_calculados ??
                (hoverInfo.object as { properties?: { total_votos_calculados?: number } }).properties
                  ?.total_votos_calculados}
            </span>
          </div>
          <div className="mt-2 text-xs text-gray-400 max-w-xs break-words">
            {typeof hoverInfo.object.votos_desglosados === "string"
              ? `${hoverInfo.object.votos_desglosados.substring(0, 100)}...`
              : `${JSON.stringify(hoverInfo.object.votos_desglosados ?? {}).substring(0, 100)}...`}
          </div>
        </div>
      )}

      <div className="absolute top-6 left-6 z-10 w-96 flex gap-2">
        <div className="flex-1 bg-gray-900/80 backdrop-blur-md border border-gray-700/50 rounded-2xl p-2 shadow-2xl flex items-center px-3 focus-within:border-teal-500 transition-colors">
          <div className="flex items-center bg-gray-950 rounded-xl px-3 py-2 border border-gray-800 w-full">
            <Search className="w-5 h-5 text-teal-400 mr-2" />
            <input
              type="text"
              className="bg-transparent w-full outline-none text-sm placeholder-gray-500 text-white"
              placeholder="Ej: Resultados ayuntamientos Michoacan..."
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={handleSearch}
            />
          </div>
        </div>
        <button
          onClick={handleReset}
          className="bg-gray-900/80 backdrop-blur-md border border-gray-700/50 rounded-2xl p-3 hover:bg-gray-800 transition-colors"
          title="Vision Nacional"
        >
          <RotateCcw className="w-5 h-5 text-gray-400 hover:text-white" />
        </button>
      </div>

      {notification && (
        <div className="absolute top-24 left-6 z-10 w-96 bg-amber-900/40 border border-amber-500/50 backdrop-blur-md rounded-xl p-3 flex items-start gap-3 shadow-lg">
          <AlertCircle className="w-5 h-5 text-amber-400 flex-shrink-0 mt-0.5" />
          <p className="text-xs text-amber-200 leading-relaxed">{notification}</p>
        </div>
      )}

      <div className="absolute top-6 right-6 z-10 w-80">
        <div className="bg-gray-900/80 backdrop-blur-md border border-gray-700/50 rounded-2xl p-5 shadow-2xl">
          <h2 className="text-sm font-bold tracking-widest text-gray-400 uppercase flex items-center gap-2 mb-2">
            <PieChart className="w-4 h-4" />
            Inteligencia Electoral
          </h2>
          <h3 className="text-xs text-teal-500 font-mono tracking-widest border-b border-gray-800 pb-2 mb-4">
            CAPA: {activeElection.replace("_", " ")}{" "}
            {activeEntidadFilter ? `| EDON: ${activeEntidadFilter}` : "| NACIONAL"}
          </h3>
        </div>
      </div>
    </div>
  );
}
