"use client";
import { useEffect, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL || "https://trading-app-jn5a.onrender.com";

function calcGoldTPSL(entry, direction) {
  const dist = 6.17; // 10 USD con tu lotaje 1.62
  if (direction === "BUY") {
    return {
      sl: entry - dist,
      tp1: entry + dist,
      tp2: entry + dist*2,
      tp3: entry + dist*3,
      dist
    };
  } else {
    return {
      sl: entry + dist,
      tp1: entry - dist,
      tp2: entry - dist*2,
      tp3: entry - dist*3,
      dist
    };
  }
}

export default function Page() {
  const [signal, setSignal] = useState(null);
  const [loading, setLoading] = useState(true);
  const [timeEc, setTimeEc] = useState("");
  const [backendStatus, setBackendStatus] = useState("conectando...");
  const [goldStats, setGoldStats] = useState(null);

  const fetchData = async () => {
    try {
      const res = await fetch(`${API}/signals/live`, { cache: 'no-store' });
      if (!res.ok) throw new Error(`Backend ${res.status}`);
      const data = await res.json();
      let sig = null;
      if (Array.isArray(data) && data.length > 0) sig = data[0];
      else if (data.symbol) sig = data;
      else if (data.signals && data.signals.length > 0) sig = data.signals[0];
      
      if (sig && sig.symbol && sig.symbol.includes("XAU")) {
        setSignal(sig);
        setBackendStatus("conectado - ORO PURO potenciado");
        // Fetch stats oro
        try {
          const res2 = await fetch(`${API}/gold/learning`, { cache: 'no-store' });
          if (res2.ok) {
            const stats = await res2.json();
            setGoldStats(stats);
          }
        } catch {}
      } else throw new Error("vacio");
    } catch (e) {
      setBackendStatus("demo - ORO PURO - Render durmiendo 50s");
      const demoPrice = 4025 + Math.random() * 8;
      const demo = calcGoldTPSL(demoPrice, "BUY");
      setSignal({
        symbol: "XAUUSD",
        direction: "BUY",
        entry: parseFloat(demoPrice.toFixed(2)),
        sl: parseFloat(demo.sl.toFixed(2)),
        tp1: parseFloat(demo.tp1.toFixed(2)),
        tp2: parseFloat(demo.tp2.toFixed(2)),
        tp3: parseFloat(demo.tp3.toFixed(2)),
        sl_distance: demo.dist,
        tp1_distance: demo.dist,
        sl_explain: `SL ${demo.sl.toFixed(2)} ABAJO de ENTRY (si baja ${demo.dist} USD pierdes $10)`,
        tp_explain: `TP1 ${demo.tp1.toFixed(2)} ARRIBA de ENTRY (si sube ${demo.dist} USD ganas $10) - COMPRA ORO`,
        probability: 84,
        confidence: 86,
        win_rate: 78.5,
        win_rate_direction: 82.3,
        win_rate_buy: 81.5,
        win_rate_sell: 72.1,
        is_optimal_hour: true,
        ny_session: true,
        pattern: "NY_OPEN + SMA_BULL + BREAK_HIGH_10",
        support: demoPrice - 5.2,
        resistance: demoPrice + 6.8,
        market_analysis: {
          trend: "BULLISH",
          up_streak: 3,
          down_streak: 0,
          high_10: demoPrice + 4.5,
          low_10: demoPrice - 3.2,
          high_15: demoPrice + 7.1,
          low_15: demoPrice - 5.5,
          high_30: demoPrice + 9.2,
          low_30: demoPrice - 7.8,
          sma10: demoPrice - 1.5,
          sma15: demoPrice - 2.8,
          sma30: demoPrice - 3.5,
          support: demoPrice - 5.2,
          resistance: demoPrice + 6.8,
          buy_score: 7,
          sell_score: 2,
          volatility: 4.8,
          ny_session: true,
          pattern: "NY_OPEN"
        },
        probabilidad_nuevos_objetivos: { prob_tp1_10usd_10_15min: 76, prob_tp2_20usd_15min: 54, prob_tp3_30usd_15min: 38 },
        reason: "🔥 ORO: 3 velas 10min alcistas + Precio > SMA10(4023.50)>SMA15>SMA30 + RUPTURA ALTO 10min 4029.50 + SESION NY 8-10AM EC alta volatilidad oro",
        flip_reason: "Misma dirección oro - continua (analisis 10-15-30 min evita flip-flop)",
        timestamp: new Date().toISOString()
      });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
    const id = setInterval(fetchData, 30000);
    const tId = setInterval(() => {
      const now = new Date().toLocaleString("es-EC", {
        timeZone: "America/Guayaquil",
        hour: "2-digit", minute: "2-digit", second: "2-digit",
        weekday: "long", day: "2-digit", month: "short", year: "numeric"
      });
      setTimeEc(now);
    }, 1000);
    return () => { clearInterval(id); clearInterval(tId); };
  }, []);

  const sendResult = async (result) => {
    try {
      await fetch(`${API}/trades/result`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ result, symbol: "XAUUSD" })
      });
      alert(`✅ Aprendizaje ORO: XAUUSD -> ${result} (aprende como opera el oro)`);
      fetchData();
    } catch {}
  };

  const getProbColor = (p) => p >= 82 ? "#f59e0b" : p >= 70 ? "#10b981" : "#f59e0b"; // oro dorado

  if (loading) {
    return (
      <div style={{ minHeight: "100vh", background: "#0a0a0a", color: "white", display: "flex", alignItems: "center", justifyContent: "center", fontFamily: "system-ui" }}>
        <div style={{ textAlign: "center" }}>
          <div style={{ fontSize: "24px", fontWeight: "900" }}>ORO PURO</div>
          <div style={{ color: "#a1a1aa", marginTop: "8px" }}>Analizando XAUUSD potenciado 10-15-30 min...</div>
        </div>
      </div>
    );
  }

  const s = signal;
  if (!s) return null;
  const isBuy = s.direction === "BUY";
  const prob = s.probability || 78;

  return (
    <div style={{ minHeight: "100vh", background: "#0a0a0a", color: "white", padding: "16px", fontFamily: "system-ui, -apple-system, sans-serif" }}>
      <div style={{ maxWidth: "900px", margin: "0 auto" }}>
        {/* HEADER ORO */}
        <div style={{ display: "flex", justifyContent: "space-between", flexWrap: "wrap", gap: "16px", borderBottom: "2px solid #f59e0b", paddingBottom: "16px", marginBottom: "20px" }}>
          <div>
            <h1 style={{ fontSize: "34px", fontWeight: "900", margin: 0, letterSpacing: "-1px", color: "#fbbf24" }}>EDGEALERT ORO PURO</h1>
            <p style={{ color: "#a1a1aa", fontSize: "13px", marginTop: "6px" }}>Solo XAUUSD • Analisis 10-15-30 min con altos/bajos • 6.17 USD = $10 • Sin BTC • Sin Telegram</p>
            <p style={{ fontSize: "11px", marginTop: "4px", color: backendStatus.includes("conectado") ? "#10b981" : "#f59e0b" }}>Backend: {backendStatus}</p>
          </div>
          <div style={{ background: "#1c1917", border: "1px solid #44403c", borderRadius: "12px", padding: "12px 16px", minWidth: "240px" }}>
            <div style={{ color: "#a8a29e", fontSize: "10px", letterSpacing: "1px", textTransform: "uppercase" }}>HORA ECUADOR - ORO NY OPEN</div>
            <div style={{ fontFamily: "monospace", fontSize: "13px", marginTop: "4px", fontWeight: "600" }}>{timeEc}</div>
            <div style={{ color: "#fbbf24", fontSize: "11px", marginTop: "6px", fontWeight: "700" }}>🔥 8-10 AM EC = NY OPEN ORO</div>
            <div style={{ color: "#10b981", fontSize: "10px", marginTop: "2px" }}>Mejor volatilidad oro</div>
          </div>
        </div>

        {/* SEÑAL ORO POTENCIADA */}
        <div style={{ background: "linear-gradient(135deg, #1c1917 0%, #18181b 100%)", border: "2px solid #f59e0b", borderRadius: "20px", padding: "24px", position: "relative", overflow: "hidden", boxShadow: "0 0 30px rgba(245, 158, 11, 0.15)" }}>
          <div style={{ position: "absolute", top: 0, right: 0, background: getProbColor(prob), color: "#000", padding: "10px 20px", borderRadius: "0 18px 0 16px", fontWeight: "900", fontSize: "18px", letterSpacing: "0.5px" }}>
            {prob}% ORO
          </div>

          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: "10px", marginBottom: "8px" }}>
            <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
              <span style={{ fontSize: "28px", fontWeight: "900", color: "#fbbf24" }}>{s.symbol}</span>
              <span style={{ fontSize: "12px", color: "#a8a29e", background: "#292524", padding: "4px 8px", borderRadius: "6px" }}>SOLO ORO</span>
            </div>
            <span style={{
              background: isBuy ? "rgba(245, 158, 11, 0.2)" : "rgba(239, 68, 68, 0.15)",
              color: isBuy ? "#fbbf24" : "#ef4444",
              border: `1px solid ${isBuy ? "rgba(245, 158, 11, 0.4)" : "rgba(239, 68, 68, 0.3)"}`,
              padding: "8px 16px", borderRadius: "24px", fontSize: "13px", fontWeight: "900"
            }}>
              {s.direction} {isBuy ? "↑ COMPRA ORO" : "↓ VENTA ORO"}
            </span>
          </div>

          <div style={{ fontSize: "12px", color: "#d6d3d1", marginBottom: "12px", lineHeight: "1.5", background: "#0c0a09", padding: "10px", borderRadius: "8px", border: "1px solid #292524" }}>
            {s.reason}
            {s.is_optimal_hour && <span style={{ color: "#fbbf24", marginLeft: "8px", fontWeight: "800" }}>🔥 NY OPEN 8-10AM OPTIMA ORO</span>}
          </div>

          {/* ANALISIS ORO POTENCIADO */}
          {s.market_analysis && (
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "10px", marginBottom: "14px" }}>
              <div style={{ background: "#0c0a09", border: "1px solid #292524", borderRadius: "10px", padding: "12px" }}>
                <div style={{ fontSize: "10px", color: "#a8a29e", marginBottom: "6px", fontWeight: "700" }}>📊 ANALISIS 10-15-30 MIN ORO</div>
                <div style={{ fontSize: "11px", display: "flex", justifyContent: "space-between", marginBottom: "3px" }}>
                  <span style={{ color: "#78716c" }}>Tendencia:</span>
                  <b style={{ color: s.market_analysis.trend === "BULLISH" ? "#fbbf24" : s.market_analysis.trend === "BEARISH" ? "#ef4444" : "#fff" }}>{s.market_analysis.trend} {s.market_analysis.pattern}</b>
                </div>
                <div style={{ fontSize: "11px", display: "flex", justifyContent: "space-between", marginBottom: "3px" }}>
                  <span style={{ color: "#78716c" }}>Alto 10m:</span><span style={{ color: "#fff" }}>{s.market_analysis.high_10?.toFixed(2)}</span>
                </div>
                <div style={{ fontSize: "11px", display: "flex", justifyContent: "space-between", marginBottom: "3px" }}>
                  <span style={{ color: "#78716c" }}>Bajo 10m:</span><span style={{ color: "#fff" }}>{s.market_analysis.low_10?.toFixed(2)}</span>
                </div>
                <div style={{ fontSize: "11px", display: "flex", justifyContent: "space-between" }}>
                  <span style={{ color: "#78716c" }}>Alto 15m:</span><span style={{ color: "#fbbf24", fontWeight: "700" }}>{s.market_analysis.high_15?.toFixed(2)}</span>
                </div>
                <div style={{ fontSize: "11px", display: "flex", justifyContent: "space-between" }}>
                  <span style={{ color: "#78716c" }}>Bajo 15m:</span><span style={{ color: "#fbbf24", fontWeight: "700" }}>{s.market_analysis.low_15?.toFixed(2)}</span>
                </div>
              </div>
              <div style={{ background: "#0c0a09", border: "1px solid #292524", borderRadius: "10px", padding: "12px" }}>
                <div style={{ fontSize: "10px", color: "#a8a29e", marginBottom: "6px", fontWeight: "700" }}>🎯 SOPORTES/RESISTENCIAS ORO</div>
                <div style={{ fontSize: "11px", display: "flex", justifyContent: "space-between", marginBottom: "3px" }}>
                  <span style={{ color: "#78716c" }}>Soporte:</span><span style={{ color: "#10b981", fontWeight: "700" }}>{s.support?.toFixed(2) || s.market_analysis.support?.toFixed(2)}</span>
                </div>
                <div style={{ fontSize: "11px", display: "flex", justifyContent: "space-between", marginBottom: "3px" }}>
                  <span style={{ color: "#78716c" }}>Resistencia:</span><span style={{ color: "#ef4444", fontWeight: "700" }}>{s.resistance?.toFixed(2) || s.market_analysis.resistance?.toFixed(2)}</span>
                </div>
                <div style={{ fontSize: "11px", display: "flex", justifyContent: "space-between", marginBottom: "3px" }}>
                  <span style={{ color: "#78716c" }}>SMA10/15/30:</span>
                </div>
                <div style={{ fontSize: "10px", color: "#d6d3d1" }}>
                  {s.market_analysis.sma10?.toFixed(2)} / {s.market_analysis.sma15?.toFixed(2)} / {s.market_analysis.sma30?.toFixed(2)}
                </div>
                <div style={{ fontSize: "10px", color: "#78716c", marginTop: "6px" }}>
                  Vol 10m: {s.market_analysis.volatility?.toFixed(2)} USD • Score: {s.market_analysis.buy_score}B/{s.market_analysis.sell_score}S
                </div>
                <div style={{ fontSize: "10px", color: "#a8a29e", marginTop: "4px" }}>{s.flip_reason}</div>
              </div>
            </div>
          )}

          {/* PROBABILIDAD ORO */}
          <div style={{ background: "#0c0a09", borderRadius: "10px", padding: "12px", marginBottom: "14px", border: "1px solid #292524" }}>
            <div style={{ display: "flex", justifyContent: "space-between", height: "8px", background: "#292524", borderRadius: "4px", overflow: "hidden" }}>
              <div style={{ width: `${prob}%`, background: `linear-gradient(90deg, #f59e0b, #fbbf24)`, transition: "width 0.5s" }}></div>
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "8px", fontSize: "10px", color: "#a8a29e", marginTop: "8px" }}>
              <span>WinRate Global: {s.win_rate || 0}%</span>
              <span style={{ color: "#fbbf24", fontWeight: "700" }}>WinRate {s.direction}: {s.win_rate_direction || 0}%</span>
              <span>BUY: {s.win_rate_buy || 0}% | SELL: {s.win_rate_sell || 0}%</span>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: "10px", color: "#78716c", marginTop: "4px" }}>
              <span>TP1 $10: {s.probabilidad_nuevos_objetivos?.prob_tp1_10usd_10_15min || 0}% en 10-15min</span>
              <span>TP2: {s.probabilidad_nuevos_objetivos?.prob_tp2_20usd_15min || 0}% | TP3: {s.probabilidad_nuevos_objetivos?.prob_tp3_30usd_15min || 0}%</span>
            </div>
          </div>

          {/* PRECIOS ORO CONGRUENTES */}
          <div style={{ fontFamily: "monospace", fontSize: "13px", background: "#0c0a09", borderRadius: "12px", padding: "14px", border: "1px solid #44403c" }}>
            <div style={{ display: "flex", justifyContent: "space-between", padding: "6px 0", borderBottom: "1px solid #292524" }}>
              <span style={{ color: "#a8a29e" }}>ENTRY ORO</span><span style={{ fontWeight: "900", color: "#fbbf24", fontSize: "15px" }}>{s.entry?.toFixed(2)}</span>
            </div>

            <div style={{ display: "flex", justifyContent: "space-between", padding: "6px 0", color: "#f87171", marginTop: "6px" }}>
              <span style={{ color: "#a8a29e" }}>SL (-$10) {isBuy ? "↓ ABAJO" : "↑ ARRIBA"}</span>
              <span style={{ fontWeight: "700" }}>{s.sl?.toFixed(2)}</span>
            </div>
            <div style={{ fontSize: "10px", color: "#78716c", paddingBottom: "6px", background: "rgba(239,68,68,0.05)", padding: "4px 6px", borderRadius: "4px" }}>{s.sl_explain}</div>

            <div style={{ display: "flex", justifyContent: "space-between", padding: "6px 0", color: "#fbbf24", marginTop: "6px" }}>
              <span style={{ color: "#a8a29e" }}>TP1 (+$10) {isBuy ? "↑ ARRIBA" : "↓ ABAJO"}</span>
              <span style={{ fontWeight: "700" }}>{s.tp1?.toFixed(2)}</span>
            </div>
            <div style={{ fontSize: "10px", color: "#78716c", paddingBottom: "6px", background: "rgba(245,158,11,0.08)", padding: "4px 6px", borderRadius: "4px" }}>{s.tp_explain}</div>

            <div style={{ display: "flex", justifyContent: "space-between", padding: "6px 0", color: "#fbbf24" }}><span style={{ color: "#a8a29e" }}>TP2 (+$20)</span><span style={{ fontWeight: "600" }}>{s.tp2?.toFixed(2)}</span></div>
            <div style={{ display: "flex", justifyContent: "space-between", padding: "6px 0", color: "#fde68a" }}><span style={{ color: "#a8a29e" }}>TP3 (+$30)</span><span style={{ fontWeight: "600" }}>{s.tp3?.toFixed(2)}</span></div>
          </div>

          <div style={{ fontSize: "10px", color: "#78716c", marginTop: "10px", textAlign: "center", background: "#1c1917", padding: "6px", borderRadius: "6px" }}>
            {isBuy ? "🟡 COMPRA ORO: Ganas si sube" : "🔴 VENTA ORO: Ganas si baja"} • 6.17 USD = $10 con tu lotaje (1 USD = $1.62) • Solo XAUUSD potenciado
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "10px", marginTop: "16px" }}>
            <button onClick={() => sendResult("SL")} style={{ background: "rgba(239,68,68,0.12)", border: "1px solid rgba(239,68,68,0.4)", color: "#f87171", borderRadius: "10px", padding: "12px 4px", fontSize: "13px", fontWeight: "800", cursor: "pointer" }}>SL -$10</button>
            <button onClick={() => sendResult("TP1")} style={{ background: "rgba(245,158,11,0.18)", border: "1px solid rgba(245,158,11,0.5)", color: "#fbbf24", borderRadius: "10px", padding: "12px 4px", fontSize: "13px", fontWeight: "800", cursor: "pointer" }}>TP1 +$10</button>
            <button onClick={() => sendResult("TP2")} style={{ background: "rgba(245,158,11,0.14)", border: "1px solid rgba(245,158,11,0.4)", color: "#fbbf24", borderRadius: "10px", padding: "12px 4px", fontSize: "13px", fontWeight: "800", cursor: "pointer" }}>TP2 +$20</button>
            <button onClick={() => sendResult("TP3")} style={{ background: "linear-gradient(135deg, rgba(245,158,11,0.2), rgba(251,191,36,0.2))", border: "1px solid #f59e0b", color: "#fbbf24", borderRadius: "10px", padding: "12px 4px", fontSize: "13px", fontWeight: "800", cursor: "pointer" }}>TP3 +$30</button>
          </div>
          <div style={{ fontSize: "10px", color: "#78716c", marginTop: "10px", textAlign: "center" }}>Click TP/SL para que el oro aprenda como opera • Aprendizaje potenciado solo XAUUSD</div>
        </div>

        <div style={{ marginTop: "20px", padding: "14px", background: "#1c1917", border: "1px solid #44403c", borderRadius: "12px" }}>
          <h3 style={{ fontSize: "13px", fontWeight: "800", marginBottom: "8px", color: "#fbbf24" }}>🥇 ORO PURO POTENCIADO - Sin BTC, Sin Telegram</h3>
          <ul style={{ fontSize: "11px", color: "#d6d3d1", margin: 0, paddingLeft: "16px", lineHeight: "1.7" }}>
            <li><b style={{ color: "#fbbf24" }}>Solo XAUUSD:</b> Todo el poder de cómputo solo para oro, sin distracción BTC</li>
            <li><b style={{ color: "#fbbf24" }}>Analisis 10-15-30 min:</b> Velas con HIGH/LOW reales, soportes, resistencias, SMA10/15/30</li>
            <li><b style={{ color: "#fbbf24" }}>Aprendizaje como opera el oro:</b> Horas ganadoras, patrones (BREAK_HIGH, SMA_BULL, NY_OPEN), WinRate BUY/SELL separado</li>
            <li><b style={{ color: "#fbbf24" }}>NY OPEN 8-10 AM EC:</b> Detecta sesión más volátil oro y da bonus +12% prob</li>
            <li><b style={{ color: "#fbbf24" }}>Sin Telegram:</b> Backend más liviano, sin envíos, solo API /signals/live y aprendizaje local</li>
            <li><b style={{ color: "#fbbf24" }}>SL/TP congruente oro:</b> BUY SL abajo / TP arriba | SELL SL arriba / TP abajo - 6.17 USD = $10</li>
          </ul>
        </div>

        <div style={{ textAlign: "center", color: "#57534e", fontSize: "11px", marginTop: "20px" }}>
          Backend: {API} • Solo XAUUSD • ORO potenciado 10-15-30 min • 6.17 USD = $10 • Sin BTC • Sin Telegram
        </div>
      </div>
    </div>
  );
}
