"use client";
import { useEffect, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL || "https://trading-app-jn5a.onrender.com";

function calcTPSL(entry, dir, volatility = 4.0) {
  const d = Math.max(3.5, Math.min(volatility * 1.2, 5.0));
  if (dir === "BUY") return { sl: entry - d, tp1: entry + d, tp2: entry + (d * 1.5), tp3: entry + (d * 2.0), dist: d };
  return { sl: entry + d, tp1: entry - d, tp2: entry - (d * 1.5), tp3: entry - (d * 2.0), dist: d };
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
        setBackendStatus("conectado - SCALPER ANTI-LAG");
      } else throw new Error("vacio");
    } catch (e) {
      setBackendStatus("demo - anti-lag mode");
      const demoPrice = 3942.70 + Math.random() * 2;
      const demo = calcTPSL(demoPrice, "SELL", 3.3);
      setSignal({
        symbol: "XAUUSD", direction: "SELL", entry: demoPrice, sl: demo.sl, tp1: demo.tp1, tp2: demo.tp2, tp3: demo.tp3, sl_distance: demo.dist, tp1_distance: demo.dist,
        probability: 72, probability_tp1: 58, confidence: 72, win_rate: 78.5, win_rate_direction: 82.3, is_optimal_hour: true,
        phase: "TRANSICION", phase_desc: "Simulación de Impulso en contra",
        alert: "🔴 SALIR AHORA: TENDENCIA GIRANDO A BUY", alert_type: "EXIT", alert_desc: "Impulso en contra detectado. Cierra tu operación en SELL manualmente.",
        candle_patterns: [],
        points_detail: [
          { side: "BUY", points: 5, name: "🚨 IMPULSO VIVO ALCISTA", reason: `Sube +$2.65 en vivo vs vela cerrada. Peligro para ventas.` }
        ],
        market_analysis: {
          trend: "LATERAL", buy_score: 5, sell_score: 0, volatility: 3.3, volatility_15: 5.0, phase: "TRANSICION", phase_desc: "Impulso Vivo", phase_info: { phase: "TRANSICION", band: 15, avg6: 5.0, avg3: 3.3, up: 1, down: 0, slope: 0.81, is_acc: false },
          analysis_price: 3939.65, live_price: demoPrice,
          ag_bands: { upper: demoPrice + 8.5, lower: demoPrice - 8.5, mean: demoPrice, std: 3.4 }, smc_pats: []
        },
        probabilidad_nuevos_objetivos: { prob_tp1_10usd_10_15min: 58, prob_tp2_20usd_15min: 38, prob_tp3_30usd_15min: 22 },
        reason: "IMPULSO VIVO ALCISTA", flip_reason: "Esperando confirmación para cambiar a BUY", support: 3920.70, resistance: 3971.85
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

  const sendResult = async (r) => {
    try {
      await fetch(`${API}/trades/result`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ result: r, symbol: "XAUUSD" }) });
      alert(`ACCIÓN REGISTRADA: ${r}`); fetchData();
    } catch {}
  };

  if (loading) return <div style={{ minHeight: "100vh", background: "#0a0a0a", color: "white", display: "flex", alignItems: "center", justifyContent: "center" }}>Iniciando Scalper Anti-Lag...</div>;
  const s = signal; if (!s) return null;
  const isBuy = s.direction === "BUY";
  const confidence = s.confidence || s.probability || 72;
  const probTP1 = s.probability_tp1 || s.probabilidad_nuevos_objetivos?.prob_tp1_10usd_10_15min || 0;
  const phase = s.phase || s.market_analysis?.phase || "RANGO";
  const phaseDesc = s.phase_desc || s.market_analysis?.phase_desc || "";
  const points = s.points_detail || s.market_analysis?.points_detail || [];
  const alertText = s.alert || "";
  const alertType = s.alert_type || "WAIT";
  const alertDesc = s.alert_desc || "";
  const dynamicDist = s.sl_distance || 4.0;

  const getPhaseColor = (ph) => {
    if (ph.includes("ALCISTA")) return "#fbbf24";
    if (ph.includes("BAJISTA")) return "#ef4444";
    if (ph.includes("ACUMULACION") || ph.includes("RANGO")) return "#a78bfa";
    return "#a1a1aa";
  };
  
  const getAlertStyle = (type) => {
    if (type === "ENTER") return { bg: "linear-gradient(135deg, rgba(34,197,94,0.15), rgba(16,185,129,0.15))", border: "#22c55e", color: "#22c55e" };
    if (type === "EXIT") return { bg: "linear-gradient(135deg, rgba(249,115,22,0.25), rgba(220,38,38,0.25))", border: "#ef4444", color: "#f87171", animation: "pulse 2s infinite" };
    if (type === "WAIT") return { bg: "linear-gradient(135deg, rgba(239,68,68,0.15), rgba(239,68,68,0.08))", border: "#ef4444", color: "#ef4444" };
    if (type === "CAUTION") return { bg: "linear-gradient(135deg, rgba(245,158,11,0.15), rgba(251,191,36,0.10))", border: "#f59e0b", color: "#fbbf24" };
    return { bg: "rgba(0,0,0,0)", border: "#71717a", color: "#a1a1aa" };
  };
  const alertStyle = getAlertStyle(alertType);

  return (
    <div style={{ minHeight: "100vh", background: "#0a0a0a", color: "white", padding: "14px", fontFamily: "system-ui" }}>
      <div style={{ maxWidth: "920px", margin: "0 auto" }}>
        
        {/* CABECERA */}
        <div style={{ display: "flex", justifyContent: "space-between", flexWrap: "wrap", gap: "12px", borderBottom: "2px solid #f59e0b", paddingBottom: "14px", marginBottom: "14px" }}>
          <div>
            <h1 style={{ fontSize: "24px", fontWeight: "900", margin: 0, color: "#fbbf24" }}>EDGEALERT ORO - SCALPER ANTI-LAG</h1>
            <div style={{ fontSize: "11px", color: "#a8a29e" }}>{timeEc} • EC • {backendStatus}</div>
            <div style={{ fontSize: "11px", color: "#fbbf24", fontWeight: "700" }}>Análisis cerrado: {s.market_analysis?.analysis_price?.toFixed(2)} • Vivo: {s.entry?.toFixed(2)}</div>
            <div style={{ fontSize: "10px", color: "#71717a", marginTop: "4px" }}>Fase: <b style={{ color: getPhaseColor(phase) }}>{phase}</b> • {phaseDesc}</div>
          </div>
          <div style={{ textAlign: "right" }}>
            <div style={{ fontSize: "12px", padding: "6px 12px", borderRadius: "8px", background: isBuy ? "rgba(34,197,94,0.15)" : "rgba(239,68,68,0.15)", border: `1px solid ${isBuy ? "#22c55e" : "#ef4444"}`, color: isBuy ? "#22c55e" : "#ef4444", fontWeight: "800" }}>{s.direction} {isBuy ? "↑" : "↓"}</div>
            <div style={{ fontSize: "9px", marginTop: "6px", color: "#a1a1aa", background: "rgba(255,255,255,0.05)", padding: "4px", borderRadius: "4px" }}>{s.flip_reason}</div>
          </div>
        </div>

        {/* ALERTA PRINCIPAL */}
        <div style={{ background: alertStyle.bg, border: `2px solid ${alertStyle.border}`, borderRadius: "12px", padding: "14px", marginBottom: "12px", boxShadow: alertType === "EXIT" ? "0 0 15px rgba(239,68,68,0.4)" : "none" }}>
          <div style={{ fontWeight: "900", fontSize: "15px", color: alertStyle.color, textAlign: "center" }}>{alertText}</div>
          <div style={{ fontSize: "11px", color: "#a8a29e", textAlign: "center", marginTop: "6px" }}>{alertDesc}</div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "10px", marginTop: "12px" }}>
            <div style={{ background: "rgba(0,0,0,0.3)", borderRadius: "8px", padding: "10px", textAlign: "center" }}>
              <div style={{ fontSize: "10px", color: "#a8a29e" }}>SCORE VIVO</div>
              <div style={{ fontSize: "22px", fontWeight: "900", color: alertStyle.color }}>{s.market_analysis?.buy_score} C / {s.market_analysis?.sell_score} V</div>
            </div>
            <div style={{ background: "rgba(0,0,0,0.3)", borderRadius: "8px", padding: "10px", textAlign: "center" }}>
              <div style={{ fontSize: "10px", color: "#a8a29e" }}>CONFIANZA MATEMÁTICA</div>
              <div style={{ fontSize: "22px", fontWeight: "900", color: "#fbbf24" }}>{confidence.toFixed(1)}%</div>
            </div>
          </div>
        </div>

        {/* DETALLE DE SEÑALES (AQUÍ APARECERÁ LA ALERTA ANTI-LAG) */}
        <div style={{ background: "#18181b", border: "1px solid #27272a", borderRadius: "12px", padding: "12px", marginBottom: "12px" }}>
          <div style={{ fontWeight: "800", fontSize: "12px", marginBottom: "8px", color: "#fbbf24" }}>RADARES ANTIGRAVITY & SMC - {s.market_analysis?.buy_score} COMPRA vs {s.market_analysis?.sell_score} VENTA</div>
          <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
            {points.map((p,i) => (
              <div key={i} style={{ display: "flex", justifyContent: "space-between", background: p.side==="BUY" ? "rgba(34,197,94,0.08)" : "rgba(239,68,68,0.08)", border: `1px solid ${p.side==="BUY" ? "rgba(34,197,94,0.2)" : "rgba(239,68,68,0.2)"}`, borderRadius: "8px", padding: "8px", fontSize: "11px" }}>
                <div><b style={{ color: p.side==="BUY" ? "#22c55e" : "#ef4444" }}>{p.side==="BUY" ? "COMPRA" : "VENTA"} +{p.points} {p.name}</b><div style={{ fontSize: "10px", color: "#a1a1aa" }}>{p.reason}</div></div>
                <span style={{ fontWeight: "900", color: p.side==="BUY" ? "#22c55e" : "#ef4444" }}>+{p.points}</span>
              </div>
            ))}
          </div>
        </div>

        {/* BOTÓN NUEVO DE SALIDA DE EMERGENCIA */}
        <button onClick={()=>sendResult("SALIDA MANUAL")} style={{ background: "linear-gradient(135deg, rgba(239,68,68,0.15), rgba(185,28,28,0.15))", border: "1px solid #ef4444", color: "#fca5a5", borderRadius: "8px", padding: "12px", fontSize: "12px", fontWeight: "900", cursor: "pointer", width: "100%", marginBottom: "12px", textTransform: "uppercase", letterSpacing: "1px" }}>🔴 CERRAR OPERACIÓN AHORA (SALIR)</button>

        {/* ZONA DE ENTRADA Y BOTONES TP/SL */}
        <div style={{ fontFamily: "monospace", fontSize: "11px", background: "#0c0a09", borderRadius: "10px", padding: "10px", border: "1px solid #44403c" }}>
          <div style={{ display: "flex", justifyContent: "space-between" }}><span style={{ color: "#a8a29e" }}>ENTRADA</span><span style={{ fontWeight: "900", color: "#fbbf24" }}>{s.entry?.toFixed(2)}</span></div>
          <div style={{ display: "flex", justifyContent: "space-between", color: "#f87171" }}><span style={{ color: "#a8a29e" }}>SL (-${dynamicDist.toFixed(1)}) {s.direction==="BUY"?"↓":"↑"}</span><span>{s.sl?.toFixed(2)}</span></div>
          <div style={{ display: "flex", justifyContent: "space-between", color: "#fbbf24" }}><span style={{ color: "#a8a29e" }}>TP1 (+${dynamicDist.toFixed(1)}) {s.direction==="BUY"?"↑":"↓"}</span><span>{s.tp1?.toFixed(2)}</span></div>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: "8px", marginTop: "10px" }}>
          <button onClick={()=>sendResult("SL TOCADO")} style={{ background: "rgba(239,68,68,0.12)", border: "1px solid rgba(239,68,68,0.4)", color: "#f87171", borderRadius: "8px", padding: "8px", fontSize: "10px", fontWeight: "800", cursor: "pointer" }}>SL -${dynamicDist.toFixed(1)}</button>
          <button onClick={()=>sendResult("TP1 TOCADO")} style={{ background: "rgba(245,158,11,0.18)", border: "1px solid #f59e0b", color: "#fbbf24", borderRadius: "8px", padding: "8px", fontSize: "10px", fontWeight: "800", cursor: "pointer" }}>TP1 +${dynamicDist.toFixed(1)}</button>
          <button onClick={()=>sendResult("TP2 TOCADO")} style={{ background: "rgba(245,158,11,0.14)", border: "1px solid rgba(245,158,11,0.4)", color: "#fbbf24", borderRadius: "8px", padding: "8px", fontSize: "10px", fontWeight: "800", cursor: "pointer" }}>TP2 +${(dynamicDist*1.5).toFixed(1)}</button>
          <button onClick={()=>sendResult("TP3 TOCADO")} style={{ background: "linear-gradient(135deg, rgba(245,158,11,0.2), rgba(251,191,36,0.2))", border: "1px solid #f59e0b", color: "#fbbf24", borderRadius: "8px", padding: "8px", fontSize: "10px", fontWeight: "800", cursor: "pointer" }}>TP3 +${(dynamicDist*2).toFixed(1)}</button>
        </div>
      </div>
    </div>
  );
}
