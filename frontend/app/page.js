"use client";
import { useEffect, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL || "https://trading-app-jn5a.onrender.com";

function calcGoldTPSL(entry, direction) {
  const dist = 6.17;
  if (direction === "BUY") {
    return { sl: entry - dist, tp1: entry + dist, tp2: entry + dist*2, tp3: entry + dist*3, dist };
  } else {
    return { sl: entry + dist, tp1: entry - dist, tp2: entry - dist*2, tp3: entry - dist*3, dist };
  }
}

export default function Page() {
  const [signal, setSignal] = useState(null);
  const [loading, setLoading] = useState(true);
  const [timeEc, setTimeEc] = useState("");
  const [backendStatus, setBackendStatus] = useState("conectando...");

  const fetchData = async () => {
    try {
      const res = await fetch(`${API}/signals/live`, { cache: 'no-store' });
      if (!res.ok) throw new Error(`Backend ${res.status}`);
      const data = await res.json();
      let sig = Array.isArray(data) && data.length > 0 ? data[0] : data.symbol ? data : data.signals?.[0];
      if (sig && sig.symbol?.includes("XAU")) {
        setSignal(sig);
        setBackendStatus("conectado - FASES + VELAS");
      } else throw new Error("vacio");
    } catch (e) {
      setBackendStatus("demo - FASES + VELAS oro");
      const demoPrice = 4025 + Math.random() * 6;
      const demo = calcGoldTPSL(demoPrice, "BUY");
      setSignal({
        symbol: "XAUUSD", direction: "BUY", entry: demoPrice,
        sl: demo.sl, tp1: demo.tp1, tp2: demo.tp2, tp3: demo.tp3, sl_distance: demo.dist, tp1_distance: demo.dist,
        sl_explain: `SL ${demo.sl.toFixed(2)} ABAJO`, tp_explain: `TP1 ${demo.tp1.toFixed(2)} ARRIBA COMPRA`,
        probability: 84, confidence: 82, win_rate: 78.5, win_rate_direction: 82.3, win_rate_buy: 81, win_rate_sell: 72,
        is_optimal_hour: true, phase: "EXPANSION_ALCISTA", phase_desc: "🔥 PICO COMPRA tras acumulacion - ruptura 4028.50 con vela fuerte 2.1 USD",
        candle_patterns: [
          { name: "BULLISH_ENGULFING", direction: "BUY", strength: 3, desc: "Envolvente alcista - fuerte compra tras bajada" },
          { name: "HAMMER", direction: "BUY", strength: 2, desc: "Martillo alcista - rechazo de bajos" }
        ],
        market_analysis: {
          trend: "BULLISH", up_streak: 3, down_streak: 0, high_10: demoPrice + 4.5, low_10: demoPrice - 3.2, high_15: demoPrice + 7.1, low_15: demoPrice - 5.5,
          high_30: demoPrice + 9.2, low_30: demoPrice - 7.8, sma10: demoPrice - 1.5, sma15: demoPrice - 2.8, sma30: demoPrice - 3.5,
          support: demoPrice - 5.2, resistance: demoPrice + 6.8, buy_score: 8, sell_score: 2, volatility: 4.8,
          phase: "EXPANSION_ALCISTA", phase_desc: "🔥 PICO COMPRA tras acumulacion - ruptura 4028.50 con vela fuerte 2.1 USD",
          phase_info: { phase: "EXPANSION_ALCISTA", price_band_6: 2.8, avg_range_6: 1.2, avg_range_3: 3.8, up_streak: 3, down_streak: 0, sma_slope: 1.2 },
          candle_patterns: [
            { name: "BULLISH_ENGULFING", direction: "BUY", strength: 3, desc: "Envolvente alcista" },
            { name: "HAMMER", direction: "BUY", strength: 2, desc: "Martillo alcista" }
          ]
        },
        probabilidad_nuevos_objetivos: { prob_tp1_10usd_10_15min: 76, prob_tp2_20usd_15min: 54, prob_tp3_30usd_15min: 38 },
        reason: "🔥 PICO COMPRA tras acumulacion 2.8 USD rango + BULLISH_ENGULFING + HAMMER + SMA alcista + NY 8-10AM",
        flip_reason: "EXPANSION_ALCISTA tras acumulacion - cambio rapido 84%",
        support: demoPrice - 5.2, resistance: demoPrice + 6.8
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

  const sendResult = async (result) => {
    try {
      await fetch(`${API}/trades/result`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ result, symbol: "XAUUSD" }) });
      alert(`✅ ORO ${result} - aprende fase + vela`);
      fetchData();
    } catch {}
  };

  if (loading) return <div style={{ minHeight: "100vh", background: "#0a0a0a", color: "white", display: "flex", alignItems: "center", justifyContent: "center" }}><div>ORO FASES + VELAS - Analizando...</div></div>;
  const s = signal; if (!s) return null;
  const isBuy = s.direction === "BUY";
  const prob = s.probability || 78;
  const phase = s.phase || s.market_analysis?.phase || "RANGO";
  const phaseDesc = s.phase_desc || s.market_analysis?.phase_desc || "";
  const candles = s.candle_patterns || s.market_analysis?.candle_patterns || [];
  const phaseInfo = s.market_analysis?.phase_info || {};

  const getPhaseColor = (ph) => {
    if (ph.includes("EXPANSION_ALCISTA") || ph.includes("TENDENCIA_ALCISTA")) return "#fbbf24";
    if (ph.includes("EXPANSION_BAJISTA") || ph.includes("TENDENCIA_BAJISTA")) return "#ef4444";
    if (ph.includes("ACUMULACION")) return "#a78bfa";
    if (ph.includes("AGOTAMIENTO") || ph.includes("DISTRIBUCION")) return "#fb923c";
    return "#a1a1aa";
  };
  const getPhaseIcon = (ph) => {
    if (ph.includes("ACUMULACION")) return "⏸️";
    if (ph.includes("EXPANSION_ALCISTA")) return "🚀";
    if (ph.includes("EXPANSION_BAJISTA")) return "💥";
    if (ph.includes("TENDENCIA_ALCISTA")) return "📈";
    if (ph.includes("TENDENCIA_BAJISTA")) return "📉";
    if (ph.includes("AGOTAMIENTO")) return "⚠️";
    if (ph.includes("DISTRIBUCION")) return "🔄";
    return "➡️";
  };

  return (
    <div style={{ minHeight: "100vh", background: "#0a0a0a", color: "white", padding: "16px", fontFamily: "system-ui" }}>
      <div style={{ maxWidth: "900px", margin: "0 auto" }}>
        <div style={{ display: "flex", justifyContent: "space-between", flexWrap: "wrap", gap: "16px", borderBottom: "2px solid #f59e0b", paddingBottom: "16px", marginBottom: "20px" }}>
          <div>
            <h1 style={{ fontSize: "32px", fontWeight: "900", margin: 0, color: "#fbbf24" }}>EDGEALERT ORO FASES</h1>
            <p style={{ color: "#a1a1aa", fontSize: "12px", marginTop: "4px" }}>Solo XAUUSD • Fases: Acumulacion → Picos → Velas Japonesas • 6.17 USD = $10</p>
            <p style={{ fontSize: "11px", color: backendStatus.includes("conectado") ? "#10b981" : "#f59e0b" }}>{backendStatus}</p>
          </div>
          <div style={{ background: "#1c1917", border: "1px solid #44403c", borderRadius: "12px", padding: "12px", minWidth: "200px" }}>
            <div style={{ color: "#a8a29e", fontSize: "10px" }}>HORA ECUADOR</div>
            <div style={{ fontFamily: "monospace", fontSize: "12px", marginTop: "4px" }}>{timeEc}</div>
            <div style={{ color: "#fbbf24", fontSize: "10px", marginTop: "6px", fontWeight: "700" }}>8-10 AM = NY OPEN ORO</div>
          </div>
        </div>

        <div style={{ background: "linear-gradient(135deg, #1c1917 0%, #18181b 100%)", border: "2px solid #f59e0b", borderRadius: "20px", padding: "20px", position: "relative", overflow: "hidden" }}>
          <div style={{ position: "absolute", top: 0, right: 0, background: prob >= 78 ? "#fbbf24" : prob >= 65 ? "#f59e0b" : "#a1a1aa", color: "#000", padding: "8px 18px", borderRadius: "0 18px 0 16px", fontWeight: "900", fontSize: "16px" }}>
            {prob}% {phase.includes("EXPANSION") ? "🔥 PICO" : "ORO"}
          </div>

          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: "8px", marginBottom: "8px" }}>
            <div style={{ display: "flex", gap: "10px", alignItems: "center" }}>
              <span style={{ fontSize: "24px", fontWeight: "900", color: "#fbbf24" }}>{s.symbol}</span>
              <span style={{ fontSize: "11px", background: getPhaseColor(phase), color: "#000", padding: "4px 10px", borderRadius: "20px", fontWeight: "800" }}>{getPhaseIcon(phase)} {phase}</span>
            </div>
            <span style={{ background: isBuy ? "rgba(245,158,11,0.2)" : "rgba(239,68,68,0.15)", color: isBuy ? "#fbbf24" : "#ef4444", border: `1px solid ${isBuy ? "#f59e0b" : "#ef4444"}`, padding: "6px 14px", borderRadius: "20px", fontSize: "12px", fontWeight: "900" }}>{s.direction} {isBuy ? "↑ COMPRA" : "↓ VENTA"}</span>
          </div>

          {/* FASE DEL MERCADO - LO NUEVO */}
          <div style={{ background: "#0c0a09", border: `1px solid ${getPhaseColor(phase)}`, borderRadius: "12px", padding: "12px", marginBottom: "12px" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "6px" }}>
              <div style={{ fontSize: "11px", color: "#a8a29e", fontWeight: "700" }}>📊 FASE DEL MERCADO ORO (hoy predecible)</div>
              <div style={{ fontSize: "10px", color: getPhaseColor(phase), fontWeight: "700" }}>{phaseInfo.up_streak || 0}↑ {phaseInfo.down_streak || 0}↓ • Banda {phaseInfo.price_band_6?.toFixed(1) || 0} USD</div>
            </div>
            <div style={{ fontSize: "12px", color: "#fff", lineHeight: "1.4", fontWeight: "600" }}>{phaseDesc}</div>
            {phaseInfo.avg_range_6 !== undefined && (
              <div style={{ fontSize: "10px", color: "#78716c", marginTop: "6px", display: "flex", gap: "12px" }}>
                <span>Rango 6 velas: {phaseInfo.avg_range_6?.toFixed(2)} USD</span>
                <span>Ahora: {phaseInfo.avg_range_3?.toFixed(2)} USD {phaseInfo.avg_range_3 > phaseInfo.avg_range_6 ? "🔥 EXPANSION" : phaseInfo.avg_range_3 < phaseInfo.avg_range_6*0.7 ? "⏸️ CONTRACCION" : ""}</span>
                <span>SMA slope: {phaseInfo.sma_slope?.toFixed(2)}</span>
              </div>
            )}
            <div style={{ fontSize: "10px", color: "#a78bfa", marginTop: "6px" }}>
              {phase === "ACUMULACION" ? "⏸️ NO operar - esperar pico tras acumulacion (como hoy)" : phase.includes("EXPANSION") ? "✅ SEÑAL LIMPIA - pico tras acumulacion + vela fuerte" : phase.includes("TENDENCIA") ? "📈 Tendencia clara - seguir" : phase.includes("AGOTAMIENTO") ? "⚠️ Agotamiento - buscar reversal con vela opuesta" : ""}
            </div>
          </div>

          {/* VELAS JAPONESAS BASE */}
          {candles.length > 0 && (
            <div style={{ background: "#0c0a09", border: "1px solid #292524", borderRadius: "12px", padding: "12px", marginBottom: "12px" }}>
              <div style={{ fontSize: "11px", color: "#a8a29e", fontWeight: "700", marginBottom: "8px" }}>🕯️ VELAS JAPONESAS QUE INDICAN DIRECCION (base)</div>
              <div style={{ display: "grid", gap: "6px" }}>
                {candles.map((c, i) => (
                  <div key={i} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", background: c.direction === "BUY" ? "rgba(245,158,11,0.08)" : "rgba(239,68,68,0.08)", border: `1px solid ${c.direction === "BUY" ? "rgba(245,158,11,0.3)" : "rgba(239,68,68,0.3)"}`, borderRadius: "8px", padding: "8px 10px" }}>
                    <div>
                      <span style={{ fontSize: "11px", fontWeight: "800", color: c.direction === "BUY" ? "#fbbf24" : "#ef4444" }}>{c.name} {c.direction === "BUY" ? "↑" : "↓"}</span>
                      <span style={{ fontSize: "10px", color: "#a8a29e", marginLeft: "8px" }}>Fuerza {c.strength}/3</span>
                      <div style={{ fontSize: "10px", color: "#d6d3d1", marginTop: "2px" }}>{c.desc}</div>
                    </div>
                    <div style={{ fontSize: "16px" }}>{c.direction === "BUY" ? "🟢" : "🔴"}</div>
                  </div>
                ))}
              </div>
              <div style={{ fontSize: "10px", color: "#78716c", marginTop: "8px" }}>Señales limpias solo cuando fase = EXPANSION + vela fuerza ≥2 (como picos de hoy tras acumulacion)</div>
            </div>
          )}

          {candles.length === 0 && (
            <div style={{ background: "#0c0a09", border: "1px solid #292524", borderRadius: "10px", padding: "10px", marginBottom: "12px", fontSize: "11px", color: "#78716c" }}>
              ⏳ Sin patron vela claro ahora - esperando envolvente, martillo, pin bar o estrella para señal limpia
            </div>
          )}

          <div style={{ fontSize: "11px", color: "#d6d3d1", marginBottom: "10px", background: "#0c0a09", padding: "8px", borderRadius: "8px", border: "1px solid #292524" }}>
            {s.reason}
            {s.is_optimal_hour && <span style={{ color: "#fbbf24", marginLeft: "8px", fontWeight: "800" }}>🔥 NY 8-10AM</span>}
          </div>

          {s.market_analysis && (
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "10px", marginBottom: "12px" }}>
              <div style={{ background: "#0c0a09", border: "1px solid #292524", borderRadius: "10px", padding: "10px" }}>
                <div style={{ fontSize: "10px", color: "#a8a29e", fontWeight: "700" }}>📊 10-15-30 MIN</div>
                <div style={{ fontSize: "11px", display: "flex", justifyContent: "space-between", marginTop: "4px" }}><span style={{ color: "#78716c" }}>Alto 10m:</span><span>{s.market_analysis.high_10?.toFixed(2)}</span></div>
                <div style={{ fontSize: "11px", display: "flex", justifyContent: "space-between" }}><span style={{ color: "#78716c" }}>Bajo 10m:</span><span>{s.market_analysis.low_10?.toFixed(2)}</span></div>
                <div style={{ fontSize: "11px", display: "flex", justifyContent: "space-between" }}><span style={{ color: "#78716c" }}>Alto 15m:</span><span style={{ color: "#fbbf24", fontWeight: "700" }}>{s.market_analysis.high_15?.toFixed(2)}</span></div>
                <div style={{ fontSize: "11px", display: "flex", justifyContent: "space-between" }}><span style={{ color: "#78716c" }}>Bajo 15m:</span><span style={{ color: "#fbbf24", fontWeight: "700" }}>{s.market_analysis.low_15?.toFixed(2)}</span></div>
                <div style={{ fontSize: "10px", color: "#78716c", marginTop: "6px" }}>SMA10/15/30: {s.market_analysis.sma10?.toFixed(1)} / {s.market_analysis.sma15?.toFixed(1)} / {s.market_analysis.sma30?.toFixed(1)}</div>
              </div>
              <div style={{ background: "#0c0a09", border: "1px solid #292524", borderRadius: "10px", padding: "10px" }}>
                <div style={{ fontSize: "10px", color: "#a8a29e", fontWeight: "700" }}>🎯 SOPORTE/RESISTENCIA</div>
                <div style={{ fontSize: "11px", display: "flex", justifyContent: "space-between", marginTop: "4px" }}><span style={{ color: "#78716c" }}>Soporte:</span><span style={{ color: "#10b981", fontWeight: "700" }}>{s.support?.toFixed(2)}</span></div>
                <div style={{ fontSize: "11px", display: "flex", justifyContent: "space-between" }}><span style={{ color: "#78716c" }}>Resistencia:</span><span style={{ color: "#ef4444", fontWeight: "700" }}>{s.resistance?.toFixed(2)}</span></div>
                <div style={{ fontSize: "10px", color: "#78716c", marginTop: "6px" }}>Vol: {s.market_analysis.volatility?.toFixed(2)} USD • {s.market_analysis.buy_score}B/{s.market_analysis.sell_score}S</div>
                <div style={{ fontSize: "10px", color: "#a8a29e", marginTop: "4px" }}>{s.flip_reason}</div>
              </div>
            </div>
          )}

          <div style={{ background: "#0c0a09", borderRadius: "10px", padding: "10px", marginBottom: "12px", border: "1px solid #292524" }}>
            <div style={{ display: "flex", height: "8px", background: "#292524", borderRadius: "4px", overflow: "hidden" }}><div style={{ width: `${prob}%`, background: `linear-gradient(90deg, #f59e0b, #fbbf24)` }}></div></div>
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: "10px", color: "#a8a29e", marginTop: "6px" }}>
              <span>Global: {s.win_rate}%</span><span style={{ color: "#fbbf24", fontWeight: "700" }}>{s.direction}: {s.win_rate_direction}%</span><span>BUY {s.win_rate_buy}% | SELL {s.win_rate_sell}%</span>
            </div>
            <div style={{ fontSize: "10px", color: "#78716c", marginTop: "4px", display: "flex", justifyContent: "space-between" }}>
              <span>TP1 $10: {s.probabilidad_nuevos_objetivos?.prob_tp1_10usd_10_15min}% en 10-15m</span><span>TP2 {s.probabilidad_nuevos_objetivos?.prob_tp2_20usd_15min}% | TP3 {s.probabilidad_nuevos_objetivos?.prob_tp3_30usd_15min}%</span>
            </div>
          </div>

          <div style={{ fontFamily: "monospace", fontSize: "13px", background: "#0c0a09", borderRadius: "12px", padding: "12px", border: "1px solid #44403c" }}>
            <div style={{ display: "flex", justifyContent: "space-between", padding: "4px 0", borderBottom: "1px solid #292524" }}><span style={{ color: "#a8a29e" }}>ENTRY ORO</span><span style={{ fontWeight: "900", color: "#fbbf24", fontSize: "15px" }}>{s.entry?.toFixed(2)}</span></div>
            <div style={{ display: "flex", justifyContent: "space-between", padding: "4px 0", color: "#f87171", marginTop: "4px" }}><span style={{ color: "#a8a29e" }}>SL (-$10) {isBuy ? "↓ ABAJO" : "↑ ARRIBA"}</span><span>{s.sl?.toFixed(2)}</span></div>
            <div style={{ fontSize: "10px", color: "#78716c", padding: "4px 6px", background: "rgba(239,68,68,0.05)", borderRadius: "4px" }}>{s.sl_explain}</div>
            <div style={{ display: "flex", justifyContent: "space-between", padding: "4px 0", color: "#fbbf24", marginTop: "4px" }}><span style={{ color: "#a8a29e" }}>TP1 (+$10) {isBuy ? "↑ ARRIBA" : "↓ ABAJO"}</span><span>{s.tp1?.toFixed(2)}</span></div>
            <div style={{ fontSize: "10px", color: "#78716c", padding: "4px 6px", background: "rgba(245,158,11,0.08)", borderRadius: "4px" }}>{s.tp_explain}</div>
            <div style={{ display: "flex", justifyContent: "space-between", padding: "4px 0", color: "#fbbf24" }}><span style={{ color: "#a8a29e" }}>TP2 (+$20)</span><span>{s.tp2?.toFixed(2)}</span></div>
            <div style={{ display: "flex", justifyContent: "space-between", padding: "4px 0", color: "#fde68a" }}><span style={{ color: "#a8a29e" }}>TP3 (+$30)</span><span>{s.tp3?.toFixed(2)}</span></div>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "10px", marginTop: "14px" }}>
            <button onClick={() => sendResult("SL")} style={{ background: "rgba(239,68,68,0.12)", border: "1px solid rgba(239,68,68,0.4)", color: "#f87171", borderRadius: "10px", padding: "10px", fontSize: "12px", fontWeight: "800", cursor: "pointer" }}>SL -$10</button>
            <button onClick={() => sendResult("TP1")} style={{ background: "rgba(245,158,11,0.18)", border: "1px solid #f59e0b", color: "#fbbf24", borderRadius: "10px", padding: "10px", fontSize: "12px", fontWeight: "800", cursor: "pointer" }}>TP1 +$10</button>
            <button onClick={() => sendResult("TP2")} style={{ background: "rgba(245,158,11,0.14)", border: "1px solid rgba(245,158,11,0.4)", color: "#fbbf24", borderRadius: "10px", padding: "10px", fontSize: "12px", fontWeight: "800", cursor: "pointer" }}>TP2 +$20</button>
            <button onClick={() => sendResult("TP3")} style={{ background: "linear-gradient(135deg, rgba(245,158,11,0.2), rgba(251,191,36,0.2))", border: "1px solid #f59e0b", color: "#fbbf24", borderRadius: "10px", padding: "10px", fontSize: "12px", fontWeight: "800", cursor: "pointer" }}>TP3 +$30</button>
          </div>
        </div>

        <div style={{ marginTop: "16px", padding: "12px", background: "#1c1917", border: "1px solid #44403c", borderRadius: "12px" }}>
          <h3 style={{ fontSize: "12px", fontWeight: "800", color: "#fbbf24", marginBottom: "6px" }}>🥇 NUEVO: FASES + VELAS JAPONESAS - Señales Limpias</h3>
          <ul style={{ fontSize: "11px", color: "#d6d3d1", margin: 0, paddingLeft: "14px", lineHeight: "1.6" }}>
            <li><b style={{ color: "#a78bfa" }}>Fase ACUMULACION:</b> Rango &lt;4 USD, volatilidad &lt;2 USD, 6 velas en 3-4 USD → NO operar (como hoy antes del pico)</li>
            <li><b style={{ color: "#fbbf24" }}>Fase EXPANSION:</b> Tras acumulacion, ruptura con vela fuerte &gt;60% cuerpo + rango x1.5 → PICO COMPRA/VENTA limpio → señal 78-84%</li>
            <li><b style={{ color: "#10b981" }}>Base velas alcistas:</b> BULLISH_ENGULFING, HAMMER, PIN_BAR_BULL, MORNING_STAR, MARUBOZU_BULL → indican subida</li>
            <li><b style={{ color: "#ef4444" }}>Base velas bajistas:</b> BEARISH_ENGULFING, SHOOTING_STAR, PIN_BAR_BEAR, EVENING_STAR → indican bajada</li>
            <li><b style={{ color: "#fbbf24" }}>Señal limpia:</b> Solo da BUY fuerte si EXPANSION_ALCISTA + vela alcista fuerza ≥2. Antes era random, ahora espera patron real.</li>
          </ul>
        </div>

        <div style={{ textAlign: "center", color: "#57534e", fontSize: "11px", marginTop: "16px" }}>Fases mercado oro: Acumulacion → Picos • Velas japonesas base • Señales limpias solo con confirmacion</div>
      </div>
    </div>
  );
}
