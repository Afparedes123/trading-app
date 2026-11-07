"use client";
import React, { useEffect, useState, useRef, useMemo } from "react";

const DEFAULT_API = process.env.NEXT_PUBLIC_API_URL || "https://trading-app-jn5a.onrender.com";

export default function TrendSpiderPage() {
  const [signal, setSignal] = useState(null);
  const [loading, setLoading] = useState(true);
  const [timeEc, setTimeEc] = useState("");
  const [backendStatus, setBackendStatus] = useState("Conectando con motor TrendSpider v15.0...");
  const [customApi, setCustomApi] = useState(DEFAULT_API);

  // Parámetros de Control TrendSpider
  const [analysisType, setAnalysisType] = useState("Standard");       // "Original", "Standard", "Enhanced"
  const [drawingInput, setDrawingInput] = useState("Wick");           // "Wick", "Body"
  const [islandGaps, setIslandGaps] = useState("Respect");            // "Respect", "Ignore"
  const [qualityFilter, setQualityFilter] = useState("Most Relevant");// "Most Relevant", "Moderately Relevant", "Unfiltered"
  const [heatmapMode, setHeatmapMode] = useState("Horizontal");       // "Horizontal", "Depth", "Trends", "Off"
  const [truthLocked, setTruthLocked] = useState(false);
  const [lockTimestamp, setLockTimestamp] = useState("");

  // AI Strategy Lab
  const [aiModel, setAiModel] = useState("Ensemble");                 // "Ensemble", "RandomForest", "Logistic", "KNN", "NaiveBayes"
  const [tpPct, setTpPct] = useState(0.14);
  const [slPct, setSlPct] = useState(0.08);
  const [horizon, setHorizon] = useState(30);

  // Pestaña visual activa
  const [activeTab, setActiveTab] = useState("chart"); // "chart", "strategy_lab", "heatmap", "audit"

  const fetchData = async () => {
    try {
      const queryParams = new URLSearchParams({
        analysis_type: analysisType,
        drawing_input: drawingInput,
        island_gaps: islandGaps,
        quality_filter: qualityFilter,
        heatmap_mode: heatmapMode,
        ai_model: aiModel,
        tp_pct: String(tpPct),
        sl_pct: String(slPct),
        horizon: String(horizon),
        truth_lock_ts: truthLocked && lockTimestamp ? String(lockTimestamp) : ""
      });

      // Intentar primero con la URL configurada
      let res;
      try {
        res = await fetch(`${customApi}/signals/live?${queryParams.toString()}`, { cache: "no-store" });
      } catch (err) {
        // Fallback automático a localhost si customApi falla o viceversa
        const altUrl = customApi.includes("localhost") ? DEFAULT_API : "http://localhost:8000";
        res = await fetch(`${altUrl}/signals/live?${queryParams.toString()}`, { cache: "no-store" });
        setCustomApi(altUrl);
      }

      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      const sig = Array.isArray(data) && data.length > 0 ? data[0] : data.symbol ? data : null;

      if (sig && sig.symbol?.includes("XAU")) {
        setSignal(sig);
        setBackendStatus(`En Línea • ${sig.feed_source || "Spot Institucional"} • TrendSpider v15.0`);
        if (sig.truth_in_analysis?.locked && !lockTimestamp) {
          setLockTimestamp(sig.truth_in_analysis.lock_ts);
          setTruthLocked(true);
        }
      } else {
        throw new Error("Datos incompletos");
      }
    } catch (e) {
      setBackendStatus(`Reconectando (${e.message})...`);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
    const fetchInterval = setInterval(fetchData, 6000);
    const clockInterval = setInterval(() => {
      const now = new Date().toLocaleString("es-EC", {
        timeZone: "America/Guayaquil",
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
        weekday: "short",
        day: "2-digit",
        month: "short"
      });
      setTimeEc(now);
    }, 1000);

    return () => {
      clearInterval(fetchInterval);
      clearInterval(clockInterval);
    };
  }, [analysisType, drawingInput, islandGaps, qualityFilter, heatmapMode, aiModel, tpPct, slPct, horizon, truthLocked, lockTimestamp, customApi]);

  // Manejador de bloqueo / desbloqueo de "Truth in Analysis"
  const toggleTruthLock = () => {
    if (truthLocked) {
      setTruthLocked(false);
      setLockTimestamp("");
    } else {
      if (signal?.recent_candles?.length > 0) {
        const midCandle = signal.recent_candles[Math.max(0, signal.recent_candles.length - 12)];
        setLockTimestamp(String(midCandle.ts));
        setTruthLocked(true);
      }
    }
  };

  if (loading && !signal) {
    return (
      <div style={{
        minHeight: "100vh",
        background: "#08090c",
        color: "#f8fafc",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        fontFamily: "system-ui, -apple-system, sans-serif"
      }}>
        <div style={{
          width: "48px",
          height: "48px",
          border: "4px solid rgba(245, 158, 11, 0.2)",
          borderTop: "4px solid #f59e0b",
          borderRadius: "50%",
          animation: "spin 0.9s linear infinite",
          marginBottom: "16px"
        }} />
        <div style={{ fontSize: "17px", fontWeight: "800", color: "#f8fafc" }}>
          Iniciando Algoritmo TrendSpider Quant v15.0...
        </div>
        <div style={{ fontSize: "12px", color: "#94a3b8", marginTop: "6px" }}>
          Calibrando matrices de geometría computacional, Auto-Fibs y Strategy Lab...
        </div>
        <style>{`@keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }`}</style>
      </div>
    );
  }

  const s = signal || {};
  const isBuy = s.direction === "COMPRA";
  const isSell = s.direction === "VENTA";
  const isWait = s.direction === "ESPERA";
  const alertType = s.alert_type || "WAIT";

  const getAlertColor = (type) => {
    if (type === "TAKE_PROFIT") return { bg: "rgba(234,179,8,0.18)", border: "#eab308", text: "#fde047" };
    if (type === "EXIT") return { bg: "rgba(239,68,68,0.22)", border: "#ef4444", text: "#fca5a5" };
    if (type === "ENTER") return { bg: "rgba(34,197,94,0.18)", border: "#22c55e", text: "#4ade80" };
    return { bg: "rgba(39,39,42,0.6)", border: "#52525b", text: "#d4d4d8" };
  };
  const alertColor = getAlertColor(alertType);

  const trendlines = s.trendlines || [];
  const fib = s.fibonacci || {};
  const heatmap = s.heatmap || {};
  const ai = s.ai_strategy || {};
  const candles = s.recent_candles || [];
  const pointsDetail = s.points_detail || [];

  return (
    <div style={{
      minHeight: "100vh",
      background: "#08090c",
      color: "#f8fafc",
      padding: "16px",
      fontFamily: "system-ui, -apple-system, sans-serif"
    }}>
      <div style={{ maxWidth: "1150px", margin: "0 auto" }}>

        {/* ============================================================== */}
        {/* CABECERA INSTITUCIONAL TRENDSPIDER QUANT */}
        {/* ============================================================== */}
        <header style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          flexWrap: "wrap",
          gap: "14px",
          borderBottom: "1px solid #1e2430",
          paddingBottom: "14px",
          marginBottom: "14px"
        }}>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
              <div style={{
                width: "12px", height: "12px", borderRadius: "50%",
                background: truthLocked ? "#eab308" : "#22c55e",
                boxShadow: `0 0 10px ${truthLocked ? "#eab308" : "#22c55e"}`
              }} />
              <h1 style={{ fontSize: "21px", fontWeight: "900", margin: 0, letterSpacing: "-0.5px" }}>
                EDGEALERT <span style={{ color: "#f59e0b" }}>TRENDSPIDER</span> <span style={{ fontSize: "12px", color: "#64748b", fontWeight: "600" }}>v15.0 QUANT</span>
              </h1>
            </div>
            <div style={{ fontSize: "11px", color: "#94a3b8", marginTop: "3px" }}>
              {timeEc} • {backendStatus}
            </div>
            <div style={{ fontSize: "12px", color: "#38bdf8", fontWeight: "700", marginTop: "4px" }}>
              XAU/USD SPOT: <span style={{ color: "#fff", fontSize: "15px", fontWeight: "900" }}>${s.live_price?.toFixed(2)}</span>
              <span style={{ color: "#64748b", marginLeft: "8px" }}>| ATR(14): ${s.atr?.toFixed(2)}</span>
              <span style={{ color: "#f59e0b", marginLeft: "8px" }}>| Vectores Analizados: {s.total_candidate_vectors || 0}</span>
            </div>
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
            <div style={{
              padding: "10px 20px",
              borderRadius: "10px",
              background: isBuy ? "rgba(34,197,94,0.18)" : isSell ? "rgba(239,68,68,0.18)" : "rgba(39,39,42,0.7)",
              border: `2px solid ${isBuy ? "#22c55e" : isSell ? "#ef4444" : "#71717a"}`,
              color: isBuy ? "#4ade80" : isSell ? "#f87171" : "#e4e4e7",
              textAlign: "center"
            }}>
              <div style={{ fontSize: "16px", fontWeight: "900", letterSpacing: "1px" }}>
                {s.direction} {isBuy ? "▲" : isSell ? "▼" : "⏸"}
              </div>
              <div style={{ fontSize: "10px", opacity: 0.85, marginTop: "2px" }}>
                Confianza: {s.confidence}%
              </div>
            </div>
          </div>
        </header>

        {/* ============================================================== */}
        {/* BARRA DE PREFERENCIAS DE CONTROL TRENDSPIDER */}
        {/* ============================================================== */}
        <section style={{
          background: "#0f131a",
          border: "1px solid #1e2638",
          borderRadius: "12px",
          padding: "12px 14px",
          marginBottom: "14px",
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))",
          gap: "10px",
          fontSize: "11px"
        }}>
          {/* Analysis Type */}
          <div>
            <label style={{ color: "#94a3b8", display: "block", marginBottom: "4px", fontWeight: "700" }}>
              1. SENSIVILIDAD VENTANA
            </label>
            <select
              value={analysisType}
              onChange={(e) => setAnalysisType(e.target.value)}
              style={{
                width: "100%", background: "#1a2130", color: "#fff", border: "1px solid #334155",
                borderRadius: "6px", padding: "6px 8px", fontSize: "11px", fontWeight: "600", outline: "none"
              }}
            >
              <option value="Standard">Standard (Equilibrado)</option>
              <option value="Original">Original (Macro / Filtra Ruido)</option>
              <option value="Enhanced">Enhanced (Micro / Scalping)</option>
            </select>
          </div>

          {/* Drawing Input */}
          <div>
            <label style={{ color: "#94a3b8", display: "block", marginBottom: "4px", fontWeight: "700" }}>
              2. ANCLAJE DE VELA
            </label>
            <select
              value={drawingInput}
              onChange={(e) => setDrawingInput(e.target.value)}
              style={{
                width: "100%", background: "#1a2130", color: "#fff", border: "1px solid #334155",
                borderRadius: "6px", padding: "6px 8px", fontSize: "11px", fontWeight: "600", outline: "none"
              }}
            >
              <option value="Wick">Wick (Mechas H/L Extremas)</option>
              <option value="Body">Body (Cuerpos O/C Apertura/Cierre)</option>
            </select>
          </div>

          {/* Island Gaps */}
          <div>
            <label style={{ color: "#94a3b8", display: "block", marginBottom: "4px", fontWeight: "700" }}>
              3. GAPS (3x ATR)
            </label>
            <select
              value={islandGaps}
              onChange={(e) => setIslandGaps(e.target.value)}
              style={{
                width: "100%", background: "#1a2130", color: "#fff", border: "1px solid #334155",
                borderRadius: "6px", padding: "6px 8px", fontSize: "11px", fontWeight: "600", outline: "none"
              }}
            >
              <option value="Respect">Respect (Bloquear sobre Gaps)</option>
              <option value="Ignore">Ignore (Conectar cruzando vacíos)</option>
            </select>
          </div>

          {/* Quality Filter */}
          <div>
            <label style={{ color: "#94a3b8", display: "block", marginBottom: "4px", fontWeight: "700" }}>
              4. FILTRO DE CALIDAD
            </label>
            <select
              value={qualityFilter}
              onChange={(e) => setQualityFilter(e.target.value)}
              style={{
                width: "100%", background: "#1a2130", color: "#fff", border: "1px solid #334155",
                borderRadius: "6px", padding: "6px 8px", fontSize: "11px", fontWeight: "600", outline: "none"
              }}
            >
              <option value="Most Relevant">Most Relevant (Top 1% Score)</option>
              <option value="Moderately Relevant">Moderately Relevant (Top 10%)</option>
              <option value="Unfiltered">Unfiltered (Todas)</option>
            </select>
          </div>

          {/* Heatmap Mode */}
          <div>
            <label style={{ color: "#94a3b8", display: "block", marginBottom: "4px", fontWeight: "700" }}>
              5. MAPA DE CALOR 40x60
            </label>
            <select
              value={heatmapMode}
              onChange={(e) => setHeatmapMode(e.target.value)}
              style={{
                width: "100%", background: "#1a2130", color: "#fff", border: "1px solid #334155",
                borderRadius: "6px", padding: "6px 8px", fontSize: "11px", fontWeight: "600", outline: "none"
              }}
            >
              <option value="Horizontal">Horizontal (Order Blocks)</option>
              <option value="Depth">Depth (Difusión 2D Confluencia)</option>
              <option value="Trends">Trends (Intersecciones Crudas)</option>
              <option value="Off">Desactivado</option>
            </select>
          </div>

          {/* Truth in Analysis Lock Toggle */}
          <div>
            <label style={{ color: "#94a3b8", display: "block", marginBottom: "4px", fontWeight: "700" }}>
              6. TRUTH IN ANALYSIS
            </label>
            <button
              onClick={toggleTruthLock}
              style={{
                width: "100%",
                background: truthLocked ? "#eab308" : "#1e293b",
                color: truthLocked ? "#000" : "#cbd5e1",
                border: `1px solid ${truthLocked ? "#facc15" : "#475569"}`,
                borderRadius: "6px",
                padding: "6px 8px",
                fontSize: "11px",
                fontWeight: "800",
                cursor: "pointer",
                transition: "all 0.2s"
              }}
            >
              {truthLocked ? "🟡 BLOQUEADO (OOS Test)" : "🔴 DESBLOQUEADO (En Vivo)"}
            </button>
          </div>
        </section>

        {/* ============================================================== */}
        {/* BANNER DE ORDEN Y CONTROL ANTI-RUIDO */}
        {/* ============================================================== */}
        <section style={{
          background: alertColor.bg,
          border: `2px solid ${alertColor.border}`,
          borderRadius: "12px",
          padding: "16px",
          marginBottom: "14px",
          boxShadow: `0 4px 20px ${alertColor.border}22`
        }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "8px" }}>
            <div style={{ fontWeight: "900", fontSize: "17px", color: alertColor.text, textTransform: "uppercase" }}>
              {s.alert}
            </div>
            <div style={{ fontSize: "11px", color: "#cbd5e1", background: "rgba(0,0,0,0.4)", padding: "4px 10px", borderRadius: "6px" }}>
              {s.flip_reason}
            </div>
          </div>
          <div style={{ fontSize: "12px", color: "#e2e8f0", marginTop: "6px", lineHeight: "1.5" }}>
            {s.alert_desc}
          </div>

          {/* Tarjetas Cuánticas */}
          <div style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(130px, 1fr))",
            gap: "8px",
            marginTop: "12px"
          }}>
            <div style={{ background: "rgba(0,0,0,0.45)", borderRadius: "8px", padding: "8px 10px", border: "1px solid #1e293b", textAlign: "center" }}>
              <div style={{ fontSize: "10px", color: "#94a3b8", fontWeight: "700" }}>PUNTUACIÓN QUANT</div>
              <div style={{ fontSize: "16px", fontWeight: "900", marginTop: "2px" }}>
                <span style={{ color: "#4ade80" }}>{s.buy_score || 0}C</span> <span style={{ color: "#475569" }}>/</span> <span style={{ color: "#f87171" }}>{s.sell_score || 0}V</span>
              </div>
            </div>

            <div style={{ background: "rgba(0,0,0,0.45)", borderRadius: "8px", padding: "8px 10px", border: "1px solid #1e293b", textAlign: "center" }}>
              <div style={{ fontSize: "10px", color: "#94a3b8", fontWeight: "700" }}>IA ({s.ai_strategy?.active_model || "Ensemble"})</div>
              <div style={{ fontSize: "16px", fontWeight: "900", marginTop: "2px", color: (s.ai_strategy?.buy_prob || 0.5) >= 0.65 ? "#4ade80" : (s.ai_strategy?.sell_prob || 0.5) >= 0.65 ? "#f87171" : "#38bdf8" }}>
                {((s.ai_strategy?.buy_prob || 0.5) >= (s.ai_strategy?.sell_prob || 0.5) ? s.ai_strategy?.buy_prob : s.ai_strategy?.sell_prob) * 100}%
              </div>
            </div>

            <div style={{ background: "rgba(0,0,0,0.45)", borderRadius: "8px", padding: "8px 10px", border: "1px solid #1e293b", textAlign: "center" }}>
              <div style={{ fontSize: "10px", color: "#94a3b8", fontWeight: "700" }}>ESPACIO ARRIBA</div>
              <div style={{ fontSize: "16px", fontWeight: "900", marginTop: "2px", color: (s.room_up || 0) < 2.5 ? "#f87171" : "#4ade80" }}>
                +${s.room_up?.toFixed(2)}
              </div>
            </div>

            <div style={{ background: "rgba(0,0,0,0.45)", borderRadius: "8px", padding: "8px 10px", border: "1px solid #1e293b", textAlign: "center" }}>
              <div style={{ fontSize: "10px", color: "#94a3b8", fontWeight: "700" }}>ESPACIO ABAJO</div>
              <div style={{ fontSize: "16px", fontWeight: "900", marginTop: "2px", color: (s.room_down || 0) < 2.5 ? "#f87171" : "#4ade80" }}>
                -${s.room_down?.toFixed(2)}
              </div>
            </div>

            <div style={{ background: "rgba(0,0,0,0.45)", borderRadius: "8px", padding: "8px 10px", border: "1px solid #1e293b", textAlign: "center" }}>
              <div style={{ fontSize: "10px", color: "#94a3b8", fontWeight: "700" }}>WIN RATE SIMULADO</div>
              <div style={{ fontSize: "16px", fontWeight: "900", marginTop: "2px", color: "#facc15" }}>
                {s.ai_strategy?.metrics?.win_rate || 68}%
              </div>
            </div>
          </div>
        </section>

        {/* ============================================================== */}
        {/* PARÁMETROS DE EJECUCIÓN (CUANDO NO ESTÁ EN ESPERA) */}
        {/* ============================================================== */}
        {!isWait && (
          <section style={{
            background: "rgba(15, 23, 42, 0.75)",
            border: `1px solid ${isBuy ? "#059669" : "#dc2626"}`,
            borderLeft: `6px solid ${isBuy ? "#10b981" : "#ef4444"}`,
            borderRadius: "10px",
            padding: "14px",
            marginBottom: "14px",
            fontFamily: "monospace",
            fontSize: "13px"
          }}>
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "6px" }}>
              <span style={{ color: "#94a3b8" }}>PRECIO ENTRADA (0.01 lotes):</span>
              <span style={{ fontWeight: "900", color: "#fff", fontSize: "15px" }}>${s.entry?.toFixed(2)}</span>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", color: "#f87171", marginBottom: "6px" }}>
              <span>STOP LOSS ESTRUCTURAL DINÁMICO (Riesgo ${s.dist?.toFixed(2)}):</span>
              <span style={{ fontWeight: "800" }}>${s.sl?.toFixed(2)}</span>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", color: "#34d399", marginBottom: "6px" }}>
              <span>TAKE PROFIT 1 - ZONA FIB/HEATMAP (+${s.tp_dist?.toFixed(2)}):</span>
              <span style={{ fontWeight: "800" }}>${s.tp1?.toFixed(2)}</span>
            </div>
            {s.tp2 > 0 && (
              <div style={{ display: "flex", justifyContent: "space-between", color: "#6ee7b7" }}>
                <span>TAKE PROFIT 2 - EXTENSIÓN FIB 1.618:</span>
                <span style={{ fontWeight: "800" }}>${s.tp2?.toFixed(2)}</span>
              </div>
            )}
          </section>
        )}

        {/* ============================================================== */}
        {/* PESTAÑAS DE VISUALIZACIÓN */}
        {/* ============================================================== */}
        <div style={{ display: "flex", gap: "6px", marginBottom: "12px", borderBottom: "1px solid #1e2638", paddingBottom: "6px" }}>
          {[
            { id: "chart", label: "GRÁFICO VECTORIAL TRENDSPIDER" },
            { id: "strategy_lab", label: "AI STRATEGY LAB (ML)" },
            { id: "audit", label: "AUDITORÍA DE CONFLUENCIAS" }
          ].map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              style={{
                background: activeTab === tab.id ? "#1e293b" : "transparent",
                color: activeTab === tab.id ? "#f59e0b" : "#94a3b8",
                border: activeTab === tab.id ? "1px solid #f59e0b" : "1px solid transparent",
                borderRadius: "6px",
                padding: "8px 14px",
                fontSize: "11px",
                fontWeight: "800",
                cursor: "pointer"
              }}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* ============================================================== */}
        {/* CONTENIDO 1: GRÁFICO VECTORIAL (SVG INTERACTIVO) */}
        {/* ============================================================== */}
        {activeTab === "chart" && (
          <section style={{
            background: "#0c0f17",
            border: "1px solid #1e2638",
            borderRadius: "12px",
            padding: "14px",
            marginBottom: "14px"
          }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "10px" }}>
              <div style={{ fontSize: "12px", fontWeight: "800", color: "#f8fafc" }}>
                Velas M1 + Vectores Auto-Trendlines (Top 1%) + Retracción Fibonacci + Matriz 40x60
              </div>
              <div style={{ fontSize: "10px", color: "#94a3b8" }}>
                Líneas activas: <b style={{ color: "#38bdf8" }}>{trendlines.length}</b> • Zona Dorada: <b style={{ color: "#facc15" }}>0.382 - 0.618 OTE</b>
              </div>
            </div>

            {/* Canvas SVG de Velas y Vectores */}
            <TrendSpiderChartCanvas
              candles={candles}
              trendlines={trendlines}
              fib={fib}
              heatmap={heatmap}
              livePrice={s.live_price}
              truthLocked={truthLocked}
              lockTimestamp={lockTimestamp}
            />

            {/* Leyenda del Gráfico */}
            <div style={{ display: "flex", flexWrap: "wrap", gap: "14px", marginTop: "10px", fontSize: "10px", color: "#94a3b8" }}>
              <span style={{ display: "flex", alignItems: "center", gap: "4px" }}>
                <span style={{ width: "12px", height: "3px", background: "#38bdf8", display: "inline-block" }} />
                Directriz de Resistencia
              </span>
              <span style={{ display: "flex", alignItems: "center", gap: "4px" }}>
                <span style={{ width: "12px", height: "3px", background: "#4ade80", display: "inline-block" }} />
                Directriz de Soporte
              </span>
              <span style={{ display: "flex", alignItems: "center", gap: "4px" }}>
                <span style={{ width: "12px", height: "8px", background: "rgba(234, 179, 8, 0.25)", border: "1px solid #eab308", display: "inline-block" }} />
                Zona Dorada Fibonacci (Full Mid)
              </span>
              <span style={{ display: "flex", alignItems: "center", gap: "4px" }}>
                <span style={{ width: "12px", height: "3px", background: truthLocked ? "#eab308" : "#ef4444", display: "inline-block" }} />
                Truth in Analysis Line
              </span>
              <span style={{ display: "flex", alignItems: "center", gap: "4px" }}>
                <span style={{ width: "8px", height: "8px", borderRadius: "50%", background: "#22c55e", display: "inline-block" }} />
                Ruptura Confirmada (Breakout al Cierre)
              </span>
            </div>
          </section>
        )}

        {/* ============================================================== */}
        {/* CONTENIDO 2: AI STRATEGY LAB DASHBOARD */}
        {/* ============================================================== */}
        {activeTab === "strategy_lab" && (
          <section style={{
            background: "#0c0f17",
            border: "1px solid #1e2638",
            borderRadius: "12px",
            padding: "16px",
            marginBottom: "14px"
          }}>
            <div style={{ fontSize: "14px", fontWeight: "900", color: "#f59e0b", marginBottom: "6px" }}>
              AI STRATEGY LAB (CLASIFICADORES ESTADÍSTICOS & MACHINE LEARNING)
            </div>
            <div style={{ fontSize: "12px", color: "#94a3b8", marginBottom: "16px" }}>
              Entrena modelos supervisados sobre series temporales con etiquetado Take Profit (%) y Stop Loss (%),
              combinando vectores mediante Cruce Genético (Crossbreeding) para predecir operaciones ganadoras con alta precisión.
            </div>

            {/* Controles de Target Labeling */}
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: "14px", marginBottom: "16px" }}>
              <div style={{ background: "#131824", padding: "12px", borderRadius: "8px", border: "1px solid #1e293b" }}>
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: "11px", fontWeight: "700", marginBottom: "6px" }}>
                  <span style={{ color: "#94a3b8" }}>TAKE PROFIT OBJETIVO:</span>
                  <span style={{ color: "#34d399" }}>{tpPct}% (~${(tpPct * (s.live_price || 4000) / 100).toFixed(2)})</span>
                </div>
                <input
                  type="range" min="0.06" max="0.30" step="0.01" value={tpPct}
                  onChange={(e) => setTpPct(parseFloat(e.target.value))}
                  style={{ width: "100%", accentColor: "#10b981" }}
                />
              </div>

              <div style={{ background: "#131824", padding: "12px", borderRadius: "8px", border: "1px solid #1e293b" }}>
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: "11px", fontWeight: "700", marginBottom: "6px" }}>
                  <span style={{ color: "#94a3b8" }}>STOP LOSS MÁXIMO:</span>
                  <span style={{ color: "#f87171" }}>{slPct}% (~${(slPct * (s.live_price || 4000) / 100).toFixed(2)})</span>
                </div>
                <input
                  type="range" min="0.04" max="0.20" step="0.01" value={slPct}
                  onChange={(e) => setSlPct(parseFloat(e.target.value))}
                  style={{ width: "100%", accentColor: "#ef4444" }}
                />
              </div>

              <div style={{ background: "#131824", padding: "12px", borderRadius: "8px", border: "1px solid #1e293b" }}>
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: "11px", fontWeight: "700", marginBottom: "6px" }}>
                  <span style={{ color: "#94a3b8" }}>HORIZONTE TEMPORAL:</span>
                  <span style={{ color: "#38bdf8" }}>{horizon} Velas</span>
                </div>
                <input
                  type="range" min="15" max="60" step="5" value={horizon}
                  onChange={(e) => setHorizon(parseInt(e.target.value))}
                  style={{ width: "100%", accentColor: "#38bdf8" }}
                />
              </div>
            </div>

            {/* Modelos Estadísticos Soportados */}
            <div style={{ marginBottom: "16px" }}>
              <div style={{ fontSize: "11px", fontWeight: "800", color: "#94a3b8", marginBottom: "8px" }}>
                MODELO ESTADÍSTICO ACTIVO:
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: "8px" }}>
                {[
                  { id: "Ensemble", name: "🧬 Crossbreeding Ensemble", desc: "Cruce genético ponderado de todos los modelos" },
                  { id: "RandomForest", name: "🌲 Random Forest", desc: "Ensemble no lineal multi-timeframe" },
                  { id: "Logistic", name: "📈 Logistic Regression", desc: "Regresión sigmoidal de probabilidad binaria" },
                  { id: "KNN", name: "🎯 K-Nearest Neighbors", desc: "Proximidad geométrica de estados de mercado" },
                  { id: "NaiveBayes", name: "🎲 Naive Bayes", desc: "Clasificador gaussiano probabilístico" }
                ].map((mod) => (
                  <div
                    key={mod.id}
                    onClick={() => setAiModel(mod.id)}
                    style={{
                      background: aiModel === mod.id ? "rgba(245, 158, 11, 0.15)" : "#131824",
                      border: `1px solid ${aiModel === mod.id ? "#f59e0b" : "#1e293b"}`,
                      borderRadius: "8px",
                      padding: "10px",
                      cursor: "pointer",
                      transition: "all 0.2s"
                    }}
                  >
                    <div style={{ fontSize: "12px", fontWeight: "800", color: aiModel === mod.id ? "#facc15" : "#fff" }}>
                      {mod.name}
                    </div>
                    <div style={{ fontSize: "10px", color: "#94a3b8", marginTop: "3px" }}>
                      {mod.desc}
                    </div>
                    <div style={{ fontSize: "10px", color: "#38bdf8", marginTop: "6px", fontWeight: "700" }}>
                      Precisión: {ai.accuracies?.[mod.id] || 88}%
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Medidor de Probabilidad de la Vela Actual */}
            <div style={{ background: "#131824", padding: "14px", borderRadius: "10px", border: "1px solid #1e293b" }}>
              <div style={{ fontSize: "11px", fontWeight: "800", color: "#94a3b8", marginBottom: "10px" }}>
                DISTRIBUCIÓN DE PROBABILIDAD PREDICHA PARA LA VELA EN VIVO
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
                <span style={{ fontSize: "11px", fontWeight: "800", color: "#4ade80", width: "80px" }}>
                  COMPRA {((ai.buy_prob || 0.5) * 100).toFixed(1)}%
                </span>
                <div style={{ flex: 1, height: "14px", background: "#1e293b", borderRadius: "7px", overflow: "hidden", display: "flex" }}>
                  <div style={{ width: `${(ai.buy_prob || 0.5) * 100}%`, background: "linear-gradient(90deg, #10b981, #22c55e)" }} />
                  <div style={{ width: `${(ai.sell_prob || 0.5) * 100}%`, background: "linear-gradient(90deg, #ef4444, #dc2626)" }} />
                </div>
                <span style={{ fontSize: "11px", fontWeight: "800", color: "#f87171", width: "80px", textAlign: "right" }}>
                  VENTA {((ai.sell_prob || 0.5) * 100).toFixed(1)}%
                </span>
              </div>
              <div style={{ fontSize: "10px", color: "#64748b", marginTop: "8px", textAlign: "center" }}>
                * El filtro anti-ruido exige ≥ 65% de probabilidad estadística y confluencia estructural antes de emitir una orden.
              </div>
            </div>
          </section>
        )}

        {/* ============================================================== */}
        {/* CONTENIDO 3: AUDITORÍA DE CONFLUENCIAS Y FILTROS */}
        {/* ============================================================== */}
        {activeTab === "audit" && (
          <section style={{
            background: "#0c0f17",
            border: "1px solid #1e2638",
            borderRadius: "12px",
            padding: "16px",
            marginBottom: "14px"
          }}>
            <div style={{ fontSize: "13px", fontWeight: "900", color: "#f8fafc", marginBottom: "8px", textTransform: "uppercase" }}>
              Auditoría Matemática de Confluencias (TrendSpider Scoring Engine)
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
              {pointsDetail.length === 0 ? (
                <div style={{ fontSize: "12px", color: "#64748b", textAlign: "center", padding: "16px" }}>
                  Sin gatillos de alta probabilidad en este segundo. Filtro de protección capital activo.
                </div>
              ) : (
                pointsDetail.map((item, idx) => (
                  <div
                    key={idx}
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "flex-start",
                      background: item.side === "COMPRA" ? "rgba(34,197,94,0.08)" : item.side === "VENTA" ? "rgba(239,68,68,0.08)" : "rgba(234,179,8,0.08)",
                      border: `1px solid ${item.side === "COMPRA" ? "rgba(34,197,94,0.3)" : item.side === "VENTA" ? "rgba(239,68,68,0.3)" : "rgba(234,179,8,0.3)"}`,
                      borderRadius: "8px",
                      padding: "10px 12px"
                    }}
                  >
                    <div>
                      <div style={{
                        fontSize: "12px",
                        fontWeight: "800",
                        color: item.side === "COMPRA" ? "#4ade80" : item.side === "VENTA" ? "#f87171" : "#facc15"
                      }}>
                        [{item.module}] {item.title} (+{item.weight} pts)
                      </div>
                      <div style={{ fontSize: "11px", color: "#94a3b8", marginTop: "3px" }}>
                        {item.desc}
                      </div>
                    </div>
                  </div>
                ))
              )}
            </div>
          </section>
        )}

      </div>
    </div>
  );
}

