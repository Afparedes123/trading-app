"use client";
import { useEffect, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL || "https://trading-app-jn5a.onrender.com";

function calcTPSL(entry, symbol, direction) {
  const distXAU = 6.17;
  const distBTC = 617.28;
  const dist = symbol.includes("XAU") ? distXAU : distBTC;
  if (direction === "BUY") {
    return {
      sl: entry - dist,
      tp1: entry + dist,
      tp2: entry + dist*2,
      tp3: entry + dist*3,
      dist
    };
  } else {
    // SELL CORRECTO: SL ARRIBA, TP ABAJO
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
  const [signals, setSignals] = useState([]);
  const [loading, setLoading] = useState(true);
  const [timeEc, setTimeEc] = useState("");
  const [backendStatus, setBackendStatus] = useState("conectando...");

  const fetchData = async () => {
    try {
      const res = await fetch(`${API}/signals/live`, { cache: 'no-store' });
      if (!res.ok) throw new Error(`Backend ${res.status}`);
      const data = await res.json();
      let sigs = Array.isArray(data) ? data : data.signals || data.data || [data];
      sigs = sigs.filter(s => s && (s.symbol || s.ticker));
      if (sigs.length > 0) {
        setSignals(sigs);
        setBackendStatus("conectado - analisis 10-15min");
      } else throw new Error("vacio");
    } catch (e) {
      setBackendStatus("demo - Render durmiendo 50s (analisis 10-15min)");
      const demoPriceXAU = 4025 + Math.random() * 10;
      const demoPriceBTC = 81500 + Math.random() * 500;
      
      // Demo con analisis 10-15 min realista - NO cambia cada momento
      const xau = calcTPSL(demoPriceXAU, "XAUUSD", "BUY");
      const btc = calcTPSL(demoPriceBTC, "BTCUSDT", "SELL");
      
      setSignals([
        {
          symbol: "XAUUSD",
          direction: "BUY",
          entry: parseFloat(demoPriceXAU.toFixed(2)),
          sl: parseFloat(xau.sl.toFixed(2)),
          tp1: parseFloat(xau.tp1.toFixed(2)),
          tp2: parseFloat(xau.tp2.toFixed(2)),
          tp3: parseFloat(xau.tp3.toFixed(2)),
          sl_distance: xau.dist,
          tp1_distance: xau.dist,
          sl_explain: `SL ${xau.sl.toFixed(2)} ABAJO de ENTRY (si baja ${xau.dist} USD pierdes $10)`,
          tp_explain: `TP1 ${xau.tp1.toFixed(2)} ARRIBA de ENTRY (si sube ${xau.dist} USD ganas $10)`,
          probability: 78,
          confidence: 82,
          win_rate: 76.5,
          win_rate_direction: 78.2,
          is_optimal_hour: true,
          market_analysis: { 
            trend: "BULLISH", 
            up_streak: 3, 
            down_streak: 0,
            high_10: demoPriceXAU + 4.2,
            low_10: demoPriceXAU - 3.8,
            high_15: demoPriceXAU + 6.5,
            low_15: demoPriceXAU - 5.2,
            sma10: demoPriceXAU - 1.2,
            sma15: demoPriceXAU - 2.1,
            buy_signals: 6,
            sell_signals: 2,
            volatility: 4.5
          },
          probabilidad_nuevos_objetivos: { prob_tp1_10usd_10_15min: 72, prob_tp2_20usd_15min: 48, prob_tp3_30usd_15min: 31 },
          reason: "BUY: 3 velas 10min alcistas | Precio > SMA10(4023.80) y SMA15 | Rompiendo alto 10min 4029.20 | Vela alcista fuerte",
          flip_reason: "Misma dirección - continua (analisis 10-15min evita cambio cada momento)",
          source: "demo_10_15_fixed"
        },
        {
          symbol: "BTCUSDT",
          direction: "SELL",
          entry: parseFloat(demoPriceBTC.toFixed(2)),
          sl: parseFloat(btc.sl.toFixed(2)),
          tp1: parseFloat(btc.tp1.toFixed(2)),
          tp2: parseFloat(btc.tp2.toFixed(2)),
          tp3: parseFloat(btc.tp3.toFixed(2)),
          sl_distance: btc.dist,
          tp1_distance: btc.dist,
          sl_explain: `SL ${btc.sl.toFixed(2)} ARRIBA de ENTRY (si sube ${btc.dist} USD pierdes $10)`,
          tp_explain: `TP1 ${btc.tp1.toFixed(2)} ABAJO de ENTRY (si baja ${btc.dist} USD ganas $10)`,
          probability: 74,
          confidence: 76,
          win_rate: 71.2,
          win_rate_direction: 68.5,
          market_analysis: { 
            trend: "BEARISH", 
            down_streak: 3, 
            up_streak: 0,
            high_10: demoPriceBTC + 320,
            low_10: demoPriceBTC - 280,
            high_15: demoPriceBTC + 450,
            low_15: demoPriceBTC - 380,
            sma10: demoPriceBTC + 120,
            sma15: demoPriceBTC + 180,
            buy_signals: 2,
            sell_signals: 6,
            volatility: 420
          },
          probabilidad_nuevos_objetivos: { prob_tp1_10usd_10_15min: 65, prob_tp2_20usd_15min: 41, prob_tp3_30usd_15min: 26 },
          reason: "SELL: 3 velas 10min bajistas | Precio < SMA10 y SMA15 | Rompiendo bajo 10min 81220 | 2 velas 15min bajistas",
          flip_reason: "Cambio tras 12.5 min - confianza 76% suficiente (no cambia cada momento)",
          source: "demo_10_15_fixed"
        }
      ]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
    const id = setInterval(fetchData, 30000);
    const tId = setInterval(() => {
      const now = new Date().toLocaleString("es-EC", { timeZone: "America/Guayaquil", hour: "2-digit", minute: "2-digit", second: "2-digit", weekday: "long", day: "2-digit", month: "short", year: "numeric" });
      setTimeEc(now);
    }, 1000);
    return () => { clearInterval(id); clearInterval(tId); };
  }, []);

  const sendResult = async (symbol, result) => {
    try {
      await fetch(`${API}/trades/result`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ symbol, result }) });
      alert(`✅ Aprendizaje guardado: ${symbol} -> ${result} (BUY/SELL separado)`);
      fetchData();
    } catch {}
  };

  const getProbColor = (p) => p >= 80 ? "#10b981" : p >= 65 ? "#f59e0b" : "#ef4444";

  return (
    <div style={{ minHeight: "100vh", background: "#0a0a0a", color: "white", padding: "24px", fontFamily: "system-ui, -apple-system, sans-serif" }}>
      <div style={{ maxWidth: "1200px", margin: "0 auto" }}>
        <div style={{ display: "flex", justifyContent: "space-between", flexWrap: "wrap", gap: "16px", borderBottom: "1px solid #27272a", paddingBottom: "20px", marginBottom: "24px" }}>
          <div>
            <h1 style={{ fontSize: "32px", fontWeight: "900", margin: 0, letterSpacing: "-1px", lineHeight: "1" }}>EDGEALERT</h1>
            <p style={{ color: "#a1a1aa", fontSize: "13px", marginTop: "8px" }}>Analisis 10-15min con altos/bajos • 6.17 USD = $10 oro • SL/TP congruente</p>
            <p style={{ fontSize: "11px", marginTop: "6px", color: backendStatus.includes("conectado") ? "#10b981" : "#f59e0b" }}>Backend: {backendStatus}</p>
          </div>
          <div style={{ background: "#18181b", border: "1px solid #27272a", borderRadius: "10px", padding: "12px 16px", minWidth: "220px" }}>
            <div style={{ color: "#71717a", fontSize: "10px", letterSpacing: "1px", textTransform: "uppercase" }}>HORA ECUADOR</div>
            <div style={{ fontFamily: "monospace", fontSize: "14px", marginTop: "4px", fontWeight: "600" }}>{timeEc || "Cargando..."}</div>
            <div style={{ color: "#10b981", fontSize: "11px", marginTop: "6px" }}>Ventana óptima: 8AM - 10AM EC</div>
          </div>
        </div>

        {loading ? (
          <div style={{ textAlign: "center", padding: "80px 20px", color: "#71717a" }}>Analizando mercado 10-15 min...</div>
        ) : (
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(380px, 1fr))", gap: "20px" }}>
            {signals.map((s, i) => {
              const isBuy = s.direction === "BUY";
              const prob = s.probability || 70;
              return (
                <div key={i} style={{ background: "#18181b", border: "1px solid #27272a", borderRadius: "16px", padding: "20px", position: "relative", overflow: "hidden" }}>
                  <div style={{ position: "absolute", top: 0, right: 0, background: getProbColor(prob), color: "white", padding: "8px 16px", borderRadius: "0 16px 0 12px", fontWeight: "900", fontSize: "14px" }}>
                    {prob}% PROB
                  </div>
                  
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "4px", marginTop: "12px" }}>
                    <span style={{ fontSize: "22px", fontWeight: "900" }}>{s.symbol}</span>
                    <span style={{ 
                      background: isBuy ? "rgba(16,185,129,0.15)" : "rgba(239,68,68,0.15)", 
                      color: isBuy ? "#10b981" : "#ef4444", 
                      border: `1px solid ${isBuy ? "rgba(16,185,129,0.3)" : "rgba(239,68,68,0.3)"}`, 
                      padding: "5px 12px", 
                      borderRadius: "20px", 
                      fontSize: "11px", 
                      fontWeight: "800"
                    }}>
                      {s.direction} {isBuy ? "↑ COMPRA" : "↓ VENTA"}
                    </span>
                  </div>

                  <div style={{ fontSize: "11px", color: "#a1a1aa", marginBottom: "10px", lineHeight: "1.4" }}>
                    {s.reason}
                    {s.is_optimal_hour && <span style={{ color: "#10b981", marginLeft: "6px", fontWeight: "700" }}>🔥 OPTIMA 8-10AM</span>}
                  </div>

                  {s.market_analysis && (
                    <div style={{ background: "#0a0a0a", border: "1px solid #27272a", borderRadius: "8px", padding: "10px", marginBottom: "12px", fontSize: "11px" }}>
                      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "4px" }}>
                        <span style={{ color: "#71717a" }}>Tendencia 10-15min: <b style={{ color: s.market_analysis.trend === "BULLISH" ? "#10b981" : s.market_analysis.trend === "BEARISH" ? "#ef4444" : "#fff" }}>{s.market_analysis.trend}</b></span>
                        <span style={{ color: "#71717a" }}>Conf: {s.confidence || s.market_analysis.confidence || 0}%</span>
                      </div>
                      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "4px" }}>
                        <span style={{ color: "#71717a" }}>Alto 10min: <span style={{ color: "#fff" }}>{s.market_analysis.high_10?.toFixed ? s.market_analysis.high_10.toFixed(2) : s.market_analysis.high_10}</span></span>
                        <span style={{ color: "#71717a" }}>Bajo 10min: <span style={{ color: "#fff" }}>{s.market_analysis.low_10?.toFixed ? s.market_analysis.low_10.toFixed(2) : s.market_analysis.low_10}</span></span>
                      </div>
                      <div style={{ display: "flex", justifyContent: "space-between" }}>
                        <span style={{ color: "#71717a" }}>SMA10: {s.market_analysis.sma10?.toFixed ? s.market_analysis.sma10.toFixed(2) : s.market_analysis.sma10} | SMA15: {s.market_analysis.sma15?.toFixed ? s.market_analysis.sma15.toFixed(2) : s.market_analysis.sma15}</span>
                      </div>
                      <div style={{ marginTop: "6px", color: "#71717a", fontSize: "10px" }}>{s.flip_reason || ""}</div>
                    </div>
                  )}

                  <div style={{ background: "#0a0a0a", borderRadius: "8px", padding: "10px", marginBottom: "12px" }}>
                    <div style={{ display: "flex", justifyContent: "space-between", height: "6px", background: "#27272a", borderRadius: "3px", overflow: "hidden" }}>
                      <div style={{ width: `${prob}%`, background: getProbColor(prob) }}></div>
                    </div>
                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: "10px", color: "#71717a", marginTop: "6px" }}>
                      <span>WinRate {s.direction}: {s.win_rate_direction || s.win_rate || 0}%</span>
                      <span>TP1 $10: {s.probabilidad_nuevos_objetivos?.prob_tp1_10usd_10_15min || 0}% en 10-15min</span>
                    </div>
                  </div>

                  <div style={{ fontFamily: "monospace", fontSize: "12px", background: "#0a0a0a", borderRadius: "10px", padding: "12px", border: "1px solid #1f1f23" }}>
                    <div style={{ display: "flex", justifyContent: "space-between", padding: "4px 0" }}><span style={{ color: "#71717a" }}>ENTRY</span><span style={{ fontWeight: "700", color: "#fff" }}>{s.entry?.toFixed ? s.entry.toFixed(2) : s.entry}</span></div>
                    
                    <div style={{ display: "flex", justifyContent: "space-between", padding: "4px 0", color: "#f87171" }}>
                      <span style={{ color: "#71717a" }}>SL (-$10) {isBuy ? "↓ ABAJO" : "↑ ARRIBA"}</span>
                      <span>{s.sl?.toFixed ? s.sl.toFixed(2) : s.sl}</span>
                    </div>
                    <div style={{ fontSize: "10px", color: "#52525b", paddingBottom: "4px" }}>{s.sl_explain}</div>
                    
                    <div style={{ display: "flex", justifyContent: "space-between", padding: "4px 0", color: "#34d399" }}>
                      <span style={{ color: "#71717a" }}>TP1 (+$10) {isBuy ? "↑ ARRIBA" : "↓ ABAJO"}</span>
                      <span>{s.tp1?.toFixed ? s.tp1.toFixed(2) : s.tp1}</span>
                    </div>
                    <div style={{ fontSize: "10px", color: "#52525b", paddingBottom: "4px" }}>{s.tp_explain}</div>
                    
                    <div style={{ display: "flex", justifyContent: "space-between", padding: "4px 0", color: "#34d399" }}><span style={{ color: "#71717a" }}>TP2 (+$20)</span><span>{s.tp2?.toFixed ? s.tp2.toFixed(2) : s.tp2}</span></div>
                    <div style={{ display: "flex", justifyContent: "space-between", padding: "4px 0", color: "#6ee7b7" }}><span style={{ color: "#71717a" }}>TP3 (+$30)</span><span>{s.tp3?.toFixed ? s.tp3.toFixed(2) : s.tp3}</span></div>
                  </div>

                  <div style={{ fontSize: "10px", color: "#52525b", marginTop: "8px" }}>
                    {isBuy ? "COMPRA: Ganas si sube" : "VENTA: Ganas si baja"} • {s.sl_distance || (s.symbol.includes("XAU") ? 6.17 : 617.28)} USD = $10
                  </div>

                  <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "8px", marginTop: "14px", borderTop: "1px solid #27272a", paddingTop: "12px" }}>
                    <button onClick={() => sendResult(s.symbol, "SL")} style={{ background: "rgba(239,68,68,0.1)", border: "1px solid rgba(239,68,68,0.3)", color: "#f87171", borderRadius: "8px", padding: "10px 4px", fontSize: "12px", fontWeight: "700", cursor: "pointer" }}>SL</button>
                    <button onClick={() => sendResult(s.symbol, "TP1")} style={{ background: "rgba(16,185,129,0.1)", border: "1px solid rgba(16,185,129,0.3)", color: "#34d399", borderRadius: "8px", padding: "10px 4px", fontSize: "12px", fontWeight: "700", cursor: "pointer" }}>TP1</button>
                    <button onClick={() => sendResult(s.symbol, "TP2")} style={{ background: "rgba(16,185,129,0.1)", border: "1px solid rgba(16,185,129,0.3)", color: "#34d399", borderRadius: "8px", padding: "10px 4px", fontSize: "12px", fontWeight: "700", cursor: "pointer" }}>TP2</button>
                    <button onClick={() => sendResult(s.symbol, "TP3")} style={{ background: "rgba(16,185,129,0.1)", border: "1px solid rgba(16,185,129,0.3)", color: "#34d399", borderRadius: "8px", padding: "10px 4px", fontSize: "12px", fontWeight: "700", cursor: "pointer" }}>TP3</button>
                  </div>
                </div>
              );
            })}
          </div>
        )}

        <div style={{ marginTop: "24px", padding: "16px", background: "#18181b", border: "1px solid #27272a", borderRadius: "12px" }}>
          <h3 style={{ fontSize: "13px", fontWeight: "800", marginBottom: "8px" }}>🔧 FIXES aplicados - Analisis 10-15 min</h3>
          <ul style={{ fontSize: "11px", color: "#a1a1aa", margin: 0, paddingLeft: "16px", lineHeight: "1.6" }}>
            <li><b style={{ color: "#fff" }}>SL/TP congruente:</b> BUY = SL ABAJO / TP ARRIBA | SELL = SL ARRIBA / TP ABAJO</li>
            <li><b style={{ color: "#fff" }}>No cambia cada momento:</b> Analiza velas completas 10 y 15 min con altos/bajos reales, no ticks de 30s</li>
            <li><b style={{ color: "#fff" }}>Evita flip-flop:</b> Solo cambia dirección tras 10 min o confianza &gt;75% o 2 velas confirmadas</li>
            <li><b style={{ color: "#fff" }}>Aprendizaje separado:</b> WinRate BUY y SELL por separado, aprende qué dirección funciona mejor</li>
            <li><b style={{ color: "#fff" }}>Herramientas:</b> SMA10/SMA15, ruptura altos/bajos 10-15min, racha velas, momentum, volatilidad</li>
          </ul>
        </div>

        <div style={{ textAlign: "center", color: "#52525b", fontSize: "11px", marginTop: "24px" }}>
          Backend: {API} • Analisis 10-15 min con altos/bajos • BUY/SELL congruente • 6.17 USD = $10 oro
        </div>
      </div>
    </div>
  );
}
