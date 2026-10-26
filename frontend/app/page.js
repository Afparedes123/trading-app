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
        setBackendStatus("conectado - FASES + PUNTOS 10-15-30 v6.1 fix");
      } else throw new Error("vacio");
    } catch (e) {
      setBackendStatus("demo - FASES + PUNTOS fix");
      const demoPrice = 4028.5 + Math.random() * 4;
      const demo = calcTPSL(demoPrice, "SELL");
      setSignal({
        symbol: "XAUUSD", direction: "SELL", entry: demoPrice, sl: demo.sl, tp1: demo.tp1, tp2: demo.tp2, tp3: demo.tp3, sl_distance: demo.dist, tp1_distance: demo.dist,
        sl_explain: `SL ${demo.sl.toFixed(2)} ARRIBA`, tp_explain: `TP1 ${demo.tp1.toFixed(2)} ABAJO VENTA`,
        probability: 84, probability_tp1: 57.8, confidence: 84, win_rate: 78.5, win_rate_direction: 82.3, win_rate_buy: 71, win_rate_sell: 81, is_optimal_hour: true,
        phase: "TRANSICION", phase_desc: "TRANSICION - vol 8.1 USD, pendiente 0.81",
        alert: "✅ ENTRA - SELL CONFIRMADO - TENDENCIA FUERTE", alert_type: "ENTER", alert_desc: "Score 8 vs 2 - confianza 84%",
        candle_patterns: [{ name: "SHOOTING_STAR", dir: "SELL", strength: 2, desc: "Estrella fugaz - rechazo altos" }],
        points_detail: [
          { side: "SELL", points: 3, name: "SMA BEAR FUERTE", reason: "Precio < SMA10 < SMA15 < SMA30" },
          { side: "SELL", points: 3, name: "BREAK LOW 10m FUERTE", reason: "Ruptura bajo 10m vela fuerte" },
          { side: "SELL", points: 2, name: "SHOOTING_STAR", reason: "🕯️ Estrella fugaz" },
          { side: "BUY", points: 1, name: "SMA BULL DEBIL", reason: "Precio > SMA10 y SMA15" },
          { side: "BUY", points: 1, name: "SESION NY", reason: "NY OPEN" }
        ],
        market_analysis: {
          trend: "BEARISH", up_streak: 0, down_streak: 1, high_10: demoPrice + 3.2, low_10: demoPrice - 2.8, high_15: demoPrice + 5.5, low_15: demoPrice - 4.8,
          sma10: demoPrice + 1.2, sma15: demoPrice + 2.1, sma30: demoPrice + 3.0, support: demoPrice - 4.8, resistance: demoPrice + 5.5,
          buy_score: 2, sell_score: 8, volatility: 8.1, volatility_15: 5.0, phase: "TRANSICION", phase_desc: "TRANSICION - vol 8.1 USD, pendiente 0.81", phase_info: { phase: "TRANSICION", band: 5.8, avg6: 5.0, avg3: 8.1, up: 0, down: 1, slope: 0.81, is_acc: false }
        },
        probabilidad_nuevos_objetivos: { prob_tp1_10usd_10_15min: 57.8, prob_tp2_20usd_15min: 38, prob_tp3_30usd_15min: 22 },
        reason: "SMA BEAR + BREAK LOW + SHOOTING_STAR", flip_reason: "Tendencia fuerte SELL", support: demoPrice - 4.8, resistance: demoPrice + 5.5
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
      alert(`✅ ORO ${r}`); fetchData();
    } catch {}
  };

  if (loading) return <div style={{ minHeight: "100vh", background: "#0a0a0a", color: "white", display: "flex", alignItems: "center", justifyContent: "center" }}>ORO FASES + PUNTOS - Analizando...</div>;
  const s = signal; if (!s) return null;
  const isBuy = s.direction === "BUY";
  const confidence = s.confidence || s.probability || 78;
  const probTP1 = s.probability_tp1 || s.probabilidad_nuevos_objetivos?.prob_tp1_10usd_10_15min || 0;
  const displayProb = s.probability || confidence;
  const phase = s.phase || s.market_analysis?.phase || "RANGO";
  const phaseDesc = s.phase_desc || s.market_analysis?.phase_desc || "";
  const points = s.points_detail || s.market_analysis?.points_detail || [];
  const candles = s.candle_patterns || s.market_analysis?.candle_patterns || [];
  const phaseInfo = s.market_analysis?.phase_info || {};
  const alert = s.alert || "";
  const alertType = s.alert_type || "WAIT";
  const alertDesc = s.alert_desc || "";

  const getPhaseColor = (ph) => {
    if (ph.includes("EXPANSION_ALCISTA") || ph.includes("TENDENCIA_ALCISTA")) return "#fbbf24";
    if (ph.includes("EXPANSION_BAJISTA") || ph.includes("TENDENCIA_BAJISTA")) return "#ef4444";
    if (ph.includes("ACUMULACION")) return "#a78bfa";
    if (ph.includes("AGOTAMIENTO") || ph.includes("DISTRIBUCION")) return "#fb923c";
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
            <h1 style={{ fontSize: "28px", fontWeight: "900", margin: 0, color: "#fbbf24" }}>EDGEALERT ORO FASES + PUNTOS v6.1</h1>
            <p style={{ color: "#a1a1aa", fontSize: "10px", marginTop: "4px" }}>FASE en vivo + ALERTA ENTRA/ESPERA + Puntos 10-15-30 • FIX: % unificados</p>
            <p style={{ fontSize: "10px", color: backendStatus.includes("conectado") ? "#10b981" : "#f59e0b" }}>{backendStatus}</p>
          </div>
          <div style={{ background: "#1c1917", border: "1px solid #44403c", borderRadius: "10px", padding: "10px", minWidth: "180px" }}>
            <div style={{ color: "#a8a29e", fontSize: "9px" }}>HORA ECUADOR -5</div>
            <div style={{ fontFamily: "monospace", fontSize: "11px", marginTop: "4px" }}>{timeEc}</div>
            <div style={{ color: "#fbbf24", fontSize: "9px", marginTop: "4px", fontWeight: "700" }}>NY OPEN 8-10 AM EC</div>
          </div>
        </div>

        <div style={{ background: "linear-gradient(135deg, #1c1917 0%, #18181b 100%)", border: "2px solid #f59e0b", borderRadius: "18px", padding: "16px", position: "relative" }}>
          <div style={{ position: "absolute", top: 0, right: 0, background: alertType === "ENTER" ? (isBuy ? "#fbbf24" : "#ef4444") : "#a1a1aa", color: alertType === "ENTER" ? "#000" : "#fff", padding: "8px 14px", borderRadius: "0 16px 0 12px", fontWeight: "900", fontSize: "13px", textAlign: "right", lineHeight: "1.2" }}>
            <div>{displayProb.toFixed(1)}% {s.direction} • CONFIANZA</div>
            <div style={{ fontSize: "9px", fontWeight: "600", opacity: 0.8 }}>{probTP1.toFixed(1)}% prob TP1 $10 en 10-15m</div>
          </div>

          <div style={{ display: "flex", gap: "8px", alignItems: "center", marginBottom: "10px", marginTop: "4px" }}>
            <span style={{ fontSize: "20px", fontWeight: "900", color: "#fbbf24" }}>XAUUSD</span>
            <span style={{ fontSize: "10px", background: getPhaseColor(phase), color: "#000", padding: "3px 8px", borderRadius: "12px", fontWeight: "800" }}>{phase}</span>
            <span style={{ background: isBuy ? "rgba(245,158,11,0.2)" : "rgba(239,68,68,0.15)", color: isBuy ? "#fbbf24" : "#ef4444", border: `1px solid ${isBuy ? "#f59e0b" : "#ef4444"}`, padding: "4px 10px", borderRadius: "16px", fontSize: "11px", fontWeight: "900" }}>{s.direction} {isBuy ? "↑" : "↓"}</span>
          </div>

          <div style={{ background: "#0c0a09", border: `1px solid ${getPhaseColor(phase)}`, borderRadius: "10px", padding: "10px", marginBottom: "10px" }}>
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "4px" }}>
              <span style={{ fontSize: "10px", color: "#a8a29e", fontWeight: "800" }}>📍 FASE EN EL MOMENTO</span>
              <span style={{ fontSize: "9px", color: getPhaseColor(phase) }}>Banda {phaseInfo.band?.toFixed(1)} USD • Vol {phaseInfo.avg6?.toFixed(1)}→{phaseInfo.avg3?.toFixed(1)} • {phaseInfo.up||0}↑ {phaseInfo.down||0}↓</span>
            </div>
            <div style={{ fontSize: "12px", fontWeight: "700" }}>{phaseDesc}</div>
          </div>

          <div style={{ background: alertStyle.bg, border: `2px solid ${alertStyle.border}`, borderRadius: "12px", padding: "12px", marginBottom: "10px" }}>
            <div style={{ fontSize: "14px", fontWeight: "900", color: alertStyle.color, textAlign: "center" }}>{alert}</div>
            <div style={{ fontSize: "11px", color: "#d6d3d1", textAlign: "center", marginTop: "4px" }}>{alertDesc}</div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "8px", marginTop: "10px", fontSize: "10px" }}>
              <div style={{ background: "rgba(0,0,0,0.3)", borderRadius: "8px", padding: "8px", textAlign: "center" }}>
                <div style={{ color: "#a8a29e" }}>CONFIANZA DIRECCIÓN</div>
                <div style={{ fontSize: "16px", fontWeight: "900", color: alertStyle.color }}>{confidence.toFixed(1)}%</div>
                <div style={{ fontSize: "9px", color: "#78716c" }}>Score {s.market_analysis?.buy_score||0} BUY vs {s.market_analysis?.sell_score||0} SELL • Puntos 10-15-30 + velas</div>
              </div>
              <div style={{ background: "rgba(0,0,0,0.3)", borderRadius: "8px", padding: "8px", textAlign: "center" }}>
                <div style={{ color: "#a8a29e" }}>PROB TP1 $10 (10-15m)</div>
                <div style={{ fontSize: "16px", fontWeight: "900", color: "#fbbf24" }}>{probTP1.toFixed(1)}%</div>
                <div style={{ fontSize: "9px", color: "#78716c" }}>Basado en histórico 300 velas oro + winrate</div>
              </div>
            </div>
            <div style={{ fontSize: "9px", color: "#78716c", marginTop: "8px", background: "rgba(0,0,0,0.2)", padding: "6px", borderRadius: "6px" }}>
              <b>Por qué había 57.8% vs 84%:</b> El gris 57.8% es la prob histórica de que TP1 de $10 se alcance en 10-15 min. El verde 84% es la confianza de la dirección según tu sistema de puntos 10-15-30 (Score 8 vs 2). Son 2 métricas distintas. Ahora arriba muestro ambas etiquetadas para no confundir. Cuando dice ENTRA, ambos son SELL (o ambos BUY) — no uno BUY y otro SELL.
            </div>
          </div>

          <div style={{ background: "#0c0a09", border: "1px solid #44403c", borderRadius: "10px", padding: "10px", marginBottom: "10px" }}>
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "8px" }}>
              <span style={{ fontSize: "10px", color: "#fbbf24", fontWeight: "800" }}>🎯 SISTEMA PUNTOS 10-15-30 (tu lógica)</span>
              <span style={{ fontSize: "10px", fontWeight: "900" }}><span style={{ color: "#fbbf24" }}>{s.market_analysis?.buy_score||0} BUY</span> vs <span style={{ color: "#ef4444" }}>{s.market_analysis?.sell_score||0} SELL</span></span>
            </div>
            <div style={{ display: "grid", gap: "5px" }}>
              {points.map((p,i)=>(
                <div key={i} style={{ display: "flex", justifyContent: "space-between", background: p.side==="BUY"?"rgba(245,158,11,0.08)":p.side==="SELL"?"rgba(239,68,68,0.08)":"rgba(167,139,250,0.08)", border: `1px solid ${p.side==="BUY"?"rgba(245,158,11,0.25)":p.side==="SELL"?"rgba(239,68,68,0.25)":"rgba(167,139,250,0.25)"}`, borderRadius: "6px", padding: "6px 8px", fontSize: "10px" }}>
                  <div><span style={{ fontWeight: "800", color: p.side==="BUY"?"#fbbf24":p.side==="SELL"?"#ef4444":"#a78bfa" }}>{p.side} +{p.points}</span> <span style={{ fontWeight: "700" }}>{p.name}</span> <span style={{ color: "#a8a29e" }}>- {p.reason}</span></div>
                  <span style={{ fontWeight: "900" }}>+{p.points}</span>
                </div>
              ))}
            </div>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "8px", marginBottom: "10px" }}>
            <div style={{ background: "#0c0a09", border: "1px solid #292524", borderRadius: "8px", padding: "8px", fontSize: "10px" }}>
              <div style={{ color: "#a8a29e", fontWeight: "700" }}>📊 10-15-30 MIN</div>
              <div>Alto 10m: {s.market_analysis?.high_10?.toFixed(2)} | Bajo 10m: {s.market_analysis?.low_10?.toFixed(2)}</div>
              <div>Alto 15m: <b style={{ color: "#fbbf24" }}>{s.market_analysis?.high_15?.toFixed(2)}</b> | Bajo 15m: <b style={{ color: "#fbbf24" }}>{s.market_analysis?.low_15?.toFixed(2)}</b></div>
              <div>SMA: {s.market_analysis?.sma10?.toFixed(1)}/{s.market_analysis?.sma15?.toFixed(1)}/{s.market_analysis?.sma30?.toFixed(1)}</div>
            </div>
            <div style={{ background: "#0c0a09", border: "1px solid #292524", borderRadius: "8px", padding: "8px", fontSize: "10px" }}>
              <div style={{ color: "#a8a29e", fontWeight: "700" }}>🎯 SOPORTE / RESISTENCIA</div>
              <div>Soporte: <b style={{ color: "#10b981" }}>{s.support?.toFixed(2)}</b> | Resistencia: <b style={{ color: "#ef4444" }}>{s.resistance?.toFixed(2)}</b></div>
              <div>Vol: {s.market_analysis?.volatility?.toFixed(1)} USD | {s.flip_reason}</div>
            </div>
          </div>

          <div style={{ fontFamily: "monospace", fontSize: "11px", background: "#0c0a09", borderRadius: "10px", padding: "10px", border: "1px solid #44403c" }}>
            <div style={{ display: "flex", justifyContent: "space-between" }}><span style={{ color: "#a8a29e" }}>ENTRY</span><span style={{ fontWeight: "900", color: "#fbbf24" }}>{s.entry?.toFixed(2)}</span></div>
            <div style={{ display: "flex", justifyContent: "space-between", color: "#f87171" }}><span style={{ color: "#a8a29e" }}>SL (-$10) {isBuy?"↓":"↑"}</span><span>{s.sl?.toFixed(2)}</span></div>
            <div style={{ display: "flex", justifyContent: "space-between", color: "#fbbf24" }}><span style={{ color: "#a8a29e" }}>TP1 (+$10) {isBuy?"↑":"↓"}</span><span>{s.tp1?.toFixed(2)}</span></div>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: "8px", marginTop: "10px" }}>
            <button onClick={()=>sendResult("SL")} style={{ background: "rgba(239,68,68,0.12)", border: "1px solid rgba(239,68,68,0.4)", color: "#f87171", borderRadius: "8px", padding: "8px", fontSize: "10px", fontWeight: "800" }}>SL -$10</button>
            <button onClick={()=>sendResult("TP1")} style={{ background: "rgba(245,158,11,0.18)", border: "1px solid #f59e0b", color: "#fbbf24", borderRadius: "8px", padding: "8px", fontSize: "10px", fontWeight: "800" }}>TP1 +$10</button>
            <button onClick={()=>sendResult("TP2")} style={{ background: "rgba(245,158,11,0.14)", border: "1px solid rgba(245,158,11,0.4)", color: "#fbbf24", borderRadius: "8px", padding: "8px", fontSize: "10px", fontWeight: "800" }}>TP2 +$20</button>
            <button onClick={()=>sendResult("TP3")} style={{ background: "linear-gradient(135deg, rgba(245,158,11,0.2), rgba(251,191,36,0.2))", border: "1px solid #f59e0b", color: "#fbbf24", borderRadius: "8px", padding: "8px", fontSize: "10px", fontWeight: "800" }}>TP3 +$30</button>
          </div>
        </div>
      </div>
    </div>
  );
}
