"use client";
import { useEffect, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL || "https://trading-app-jn5a.onrender.com";

// Calculadora dinámica para el modo Demo (escala $4 - $5 para cuenta de $50)
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
        setBackendStatus("conectado - ORO SCALPER DINÁMICO");
      } else throw new Error("vacio");
    } catch (e) {
      setBackendStatus("demo - modo scalping");
      const demoPrice = 4052.70 + Math.random() * 2;
      const demo = calcTPSL(demoPrice, "BUY", 3.3);
      setSignal({
        symbol: "XAUUSD", direction: "BUY", entry: demoPrice, sl: demo.sl, tp1: demo.tp1, tp2: demo.tp2, tp3: demo.tp3, sl_distance: demo.dist, tp1_distance: demo.dist,
        sl_explain: `SL ${demo.sl.toFixed(2)} (Máx pérdida $${demo.dist.toFixed(2)})`, tp_explain: `TP1 ${demo.tp1.toFixed(2)} (Gana $${demo.dist.toFixed(2)}) COMPRA`,
        probability: 72, probability_tp1: 58, confidence: 72, win_rate: 78.5, win_rate_direction: 82.3, win_rate_buy: 71, win_rate_sell: 81, is_optimal_hour: true,
        phase: "RANGO AMPLIO", phase_desc: "RANGO AMPLIO 21 USD - micro scalping",
        alert: "🔴 SALIR AHORA: ASEGURA GANANCIA O CORTA PÉRDIDA", alert_type: "EXIT", alert_desc: "La tendencia giró repentinamente. Cierra tu operación manualmente.",
        candle_patterns: [{ name: "MARTILLO", dir: "BUY", strength: 2, desc: "Martillo alcista" }],
        points_detail: [
          { side: "BUY", points: 4, name: "ANTIGRAVITY BUY", reason: `Precio rompió banda inferior (-2.5 SD).` },
          { side: "BUY", points: 3, name: "FVG ALCISTA", reason: "Vacío de liquidez institucional SMC" }
        ],
        market_analysis: {
          trend: "ALCISTA", up_streak: 1, down_streak: 0, high_10: demoPrice + 3.2, low_10: demoPrice - 2.8, high_15: demoPrice + 5.5, low_15: demoPrice - 4.8,
          sma10: demoPrice + 1.2, sma15: demoPrice + 2.1, sma30: demoPrice + 3.0, support: 4052.70, resistance: 4073.85, support_long: 4052.70, resistance_long: 4073.85, high_long: 4073.85, low_long: 4052.70, band_long: 21.1, high_clusters: [[4065.79,3],[4073.85,2]], low_clusters: [[4052.70,5],[4054.20,2]], 
          fib: { dir: "ALCISTA", low: 4052.70, high: 4073.85, range: 21.15, current: demoPrice, near: "0.618", dist: 0.8, levels: {"0":4073.85,"0.236":4068.86,"0.382":4065.77,"0.5":4063.27,"0.618":4060.78,"0.786":4057.23,"1":4052.70} },
          buy_score: 9, sell_score: 0, volatility: 3.3, volatility_15: 5.0, phase: "RANGO AMPLIO", phase_desc: "RANGO AMPLIO 21 USD - scalping", phase_info: { phase: "RANGO AMPLIO", band: 21.1, avg6: 5.0, avg3: 3.3, up: 1, down: 0, slope: 0.81, is_acc: false },
          ag_bands: { upper: demoPrice + 8.5, lower: demoPrice - 8.5, mean: demoPrice, std: 3.4 },
          smc_pats: [{ name: "FVG ALCISTA", dir: "BUY", strength: 3, desc: "Vacío de liquidez SMC" }]
        },
        probabilidad_nuevos_objetivos: { prob_tp1_10usd_10_15min: 58, prob_tp2_20usd_15min: 38, prob_tp3_30usd_15min: 22 },
        reason: "ANTIGRAVITY + FVG", flip_reason: "Desviación extrema a la baja detectada", support: 4052.70, resistance: 4073.85
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
      alert(`ORO ${r}`); fetchData();
    } catch {}
  };

  if (loading) return <div style={{ minHeight: "100vh", background: "#0a0a0a", color: "white", display: "flex", alignItems: "center", justifyContent: "center" }}>Iniciando Scalper Dinámico...</div>;
  const s = signal; if (!s) return null;
  const isBuy = s.direction === "BUY";
  const confidence = s.confidence || s.probability || 72;
  const probTP1 = s.probability_tp1 || s.probabilidad_nuevos_objetivos?.prob_tp1_10usd_10_15min || 0;
  const displayProb = s.probability || confidence;
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
  
  // NUEVO SISTEMA DE COLORES CON ALERTA NARANJA PARA SALIDA
  const getAlertStyle = (type) => {
    if (type === "ENTER") return { bg: "linear-gradient(135deg, rgba(34,197,94,0.15), rgba(16,185,129,0.15))", border: "#22c55e", color: "#22c55e" };
    if (type === "EXIT") return { bg: "linear-gradient(135deg, rgba(249,115,22,0.15), rgba(234,88,12,0.15))", border: "#f97316", color: "#f97316" };
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
            <h1 style={{ fontSize: "24px", fontWeight: "900", margin: 0, color: "#fbbf24" }}>EDGEALERT ORO - SCALPER DINÁMICO</h1>
            <div style={{ fontSize: "11px", color: "#a8a29e" }}>{timeEc} • EC • {backendStatus}</div>
            <div style={{ fontSize: "11px", color: "#fbbf24", fontWeight: "700" }}>Análisis: {s.market_analysis?.analysis_price?.toFixed(2)} (vela cerrada) • Vivo: {s.entry?.toFixed(2)}</div>
            <div style={{ fontSize: "10px", color: "#71717a", marginTop: "4px" }}>Fase: <b style={{ color: getPhaseColor(phase) }}>{phase}</b> • {phaseDesc}</div>
          </div>
          <div style={{ textAlign: "right" }}>
            <div style={{ fontSize: "12px", padding: "6px 12px", borderRadius: "8px", background: isBuy ? "rgba(34,197,94,0.15)" : "rgba(239,68,68,0.15)", border: `1px solid ${isBuy ? "#22c55e" : "#ef4444"}`, color: isBuy ? "#22c55e" : "#ef4444", fontWeight: "800" }}>{s.direction} {isBuy ? "↑" : "↓"}</div>
            <div style={{ fontSize: "9px", marginTop: "6px", color: "#a1a1aa", background: "rgba(255,255,255,0.05)", padding: "4px", borderRadius: "4px" }}>{s.flip_reason}</div>
          </div>
        </div>

        {/* ALERTA PRINCIPAL */}
        <div style={{ background: alertStyle.bg, border: `2px solid ${alertStyle.border}`, borderRadius: "12px", padding: "14px", marginBottom: "12px" }}>
          <div style={{ fontWeight: "900", fontSize: "15px", color: alertStyle.color, textAlign: "center" }}>{alertText}</div>
          <div style={{ fontSize: "11px", color: "#a8a29e", textAlign: "center", marginTop: "6px" }}>{alertDesc}</div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "10px", marginTop: "12px" }}>
            <div style={{ background: "rgba(0,0,0,0.3)", borderRadius: "8px", padding: "10px", textAlign: "center" }}>
              <div style={{ fontSize: "10px", color: "#a8a29e" }}>CONFIANZA DIRECCIÓN</div>
              <div style={{ fontSize: "22px", fontWeight: "900", color: alertStyle.color }}>{confidence.toFixed(1)}%</div>
              <div style={{ fontSize: "9px", color: "#71717a" }}>Score {s.market_analysis?.buy_score} C / {s.market_analysis?.sell_score} V</div>
            </div>
            <div style={{ background: "rgba(0,0,0,0.3)", borderRadius: "8px", padding: "10px", textAlign: "center" }}>
              <div style={{ fontSize: "10px", color: "#a8a29e" }}>PROBABILIDAD MICRO-TP</div>
              <div style={{ fontSize: "22px", fontWeight: "900", color: "#fbbf24" }}>{probTP1.toFixed(1)}%</div>
              <div style={{ fontSize: "9px", color: "#71717a" }}>Algoritmo Institucional SMC</div>
            </div>
          </div>
        </div>

        {/* SISTEMA DE PUNTOS DETALLADO */}
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

        {/* PANELES DE ANÁLISIS */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "8px", marginBottom: "10px" }}>
          
          <div style={{ background: "#0c0a09", border: "1px solid #292524", borderRadius: "8px", padding: "8px", fontSize: "10px" }}>
            <div style={{ color: "#a8a29e", fontWeight: "700" }}>SMART MONEY & ANTIGRAVITY</div>
            
            {s.market_analysis?.ag_bands && (
              <div style={{ marginTop: "4px", background: "rgba(59,130,246,0.1)", borderRadius: "6px", padding: "4px" }}>
                <div style={{ color: "#3b82f6", fontWeight: "700" }}>Zonas de Gravedad (2.5 SD)</div>
                <div>Techo (Venta): <b style={{ color: "#ef4444" }}>{s.market_analysis.ag_bands.upper.toFixed(2)}</b></div>
                <div>Suelo (Compra): <b style={{ color: "#22c55e" }}>{s.market_analysis.ag_bands.lower.toFixed(2)}</b></div>
                <div style={{ color: "#9ca3af", fontSize: "9px" }}>Precio Medio: {s.market_analysis.ag_bands.mean.toFixed(2)}</div>
              </div>
            )}

            {s.market_analysis?.smc_pats?.length > 0 && (
              <div style={{ marginTop: "4px", background: "rgba(167,139,250,0.1)", borderRadius: "6px", padding: "4px" }}>
                <div style={{ color: "#a78bfa", fontWeight: "700" }}>Huella Institucional SMC / FVG</div>
                {s.market_analysis.smc_pats.map((pat, i) => (
                  <div key={i} style={{ color: pat.dir==="BUY" ? "#22c55e" : "#ef4444" }}>{pat.name} - {pat.desc}</div>
                ))}
              </div>
            )}

            <div style={{ borderTop: "1px solid #292524", marginTop: "6px", paddingTop: "4px" }}>
              SMA Retail: {s.market_analysis?.sma10?.toFixed(1)}/{s.market_analysis?.sma15?.toFixed(1)}/{s.market_analysis?.sma30?.toFixed(1)}
              <br/>SR 4H: <b style={{ color: "#a78bfa" }}>{s.market_analysis?.low_long?.toFixed(2)} - {s.market_analysis?.high_long?.toFixed(2)}</b>
            </div>
          </div>
          
          <div style={{ background: "#0c0a09", border: "1px solid #292524", borderRadius: "8px", padding: "8px", fontSize: "10px" }}>
            <div style={{ color: "#a8a29e", fontWeight: "700" }}>ESTRUCTURA & FIBONACCI</div>
            <div>Alto 15m: <b style={{ color: "#fbbf24" }}>{s.market_analysis?.high_15?.toFixed(2)}</b> | Bajo 15m: <b style={{ color: "#fbbf24" }}>{s.market_analysis?.low_15?.toFixed(2)}</b></div>
            <div>Soporte: <b style={{ color: "#10b981" }}>{s.support?.toFixed(2)}</b> | Resistencia: <b style={{ color: "#ef4444" }}>{s.resistance?.toFixed(2)}</b></div>
            
            {s.market_analysis?.fib && (
              <div style={{ marginTop: "4px", background: "rgba(245,158,11,0.1)", borderRadius: "6px", padding: "4px" }}>
                <div style={{ color: "#fbbf24", fontWeight: "700" }}>FIB {s.market_analysis?.fib?.dir} {s.market_analysis?.fib?.range?.toFixed(1)} USD</div>
                <div>0.382: {s.market_analysis?.fib?.levels?.["0.382"]?.toFixed(2)} | 0.5: {s.market_analysis?.fib?.levels?.["0.5"]?.toFixed(2)} | 0.618: <b style={{ color: "#fbbf24" }}>{s.market_analysis?.fib?.levels?.["0.618"]?.toFixed(2)}</b></div>
                {s.market_analysis?.fib?.near && <div style={{ color: "#fbbf24" }}>Cerca Fib {s.market_analysis?.fib?.near} a {s.market_analysis?.fib?.dist?.toFixed(2)} USD</div>}
              </div>
            )}

            {s.market_analysis?.high_clusters?.length > 0 && (
              <div style={{ marginTop: "4px", background: "rgba(239,68,68,0.08)", borderRadius: "6px", padding: "4px", fontSize: "9px" }}>
                <div style={{ color: "#ef4444", fontWeight: "700" }}>Resistencias 4H</div>
                {s.market_analysis?.high_clusters?.map((c,i) => <div key={i}>R{i+1}: {c[0].toFixed(2)}</div>)}
              </div>
            )}
          </div>
        </div>

        {/* ZONA DE ENTRADA Y BOTONES DINÁMICOS */}
        <div style={{ fontFamily: "monospace", fontSize: "11px", background: "#0c0a09", borderRadius: "10px", padding: "10px", border: "1px solid #44403c" }}>
          <div style={{ display: "flex", justifyContent: "space-between" }}><span style={{ color: "#a8a29e" }}>ENTRADA</span><span style={{ fontWeight: "900", color: "#fbbf24" }}>{s.entry?.toFixed(2)}</span></div>
          <div style={{ display: "flex", justifyContent: "space-between", color: "#f87171" }}><span style={{ color: "#a8a29e" }}>SL (-${dynamicDist.toFixed(1)}) {s.direction==="BUY"?"↓":"↑"}</span><span>{s.sl?.toFixed(2)}</span></div>
          <div style={{ display: "flex", justifyContent: "space-between", color: "#fbbf24" }}><span style={{ color: "#a8a29e" }}>TP1 (+${dynamicDist.toFixed(1)}) {s.direction==="BUY"?"↑":"↓"}</span><span>{s.tp1?.toFixed(2)}</span></div>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: "8px", marginTop: "10px" }}>
          <button onClick={()=>sendResult("SL")} style={{ background: "rgba(239,68,68,0.12)", border: "1px solid rgba(239,68,68,0.4)", color: "#f87171", borderRadius: "8px", padding: "8px", fontSize: "10px", fontWeight: "800", cursor: "pointer" }}>SL -${dynamicDist.toFixed(1)}</button>
          <button onClick={()=>sendResult("TP1")} style={{ background: "rgba(245,158,11,0.18)", border: "1px solid #f59e0b", color: "#fbbf24", borderRadius: "8px", padding: "8px", fontSize: "10px", fontWeight: "800", cursor: "pointer" }}>TP1 +${dynamicDist.toFixed(1)}</button>
          <button onClick={()=>sendResult("TP2")} style={{ background: "rgba(245,158,11,0.14)", border: "1px solid rgba(245,158,11,0.4)", color: "#fbbf24", borderRadius: "8px", padding: "8px", fontSize: "10px", fontWeight: "800", cursor: "pointer" }}>TP2 +${(dynamicDist*1.5).toFixed(1)}</button>
          <button onClick={()=>sendResult("TP3")} style={{ background: "linear-gradient(135deg, rgba(245,158,11,0.2), rgba(251,191,36,0.2))", border: "1px solid #f59e0b", color: "#fbbf24", borderRadius: "8px", padding: "8px", fontSize: "10px", fontWeight: "800", cursor: "pointer" }}>TP3 +${(dynamicDist*2).toFixed(1)}</button>
        </div>
      </div>
    </div>
  );
}