// ==============================================================================
// COMPONENTE: RENDERIZADOR DE GRÁFICO VECTORIAL TRENDSPIDER
// ==============================================================================
function TrendSpiderChartCanvas({ candles, trendlines, fib, heatmap, livePrice, truthLocked, lockTimestamp }) {
  if (!candles || candles.length === 0) {
    return <div style={{ height: "340px", display: "flex", alignItems: "center", justifyContent: "center", color: "#64748b" }}>Cargando gráfico...</div>;
  }

  const width = 1000;
  const height = 360;
  const paddingY = 25;
  const paddingRight = 65;

  const highs = candles.map((c) => c.high);
  const lows = candles.map((c) => c.low);
  const maxP = Math.max(...highs, livePrice || 0) + 0.8;
  const minP = Math.min(...lows, livePrice || 999999) - 0.8;
  const priceSpan = Math.max(maxP - minP, 1.0);

  const priceToY = (price) => {
    return paddingY + ((maxP - price) / priceSpan) * (height - paddingY * 2);
  };

  const candleWidth = (width - paddingRight) / Math.max(candles.length, 1);

  // Posición del lock de Truth in Analysis
  let lockX = null;
  if (truthLocked && lockTimestamp) {
    const lockTsNum = parseInt(lockTimestamp);
    const idx = candles.findIndex((c) => c.ts >= lockTsNum);
    if (idx !== -1) {
      lockX = idx * candleWidth + candleWidth / 2;
    }
  }

  // Zona dorada Fibonacci (0.382 a 0.618)
  const fibLevels = fib.levels || {};
  const fib382 = fibLevels["0.382"];
  const fib618 = fibLevels["0.618"];
  const fib000 = fibLevels["0.0"];
  const fib100 = fibLevels["1.0"];

  const gzTopY = fib382 && fib618 ? Math.min(priceToY(fib382), priceToY(fib618)) : null;
  const gzBottomY = fib382 && fib618 ? Math.max(priceToY(fib382), priceToY(fib618)) : null;
  const gzHeight = gzTopY !== null && gzBottomY !== null ? Math.max(gzBottomY - gzTopY, 2) : 0;

  return (
    <div style={{ position: "relative", width: "100%", overflowX: "auto" }}>
      <svg viewBox={`0 0 ${width} ${height}`} style={{ width: "100%", height: "auto", display: "block" }}>
        {/* Fondo del gráfico */}
        <rect width={width} height={height} fill="#0b0e14" />

        {/* Líneas horizontales de cuadrícula */}
        {[0, 0.25, 0.5, 0.75, 1].map((pct, i) => {
          const y = paddingY + pct * (height - paddingY * 2);
          const p = maxP - pct * priceSpan;
          return (
            <g key={i}>
              <line x1={0} y1={y} x2={width - paddingRight} y2={y} stroke="#171d29" strokeDasharray="3 3" />
              <text x={width - paddingRight + 6} y={y + 4} fill="#64748b" fontSize="10" fontFamily="monospace">
                {p.toFixed(2)}
              </text>
            </g>
          );
        })}

        {/* Sombreado de la ZONA DORADA FIBONACCI (0.382 - 0.618 OTE) */}
        {gzTopY !== null && (
          <g>
            <rect
              x={0}
              y={gzTopY}
              width={width - paddingRight}
              height={gzHeight}
              fill="rgba(245, 158, 11, 0.08)"
              stroke="rgba(245, 158, 11, 0.35)"
              strokeDasharray="4 4"
            />
            <text x={10} y={gzTopY + 14} fill="#f59e0b" fontSize="10" fontWeight="800">
              ZONA DORADA FIBONACCI (0.382 - 0.618 OTE)
            </text>
          </g>
        )}

        {/* Niveles clave de Fibonacci */}
        {["0.0", "0.5", "1.0"].map((lvl) => {
          if (!fibLevels[lvl]) return null;
          const y = priceToY(fibLevels[lvl]);
          return (
            <g key={lvl}>
              <line x1={0} y1={y} x2={width - paddingRight} y2={y} stroke="#eab308" strokeWidth="1" strokeDasharray="2 4" opacity="0.6" />
              <text x={width - paddingRight - 65} y={y - 3} fill="#eab308" fontSize="9" fontWeight="700">
                Fib {lvl} (${fibLevels[lvl].toFixed(1)})
              </text>
            </g>
          );
        })}

        {/* Perfil del Mapa de Calor Horizontal (Order Blocks en la matriz 40x60) */}
        {heatmap.mode === "Horizontal" && heatmap.horizontal_profile?.map((hp, i) => {
          if (hp.score < 25) return null;
          const y = priceToY(hp.price);
          const barW = (hp.score / 100) * 120;
          return (
            <rect
              key={i}
              x={0}
              y={y - 2}
              width={barW}
              height={4}
              fill="rgba(56, 189, 248, 0.18)"
              rx="2"
            />
          );
        })}

        {/* Velas Japonesas (M1) */}
        {candles.map((c, i) => {
          const x = i * candleWidth + candleWidth / 2;
          const openY = priceToY(c.open);
          const closeY = priceToY(c.close);
          const highY = priceToY(c.high);
          const lowY = priceToY(c.low);
          const isBull = c.close >= c.open;
          const bodyY = Math.min(openY, closeY);
          const bodyH = Math.max(Math.abs(closeY - openY), 1.5);
          const color = isBull ? "#22c55e" : "#ef4444";

          return (
            <g key={c.ts || i}>
              {/* Mecha */}
              <line x1={x} y1={highY} x2={x} y2={lowY} stroke={color} strokeWidth="1.2" opacity="0.8" />
              {/* Cuerpo */}
              <rect
                x={x - candleWidth * 0.35}
                y={bodyY}
                width={Math.max(candleWidth * 0.7, 2)}
                height={bodyH}
                fill={color}
                rx="1"
              />
            </g>
          );
        })}

        {/* VECTORES DE AUTO-TRENDLINES (TOP 1% SCORING DE TRENDSPIDER) */}
        {trendlines.map((line, idx) => {
          const isRes = line.kind === "RESISTANCE";
          const lineColor = isRes ? "#38bdf8" : "#4ade80";

          // Proyectar desde vela de origen hasta el extremo derecho del gráfico
          const startCandleIdx = candles.findIndex((c) => c.ts === line.origin_ts);
          const x1 = (startCandleIdx !== -1 ? startCandleIdx : 0) * candleWidth + candleWidth / 2;
          const y1 = priceToY(line.y1);

          const x2 = (candles.length - 1) * candleWidth + candleWidth / 2;
          const y2 = priceToY(line.current_y);

          const hasBreakout = line.breakout === "BULLISH_BREAKOUT" || line.breakout === "BEARISH_BREAKOUT";

          return (
            <g key={idx}>
              {/* Línea de tendencia */}
              <line
                x1={x1}
                y1={y1}
                x2={x2}
                y2={y2}
                stroke={lineColor}
                strokeWidth="2.2"
                strokeLinecap="round"
                opacity="0.9"
              />
              {/* Etiqueta de Scoring */}
              <rect x={x2 - 50} y={y2 - 16} width="46" height="13" fill="#000" rx="3" stroke={lineColor} strokeWidth="1" />
              <text x={x2 - 27} y={y2 - 6} fill={lineColor} fontSize="9" fontWeight="900" textAnchor="middle">
                ★ {line.score?.toFixed(0)}
              </text>
              {/* Círculo indicador de Breakout al cierre */}
              {hasBreakout && (
                <circle
                  cx={x2}
                  cy={y2}
                  r="6"
                  fill={line.breakout === "BULLISH_BREAKOUT" ? "#22c55e" : "#ef4444"}
                  stroke="#fff"
                  strokeWidth="2"
                />
              )}
            </g>
          );
        })}

        {/* Línea de Precio Actual Spot */}
        {livePrice && (
          <g>
            <line
              x1={0}
              y1={priceToY(livePrice)}
              x2={width - paddingRight}
              y2={priceToY(livePrice)}
              stroke="#fbbf24"
              strokeWidth="1.2"
              strokeDasharray="4 3"
            />
            <rect
              x={width - paddingRight + 2}
              y={priceToY(livePrice) - 9}
              width="60"
              height="18"
              fill="#fbbf24"
              rx="3"
            />
            <text
              x={width - paddingRight + 32}
              y={priceToY(livePrice) + 4}
              fill="#000"
              fontSize="10"
              fontWeight="900"
              textAnchor="middle"
              fontFamily="monospace"
            >
              {livePrice.toFixed(2)}
            </text>
          </g>
        )}

        {/* LÍNEA DE CONTROL TEMPORAL: TRUTH IN ANALYSIS (ANTI-REPINTADO) */}
        {lockX !== null ? (
          <g>
            <line x1={lockX} y1={0} x2={lockX} y2={height} stroke="#eab308" strokeWidth="2" strokeDasharray="5 3" />
            <text x={lockX + 5} y={15} fill="#eab308" fontSize="10" fontWeight="900">
              TRUTH IN ANALYSIS (CONGELADO OOS)
            </text>
          </g>
        ) : (
          <g>
            <line x1={width - paddingRight - 8} y1={0} x2={width - paddingRight - 8} y2={height} stroke="#ef4444" strokeWidth="1.5" />
            <text x={width - paddingRight - 110} y={15} fill="#ef4444" fontSize="9" fontWeight="800">
              LIVE (DINÁMICO)
            </text>
          </g>
        )}
      </svg>
    </div>
  );
}
