"use client";
import dynamic from "next/dynamic";
import React, { useEffect, useMemo, useState } from "react";
import DeckGL from "@deck.gl/react";
import { MVTLayer } from "@deck.gl/geo-layers";
import { Map } from "react-map-gl/maplibre";
import "maplibre-gl/dist/maplibre-gl.css";
import type { PickingInfo } from "@deck.gl/core";
import {
  AlertCircle,
  ChevronDown,
  Paperclip,
  RotateCcw,
  User,
  X,
} from "lucide-react";
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

// CATALOGO MAESTRO DE TOPONIMIA (Evita llamadas asincronas fallidas a la BD)
const resolveMunicipioName = (entidadId: unknown, municipioId: unknown): string => {
  const ent = Number(entidadId);
  const mun = Number(municipioId);
  if (!mun) return "N/A";

  // Base de conocimiento estatica (Muestra representativa nacional)
  const masterCatalog: Record<number, Record<number, string>> = {
    1: { 1: "Aguascalientes", 2: "Asientos", 5: "Jesus Maria" },
    2: { 1: "Ensenada", 2: "Mexicali", 4: "Tijuana", 5: "Playas de Rosarito" },
    9: {
      2: "Azcapotzalco",
      3: "Coyoacan",
      5: "Gustavo A. Madero",
      7: "Iztapalapa",
      14: "Benito Juarez",
      15: "Cuauhtemoc",
      16: "Miguel Hidalgo",
    },
    14: {
      39: "Guadalajara",
      70: "Puerto Vallarta",
      97: "Tlajomulco de Zuniga",
      98: "Tlaquepaque",
      101: "Tonala",
      120: "Zapopan",
    },
    16: {
      14: "Apatzingan",
      48: "Lazaro Cardenas",
      53: "Morelia",
      65: "Patzcuaro",
      102: "Tzintzuntzan",
      103: "Uruapan",
      112: "Zamora",
      113: "Zitacuaro",
    },
    19: {
      6: "Apodaca",
      19: "San Pedro Garza Garcia",
      21: "General Escobedo",
      26: "Guadalupe",
      39: "Monterrey",
      46: "San Nicolas de los Garza",
    },
    21: { 15: "Atlixco", 34: "San Pedro Cholula", 114: "Puebla", 156: "Tehuacan" },
    32: { 10: "Guadalupe", 17: "Fresnillo", 56: "Zacatecas" },
  };

  if (masterCatalog[ent] && masterCatalog[ent][mun]) {
    return masterCatalog[ent][mun].toUpperCase();
  }

  // Fallback generico limpio si el municipio no esta en el mini-catalogo
  return `MUNICIPIO ${mun}`;
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
  const [activeMunicipioFilter, setActiveMunicipioFilter] = useState<number | null>(null);
  const [activeDLFilter, setActiveDLFilter] = useState<number | null>(null);
  const [notification, setNotification] = useState<string | null>(null);
  const [selectedFeature, setSelectedFeature] = useState<MVTFeature | null>(null);
  const [winnerIdentity, setWinnerIdentity] = useState<WinnerIdentity | null>(null);
  const [showMun, setShowMun] = useState(false);
  const [showDL, setShowDL] = useState(false);
  const [showDF, setShowDF] = useState(false);
  // Estados Menú Maestro
  const [showMenu, setShowMenu] = useState(false);
  const [selectedYear, setSelectedYear] = useState<number>(2024);
  // Estados EDI
  const [showDossier, setShowDossier] = useState(false);
  const [activeDossierCandidate, setActiveDossierCandidate] = useState<string | null>(null);
  const [isSearching, setIsSearching] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [profileImgUrl, setProfileImgUrl] = useState<string | null>(null);
  const [wikiUrl, setWikiUrl] = useState("");
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [bioData, setBioData] = useState<any>(null);
  const fileInputRef = React.useRef<HTMLInputElement>(null);
  const [isEditMode, setIsEditMode] = useState(false);
  const [dossierForm, setDossierForm] = useState({
    biografia: "",
    telefono: "",
    twitter: "",
    facebook: "",
  });
  const [isSaving, setIsSaving] = useState(false);

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setIsUploading(true);
    const formData = new FormData();
    formData.append("file", file);

    try {
      const res = await fetch("http://localhost:8000/api/v1/edi/upload", {
        method: "POST",
        body: formData,
      });
      const data = await res.json();
      if (data.url) setProfileImgUrl(`http://localhost:8000${data.url}`);
    } catch (error) {
      console.error("Error subiendo archivo:", error);
    } finally {
      setIsUploading(false);
    }
  };

  const handleWikiScan = async () => {
    if (!wikiUrl) return;
    const formData = new FormData();
    formData.append("url", wikiUrl);
    try {
      const res = await fetch("http://localhost:8000/api/v1/edi/scan_wiki", {
        method: "POST",
        body: formData,
      });
      const data = await res.json();
      if (data.data) {
        setBioData(data.data);
        setDossierForm((prev) => ({ ...prev, biografia: data.data.biografia }));
        if (data.data.foto_url && !profileImgUrl) setProfileImgUrl(data.data.foto_url);
      }
    } catch (error) {
      console.error("Error escaneando Wikipedia:", error);
    }
  };

  const handleSaveDossier = async () => {
    if (!activeDossierCandidate) return;
    setIsSaving(true);
    try {
      const payload = {
        nombre_completo: activeDossierCandidate,
        biografia: dossierForm.biografia,
        telefono: dossierForm.telefono,
        redes_sociales: { twitter: dossierForm.twitter, facebook: dossierForm.facebook },
        foto_perfil_url: profileImgUrl ? profileImgUrl.replace("http://localhost:8000", "") : "",
      };

      const res = await fetch("http://localhost:8000/api/v1/edi/profile", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (res.ok) {
        setIsEditMode(false);
        setNotification("Expediente clasificado guardado con éxito.");
      }
    } catch (error) {
      console.error("Error guardando expediente:", error);
    } finally {
      setIsSaving(false);
    }
  };

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

  useEffect(() => {
    if (showDossier && activeDossierCandidate) {
      // Reset state
      setIsEditMode(false);
      setProfileImgUrl(null);
      setBioData(null);
      setWikiUrl("");
      setDossierForm({ biografia: "", telefono: "", twitter: "", facebook: "" });

      // Fetch profile from DB
      fetch(`http://localhost:8000/api/v1/edi/profile/${encodeURIComponent(activeDossierCandidate)}`)
        .then((res) => res.json())
        .then((data) => {
          if (data.status === "success") {
            const p = data.data;
            if (p.foto_perfil_url) {
              setProfileImgUrl(
                p.foto_perfil_url.startsWith("http")
                  ? p.foto_perfil_url
                  : `http://localhost:8000${p.foto_perfil_url}`
              );
            }
            setDossierForm({
              biografia: p.biografia || "",
              telefono: p.telefono || "",
              twitter: p.redes_sociales?.twitter || "",
              facebook: p.redes_sociales?.facebook || "",
            });
            if (p.biografia || p.trayectoria?.length > 0) {
              setBioData({ biografia: p.biografia, trayectoria: p.trayectoria || [] });
            }
          }
        })
        .catch(() => console.log("Expediente nuevo, no existe en BD aún."));
    }
  }, [showDossier, activeDossierCandidate]);

  const executeSearch = async () => {
    if (query.trim() === "") return;
    setIsSearching(true);
    setNotification("Analizando intención espacial...");

    try {
      const res = await fetch(
        `http://localhost:8000/api/v1/search/intent?q=${encodeURIComponent(query)}`
      );
      if (!res.ok) throw new Error(`El motor semántico falló (Error ${res.status}). Verifica el Backend.`);
      const data = await res.json();

      if (data.warning) setNotification(data.warning);
      else setNotification(null); // Limpiar si todo fue exitoso

      if (data.bbox && data.bbox.length === 4) {
        const longitude = (data.bbox[0] + data.bbox[2]) / 2;
        const latitude = (data.bbox[1] + data.bbox[3]) / 2;
        setViewState((prev) => ({ ...prev, longitude, latitude, zoom: 8, transitionDuration: 2500 }));
      } else {
        setNotification("Se detectó la entidad, pero el motor no pudo calcular las coordenadas exactas de vuelo.");
      }

      if (data.entidad_id) setActiveEntidadFilter(data.entidad_id);
      if (data.municipio_id) setActiveMunicipioFilter(data.municipio_id);
      if (data.distrito_local_id) setActiveDLFilter(data.distrito_local_id);
      if (data.cargo_inferido) setActiveElection(data.cargo_inferido);

      if (data.candidato_inferido) {
        setActiveDossierCandidate(data.candidato_inferido);
        setShowDossier(true);
      }

      setSelectedFeature(null);
      setWinnerIdentity(null);
      setQuery("");
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    } catch (error: any) {
      console.error("Error crítico en Omnibox:", error);
      setNotification(`Fallo del Sistema: ${error.message}`);
    } finally {
      setIsSearching(false);
    }
  };

  const tileQuery = new URLSearchParams();
  if (activeEntidadFilter) tileQuery.set("entidad_filter", String(activeEntidadFilter));
  if (activeMunicipioFilter) tileQuery.set("municipio_filter", String(activeMunicipioFilter));
  if (activeDLFilter) tileQuery.set("distrito_local_filter", String(activeDLFilter));
  const tileUrl = `http://localhost:8000/api/v1/mapa/tiles/${activeElection}/{z}/{x}/{y}${
    tileQuery.toString() ? `?${tileQuery.toString()}` : ""
  }`;
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
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        getFillColor: (f: any) => {
          const rawVotos = f.properties?.votos_desglosados;
          const votos = typeof rawVotos === "string" ? JSON.parse(rawVotos || "{}") : (rawVotos || {});
          const totalVotos = Number(f.properties?.total_votos_calculados || 0);

          // FIX: Si no hay votos, devolvemos un gris azulado traslúcido para ver el territorio
          if (totalVotos === 0 && Object.keys(votos).length === 0) return [30, 41, 59, 150];

          const maxParty = Object.keys(votos).reduce((a, b) => Number(votos[a]) > Number(votos[b]) ? a : b, "");

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

      {/* OMNIBOX ESTILO GPT (Posicionado a 25vh del top) */}
      <div className="absolute top-[20vh] left-1/2 -translate-x-1/2 z-20 w-full max-w-3xl px-4 flex flex-col items-center">
        {/* Selector Contextual Superior (Anos/Cargos) */}
        <div
          className="mb-3 flex items-center gap-2 bg-gray-900/80 backdrop-blur-xl border border-gray-700/50 rounded-full px-4 py-1.5 shadow-lg cursor-pointer hover:bg-gray-800 transition-all"
          onClick={() => setShowMenu(!showMenu)}
        >
          <span className="w-2 h-2 rounded-full bg-teal-500 animate-pulse"></span>
          <User className="w-3.5 h-3.5 text-gray-400" />
          <span className="text-xs font-bold text-gray-300 tracking-wider">
            {selectedYear} • {activeElection.replace("_", " ")}
          </span>
          <ChevronDown
            className={`w-4 h-4 text-gray-400 transition-transform ${showMenu ? "rotate-180" : ""}`}
          />
        </div>

        {/* Input Bar Principal */}
        <div
          className={`relative w-full bg-gray-800/90 backdrop-blur-2xl border border-gray-600/50 rounded-[2rem] shadow-[0_10px_40px_-10px_rgba(0,0,0,0.5)] transition-all duration-300 focus-within:border-teal-500/50 focus-within:bg-gray-800 focus-within:shadow-[0_10px_50px_-10px_rgba(45,212,191,0.2)] ${
            notification ? "animate-shake border-red-500/50" : ""
          }`}
        >
          <div className="flex items-end px-3 py-3">
            {/* Boton Adjuntar (Abre Modal EDI vacio para crear perfil) */}
            <button
              title="Crear Expediente / Adjuntar"
              onClick={() => {
                setActiveDossierCandidate("NUEVO PERFIL");
                setShowDossier(true);
              }}
              className="p-2.5 text-gray-400 hover:text-teal-400 hover:bg-gray-700/50 rounded-full transition-colors"
            >
              <Paperclip className="w-5 h-5" />
            </button>

            {/* Textarea Auto-expandible */}
            <textarea
              rows={1}
              className="flex-1 bg-transparent text-white px-3 py-2.5 max-h-32 outline-none resize-none placeholder-gray-500 font-medium leading-relaxed custom-scrollbar"
              placeholder="Busca resultados, candidatos, distritos o municipios..."
              value={query}
              onChange={(e) => {
                setQuery(e.target.value);
                e.target.style.height = "auto";
                e.target.style.height = `${e.target.scrollHeight}px`;
              }}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  executeSearch();
                }
              }}
            />

            {/* Boton BUSCAR */}
            <button
              onClick={executeSearch}
              disabled={query.trim() === "" || isSearching}
              className={`ml-2 text-white text-xs font-black tracking-widest py-2.5 px-8 rounded-xl transition-all shadow-[0_0_15px_rgba(45,212,191,0.2)] flex items-center justify-center min-w-[120px] ${
                query.trim() !== "" && !isSearching
                  ? "bg-teal-600/90 hover:bg-teal-500"
                  : "bg-gray-700/50 cursor-not-allowed"
              }`}
            >
              {isSearching ? <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin"></div> : "BUSCAR"}
            </button>
          </div>
        </div>

        {/* Notificaciones / Errores de Busqueda */}
        {notification && (
          <div className="mt-4 bg-red-900/30 border border-red-500/50 backdrop-blur-md rounded-xl px-4 py-2.5 flex items-center gap-3 shadow-lg animate-in fade-in slide-in-from-top-2 w-full max-w-2xl">
            <AlertCircle className="w-5 h-5 text-red-400 flex-shrink-0" />
            <p className="text-xs text-red-200 leading-relaxed font-medium">{notification}</p>
            <button
              onClick={() => setNotification(null)}
              className="ml-auto text-red-400 hover:text-red-200"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        )}

        {/* Modal Menu Maestro (Anos/Cargos) - Diseno Refinado */}
        {showMenu && (
          <div className="absolute top-[100%] mt-4 w-full bg-gray-900/95 backdrop-blur-xl border border-gray-700/80 rounded-3xl p-6 shadow-2xl animate-in fade-in zoom-in-95">
            <div className="flex gap-8">
              <div className="w-1/4 border-r border-gray-800 pr-6">
                <h4 className="text-[10px] text-gray-500 font-bold tracking-widest uppercase mb-4">
                  Ciclo Electoral
                </h4>
                <div className="flex flex-col gap-2">
                  {[2024, 2021, 2018].map((year) => (
                    <button
                      key={year}
                      onClick={() => setSelectedYear(year)}
                      className={`text-left px-4 py-2.5 rounded-xl text-sm font-bold transition-all ${
                        selectedYear === year
                          ? "bg-teal-900/40 text-teal-400 border border-teal-800/50"
                          : "text-gray-500 hover:bg-gray-800 hover:text-gray-300"
                      }`}
                    >
                      {year}{" "}
                      {year !== 2024 && (
                        <span className="text-[9px] ml-2 text-gray-600 bg-gray-800 px-1.5 py-0.5 rounded">
                          PROX
                        </span>
                      )}
                    </button>
                  ))}
                </div>
              </div>
              <div className="w-3/4">
                <h4 className="text-[10px] text-gray-500 font-bold tracking-widest uppercase mb-4">
                  Elecciones ({selectedYear})
                </h4>
                <div className="grid grid-cols-2 gap-3">
                  {[
                    { id: "PRESIDENCIA", name: "Presidencia de la Republica" },
                    { id: "SENADURIA", name: "Senadurias" },
                    { id: "DIPUTACION_FEDERAL", name: "Diputaciones Federales" },
                    { id: "GUBERNATURA", name: "Gubernaturas" },
                    { id: "AYUNTAMIENTO", name: "Ayuntamientos y Alcaldias" },
                    { id: "DIPUTACION_LOCAL", name: "Diputaciones Locales" },
                  ].map((cargo) => (
                    <button
                      key={cargo.id}
                      disabled={selectedYear !== 2024}
                      onClick={() => {
                        setActiveElection(cargo.id);
                        setShowMenu(false);
                        setSelectedFeature(null);
                      }}
                      className={`text-left px-5 py-3.5 rounded-xl border text-sm font-bold transition-all ${
                        activeElection === cargo.id
                          ? "bg-teal-900/30 border-teal-500/50 text-white shadow-inner"
                          : "bg-gray-950 border-gray-800/50 text-gray-400 hover:border-gray-600 hover:text-white hover:bg-gray-900"
                      } ${selectedYear !== 2024 ? "opacity-50 cursor-not-allowed" : ""}`}
                    >
                      {cargo.name}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Botones Flotantes de Control de Mapa (Esquina Inferior Izquierda) */}
      <div className="absolute bottom-8 left-8 z-10 flex flex-col gap-3">
        <button
          onClick={() => {
            setViewState({
              ...INITIAL_VIEW_STATE,
              transitionDuration: 1200,
            });
            setActiveEntidadFilter(null);
            setActiveMunicipioFilter(null);
            setActiveDLFilter(null);
            setSelectedFeature(null);
            setWinnerIdentity(null);
            setHoverInfo(null);
          }}
          className="bg-gray-900/80 backdrop-blur-xl border border-gray-700/50 rounded-full p-4 shadow-lg hover:bg-gray-800 transition-colors group"
          title="Restaurar Mapa Nacional"
        >
          <RotateCcw className="w-6 h-6 text-gray-400 group-hover:text-teal-400 transition-colors" />
        </button>
        {/* Toggles Tacticos Redisenados */}
        <div className="bg-gray-900/80 backdrop-blur-xl border border-gray-700/50 rounded-full p-2 flex flex-col gap-2 shadow-lg">
          <label
            className="p-2 rounded-full cursor-pointer hover:bg-gray-800 transition-colors group"
            title="Mostrar Municipios"
          >
            <input
              type="checkbox"
              checked={showMun}
              onChange={(e) => setShowMun(e.target.checked)}
              className="hidden"
            />
            <div
              className={`w-4 h-4 rounded-full border-2 ${
                showMun ? "bg-white border-white" : "border-gray-500 group-hover:border-white"
              }`}
            ></div>
          </label>
          <label
            className="p-2 rounded-full cursor-pointer hover:bg-gray-800 transition-colors group"
            title="Mostrar Distritos Locales"
          >
            <input
              type="checkbox"
              checked={showDL}
              onChange={(e) => setShowDL(e.target.checked)}
              className="hidden"
            />
            <div
              className={`w-4 h-4 rounded-full border-2 ${
                showDL ? "bg-blue-500 border-blue-500" : "border-gray-500 group-hover:border-blue-400"
              }`}
            ></div>
          </label>
          <label
            className="p-2 rounded-full cursor-pointer hover:bg-gray-800 transition-colors group"
            title="Mostrar Distritos Federales"
          >
            <input
              type="checkbox"
              checked={showDF}
              onChange={(e) => setShowDF(e.target.checked)}
              className="hidden"
            />
            <div
              className={`w-4 h-4 rounded-full border-2 ${
                showDF
                  ? "bg-purple-500 border-purple-500"
                  : "border-gray-500 group-hover:border-purple-400"
              }`}
            ></div>
          </label>
        </div>
      </div>

      {/* PANEL ANALÍTICO DERECHO */}
      <div className="absolute top-6 right-6 z-10 w-[26rem] max-h-[calc(100vh-3rem)] flex flex-col pointer-events-none">
        <div className="bg-gray-900/90 backdrop-blur-xl border border-gray-700/50 rounded-2xl p-5 shadow-2xl pointer-events-auto overflow-y-auto custom-scrollbar">
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

      {/* EXPEDIENTE DIGITAL DE INTELIGENCIA (MODAL EDI) */}
      {showDossier && (
        <div className="absolute inset-0 z-50 flex items-center justify-center bg-gray-950/80 backdrop-blur-sm animate-in fade-in">
          <div className="bg-gray-900 border border-gray-700 w-[60rem] h-[40rem] rounded-2xl shadow-[0_0_50px_rgba(0,0,0,0.5)] flex flex-col overflow-hidden relative">
            {/* Header */}
            <div className="bg-gray-950 p-4 border-b border-gray-800 flex justify-between items-center">
              <div className="flex items-center gap-3">
                <div className="w-3 h-3 bg-red-500 rounded-full animate-pulse"></div>
                <h2 className="text-teal-500 font-mono tracking-widest text-sm">
                  EXPEDIENTE DIGITAL DE INTELIGENCIA (EDI)
                </h2>
              </div>
              <button
                onClick={() => setShowDossier(false)}
                className="text-gray-400 hover:text-white font-bold text-2xl px-2"
              >
                &times;
              </button>
            </div>

            <div className="flex flex-1 overflow-hidden">
              {/* Columna Izquierda: Biometría y Perfil */}
              <div className="w-1/3 bg-gray-950/50 border-r border-gray-800 p-6 flex flex-col items-center">
                   {/* FIX CRÍTICO: Input de archivo oculto y zona interactiva */}
                   <input type="file" ref={fileInputRef} onChange={handleFileUpload} className="hidden" accept="image/*" />
                   <div
                     onClick={() => fileInputRef.current?.click()}
                     className="w-48 h-48 rounded-2xl border-2 border-dashed border-gray-600 bg-gray-800/50 flex flex-col items-center justify-center cursor-pointer hover:border-teal-500 hover:bg-gray-800 transition-all overflow-hidden relative group shadow-inner"
                   >
                      {isUploading ? (
                        <div className="animate-spin w-8 h-8 border-4 border-teal-500 border-t-transparent rounded-full"></div>
                      ) : profileImgUrl ? (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img src={profileImgUrl} alt="Perfil" className="w-full h-full object-cover object-top" />
                      ) : (
                        <p className="text-[11px] text-gray-400 text-center px-4 group-hover:text-teal-400">
                          Clic o Arrastrar imagen
                          <br />
                          (IA quitará el fondo)
                        </p>
                      )}
                   </div>
                <h1 className="mt-6 text-2xl font-black text-white text-center uppercase leading-tight">
                  {activeDossierCandidate}
                </h1>
                <p className="text-xs text-teal-400 mt-2 border border-teal-900 bg-teal-950/30 px-3 py-1 rounded">
                  PERFIL ACTIVO
                </p>

                {isEditMode ? (
                  <button
                    onClick={handleSaveDossier}
                    className="mt-8 w-full py-3 bg-teal-600 hover:bg-teal-500 border border-teal-400 rounded text-xs font-black tracking-widest text-white transition-colors shadow-[0_0_15px_rgba(45,212,191,0.4)] flex justify-center items-center"
                  >
                    {isSaving ? (
                      <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
                    ) : (
                      "GUARDAR EXPEDIENTE"
                    )}
                  </button>
                ) : (
                  <button
                    onClick={() => setIsEditMode(true)}
                    className="mt-8 w-full py-3 bg-gray-800 hover:bg-gray-700 border border-gray-600 rounded text-xs font-bold tracking-widest text-white transition-colors shadow-lg"
                  >
                    MODO EDICIÓN (ADMIN)
                  </button>
                )}
              </div>

              {/* Columna Derecha: Inteligencia y Scraping */}
              <div className="w-2/3 p-6 overflow-y-auto custom-scrollbar flex flex-col gap-6">
                {/* Escáner Web Funcional */}
                <div className="bg-gray-950 p-5 rounded-xl border border-gray-800 shadow-md">
                  <h3 className="text-xs text-gray-500 font-bold tracking-widest mb-3 uppercase">
                    Minería de Datos (Escáner Web)
                  </h3>
                  <div className="flex gap-2">
                    <input
                      type="text"
                      value={wikiUrl}
                      onChange={(e) => setWikiUrl(e.target.value)}
                      placeholder="Pegar URL de Wikipedia, SaberVotar..."
                      className="flex-1 bg-gray-900 border border-gray-700 rounded px-4 py-2 text-sm text-white outline-none focus:border-teal-500"
                    />
                    <button onClick={handleWikiScan} className="bg-teal-700 hover:bg-teal-600 text-white px-6 rounded text-xs font-bold tracking-wider">
                      EXTRAER
                    </button>
                  </div>
                </div>

                {/* Panel de Datos Personales y Biografía */}
                {isEditMode ? (
                  <div className="bg-gray-900 p-5 rounded-xl border border-teal-900/50 flex flex-col gap-4 shadow-inner">
                    <div>
                      <label className="text-[10px] text-teal-500 font-bold uppercase tracking-widest mb-1 block">
                        Teléfono / Contacto
                      </label>
                      <input
                        type="text"
                        value={dossierForm.telefono}
                        onChange={(e) =>
                          setDossierForm({ ...dossierForm, telefono: e.target.value })
                        }
                        className="w-full bg-gray-950 border border-gray-800 rounded px-3 py-2 text-sm text-white outline-none focus:border-teal-500"
                        placeholder="+52 ..."
                      />
                    </div>
                    <div className="flex gap-4">
                      <div className="flex-1">
                        <label className="text-[10px] text-teal-500 font-bold uppercase tracking-widest mb-1 block">
                          Twitter (X)
                        </label>
                        <input
                          type="text"
                          value={dossierForm.twitter}
                          onChange={(e) =>
                            setDossierForm({ ...dossierForm, twitter: e.target.value })
                          }
                          className="w-full bg-gray-950 border border-gray-800 rounded px-3 py-2 text-sm text-white outline-none focus:border-teal-500"
                          placeholder="@usuario"
                        />
                      </div>
                      <div className="flex-1">
                        <label className="text-[10px] text-teal-500 font-bold uppercase tracking-widest mb-1 block">
                          Facebook
                        </label>
                        <input
                          type="text"
                          value={dossierForm.facebook}
                          onChange={(e) =>
                            setDossierForm({ ...dossierForm, facebook: e.target.value })
                          }
                          className="w-full bg-gray-950 border border-gray-800 rounded px-3 py-2 text-sm text-white outline-none focus:border-teal-500"
                          placeholder="/usuario"
                        />
                      </div>
                    </div>
                    <div>
                      <label className="text-[10px] text-teal-500 font-bold uppercase tracking-widest mb-1 block">
                        Extracto Biográfico (Editable)
                      </label>
                      <textarea
                        value={dossierForm.biografia}
                        onChange={(e) =>
                          setDossierForm({ ...dossierForm, biografia: e.target.value })
                        }
                        className="w-full bg-gray-950 border border-gray-800 rounded px-3 py-2 text-sm text-gray-300 outline-none focus:border-teal-500 h-32 resize-none custom-scrollbar"
                        placeholder="Ingresa el resumen biográfico o extraelo de Wikipedia..."
                      ></textarea>
                    </div>
                  </div>
                ) : (
                  (dossierForm.biografia || dossierForm.telefono) && (
                    <div className="bg-gray-900/50 p-5 rounded-xl border border-gray-800 shadow-md">
                      {dossierForm.telefono && (
                        <p className="text-sm text-white mb-2">
                          <span className="text-gray-500 text-xs font-mono mr-2">TEL:</span>
                          {dossierForm.telefono}
                        </p>
                      )}
                      {(dossierForm.twitter || dossierForm.facebook) && (
                        <div className="flex gap-4 mb-4">
                          {dossierForm.twitter && (
                            <p className="text-sm text-blue-400">
                              <span className="text-gray-500 text-xs font-mono mr-2">X:</span>
                              {dossierForm.twitter}
                            </p>
                          )}
                          {dossierForm.facebook && (
                            <p className="text-sm text-blue-500">
                              <span className="text-gray-500 text-xs font-mono mr-2">FB:</span>
                              {dossierForm.facebook}
                            </p>
                          )}
                        </div>
                      )}
                      {dossierForm.biografia && (
                        <>
                          <h4 className="text-[10px] text-gray-500 font-bold tracking-widest uppercase mb-2">
                            Perfil Analítico:
                          </h4>
                          <p className="text-sm text-gray-300 leading-relaxed text-justify">
                            {dossierForm.biografia}
                          </p>
                        </>
                      )}
                    </div>
                  )
                )}

                {/* Trayectoria Dinámica Extraída de BD */}
                <div>
                  <h3 className="text-xs text-gray-500 font-bold tracking-widest mb-4 uppercase border-b border-gray-800 pb-2">
                    Trayectoria Electoral Detectada
                  </h3>
                  <div className="space-y-4 border-l-2 border-gray-700 ml-3 pl-5">
                    {bioData?.trayectoria && bioData.trayectoria.length > 0 ? (
                      // eslint-disable-next-line @typescript-eslint/no-explicit-any
                      bioData.trayectoria.map((item: any, idx: number) => (
                        <div key={idx} className="relative">
                          <div className="absolute -left-[26px] top-1 w-3 h-3 bg-green-500 rounded-full border-2 border-gray-900 shadow-[0_0_8px_rgba(34,197,94,0.6)]"></div>
                          <p className="text-xs font-bold text-gray-400">CICLO {item.ciclo}</p>
                          <p className="text-base font-bold text-white uppercase">
                            {item.cargo.replace(/_/g, " ")}
                          </p>
                          <p className="text-sm text-gray-400 mt-1">
                            Siglado:{" "}
                            <span className="text-white font-mono">{item.siglado || "S/D"}</span>
                          </p>
                          <p className="text-sm text-gray-400">
                            Resultado:{" "}
                            <span className="text-green-400 font-bold">{item.resultado}</span>
                          </p>
                        </div>
                      ))
                    ) : (
                      <p className="text-sm text-gray-500 italic">
                        No hay registros de trayectoria previos en la base de datos local para este
                        perfil.
                      </p>
                    )}
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
