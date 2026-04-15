"use client";
import dynamic from "next/dynamic";
import React, { useEffect, useMemo, useState } from "react";
import DeckGL from "@deck.gl/react";
import { MVTLayer } from "@deck.gl/geo-layers";
import { Map } from "react-map-gl/maplibre";
import "maplibre-gl/dist/maplibre-gl.css";
import type { PickingInfo } from "@deck.gl/core";
import { AlertCircle, CheckSquare, Layers, PieChart, RotateCcw, Search } from "lucide-react";
import {
  Bar,
  BarChart,
  Cell,
  ResponsiveContainer,
  Tooltip as RechartsTooltip,
  XAxis,
  YAxis,
} from "recharts";

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
  id_municipio?: number | string;
  id_distrito_local?: number | string;
  id_distrito_federal?: number | string;
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
    id_entidad?: number | string;
    seccion?: number | string;
    id_municipio?: number | string;
    id_distrito_local?: number | string;
    id_distrito_federal?: number | string;
    votos_desglosados?: Record<string, number | string> | string;
    total_votos_calculados?: number | string;
  };
};

type WinnerIdentity = {
  candidato: string;
  detalle: string;
};

// Utilidad para extraer y ordenar el JSONB de votos
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const processVotesData = (votosDesglosados: any) => {
  if (!votosDesglosados) return [];
  const rawData = typeof votosDesglosados === "string" ? JSON.parse(votosDesglosados) : votosDesglosados;

  return Object.keys(rawData)
    .map((key) => ({
      // FIX: Reemplazar guiones bajos por un formato limpio de coalición
      name: key.replace(/_/g, " - "),
      votos: Number(rawData[key]),
    }))
    .filter((item) => item.votos > 0)
    .sort((a, b) => b.votos - a.votos)
    .slice(0, 7);
};

const getPartyColor = (partyName: string): string => {
  const p = partyName.toUpperCase();
  if (p.includes("MORENA")) return "#A52A2A";
  if (p.includes("PAN")) return "#0055B8";
  if (p.includes("PRI")) return "#00953B";
  if (p.includes("MC")) return "#F27320";
  if (p.includes("PT")) return "#E01F26";
  if (p.includes("PVEM") || p.includes("VERDE")) return "#5CB85C";
  if (p.includes("PRD")) return "#FFD700";
  return "#2DD4BF";
};

// --- UTILIDADES DE LEGIBILIDAD UX ---
const ENTIDADES_MX: Record<number, string> = {
  1: "Aguascalientes",
  2: "Baja California",
  3: "Baja California Sur",
  4: "Campeche",
  5: "Coahuila",
  6: "Colima",
  7: "Chiapas",
  8: "Chihuahua",
  9: "Ciudad de México",
  10: "Durango",
  11: "Guanajuato",
  12: "Guerrero",
  13: "Hidalgo",
  14: "Jalisco",
  15: "Estado de México",
  16: "Michoacán",
  17: "Morelos",
  18: "Nayarit",
  19: "Nuevo León",
  20: "Oaxaca",
  21: "Puebla",
  22: "Querétaro",
  23: "Quintana Roo",
  24: "San Luis Potosí",
  25: "Sinaloa",
  26: "Sonora",
  27: "Tabasco",
  28: "Tamaulipas",
  29: "Tlaxcala",
  30: "Veracruz",
  31: "Yucatán",
  32: "Zacatecas",
};

const formatCargo = (cargo: string) => {
  const map: Record<string, string> = {
    PRESIDENCIA: "Presidencia de la República",
    SENADURIA: "Senadurías",
    DIPUTACION_FEDERAL: "Diputaciones Federales",
    GUBERNATURA: "Gubernatura Estatal",
    AYUNTAMIENTO: "Ayuntamientos y Alcaldías",
    DIPUTACION_LOCAL: "Diputaciones Locales",
  };
  return map[cargo] || cargo.replace(/_/g, " ");
};

const resolveMunicipioName = (entidadId: any, municipioId: any) => {
  const ent = Number(entidadId);
  const mun = Number(municipioId);
  if (!mun) return "N/A";
  // En la Fase 12.5 conectaremos esto a un endpoint en vivo.
  // Por ahora, devolvemos el ID formateado elegantemente para evitar el fallo de renderizado.
  return `Municipio ${mun} (EDO ${ent})`;
};

