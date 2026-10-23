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
        setBackendStatus("conectado - FASES + PUNTOS 10-15-30");
      } else throw new Error("vacio");
    } catch (e) {
      setBackendStatus("demo - FASES + PUNTOS");
      const demoPrice = 4028.5 + Math.random() * 4;
      const demo = calcTPSL(demoPrice, "BUY");
      setSignal({
        symbol: "XAUUSD", direction: "BUY", entry: demoPrice, sl: demo.sl, tp1: demo.tp1, tp2: demo.tp2, tp3: demo.tp3, sl_distance: demo.dist, tp1_distance: demo.dist,
        sl_explain: `SL ${demo.sl.toFixed(2)} ABAJO`, tp_explain: `TP1 ${demo.tp1.toFixed(2)} ARRIBA COMPRA`,
        probability: 84, confidence: 82, win_rate: 78.5, win_rate_direction: 82.3, win_rate_buy: 81, win_rate_sell: 72, is_optimal_hour: true,
        phase: "ACUMULACION", phase_desc: "ACUMULACION PURA - rango 2.8 USD muy estrecho, vol 1.2 USD, esperando PICO - NO ENTRAR AUN",
        alert: "⛔ ESPERA - NO ENTRES - FASE ACUMULACION", alert_type: "WAIT", alert_desc: "Acumulacion pura rango 2.8 USD - NO operar, esperar PICO tras acumulacion como hoy. Score 3B/2S insuficiente",
        candle_patterns: [{ name: "DOJI", dir: "SELL", strength: 1, desc: "Doji en tope" }],
        points_detail: [
          { side: "BUY", points: 3, name: "SMA BULL FUERTE", reason: "Precio 4028.50 > SMA10 4026.20 > SMA15 4025.10 > SMA30 4024.00" },
          { side: "BUY", points: 2, name: "RACHA 3 VELAS ALCISTAS 10m", reason: "Racha alcista 3 velas 10min oro consecutivas" },
          { side: "BUY", points: 1, name: "SESION NY 8-10AM EC", reason: "🔥 NY OPEN alta volatilidad oro alcista +1" },
          { side: "NEUTRAL", points: 0, name: "ACUMULACION", reason: "⏸️ ACUMULACION PURA - rango 2.8 USD muy estrecho, vol 1.2 USD, esperando PICO - NO ENTRAR AUN" },
          { side: "BUY", points: 2, name: "HAMMER", reason: "🕯️ Martillo alcista - rechazo bajos" }
        ],
        market_analysis: {
          trend: "BULLISH", up_streak: 2, down_streak: 0, high_10: demoPrice + 3.2, low_10: demoPrice - 2.8, high_15: demoPrice + 5.5, low_15: demoPrice - 4.8, high_30: demoPrice + 8.1, low_30: demoPrice - 7.2,
          sma10: demoPrice - 1.2, sma15: demoPrice - 2.1, sma30: demoPrice - 3.0, support: demoPrice - 4.8, resistance: demoPrice + 5.5,
          buy_score: 5, sell_score: 2, volatility: 1.2, volatility_15: 1.8, phase: "ACUMULACION", phase_desc: "ACUMULACION PURA - rango 2.8 USD", phase_info: { phase: "ACUMULACION", band: 2.8, avg6: 1.2, avg3: 1.1, up: 2, down: 0, slope: 0.2, is_acc: true }
        },
        probabilidad_nuevos_objetivos: { prob_tp1_10usd_10_15min: 58, prob_tp2_20usd_15min: 32, prob_tp3_30usd_15min: 18 },
        reason: "SMA BULL FUERTE | RACHA 3 VELAS | NY", flip_reason: "Fase ACUMULACION esperando 12m", support: demoPrice - 4.8, resistance: demoPrice + 5.5
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
      alert(`✅ ORO ${r}`);
      fetchData();
    } catch {}
  };

  if (loading) return <div style={{ minHeight: "100vh", background: "#0a0a0a", color: "white", display: "flex", alignItems: "center", justifyContent: "center" }}>ORO FASES + PUNTOS - Analizando 10-15-30 min...</div>;
  const s = signal; if (!s) return null;
  const isBuy = s.direction === "BUY";
  const prob = s.probability || 78;
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
    if (type === "ENTER") return { bg: "linear-gradient(135deg, rgba(34,197,94,0.15), rgba(16,185,129,0.15))", border: "#22c55e", color: "#22c55e", icon: "✅" };
    if (type === "WAIT") return { bg: "linear-gradient(135deg, rgba(239,68,68,0.15), rgba(239,68,68,0.08))", border: "#ef4444", color: "#ef4444", icon: "⛔" };
    return { bg: "linear-gradient(135deg, rgba(245,158,11,0.15), rgba(251,191,36,0.10))", border: "#f59e0b", color: "#fbbf24", icon: "⚠️" };
  };
  const alertStyle = getAlertStyle(alertType);

  return (
    <div style={{ minHeight: "100vh", background: "#0a0a0a", color: "white", padding: "14px", fontFamily: "system-ui" }}>
      <div style={{ maxWidth: "920px", margin: "0 auto" }}>
        <div style={{ display: "flex", justifyContent: "space-between", flexWrap: "wrap", gap: "12px", borderBottom: "2px solid #f59e0b", paddingBottom: "14px", marginBottom: "14px" }}>
          <div>
            <h1 style={{ fontSize: "30px", fontWeight: "900", margin: 0, color: "#fbbf24" }}>EDGEALERT ORO FASES + PUNTOS</h1>
            <p style={{ color: "#a1a1aa", fontSize: "11px", marginTop: "4px" }}>Solo XAUUSD • FASE en vivo + ALERTA ENTRA/ESPERA + Puntos 10-15-30 min • 6.17 USD = $10</p>
            <p style={{ fontSize: "10px", color: backendStatus.includes("conectado") ? "#10b981" : "#f59e0b" }}>{backendStatus}</p>
          </div>
          <div style={{ background: "#1c1917", border: "1px solid #44403c", borderRadius: "10px", padding: "10px", minWidth: "190px" }}>
            <div style={{ color: "#a8a29e", fontSize: "9px" }}>HORA ECUADOR -5</div>
            <div style={{ fontFamily: "monospace", fontSize: "11px", marginTop: "4px" }}>{timeEc}</div>
            <div style={{ color: "#fbbf24", fontSize: "9px", marginTop: "4px", fontWeight: "700" }}>NY OPEN 8-10 AM EC</div>
          </div>
        </div>

        <div style={{ background: "linear-gradient(135deg, #1c1917 0%, #18181b 100%)", border: "2px solid #f59e0b", borderRadius: "18px", padding: "16px", position: "relative" }}>
          <div style={{ position: "absolute", top: 0, right: 0, background: prob >= 78 ? "#fbbf24" : prob >= 65 ? "#f59e0b" : "#a1a1aa", color: "#000", padding: "6px 14px", borderRadius: "0 16px 0 12px", fontWeight: "900", fontSize: "14px" }}>{prob}% {isBuy ? "BUY" : "SELL"}</div>

          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "10px", marginTop: "4px" }}>
            <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
              <span style={{ fontSize: "22px", fontWeight: "900", color: "#fbbf24" }}>XAUUSD</span>
              <span style={{ fontSize: "10px", background: getPhaseColor(phase), color: "#000", padding: "3px 8px", borderRadius: "16px", fontWeight: "800" }}>{phase}</span>
              <span style={{ background: isBuy ? "rgba(245,158,11,0.2)" : "rgba(239,68,68,0.15)", color: isBuy ? "#fbbf24" : "#ef4444", border: `1px solid ${isBuy ? "#f59e0b" : "#ef4444"}`, padding: "4px 10px", borderRadius: "16px", fontSize: "11px", fontWeight: "900" }}>{s.direction} {isBuy ? "↑" : "↓"}</span>
            </div>
          </div>

          {/* FASE EN EL MOMENTO */}
          <div style={{ background: "#0c0a09", border: `1px solid ${getPhaseColor(phase)}`, borderRadius: "12px", padding: "12px", marginBottom: "12px" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "6px" }}>
              <div style={{ fontSize: "11px", color: "#a8a29e", fontWeight: "800" }}>📍 FASE EN EL MOMENTO</div>
              <div style={{ fontSize: "9px", color: getPhaseColor(phase), fontWeight: "700" }}>Banda {phaseInfo.band?.toFixed(1) || "-"} USD • Vol {phaseInfo.avg6?.toFixed(1) || "-"} → {phaseInfo.avg3?.toFixed(1) || "-"} USD • {phaseInfo.up || 0}↑ {phaseInfo.down || 0}↓</div>
            </div>
            <div style={{ fontSize: "13px", color: "#fff", fontWeight: "700", lineHeight: "1.3" }}>{phaseDesc}</div>
            <div style={{ fontSize: "10px", color: "#78716c", marginTop: "6px" }}>
              {phase.includes("ACUMULACION") ? "⏸️ Mercado en acumulación = rango estrecho como hoy antes de picos → NO ENTRAR, esperar ruptura" : phase.includes("EXPANSION") ? "🚀 Fase de expansión tras acumulación = PICO compra/venta - ENTRAR con señal limpia" : phase.includes("TENDENCIA") ? "📈 Tendencia clara - seguir dirección" : phase.includes("AGOTAMIENTO") ? "⚠️ Agotamiento - posible reversal, buscar vela opuesta" : "Rango / Transición"}
            </div>
          </div>

          {/* ALERTA ENTRA / ESPERA NO ENTRES */}
          <div style={{ background: alertStyle.bg, border: `2px solid ${alertStyle.border}`, borderRadius: "14px", padding: "14px", marginBottom: "12px", textAlign: "center" }}>
            <div style={{ fontSize: "16px", fontWeight: "900", color: alertStyle.color, letterSpacing: "-0.5px" }}>{alert}</div>
            <div style={{ fontSize: "11px", color: "#d6d3d1", marginTop: "6px", lineHeight: "1.3" }}>{alertDesc}</div>
            {alertType === "WAIT" && phase.includes("ACUMULACION") && (
              <div style={{ fontSize: "10px", color: "#a78bfa", marginTop: "8px", background: "rgba(167,139,250,0.1)", padding: "6px", borderRadius: "6px" }}>💡 Hoy ha sido predecible: acumulación → pico. Si ves esta alerta, NO entres hasta que aparezca ✅ ENTRA tras ruptura</div>
            )}
            {alertType === "ENTER" && (
              <div style={{ fontSize: "10px", color: "#22c55e", marginTop: "8px", background: "rgba(34,197,94,0.1)", padding: "6px", borderRadius: "6px" }}>💡 Señal limpia: fase {phase} + vela japonesa confirmada + puntos ≥5</div>
            )}
          </div>

          {/* SISTEMA DE PUNTOS 10-15-30 MIN */}
          <div style={{ background: "#0c0a09", border: "1px solid #44403c", borderRadius: "12px", padding: "12px", marginBottom: "12px" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "10px" }}>
              <div style={{ fontSize: "11px", color: "#fbbf24", fontWeight: "800" }}>🎯 SISTEMA DE PUNTOS 10-15-30 MIN (tu lógica)</div>
              <div style={{ fontSize: "11px", fontWeight: "900" }}><span style={{ color: "#fbbf24" }}>{s.market_analysis?.buy_score || 0} BUY</span> <span style={{ color: "#78716c" }}>vs</span> <span style={{ color: "#ef4444" }}>{s.market_analysis?.sell_score || 0} SELL</span></div>
            </div>
            
            <div style={{ display: "grid", gap: "6px" }}>
              {points.map((p, i) => (
                <div key={i} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", background: p.side === "BUY" ? "rgba(245,158,11,0.08)" : p.side === "SELL" ? "rgba(239,68,68,0.08)" : "rgba(167,139,250,0.08)", border: `1px solid ${p.side === "BUY" ? "rgba(245,158,11,0.25)" : p.side === "SELL" ? "rgba(239,68,68,0.25)" : "rgba(167,139,250,0.25)"}`, borderRadius: "8px", padding: "8px 10px" }}>
                  <div style={{ flex: 1 }}>
                    <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
                      <span style={{ fontSize: "10px", fontWeight: "800", color: p.side === "BUY" ? "#fbbf24" : p.side === "SELL" ? "#ef4444" : "#a78bfa" }}>{p.side === "BUY" ? "BUY" : p.side === "SELL" ? "SELL" : "NEUTRAL"} +{p.points}</span>
                      <span style={{ fontSize: "11px", fontWeight: "700", color: "#fff" }}>{p.name}</span>
                    </div>
                    <div style={{ fontSize: "10px", color: "#a8a29e", marginTop: "2px", lineHeight: "1.2" }}>{p.reason}</div>
                  </div>
                  <div style={{ fontSize: "12px", fontWeight: "900", color: p.side === "BUY" ? "#fbbf24" : p.side === "SELL" ? "#ef4444" : "#a78bfa" }}>+{p.points}</div>
                </div>
              ))}
            </div>

            <div style={{ marginTop: "10px", background: "#1c1917", borderRadius: "8px", padding: "8px", display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "8px", fontSize: "10px" }}>
              <div><span style={{ color: "#78716c" }}>Total BUY:</span> <span style={{ color: "#fbbf24", fontWeight: "800" }}>{s.market_analysis?.buy_score || 0} pts</span></div>
              <div><span style={{ color: "#78716c" }}>Total SELL:</span> <span style={{ color: "#ef4444", fontWeight: "800" }}>{s.market_analysis?.sell_score || 0} pts</span></div>
              <div><span style={{ color: "#78716c" }}>Diferencia:</span> <span style={{ color: Math.abs((s.market_analysis?.buy_score || 0) - (s.market_analysis?.sell_score || 0)) >= 2 ? "#22c55e" : "#f59e0b", fontWeight: "800" }}>{Math.abs((s.market_analysis?.buy_score || 0) - (s.market_analysis?.sell_score || 0))} pts {Math.abs((s.market_analysis?.buy_score || 0) - (s.market_analysis?.sell_score || 0)) >= 2 ? "✅ Señal" : "⏸️ Débil"}</span></div>
            </div>

            <div style={{ fontSize: "9px", color: "#57534e", marginTop: "8px", lineHeight: "1.4" }}>
              <b>TU SISTEMA:</b> +3 SMA10&gt;15&gt;30 fuerte, +3 ruptura alto 10m vela &gt;60%, +2 cerca resistencia 15m high_15, +2 racha 3 velas 10m alcistas, +1 vela fuerte, +1 NY 8-10AM EC, +2 3 velas 15-30m confirmadas. SELL es espejo. Se mantiene.
            </div>
          </div>

          {/* VELAS JAPONESAS */}
          {candles.length > 0 && (
            <div style={{ background: "#0c0a09", border: "1px solid #292524", borderRadius: "10px", padding: "10px", marginBottom: "12px" }}>
              <div style={{ fontSize: "10px", color: "#a8a29e", fontWeight: "700", marginBottom: "6px" }}>🕯️ VELAS JAPONESAS QUE INDICAN DIRECCIÓN</div>
              <div style={{ display: "grid", gap: "5px" }}>
                {candles.map((c, i) => (
                  <div key={i} style={{ display: "flex", justifyContent: "space-between", background: c.dir === "BUY" ? "rgba(245,158,11,0.08)" : "rgba(239,68,68,0.08)", borderRadius: "6px", padding: "6px 8px", fontSize: "10px" }}>
                    <div><span style={{ fontWeight: "800", color: c.dir === "BUY" ? "#fbbf24" : "#ef4444" }}>{c.name} {c.dir === "BUY" ? "↑" : "↓"} F{c.strength}</span> <span style={{ color: "#a8a29e" }}>{c.desc}</span></div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* 10-15-30 DATOS */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "8px", marginBottom: "12px" }}>
            <div style={{ background: "#0c0a09", border: "1px solid #292524", borderRadius: "10px", padding: "10px" }}>
              <div style={{ fontSize: "9px", color: "#a8a29e", fontWeight: "700" }}>📊 ALTOS/BAJOS 10-15-30 MIN</div>
              <div style={{ fontSize: "10px", marginTop: "6px", lineHeight: "1.6" }}>
                <div style={{ display: "flex", justifyContent: "space-between" }}><span style={{ color: "#78716c" }}>Alto 10m:</span><span>{s.market_analysis?.high_10?.toFixed(2)}</span></div>
                <div style={{ display: "flex", justifyContent: "space-between" }}><span style={{ color: "#78716c" }}>Bajo 10m:</span><span>{s.market_analysis?.low_10?.toFixed(2)}</span></div>
                <div style={{ display: "flex", justifyContent: "space-between" }}><span style={{ color: "#78716c" }}>Alto 15m:</span><span style={{ color: "#fbbf24", fontWeight: "700" }}>{s.market_analysis?.high_15?.toFixed(2)}</span></div>
                <div style={{ display: "flex", justifyContent: "space-between" }}><span style={{ color: "#78716c" }}>Bajo 15m:</span><span style={{ color: "#fbbf24", fontWeight: "700" }}>{s.market_analysis?.low_15?.toFixed(2)}</span></div>
                <div style={{ display: "flex", justifyContent: "space-between" }}><span style={{ color: "#78716c" }}>SMA10/15/30:</span><span style={{ fontSize: "9px" }}>{s.market_analysis?.sma10?.toFixed(1)}/{s.market_analysis?.sma15?.toFixed(1)}/{s.market_analysis?.sma30?.toFixed(1)}</span></div>
              </div>
            </div>
            <div style={{ background: "#0c0a09", border: "1px solid #292524", borderRadius: "10px", padding: "10px" }}>
              <div style={{ fontSize: "9px", color: "#a8a29e", fontWeight: "700" }}>🎯 SOPORTE / RESISTENCIA + VOL</div>
              <div style={{ fontSize: "10px", marginTop: "6px", lineHeight: "1.6" }}>
                <div style={{ display: "flex", justifyContent: "space-between" }}><span style={{ color: "#78716c" }}>Soporte:</span><span style={{ color: "#10b981", fontWeight: "700" }}>{s.support?.toFixed(2)}</span></div>
                <div style={{ display: "flex", justifyContent: "space-between" }}><span style={{ color: "#78716c" }}>Resistencia:</span><span style={{ color: "#ef4444", fontWeight: "700" }}>{s.resistance?.toFixed(2)}</span></div>
                <div style={{ display: "flex", justifyContent: "space-between" }}><span style={{ color: "#78716c" }}>Vol 10m:</span><span>{s.market_analysis?.volatility?.toFixed(2)} USD</span></div>
                <div style={{ fontSize: "9px", color: "#a8a29e", marginTop: "4px" }}>{s.flip_reason}</div>
              </div>
            </div>
          </div>

          <div style={{ background: "#0c0a09", borderRadius: "10px", padding: "10px", marginBottom: "12px", border: "1px solid #292524" }}>
            <div style={{ display: "flex", height: "8px", background: "#292524", borderRadius: "4px", overflow: "hidden" }}><div style={{ width: `${prob}%`, background: "linear-gradient(90deg, #f59e0b, #fbbf24)" }}></div></div>
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: "9px", color: "#a8a29e", marginTop: "6px" }}><span>Global: {s.win_rate}%</span><span style={{ color: "#fbbf24", fontWeight: "700" }}>{s.direction}: {s.win_rate_direction}%</span><span>BUY {s.win_rate_buy}% | SELL {s.win_rate_sell}%</span></div>
            <div style={{ fontSize: "9px", color: "#78716c", marginTop: "4px", display: "flex", justifyContent: "space-between" }}><span>TP1 $10: {s.probabilidad_nuevos_objetivos?.prob_tp1_10usd_10_15min}% 10-15m</span><span>TP2 {s.probabilidad_nuevos_objetivos?.prob_tp2_20usd_15min}% | TP3 {s.probabilidad_nuevos_objetivos?.prob_tp3_30usd_15min}%</span></div>
          </div>

          <div style={{ fontFamily: "monospace", fontSize: "12px", background: "#0c0a09", borderRadius: "12px", padding: "12px", border: "1px solid #44403c" }}>
            <div style={{ display: "flex", justifyContent: "space-between", padding: "4px 0", borderBottom: "1px solid #292524" }}><span style={{ color: "#a8a29e" }}>ENTRY ORO</span><span style={{ fontWeight: "900", color: "#fbbf24", fontSize: "14px" }}>{s.entry?.toFixed(2)}</span></div>
            <div style={{ display: "flex", justifyContent: "space-between", padding: "4px 0", color: "#f87171", marginTop: "4px" }}><span style={{ color: "#a8a29e" }}>SL (-$10) {isBuy ? "↓ ABAJO" : "↑ ARRIBA"}</span><span>{s.sl?.toFixed(2)}</span></div>
            <div style={{ fontSize: "9px", color: "#78716c", padding: "3px 6px", background: "rgba(239,68,68,0.05)", borderRadius: "4px" }}>{s.sl_explain}</div>
            <div style={{ display: "flex", justifyContent: "space-between", padding: "4px 0", color: "#fbbf24", marginTop: "4px" }}><span style={{ color: "#a8a29e" }}>TP1 (+$10) {isBuy ? "↑ ARRIBA" : "↓ ABAJO"}</span><span>{s.tp1?.toFixed(2)}</span></div>
            <div style={{ fontSize: "9px", color: "#78716c", padding: "3px 6px", background: "rgba(245,158,11,0.08)", borderRadius: "4px" }}>{s.tp_explain}</div>
            <div style={{ display: "flex", justifyContent: "space-between", padding: "3px 0", color: "#fbbf24" }}><span style={{ color: "#a8a29e" }}>TP2 (+$20)</span><span>{s.tp2?.toFixed(2)}</span></div>
            <div style={{ display: "flex", justifyContent: "space-between", padding: "3px 0", color: "#fde68a" }}><span style={{ color: "#a8a29e" }}>TP3 (+$30)</span><span>{s.tp3?.toFixed(2)}</span></div>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "8px", marginTop: "12px" }}>
            <button onClick={() => sendResult("SL")} style={{ background: "rgba(239,68,68,0.12)", border: "1px solid rgba(239,68,68,0.4)", color: "#f87171", borderRadius: "10px", padding: "10px", fontSize: "11px", fontWeight: "800", cursor: "pointer" }}>SL -$10</button>
            <button onClick={() => sendResult("TP1")} style={{ background: "rgba(245,158,11,0.18)", border: "1px solid #f59e0b", color: "#fbbf24", borderRadius: "10px", padding: "10px", fontSize: "11px", fontWeight: "800", cursor: "pointer" }}>TP1 +$10</button>
            <button onClick={() => sendResult("TP2")} style={{ background: "rgba(245,158,11,0.14)", border: "1px solid rgba(245,158,11,0.4)", color: "#fbbf24", borderRadius: "10px", padding: "10px", fontSize: "11px", fontWeight: "800", cursor: "pointer" }}>TP2 +$20</button>
            <button onClick={() => sendResult("TP3")} style={{ background: "linear-gradient(135deg, rgba(245,158,11,0.2), rgba(251,191,36,0.2))", border: "1px solid #f59e0b", color: "#fbbf24", borderRadius: "10px", padding: "10px", fontSize: "11px", fontWeight: "800", cursor: "pointer" }}>TP3 +$30</button>
          </div>
        </div>

        <div style={{ textAlign: "center", color: "#57534e", fontSize: "10px", marginTop: "14px" }}>FASE: Acumulacion → Pico tras acumulacion • Puntos 10-15-30 min + Velas japonesas • Alerta ENTRA / ESPERA</div>
      </div>
    </div>
  );
}
