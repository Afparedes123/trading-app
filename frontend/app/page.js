"use client";
import { useEffect, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL || "https://trading-app-jn5a.onrender.com";

// Función demo en caso de no conexión
function calcTPSL(entry, dir, volatility = 4.0) {
  const d = Math.max(3.5, Math.min(volatility * 1.2, 5.0));
  if (dir === "COMPRA") return { sl: entry - d, tp1: entry + d, dist: d };
  return { sl: entry + d, tp1: entry - d, dist: d };
}

export default function Page() {
  const [signal, setSignal] = useState(null);
  const [loading, setLoading] = useState(true);
  const [timeEc, setTimeEc] = useState("");
  const [backendStatus, setBackendStatus] = useState("conectando...");

  const fetchData = async () => {
    try {
      const res = await fetch(`${API}/signals/live`, { cache: "no-store" });
      if (!res.ok) throw new Error(`Backend ${res.status}`);
      const data = await res.json();
      let sig = Array.isArray(data) && data.length > 0 ? data[0] : data.symbol ? data : data.signals?.[0];
      if (sig && sig.symbol?.includes("XAU")) {
        setSignal(sig);
        setBackendStatus("conectado - SCALPER PRECISIÓN");
      } else throw new Error("vacio");
    } catch (e) {
      setBackendStatus("demo - precisión mode");
      const demoPrice = 3942.70 + Math.random() * 2;
      const demo = calcTPSL(demoPrice, "VENTA", 3.3);
      setSignal({
        symbol: "XAUUSD", direction: "ESPERA", entry: demoPrice, sl: 0, tp1: 0, dist: 0,
        confidence: 50, analysis_price: 3939.65, live_price: demoPrice,
        phase: "TRANSICION", phase_desc: "Simulación de Impulso en contra",
        alert: "🔴 SALIR Y ESPERAR: SEÑALES NULAS", alert_type: "EXIT", alert_desc: "El mercado perdió fuerza o se invirtió. Cierra tus posiciones.",
        points_detail: [
          { side: "COMPRA", points: 6, name: "🚨 IMPULSO VIVO", reason: `El precio acaba de subir +$2.65 rompiendo el análisis previo.` }
        ],
        market_analysis: {
          buy_score: 6, sell_score: 0, volatility: 3.3, 
          ag_bands: { upper: demoPrice + 8.5, lower: demoPrice - 8.5, mean: demoPrice }, smc_pats: []
        },
        flip_reason: "Filtro anti-lag suprimió las ventas.", support: 3920.70, resistance: 3971.85
      });
    } finally { setLoading(false); }
  };

  useEffect(() => {
    fetchData();
    const id = setInterval(fetchData, 30000);
    const tId = setInterval(() => {
      const now = new Date().toLocaleString("es-EC", { timeZone: "America/Guayaquil", hour: "2-digit", minute: "2-digit", second: "2-digit", weekday: "long", day: "2-digit", month: "short" });
      setTimeEc(now);
    }, 1000);
    return () => { clearInterval(id); clearInterval(tId); };
  }, []);

  if (loading) return <div style={{ minHeight: "100vh", background: "#0a0a0a", color: "white", display: "flex", alignItems: "center", justifyContent: "center" }}>Iniciando Motor de Precisión...</div>;
  const s = signal; if (!s) return null;
  const isBuy = s.direction === "COMPRA";
  const isSell = s.direction === "VENTA";
  const confidence = s.confidence || 50;
  const phase = s.phase || "RANGO";
  const phaseDesc = s.phase_desc || "";
  const points = s.points_detail || [];
  const alertText = s.alert || "";
  const alertType = s.alert_type || "WAIT";
  const alertDesc = s.alert_desc || "";
  const dynamicDist = s.dist || 4.0;

  const getPhaseColor = (ph) => {
    if (ph.includes("ALCISTA") || ph.includes("COMPRA")) return "#fbbf24";
    if (ph.includes("BAJISTA") || ph.includes("VENTA")) return "#ef4444";
    if (ph.includes("ACUMULACION") || ph.includes("RANGO")) return "#a78bfa";
    return "#a1a1aa";
  };
  
  const getAlertStyle = (type) => {
    if (type === "ENTER") return { bg: "linear-gradient(135deg, rgba(34,197,94,0.15), rgba(16,185,129,0.15))", border: "#22c55e", color: "#22c55e" };
    if (type === "EXIT") return { bg: "linear-gradient(135deg, rgba(249,115,22,0.25), rgba(220,38,38,0.25))", border: "#ef4444", color: "#f87171", animation: "pulse 2s infinite" };
    if (type === "WAIT") return { bg: "linear-gradient(135deg, rgba(239,68,68,0.15), rgba(239,68,68,0.08))", border: "#ef4444", color: "#ef4444" };
    return { bg: "rgba(0,0,0,0)", border: "#71717a", color: "#a1a1aa" };
  };
  const alertStyle = getAlertStyle(alertType);

  return (
    <div style={{ minHeight: "100vh", background: "#0a0a0a", color: "white", padding: "14px", fontFamily: "system-ui" }}>
      <div style={{ maxWidth: "920px", margin: "0 auto" }}>
        
        {/* CABECERA */}
        <div style={{ display: "flex", justifyContent: "space-between", flexWrap: "wrap", gap: "12px", borderBottom: "2px solid #f59e0b", paddingBottom: "14px", marginBottom: "14px" }}>
          <div>
            <h1 style={{ fontSize: "24px", fontWeight: "900", margin: 0, color: "#fbbf24" }}>EDGEALERT ORO - PRECISIÓN</h1>
            <div style={{ fontSize: "11px", color: "#a8a29e" }}>{timeEc} • {backendStatus}</div>
            <div style={{ fontSize: "11px", color: "#fbbf24", fontWeight: "700" }}>Análisis: {s.analysis_price?.toFixed(2)} • Vivo: {s.entry?.toFixed(2)}</div>
            <div style={{ fontSize: "10px", color: "#71717a", marginTop: "4px" }}>Fase: <b style={{ color: getPhaseColor(phase) }}>{phase}</b> • {phaseDesc}</div>
          </div>
          <div style={{ textAlign: "right" }}>
            <div style={{ fontSize: "14px", padding: "8px 16px", borderRadius: "8px", background: isBuy ? "rgba(34,197,94,0.2)" : isSell ? "rgba(239,68,68,0.2)" : "rgba(161,161,170,0.2)", border: `1px solid ${isBuy ? "#22c55e" : isSell ? "#ef4444" : "#a1a1aa"}`, color: isBuy ? "#22c55e" : isSell ? "#ef4444" : "#a1a1aa", fontWeight: "900" }}>
              {s.direction} {isBuy ? "↑" : isSell ? "↓" : "⏸"}
            </div>
            <div style={{ fontSize: "9px", marginTop: "6px", color: "#a1a1aa", background: "rgba(255,255,255,0.05)", padding: "4px", borderRadius: "4px" }}>{s.flip_reason}</div>
          </div>
        </div>

        {/* ALERTA PRINCIPAL Y SCORE */}
        <div style={{ background: alertStyle.bg, border: `2px solid ${alertStyle.border}`, borderRadius: "12px", padding: "14px", marginBottom: "12px", boxShadow: alertType === "EXIT" ? "0 0 15px rgba(239,68,68,0.4)" : "none" }}>
          <div style={{ fontWeight: "900", fontSize: "15px", color: alertStyle.color, textAlign: "center" }}>{alertText}</div>
          <div style={{ fontSize: "11px", color: "#a8a29e", textAlign: "center", marginTop: "6px", marginBottom: "12px" }}>{alertDesc}</div>
          
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "10px" }}>
            <div style={{ background: "rgba(0,0,0,0.4)", borderRadius: "8px", padding: "12px", textAlign: "center", border: "1px solid #27272a" }}>
              <div style={{ fontSize: "10px", color: "#a8a29e", marginBottom: "4px", fontWeight: "700" }}>FUERZA EN VIVO</div>
              <div style={{ fontSize: "20px", fontWeight: "900" }}>
                <span style={{ color: "#22c55e" }}>{s.market_analysis?.buy_score} C</span> <span style={{ color: "#52525b" }}>/</span> <span style={{ color: "#ef4444" }}>{s.market_analysis?.sell_score} V</span>
              </div>
            </div>
            <div style={{ background: "rgba(0,0,0,0.4)", borderRadius: "8px", padding: "12px", textAlign: "center", border: "1px solid #27272a" }}>
              <div style={{ fontSize: "10px", color: "#a8a29e", marginBottom: "4px", fontWeight: "700" }}>CONFIANZA TOTAL</div>
              <div style={{ fontSize: "20px", fontWeight: "900", color: confidence >= 75 ? "#22c55e" : confidence >= 60 ? "#fbbf24" : "#ef4444" }}>{confidence.toFixed(1)}%</div>
            </div>
          </div>
        </div>

        {/* DETALLE DE SEÑALES */}
        <div style={{ background: "#18181b", border: "1px solid #27272a", borderRadius: "12px", padding: "12px", marginBottom: "12px" }}>
          <div style={{ fontWeight: "800", fontSize: "12px", marginBottom: "8px", color: "#fbbf24" }}>RADARES ANTIGRAVITY & ESTRUCTURA</div>
          <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
            {points.length === 0 && <div style={{ fontSize: "11px", color: "#71717a", textAlign: "center", padding: "10px" }}>Buscando patrones en el mercado...</div>}
            {points.map((p,i) => (
              <div key={i} style={{ display: "flex", justifyContent: "space-between", background: p.side==="COMPRA" ? "rgba(34,197,94,0.08)" : "rgba(239,68,68,0.08)", border: `1px solid ${p.side==="COMPRA" ? "rgba(34,197,94,0.2)" : "rgba(239,68,68,0.2)"}`, borderRadius: "8px", padding: "8px", fontSize: "11px" }}>
                <div><b style={{ color: p.side==="COMPRA" ? "#22c55e" : "#ef4444" }}>{p.side} +{p.points} {p.name}</b><div style={{ fontSize: "10px", color: "#a1a1aa" }}>{p.reason}</div></div>
                <span style={{ fontWeight: "900", color: p.side==="COMPRA" ? "#22c55e" : "#ef4444" }}>+{p.points}</span>
              </div>
            ))}
          </div>
        </div>

        {/* ZONA ESTRUCTURAL SIMPLIFICADA */}
        <div style={{ background: "#0c0a09", border: "1px solid #292524", borderRadius: "8px", padding: "12px", fontSize: "11px", marginBottom: "12px" }}>
          <div style={{ color: "#a8a29e", fontWeight: "700", marginBottom: "6px" }}>NIVELES INSTITUCIONALES</div>
          <div style={{ display: "flex", justifyContent: "space-between", borderBottom: "1px solid #27272a", paddingBottom: "4px", marginBottom: "4px" }}>
            <span>Resistencia 15m: <b style={{ color: "#ef4444" }}>{s.resistance?.toFixed(2)}</b></span>
            <span>Soporte 15m: <b style={{ color: "#10b981" }}>{s.support?.toFixed(2)}</b></span>
          </div>
          <div style={{ display: "flex", justifyContent: "space-between", color: "#71717a" }}>
            <span>Extremo Techo: {s.market_analysis?.ag_bands?.upper?.toFixed(2)}</span>
            <span>Extremo Suelo: {s.market_analysis?.ag_bands?.lower?.toFixed(2)}</span>
          </div>
        </div>

        {/* GUÍA DE EJECUCIÓN (SOLO VISUAL) */}
        {s.direction !== "ESPERA" && (
          <div style={{ fontFamily: "monospace", fontSize: "12px", background: "rgba(0,0,0,0.6)", borderRadius: "10px", padding: "12px", border: `1px solid ${isBuy ? "#059669" : "#dc2626"}`, borderLeft: `4px solid ${isBuy ? "#10b981" : "#ef4444"}` }}>
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "6px" }}><span style={{ color: "#a8a29e" }}>PRECIO ENTRADA</span><span style={{ fontWeight: "900", color: "#fff" }}>{s.entry?.toFixed(2)}</span></div>
            <div style={{ display: "flex", justifyContent: "space-between", color: "#f87171", marginBottom: "2px" }}><span style={{ color: "#a8a29e" }}>RIESGO SL (-${dynamicDist.toFixed(1)})</span><span>{s.sl?.toFixed(2)}</span></div>
            <div style={{ display: "flex", justifyContent: "space-between", color: "#34d399" }}><span style={{ color: "#a8a29e" }}>OBJETIVO TP (+${dynamicDist.toFixed(1)})</span><span>{s.tp1?.toFixed(2)}</span></div>
          </div>
        )}

      </div>
    </div>
  );
}