const parseVotesObject = (
  votosDesglosados: Record<string, number | string> | string | undefined
): Record<string, number | string> => {
  if (!votosDesglosados) return {};
  if (typeof votosDesglosados === "string") {
    try {
      return JSON.parse(votosDesglosados) as Record<string, number | string>;
    } catch {
      return {};
    }
  }
  return votosDesglosados;
};

const getWinningParty = (
  votosDesglosados: Record<string, number | string> | string | undefined
): string => {
  const rawData = parseVotesObject(votosDesglosados);
  const keys = Object.keys(rawData);
  if (keys.length === 0) return "";
  return keys.reduce((a, b) => {
    const va = Number(rawData[a] ?? 0);
    const vb = Number(rawData[b] ?? 0);
    return va >= vb ? a : b;
  }, keys[0]);
};

type ViewState = typeof INITIAL_VIEW_STATE & {
  transitionDuration?: number;
};

function CommandCenterUI() {
  const [query, setQuery] = useState("");
  const [hoverInfo, setHoverInfo] = useState<HoverInfo | null>(null);
  const [viewState, setViewState] = useState<ViewState>(INITIAL_VIEW_STATE);
  const [activeElection, setActiveElection] = useState("PRESIDENCIA");
  const [activeEntidadFilter, setActiveEntidadFilter] = useState<number | null>(null);
  const [notification, setNotification] = useState<string | null>(null);
  const [selectedFeature, setSelectedFeature] = useState<MVTFeature | null>(null);
  const [winnerIdentity, setWinnerIdentity] = useState<WinnerIdentity | null>(null);
  const [showMun, setShowMun] = useState(false);
  const [showDL, setShowDL] = useState(false);
  const [showDF, setShowDF] = useState(false);
  const [showDossier, setShowDossier] = useState(false);
  const [activeDossierCandidate, setActiveDossierCandidate] = useState<string | null>(null);

  useEffect(() => {
    if (!selectedFeature?.properties) return;

    const idEntidad = Number(selectedFeature.properties.id_entidad ?? 0);
    const seccion = Number(selectedFeature.properties.seccion ?? 0);
    const winningParty = getWinningParty(selectedFeature.properties.votos_desglosados);
    if (!idEntidad || !seccion || !winningParty) {
      return;
    }

    const controller = new AbortController();
    const fetchWinnerIdentity = async () => {
      try {
        const params = new URLSearchParams({
          cargo: activeElection,
          entidad: String(idEntidad),
          seccion: String(seccion),
          partido: winningParty,
        });
        const res = await fetch(
          `http://localhost:8000/api/v1/analitica/ganador?${params.toString()}`,
          { signal: controller.signal }
        );
        if (!res.ok) {
          setWinnerIdentity({
            candidato: "Sin registro",
            detalle: "No fue posible resolver identidad nominal",
          });
          return;
        }
        const data = (await res.json()) as WinnerIdentity;
        setWinnerIdentity(data);
      } catch (error) {
        if ((error as Error).name !== "AbortError") {
          console.error("Error obteniendo identidad nominal:", error);
          setWinnerIdentity({
            candidato: "Error de conexión",
            detalle: "Fallo de consulta al motor analítico",
          });
        }
      }
    };

    fetchWinnerIdentity();
    return () => controller.abort();
  }, [selectedFeature, activeElection]);

  const executeSearch = async () => {
    if (query.trim() === "") return;
    setNotification(null);
    try {
      const res = await fetch(`http://localhost:8000/api/v1/search/intent?q=${encodeURIComponent(query)}`);
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
      setSelectedFeature(null);
      setWinnerIdentity(null);
    } catch (error) {
      console.error("Error en motor semántico:", error);
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
  const boundaryMunUrl = `http://localhost:8000/api/v1/mapa/boundaries/municipios/{z}/{x}/{y}${activeEntidadFilter ? `?entidad_filter=${activeEntidadFilter}` : ""}`;
  const boundaryDLUrl = `http://localhost:8000/api/v1/mapa/boundaries/distritos_locales/{z}/{x}/{y}${activeEntidadFilter ? `?entidad_filter=${activeEntidadFilter}` : ""}`;
  const boundaryDFUrl = `http://localhost:8000/api/v1/mapa/boundaries/distritos_federales/{z}/{x}/{y}${activeEntidadFilter ? `?entidad_filter=${activeEntidadFilter}` : ""}`;

  const layers = useMemo(
    () => [
      new MVTLayer({
        id: `resultados-mvt-${activeElection}-${activeEntidadFilter ?? "nacional"}`,
        data: tileUrl,
        minZoom: 0,
        maxZoom: 14,
        opacity: 0.65,
        getFillColor: (f: MVTFeature) => {
          const rawVotos = f.properties?.votos_desglosados;
          const totalVotos = Number(f.properties?.total_votos_calculados || 0);
          let votos: Record<string, number | string> = {};
          try {
            votos =
              typeof rawVotos === "string"
                ? (JSON.parse(rawVotos || "{}") as Record<string, number | string>)
                : (rawVotos || {});
          } catch {
            votos = {};
          }

          if (totalVotos === 0 && Object.keys(votos).length === 0) return [0, 0, 0, 0];

          const maxParty = Object.keys(votos).reduce(
            (a, b) => (Number(votos[a]) > Number(votos[b]) ? a : b),
            ""
          );
          if (!maxParty) return [0, 0, 0, 0];

          if (maxParty.includes("MORENA")) return [115, 32, 39, 210];
          if (maxParty.includes("PAN")) return [0, 85, 184, 210];
          if (maxParty.includes("PRI")) return [0, 149, 59, 210];
          if (maxParty.includes("MC")) return [242, 115, 32, 210];
          return [45, 212, 191, 150];
        },
        getLineColor: [100, 116, 139, 40],
        lineWidthMinPixels: 1,
        extruded: false,
        wireframe: false,
        pickable: true,
        autoHighlight: true,
        highlightColor: [255, 255, 255, 120],
        onHover: (info: PickingInfo<HoverObject>) => setHoverInfo(info as HoverInfo),
        onClick: (info: PickingInfo<MVTFeature>) => {
          if (info.object) {
            setWinnerIdentity(null);
            setSelectedFeature(info.object as MVTFeature);
          } else {
            setWinnerIdentity(null);
            setSelectedFeature(null);
          }
        },
      }),
      new MVTLayer({
        id: `boundary-mun-${activeEntidadFilter || "nac"}`,
        data: boundaryMunUrl,
        visible: showMun,
        filled: false,
        stroked: true,
        lineWidthMinPixels: 2,
        getLineColor: [255, 255, 255, 200],
      }),
      new MVTLayer({
        id: `boundary-dl-${activeEntidadFilter || "nac"}`,
        data: boundaryDLUrl,
        visible: showDL,
        filled: false,
        stroked: true,
        lineWidthMinPixels: 3,
        getLineColor: [59, 130, 246, 255],
      }),
      new MVTLayer({
        id: `boundary-df-${activeEntidadFilter || "nac"}`,
        data: boundaryDFUrl,
        visible: showDF,
        filled: false,
        stroked: true,
        lineWidthMinPixels: 4,
        getLineColor: [168, 85, 247, 255],
      }),
    ],
    [
      activeElection,
      activeEntidadFilter,
      boundaryDFUrl,
      boundaryDLUrl,
      boundaryMunUrl,
      showDF,
      showDL,
      showMun,
      tileUrl,
    ]
  );

  // --- RENDERIZADOR DE TOOLTIP INTELIGENTE (GEOGRAPHIC HUD) ---
  const renderTooltip = () => {
    if (!hoverInfo || !hoverInfo.object) return null;

    const props = (
      hoverInfo.object as {
        properties?: {
          id_entidad?: number | string;
          seccion?: number | string;
          id_municipio?: number | string;
          id_distrito_local?: number | string;
          id_distrito_federal?: number | string;
          votos_desglosados?: Record<string, number | string> | string;
          total_votos_calculados?: number | string;
        };
      }
    ).properties ?? {
      id_entidad: hoverInfo.object.id_entidad,
      seccion: hoverInfo.object.seccion,
      id_municipio: hoverInfo.object.id_municipio,
      id_distrito_local: hoverInfo.object.id_distrito_local,
      id_distrito_federal: hoverInfo.object.id_distrito_federal,
      votos_desglosados: hoverInfo.object.votos_desglosados,
      total_votos_calculados: hoverInfo.object.total_votos_calculados,
    };

    const {
      id_entidad,
      seccion,
      id_municipio,
      id_distrito_local,
      id_distrito_federal,
      votos_desglosados,
      total_votos_calculados,
    } = props;
    let rawVotos: Record<string, number | string> = {};
    try {
      rawVotos =
        typeof votos_desglosados === "string"
          ? (JSON.parse(votos_desglosados || "{}") as Record<string, number | string>)
          : (votos_desglosados || {});
    } catch {
      rawVotos = {};
    }

    // FIX CRÍTICO: Auto-Suma Dinámica. Si la BD envió 0, calculamos el total sumando el JSONB.
    const sumVotos = Object.values(rawVotos).reduce((a, b) => Number(a) + Number(b), 0) as number;
    const total = Number(total_votos_calculados) > 0 ? Number(total_votos_calculados) : sumVotos;
    const parties = Object.keys(rawVotos)
      .map((key) => ({ name: key.replace(/_/g, " - "), votos: Number(rawVotos[key]) }))
      .sort((a, b) => b.votos - a.votos);

    const winner = parties.length > 0 && parties[0].votos > 0 ? parties[0] : null;
    const entidadLabel = ENTIDADES_MX[Number(id_entidad)] || `Entidad ${id_entidad}`;
    const totalLabel = total.toLocaleString();

    return (
      <div
        className="absolute z-50 bg-gray-950/95 backdrop-blur-xl border border-gray-800 p-4 rounded-2xl shadow-2xl pointer-events-none w-80 animate-in fade-in duration-200"
        style={{ left: hoverInfo.x + 15, top: hoverInfo.y + 15 }}
      >
        <div className="text-[10px] font-black text-teal-500 uppercase tracking-widest mb-2 border-b border-gray-800 pb-2">
          {formatCargo(activeElection)} • 2024
        </div>

        <div className="mb-3">
          <div className="text-white font-bold text-lg leading-tight">{entidadLabel}</div>
          {/* LINAJE GEOGRÁFICO EXPLÍCITO (Sin acrónimos crípticos) */}
          <div className="grid grid-cols-2 gap-2 text-[10px] font-mono mt-2 bg-gray-900/50 p-2 rounded-md border border-gray-800">
            <div className="flex flex-col">
              <span className="text-gray-500 uppercase">Municipio</span>
              <span className="text-teal-200 font-bold">
                {resolveMunicipioName(id_entidad, id_municipio)}
              </span>
            </div>
            <div className="flex flex-col text-right">
              <span className="text-gray-500 uppercase">Distrito Local</span>
              <span className="text-blue-200 font-bold">{id_distrito_local || "N/A"}</span>
            </div>
            <div className="flex flex-col">
              <span className="text-gray-500 uppercase">Distrito Federal</span>
              <span className="text-purple-200 font-bold">{id_distrito_federal || "N/A"}</span>
            </div>
            <div className="flex flex-col text-right">
              <span className="text-gray-500 uppercase">Sección</span>
              <span className="text-white font-bold text-xs">{seccion}</span>
            </div>
          </div>
        </div>

        {winner && total > 0 ? (
          <div className="space-y-2 bg-gray-900/50 p-2 rounded-lg border border-gray-800/50">
            <div className="flex justify-between items-center">
              <span className="text-xs text-gray-400">Fuerza Ganadora:</span>
              <span
                className="text-[10px] font-black px-2 py-1 rounded bg-gray-800 text-white truncate max-w-[140px]"
                style={{ color: getPartyColor(winner.name) }}
              >
                {winner.name}
              </span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-xs text-gray-400">Votos Emitidos:</span>
              <span className="text-sm font-black text-white">{totalLabel}</span>
            </div>
          </div>
        ) : (
          <div className="text-xs text-gray-500 italic p-2 bg-gray-900/30 rounded-lg text-center border border-gray-800/30">
            Sin registros de votación en esta sección.
          </div>
        )}
      </div>
    );
  };

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

      {/* TOOLTIP DINÁMICO E INTELIGENTE */}
      {renderTooltip()}

      {/* OMNIBOX CENTRALIZADO Y CONTROLES */}
      <div className="absolute top-8 left-1/2 -translate-x-1/2 z-20 w-[48rem] flex flex-col gap-3">
        {/* Barra de Búsqueda */}
        <div className="flex gap-2 w-full shadow-2xl">
          <div className="flex-1 bg-gray-900/90 backdrop-blur-xl border border-gray-700/50 rounded-2xl p-2 flex items-center px-4 focus-within:border-teal-500 focus-within:ring-2 focus-within:ring-teal-500/20 transition-all">
            <Search className="w-5 h-5 text-teal-400 mr-3" />
            <input
              type="text"
              className="bg-transparent w-full outline-none text-base placeholder-gray-500 text-white"
              placeholder="Ej: Resultados de presidencia en Nuevo León..."
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && executeSearch()}
            />
            <button
              onClick={executeSearch}
              className="ml-2 bg-teal-600/90 hover:bg-teal-500 text-white text-xs font-black tracking-widest py-2.5 px-8 rounded-xl transition-all shadow-[0_0_15px_rgba(45,212,191,0.2)]"
            >
              BUSCAR
            </button>
          </div>

          <button
            onClick={handleReset}
            className="bg-gray-900/90 backdrop-blur-xl border border-gray-700/50 rounded-2xl p-3 hover:bg-gray-800 transition-colors"
            title="Restaurar Visión Nacional"
          >
            <RotateCcw className="w-6 h-6 text-gray-400" />
          </button>
        </div>

        {/* Toggles de Demarcaciones (Fronteras) */}
        <div className="flex justify-center gap-4">
          <label className="flex items-center gap-2 bg-gray-900/80 backdrop-blur-md px-4 py-2 rounded-full border border-gray-700/50 cursor-pointer hover:bg-gray-800 transition-colors">
            <input type="checkbox" checked={showMun} onChange={(e) => setShowMun(e.target.checked)} className="hidden" />
            <div className={`w-3 h-3 rounded-full border ${showMun ? "bg-white border-white" : "border-gray-500"}`}></div>
            <span className={`text-xs font-bold uppercase tracking-wider ${showMun ? "text-white" : "text-gray-500"}`}>
              <CheckSquare className="w-3 h-3 inline mr-1" />
              Municipios
            </span>
          </label>
          <label className="flex items-center gap-2 bg-gray-900/80 backdrop-blur-md px-4 py-2 rounded-full border border-gray-700/50 cursor-pointer hover:bg-gray-800 transition-colors">
            <input type="checkbox" checked={showDL} onChange={(e) => setShowDL(e.target.checked)} className="hidden" />
            <div className={`w-3 h-3 rounded-full border ${showDL ? "bg-blue-500 border-blue-500" : "border-gray-500"}`}></div>
            <span className={`text-xs font-bold uppercase tracking-wider ${showDL ? "text-blue-400" : "text-gray-500"}`}>
              <Layers className="w-3 h-3 inline mr-1" />
              Distritos Loc.
            </span>
          </label>
          <label className="flex items-center gap-2 bg-gray-900/80 backdrop-blur-md px-4 py-2 rounded-full border border-gray-700/50 cursor-pointer hover:bg-gray-800 transition-colors">
            <input type="checkbox" checked={showDF} onChange={(e) => setShowDF(e.target.checked)} className="hidden" />
            <div className={`w-3 h-3 rounded-full border ${showDF ? "bg-purple-500 border-purple-500" : "border-gray-500"}`}></div>
            <span className={`text-xs font-bold uppercase tracking-wider ${showDF ? "text-purple-400" : "text-gray-500"}`}>
              <Layers className="w-3 h-3 inline mr-1" />
              Distritos Fed.
            </span>
          </label>
        </div>
      </div>

      {notification && (
        <div className="absolute top-24 left-6 z-10 w-96 bg-amber-900/40 border border-amber-500/50 backdrop-blur-md rounded-xl p-3 flex items-start gap-3 shadow-lg">
          <AlertCircle className="w-5 h-5 text-amber-400 flex-shrink-0 mt-0.5" />
          <p className="text-xs text-amber-200 leading-relaxed">{notification}</p>
        </div>
      )}

      {/* PANEL ANALÍTICO DERECHO */}
      <div className="absolute top-6 right-6 z-10 w-[26rem] max-h-[calc(100vh-3rem)] flex flex-col pointer-events-none">
        <div className="bg-gray-900/90 backdrop-blur-xl border border-gray-700/50 rounded-2xl p-5 shadow-2xl pointer-events-auto overflow-y-auto custom-scrollbar">
          <h2 className="text-sm font-bold tracking-widest text-gray-400 uppercase flex items-center gap-2 mb-2">
            <PieChart className="w-4 h-4" /> Inteligencia Electoral
          </h2>

          {/* FIX: Cabecera legible sin residuos técnicos ("EDON 16") */}
          <h3 className="text-xs text-teal-500 font-mono tracking-widest border-b border-gray-800 pb-2 mb-4 break-words uppercase">
            CAPA: {formatCargo(activeElection)} |{" "}
            {activeEntidadFilter
              ? ENTIDADES_MX[Number(activeEntidadFilter)] || `ENTIDAD ${activeEntidadFilter}`
              : "NACIONAL"}
          </h3>

          {!selectedFeature ? (
            <div className="flex flex-col items-center justify-center h-48 border border-dashed border-gray-700 rounded-xl p-4 text-center">
              <p className="text-gray-500 text-xs">
                Haz clic en un polígono (Sección) en el mapa para extraer el análisis forense de los votos.
              </p>
            </div>
          ) : (
            <div className="animate-in fade-in slide-in-from-right-4 duration-500">
              {/* FIX: Cuadrícula completa de linaje geográfico (Simetría con el Tooltip) */}
              <div className="flex flex-col mb-4 bg-gray-950 p-4 rounded-lg border border-gray-800">
                <div className="flex justify-between items-center mb-3 border-b border-gray-800 pb-3">
                  <div>
                    <p className="text-[10px] text-gray-500 uppercase tracking-wider">Entidad</p>
                    <p className="text-xl font-bold text-white uppercase">
                      {ENTIDADES_MX[Number(selectedFeature.properties.id_entidad)] ||
                        `Estado ${selectedFeature.properties.id_entidad}`}
                    </p>
                  </div>
                  <div className="text-right flex flex-col items-end">
                    <p className="text-[10px] text-gray-500 uppercase tracking-wider">Sección</p>
                    <p className="text-2xl font-black text-teal-400 bg-teal-900/20 px-3 py-1 rounded-md border border-teal-800/50">
                      {selectedFeature.properties.seccion}
                    </p>
                  </div>
                </div>
                <div className="grid grid-cols-3 gap-3">
                  <div className="col-span-1">
                    <p className="text-[9px] text-gray-500 uppercase tracking-wider">Municipio</p>
                    <p
                      className="text-xs font-medium text-teal-100 truncate"
                      title={resolveMunicipioName(
                        selectedFeature.properties.id_entidad,
                        selectedFeature.properties.id_municipio
                      )}
                    >
                      {resolveMunicipioName(
                        selectedFeature.properties.id_entidad,
                        selectedFeature.properties.id_municipio
                      )}
                    </p>
                  </div>
                  <div className="col-span-1 text-center border-l border-r border-gray-800 px-2">
                    <p className="text-[9px] text-gray-500 uppercase tracking-wider">Dist. Local</p>
                    <p className="text-xs font-medium text-blue-300">
                      {selectedFeature.properties.id_distrito_local || "N/A"}
                    </p>
                  </div>
                  <div className="col-span-1 text-right">
                    <p className="text-[9px] text-gray-500 uppercase tracking-wider">Dist. Fed.</p>
                    <p className="text-xs font-medium text-purple-300">
                      {selectedFeature.properties.id_distrito_federal || "N/A"}
                    </p>
                  </div>
                </div>
              </div>

              {/* BLOQUE DE IDENTIDAD NOMINAL */}
              <div className="mb-4 bg-gradient-to-r from-teal-900/30 to-transparent p-4 rounded-xl border-l-2 border-teal-500">
                <p className="text-[10px] text-teal-400 uppercase tracking-wider mb-1">
                  Fuerza Ganadora Estimada
                </p>
                {winnerIdentity ? (
                  <>
                    {/* FIX: Extraemos el partido líder para pintar el nombre del candidato con su color institucional */}
                    <button
                      onClick={() => {
                        setActiveDossierCandidate(winnerIdentity.candidato);
                        setShowDossier(true);
                      }}
                      className="text-lg font-bold leading-tight uppercase drop-shadow-md text-left hover:underline decoration-teal-500 decoration-2 transition-all cursor-pointer"
                      style={{
                        color: processVotesData(selectedFeature.properties.votos_desglosados)[0]
                          ? getPartyColor(processVotesData(selectedFeature.properties.votos_desglosados)[0].name)
                          : "#FFFFFF",
                      }}
                    >
                      {winnerIdentity.candidato}
                      <span className="ml-2 text-[10px] bg-teal-900/50 text-teal-300 px-2 py-0.5 rounded border border-teal-500/50">
                        ABRIR EXPEDIENTE
                      </span>
                    </button>
                    <p className="text-[11px] text-gray-400 mt-1 uppercase font-mono">
                      {winnerIdentity.detalle}
                    </p>
                  </>
                ) : (
                  <div className="animate-pulse flex flex-col gap-2 mt-2">
                    <div className="h-4 bg-gray-800 rounded w-3/4"></div>
                    <div className="h-3 bg-gray-800 rounded w-1/2"></div>
                  </div>
                )}
              </div>

              <div className="mb-6 flex justify-between items-end border-b border-gray-800 pb-3">
                <div>
                  <p className="text-[10px] text-gray-500 uppercase tracking-wider mb-1">
                    Total Votos Emitidos
                  </p>
                  <p className="text-3xl font-black text-white">
                    {(
                      Number(selectedFeature.properties.total_votos_calculados) > 0
                        ? Number(selectedFeature.properties.total_votos_calculados)
                        : processVotesData(selectedFeature.properties.votos_desglosados).reduce(
                            (sum, item) => sum + item.votos,
                            0
                          )
                    ).toLocaleString()}
                  </p>
                </div>
              </div>

              <p className="text-[10px] text-gray-500 uppercase tracking-wider mb-2">
                Distribución Política (Top 7)
              </p>
              <div className="h-64 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart
                    layout="vertical"
                    data={processVotesData(selectedFeature.properties.votos_desglosados)}
                    margin={{ top: 0, right: 20, left: -20, bottom: 0 }}
                  >
                    <XAxis type="number" hide />
                    <YAxis
                      dataKey="name"
                      type="category"
                      axisLine={false}
                      tickLine={false}
                      tick={{ fill: "#9ca3af", fontSize: 10 }}
                      width={170}
                      interval={0}
                    />
                    <RechartsTooltip
                      cursor={{ fill: "rgba(255,255,255,0.05)" }}
                      contentStyle={{
                        backgroundColor: "#111827",
                        borderColor: "#374151",
                        borderRadius: "0.5rem",
                        fontSize: "12px",
                        textTransform: "uppercase",
                      }}
                      itemStyle={{ color: "#fff", fontWeight: "bold" }}
                      formatter={(value: number) => [value.toLocaleString(), "VOTOS"]}
                    />
                    <Bar dataKey="votos" radius={[0, 4, 4, 0]} barSize={15}>
                      {processVotesData(selectedFeature.properties.votos_desglosados).map(
                        (entry, index) => (
                          <Cell key={`cell-${index}`} fill={getPartyColor(entry.name)} />
                        )
                      )}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* EXPEDIENTE DIGITAL DE INTELIGENCIA (MODAL GLASSMORPHISM) */}
      {showDossier && (
        <div className="absolute inset-0 z-50 flex items-center justify-center bg-gray-950/80 backdrop-blur-sm animate-in fade-in">
          <div className="bg-gray-900 border border-gray-700 w-[50rem] h-[35rem] rounded-2xl shadow-[0_0_50px_rgba(0,0,0,0.5)] flex flex-col overflow-hidden relative">
            {/* Header del Expediente */}
            <div className="bg-gray-950 p-4 border-b border-gray-800 flex justify-between items-center">
              <div className="flex items-center gap-3">
                <div className="w-3 h-3 bg-red-500 rounded-full animate-pulse"></div>
                <h2 className="text-teal-500 font-mono tracking-widest text-sm">
                  SISTEMA DE INTELIGENCIA / EXPEDIENTE CLASIFICADO
                </h2>
              </div>
              <button
                onClick={() => setShowDossier(false)}
                className="text-gray-400 hover:text-white font-bold text-xl px-2"
              >
                &times;
              </button>
            </div>

            <div className="flex flex-1 overflow-hidden">
              {/* Columna Izquierda: Identidad y Biometría */}
              <div className="w-1/3 bg-gray-950/50 border-r border-gray-800 p-6 flex flex-col items-center">
                {/* Zona de Drag & Drop para procesar foto con IA */}
                <div className="w-40 h-40 rounded-full border-2 border-dashed border-gray-600 bg-gray-800/50 flex flex-col items-center justify-center cursor-pointer hover:border-teal-500 hover:bg-gray-800 transition-all overflow-hidden relative group">
                  <p className="text-[10px] text-gray-400 text-center px-4 group-hover:text-teal-400">
                    Arrastra imagen aquí
                    <br />
                    (La IA quitará el fondo)
                  </p>
                  {/* Imagen procesada iría aquí */}
                </div>
                <h1 className="mt-4 text-xl font-black text-white text-center uppercase leading-tight">
                  {activeDossierCandidate}
                </h1>
                <p className="text-xs text-teal-400 mt-1 border border-teal-900 bg-teal-950/30 px-2 py-1 rounded">
                  PERFIL POLÍTICO ACTIVO
                </p>

                <button className="mt-6 w-full py-2 bg-gray-800 hover:bg-gray-700 border border-gray-600 rounded text-xs font-bold tracking-widest text-white transition-colors">
                  EDITAR FICHA
                </button>
              </div>

              {/* Columna Derecha: Minería de Datos y Trayectoria */}
              <div className="w-2/3 p-6 overflow-y-auto custom-scrollbar">
                {/* Minería Web */}
                <div className="mb-6 bg-gray-950 p-4 rounded-xl border border-gray-800">
                  <h3 className="text-xs text-gray-500 font-bold tracking-widest mb-3 uppercase">
                    Minería de Datos (Escáner Web)
                  </h3>
                  <div className="flex gap-2">
                    <input
                      type="text"
                      placeholder="Pegar URL de Wikipedia o SaberVotar..."
                      className="flex-1 bg-gray-900 border border-gray-700 rounded px-3 py-2 text-xs text-white outline-none focus:border-teal-500"
                    />
                    <button className="bg-teal-700 hover:bg-teal-600 text-white px-4 rounded text-xs font-bold">
                      ESCANEAR
                    </button>
                  </div>
                </div>

                {/* Trayectoria */}
                <div className="mb-6">
                  <h3 className="text-xs text-gray-500 font-bold tracking-widest mb-3 uppercase">
                    Trayectoria y Resultados Electorales
                  </h3>
                  <div className="space-y-3 border-l-2 border-gray-700 ml-2 pl-4">
                    {/* Elemento de ejemplo */}
                    <div className="relative">
                      <div className="absolute -left-[21px] top-1 w-2.5 h-2.5 bg-green-500 rounded-full border-2 border-gray-900"></div>
                      <p className="text-xs font-bold text-gray-400">2024</p>
                      <p className="text-sm font-bold text-white uppercase">
                        {activeElection.replace("_", " ")}
                      </p>
                      <p className="text-xs text-gray-400">
                        Siglado: <span className="text-white">MORENA - PT - PVEM</span> | Resultado:{" "}
                        <span className="text-green-400 font-bold">VICTORIA</span>
                      </p>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// BYPASS GLOBAL DE HIDRATACIÓN: Next.js no intentará renderizar el mapa en el servidor.
// Protege el componente de extensiones invasivas como Bitdefender.
export default dynamic(() => Promise.resolve(CommandCenterUI), {
  ssr: false,
  loading: () => (
    <div className="w-full h-screen bg-gray-950 flex flex-col items-center justify-center">
      <div className="w-12 h-12 border-4 border-teal-500/30 border-t-teal-500 rounded-full animate-spin mb-4"></div>
      <p className="text-teal-500 font-mono tracking-widest animate-pulse text-sm">
        INICIALIZANDO MOTOR ESPACIAL...
      </p>
    </div>
  ),
});
