"use client";
import { useEffect, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL || "https://trading-app-jn5a.onrender.com";

function calcTPSL(entry, dir) {
  const d = 6.17;
  if (dir === "BUY") return { sl: entry - d, tp1: entry + d, tp2: entry + d * 2, tp3: entry + d * 3, dist: d };
  return { sl: entry + d, tp1: entry - d, tp2: entry - d * 2, tp3: entry - d * 3, dist: d };
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
        setBackendStatus("conectado - ORO v8.3 ESPAÑOL + FIB + PIVOTES");
      } else throw new Error("vacio");
    } catch (e) {
      setBackendStatus("demo - v8.3 español");
      const demoPrice = 4052.70 + Math.random() * 2;
      const demo = calcTPSL(demoPrice, "BUY");
      setSignal({
        symbol: "XAUUSD", direction: "BUY", entry: demoPrice, sl: demo.sl, tp1: demo.tp1, tp2: demo.tp2, tp3: demo.tp3, sl_distance: demo.dist, tp1_distance: demo.dist,
        sl_explain: `SL ${demo.sl.toFixed(2)} ABAJO`, tp_explain: `TP1 ${demo.tp1.toFixed(2)} ARRIBA COMPRA`,
        probability: 72, probability_tp1: 58, confidence: 72, win_rate: 78.5, win_rate_direction: 82.3, win_rate_buy: 71, win_rate_sell: 81, is_optimal_hour: true,
        phase: "RANGO AMPLIO", phase_desc: "RANGO AMPLIO 21 USD - 4052 a 4073 - scalping con impulso y retroceso Fib",
        alert: "ENTRA - COMPRA EN FIB 0.618 - RETROCESO PERFECTO", alert_type: "ENTER", alert_desc: "Fib 0.618 en acumulación amplia",
        candle_patterns: [{ name: "MARTILLO", dir: "BUY", strength: 2, desc: "Martillo alcista" }],
        points_detail: [
          { side: "BUY", points: 3, name: "SMA ALCISTA FUERTE", reason: "Precio > SMA10 > SMA15 > SMA30" },
          { side: "BUY", points: 2, name: "CORTE SOPORTE EN ACUMULACIÓN AMPLIA", reason: "Acumulación amplia 21 USD - cerca soporte 4052" },
          { side: "BUY", points: 2, name: "FIB 0.618 RETROCESO ALCISTA", reason: "Impulso alcista 4052->4073 - en Fib 0.618" }
        ],
        market_analysis: {
          trend: "ALCISTA", up_streak: 1, down_streak: 0, high_10: demoPrice + 3.2, low_10: demoPrice - 2.8, high_15: demoPrice + 5.5, low_15: demoPrice - 4.8,
          sma10: demoPrice + 1.2, sma15: demoPrice + 2.1, sma30: demoPrice + 3.0, support: 4052.70, resistance: 4073.85, support_long: 4052.70, resistance_long: 4073.85, high_long: 4073.85, low_long: 4052.70, band_long: 21.1, high_clusters: [[4065.79,3],[4073.85,2]], low_clusters: [[4052.70,5],[4054.20,2]], fib: { dir: "ALCISTA", low: 4052.70, high: 4073.85, range: 21.15, current: demoPrice, near: "0.618", dist: 0.8, levels: {"0":4073.85,"0.236":4068.86,"0.382":4065.77,"0.5":4063.27,"0.618":4060.78,"0.786":4057.23,"1":4052.70} },
          buy_score: 7, sell_score: 0, volatility: 3.3, volatility_15: 5.0, phase: "RANGO AMPLIO", phase_desc: "RANGO AMPLIO 21 USD - scalping", phase_info: { phase: "RANGO AMPLIO", band: 21.1, avg6: 5.0, avg3: 3.3, up: 1, down: 0, slope: 0.81, is_acc: false }
        },
        probabilidad_nuevos_objetivos: { prob_tp1_10usd_10_15min: 58, prob_tp2_20usd_15min: 38, prob_tp3_30usd_15min: 22 },
        reason: "SMA ALCISTA + CORTE SOPORTE + FIB 0.618", flip_reason: "Acumulación amplia - corte soporte", support: 4052.70, resistance: 4073.85
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

  if (loading) return <div style={{ minHeight: "100vh", background: "#0a0a0a", color: "white", display: "flex", alignItems: "center", justifyContent: "center" }}>ORO FASES + PUNTOS + FIB - Analizando...</div>;
  const s = signal; if (!s) return null;
  const isBuy = s.direction === "BUY";
  const confidence = s.confidence || s.probability || 72;
  const probTP1 = s.probability_tp1 || s.probabilidad_nuevos_objetivos?.prob_tp1_10usd_10_15min || 0;
  const displayProb = s.probability || confidence;
  const phase = s.phase || s.market_analysis?.phase || "RANGO";
  const phaseDesc = s.phase_desc || s.market_analysis?.phase_desc || "";
  const points = s.points_detail || s.market_analysis?.points_detail || [];
  const candles = s.candle_patterns || s.market_analysis?.candle_patterns || [];
  const alert = s.alert || "";
  const alertType = s.alert_type || "WAIT";
  const alertDesc = s.alert_desc || "";

  const getPhaseColor = (ph) => {
    if (ph.includes("ALCISTA")) return "#fbbf24";
    if (ph.includes("BAJISTA")) return "#ef4444";
    if (ph.includes("ACUMULACION") || ph.includes("RANGO")) return "#a78bfa";
    return "#a1a1aa";
  };
  const getAlertStyle = (type) => {
    if (type === "ENTER") return { bg: "linear-gradient(135deg, rgba(34,197,94,0.15), rgba(16,185,129,0.15))", border: "#22c55e", color: "#22c55e" };
    if (type === "WAIT") return { bg: "linear-gradient(135deg, rgba(239,68,68,0.15), rgba(239,68,68,0.08))", border: "#ef4444", color: "#ef4444" };
    return { bg: "linear-gradient(135deg, rgba(245,158,11,0.15), rgba(251,191,36,0.10))", border: "#f59e0b", color: "#fbbf24" };
  };
  const alertStyle = getAlertStyle(alertType);

  return (
    <div style={{ minHeight: "100vh", background: "#0a0a0a", color: "white", padding: "14px", fontFamily: "system-ui" }}>
      <div style={{ maxWidth: "920px", margin: "0 auto" }}>
        <div style={{ display: "flex", justifyContent: "space-between", flexWrap: "wrap", gap: "12px", borderBottom: "2px solid #f59e0b", paddingBottom: "14px", marginBottom: "14px" }}>
          <div>
            <h1 style={{ fontSize: "24px", fontWeight: "900", margin: 0, color: "#fbbf24" }}>EDGEALERT ORO v8.5 - 15m ESTABLE</h1>
            <div style={{ fontSize: "11px", color: "#a8a29e" }}>{timeEc} • EC • {backendStatus}</div>
            <div style={{ fontSize: "11px", color: "#fbbf24", fontWeight: "700" }}>Análisis: {s.market_analysis?.analysis_price?.toFixed(2)} (vela 15m cerrada) • Vivo: {s.entry?.toFixed(2)} oscilando</div>
            <div style={{ fontSize: "10px", color: "#71717a", marginTop: "4px" }}>Fase: <b style={{ color: getPhaseColor(phase) }}>{phase}</b> • {phaseDesc}</div>
            <div style={{ fontSize: "9px", color: "#10b981", marginTop: "2px" }}>Señal estable 15 min - no cambia cada 30s por oscilación vela</div>
          </div>
          <div style={{ textAlign: "right" }}>
            <div style={{ fontSize: "12px", padding: "6px 12px", borderRadius: "8px", background: isBuy ? "rgba(34,197,94,0.15)" : "rgba(239,68,68,0.15)", border: `1px solid ${isBuy ? "#22c55e" : "#ef4444"}`, color: isBuy ? "#22c55e" : "#ef4444", fontWeight: "800" }}>{s.direction} {isBuy ? "↑" : "↓"}</div>
            <div style={{ fontSize: "9px", marginTop: "6px", color: "#a1a1aa", background: "rgba(255,255,255,0.05)", padding: "4px", borderRadius: "4px" }}>{s.flip_reason}</div>
          </div>
        </div>

        <div style={{ background: alertStyle.bg, border: `2px solid ${alertStyle.border}`, borderRadius: "12px", padding: "14px", marginBottom: "12px" }}>
          <div style={{ fontWeight: "900", fontSize: "15px", color: alertStyle.color, textAlign: "center" }}>{alert}</div>
          <div style={{ fontSize: "11px", color: "#a8a29e", textAlign: "center", marginTop: "6px" }}>{alertDesc}</div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "10px", marginTop: "12px" }}>
            <div style={{ background: "rgba(0,0,0,0.3)", borderRadius: "8px", padding: "10px", textAlign: "center" }}>
              <div style={{ fontSize: "10px", color: "#a8a29e" }}>CONFIANZA DIRECCIÓN</div>
              <div style={{ fontSize: "22px", fontWeight: "900", color: alertStyle.color }}>{confidence.toFixed(1)}%</div>
              <div style={{ fontSize: "9px", color: "#71717a" }}>Score {s.market_analysis?.buy_score} COMPRA vs {s.market_analysis?.sell_score} VENTA</div>
            </div>
            <div style={{ background: "rgba(0,0,0,0.3)", borderRadius: "8px", padding: "10px", textAlign: "center" }}>
              <div style={{ fontSize: "10px", color: "#a8a29e" }}>PROB TP1 $10 (10-15m)</div>
              <div style={{ fontSize: "22px", fontWeight: "900", color: "#fbbf24" }}>{probTP1.toFixed(1)}%</div>
              <div style={{ fontSize: "9px", color: "#71717a" }}>Histórico 600 velas oro</div>
            </div>
          </div>
        </div>

        <div style={{ background: "#18181b", border: "1px solid #27272a", borderRadius: "12px", padding: "12px", marginBottom: "12px" }}>
          <div style={{ fontWeight: "800", fontSize: "12px", marginBottom: "8px", color: "#fbbf24" }}>SISTEMA PUNTOS 10-15-30 + FIB (tu lógica) - {s.market_analysis?.buy_score} COMPRA vs {s.market_analysis?.sell_score} VENTA</div>
          <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
            {points.map((p,i) => (
              <div key={i} style={{ display: "flex", justifyContent: "space-between", background: p.side==="BUY" ? "rgba(34,197,94,0.08)" : "rgba(239,68,68,0.08)", border: `1px solid ${p.side==="BUY" ? "rgba(34,197,94,0.2)" : "rgba(239,68,68,0.2)"}`, borderRadius: "8px", padding: "8px", fontSize: "11px" }}>
                <div><b style={{ color: p.side==="BUY" ? "#22c55e" : "#ef4444" }}>{p.side==="BUY" ? "COMPRA" : "VENTA"} +{p.points} {p.name}</b><div style={{ fontSize: "10px", color: "#a1a1aa" }}>{p.reason}</div></div>
                <span style={{ fontWeight: "900" }}>+{p.points}</span>
              </div>
            ))}
          </div>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "8px", marginBottom: "10px" }}>
          <div style={{ background: "#0c0a09", border: "1px solid #292524", borderRadius: "8px", padding: "8px", fontSize: "10px" }}>
            <div style={{ color: "#a8a29e", fontWeight: "700" }}>TIEMPOS 10-15-30 MIN + SR 4H</div>
            <div>Alto 10m: {s.market_analysis?.high_10?.toFixed(2)} | Bajo 10m: {s.market_analysis?.low_10?.toFixed(2)}</div>
            <div>Alto 15m: <b style={{ color: "#fbbf24" }}>{s.market_analysis?.high_15?.toFixed(2)}</b> | Bajo 15m: <b style={{ color: "#fbbf24" }}>{s.market_analysis?.low_15?.toFixed(2)}</b></div>
            <div style={{ borderTop: "1px solid #292524", marginTop: "4px", paddingTop: "4px" }}>SR 4H (pivotes): <b style={{ color: "#a78bfa" }}>{s.market_analysis?.low_long?.toFixed(2)} - {s.market_analysis?.high_long?.toFixed(2)}</b> ({s.market_analysis?.band_long?.toFixed(1)} USD) {s.market_analysis?.band_long >=10 ? "📦 AMPLIA" : s.market_analysis?.band_long <7 ? "⏸️ ESTRECHA" : ""}</div>
            <div>SMA: {s.market_analysis?.sma10?.toFixed(1)}/{s.market_analysis?.sma15?.toFixed(1)}/{s.market_analysis?.sma30?.toFixed(1)}</div>
          </div>
          <div style={{ background: "#0c0a09", border: "1px solid #292524", borderRadius: "8px", padding: "8px", fontSize: "10px" }}>
            <div style={{ color: "#a8a29e", fontWeight: "700" }}>SOPORTE / RESISTENCIA + FIBONACCI</div>
            <div>Soporte: <b style={{ color: "#10b981" }}>{s.support?.toFixed(2)}</b> | Resistencia: <b style={{ color: "#ef4444" }}>{s.resistance?.toFixed(2)}</b></div>
            <div>SR 4H pivotes: <b style={{ color: "#a78bfa" }}>{s.market_analysis?.support_long?.toFixed(2)} - {s.market_analysis?.resistance_long?.toFixed(2)}</b> ({s.market_analysis?.band_long?.toFixed(1)} USD)</div>
            {s.market_analysis?.fib && (
              <div style={{ marginTop: "4px", background: "rgba(168,85,247,0.1)", borderRadius: "6px", padding: "4px" }}>
                <div style={{ color: "#c084fc", fontWeight: "700" }}>FIB {s.market_analysis?.fib?.dir} {s.market_analysis?.fib?.range?.toFixed(1)} USD</div>
                <div>Impulso {s.market_analysis?.fib?.low?.toFixed(2)} → {s.market_analysis?.fib?.high?.toFixed(2)}</div>
                <div>0.382: {s.market_analysis?.fib?.levels?.["0.382"]?.toFixed(2)} | 0.5: {s.market_analysis?.fib?.levels?.["0.5"]?.toFixed(2)} | 0.618: <b style={{ color: "#fbbf24" }}>{s.market_analysis?.fib?.levels?.["0.618"]?.toFixed(2)}</b></div>
                {s.market_analysis?.fib?.near && <div style={{ color: "#fbbf24" }}>Cerca Fib {s.market_analysis?.fib?.near} a {s.market_analysis?.fib?.dist?.toFixed(2)} USD - {s.market_analysis?.fib?.near === "0.618" || s.market_analysis?.fib?.near === "0.5" ? "ZONA ENTRADA" : "retroceso"}</div>}
              </div>
            )}
            {s.market_analysis?.high_clusters?.length > 0 && (
              <div style={{ marginTop: "4px", background: "rgba(239,68,68,0.08)", borderRadius: "6px", padding: "4px", fontSize: "9px" }}>
                <div style={{ color: "#ef4444", fontWeight: "700" }}>Resistencias detectadas</div>
                {s.market_analysis?.high_clusters?.map((c,i) => <div key={i}>R{i+1}: {c[0].toFixed(2)} - {c[1]} toques</div>)}
              </div>
            )}
            {s.market_analysis?.low_clusters?.length > 0 && (
              <div style={{ marginTop: "4px", background: "rgba(34,197,94,0.08)", borderRadius: "6px", padding: "4px", fontSize: "9px" }}>
                <div style={{ color: "#22c55e", fontWeight: "700" }}>Soportes detectados</div>
                {s.market_analysis?.low_clusters?.map((c,i) => <div key={i}>S{i+1}: {c[0].toFixed(2)} - {c[1]} toques</div>)}
              </div>
            )}
            <div>Vol: {s.market_analysis?.volatility?.toFixed(1)} USD | {s.flip_reason}</div>
            {s.market_analysis?.band_long >=10 && <div style={{ color: "#fbbf24", fontSize: "9px", marginTop: "3px" }}>Acumulación amplia {s.market_analysis?.band_long?.toFixed(1)} USD - señales de corte con impulso y retroceso Fib</div>}
          </div>
        </div>

        <div style={{ fontFamily: "monospace", fontSize: "11px", background: "#0c0a09", borderRadius: "10px", padding: "10px", border: "1px solid #44403c" }}>
          <div style={{ display: "flex", justifyContent: "space-between" }}><span style={{ color: "#a8a29e" }}>ENTRADA</span><span style={{ fontWeight: "900", color: "#fbbf24" }}>{s.entry?.toFixed(2)}</span></div>
          <div style={{ display: "flex", justifyContent: "space-between", color: "#f87171" }}><span style={{ color: "#a8a29e" }}>SL (-$10) {s.direction==="BUY"?"↓":"↑"}</span><span>{s.sl?.toFixed(2)}</span></div>
          <div style={{ display: "flex", justifyContent: "space-between", color: "#fbbf24" }}><span style={{ color: "#a8a29e" }}>TP1 (+$10) {s.direction==="BUY"?"↑":"↓"}</span><span>{s.tp1?.toFixed(2)}</span></div>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: "8px", marginTop: "10px" }}>
          <button onClick={()=>sendResult("SL")} style={{ background: "rgba(239,68,68,0.12)", border: "1px solid rgba(239,68,68,0.4)", color: "#f87171", borderRadius: "8px", padding: "8px", fontSize: "10px", fontWeight: "800" }}>SL -$10</button>
          <button onClick={()=>sendResult("TP1")} style={{ background: "rgba(245,158,11,0.18)", border: "1px solid #f59e0b", color: "#fbbf24", borderRadius: "8px", padding: "8px", fontSize: "10px", fontWeight: "800" }}>TP1 +$10</button>
          <button onClick={()=>sendResult("TP2")} style={{ background: "rgba(245,158,11,0.14)", border: "1px solid rgba(245,158,11,0.4)", color: "#fbbf24", borderRadius: "8px", padding: "8px", fontSize: "10px", fontWeight: "800" }}>TP2 +$20</button>
          <button onClick={()=>sendResult("TP3")} style={{ background: "linear-gradient(135deg, rgba(245,158,11,0.2), rgba(251,191,36,0.2))", border: "1px solid #f59e0b", color: "#fbbf24", borderRadius: "8px", padding: "8px", fontSize: "10px", fontWeight: "800" }}>TP3 +$30</button>
        </div>
      </div>
    </div>
  );
}
