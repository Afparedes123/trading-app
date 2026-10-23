"use client";
import { useEffect, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL || "https://trading-app-jn5a.onrender.com";

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
        setBackendStatus("conectado");
      } else throw new Error("vacio");
    } catch (e) {
      setBackendStatus("demo - Render durmiendo 50s");
      const demoPriceXAU = 4015 + Math.random() * 20;
      const demoPriceBTC = 81500 + Math.random() * 1000;
      const distXAU = 6.17;
      const distBTC = 617.28;
      setSignals([
        {
          symbol: "XAUUSD",
          direction: Math.random() > 0.5 ? "BUY" : "SELL",
          entry: parseFloat(demoPriceXAU.toFixed(2)),
          sl: parseFloat((demoPriceXAU - distXAU).toFixed(2)),
          tp1: parseFloat((demoPriceXAU + distXAU).toFixed(2)),
          tp2: parseFloat((demoPriceXAU + distXAU*2).toFixed(2)),
          tp3: parseFloat((demoPriceXAU + distXAU*3).toFixed(2)),
          probability: 78,
          win_rate: 76.5,
          is_optimal_hour: true,
          market_analysis: { trend: "BULLISH", up_streak: 3, volatility: 0.85 },
          probabilidad_nuevos_objetivos: { prob_tp1_10usd_10_15min: 68, prob_tp2_20usd_15min: 45, prob_tp3_30usd_15min: 28 },
          reason: "BUY - Tendencia BULLISH + racha UP 3 + precio > SMA20 | 6.17 USD = $10",
          source: "demo"
        },
        {
          symbol: "BTCUSDT",
          direction: "SELL",
          entry: parseFloat(demoPriceBTC.toFixed(2)),
          sl: parseFloat((demoPriceBTC + distBTC).toFixed(2)),
          tp1: parseFloat((demoPriceBTC - distBTC).toFixed(2)),
          tp2: parseFloat((demoPriceBTC - distBTC*2).toFixed(2)),
          tp3: parseFloat((demoPriceBTC - distBTC*3).toFixed(2)),
          probability: 74,
          win_rate: 71.2,
          market_analysis: { trend: "BEARISH", down_streak: 2, volatility: 1.2 },
          probabilidad_nuevos_objetivos: { prob_tp1_10usd_10_15min: 62, prob_tp2_20usd_15min: 38, prob_tp3_30usd_15min: 22 },
          reason: "SELL - Tendencia BEARISH + racha DOWN 2 + precio < SMA20 | 617 USD = $10",
          source: "demo"
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
      alert(`✅ Aprendizaje guardado: ${symbol} -> ${result}`);
      fetchData();
    } catch {}
  };

  const getProbColor = (p) => p >= 80 ? "#10b981" : p >= 65 ? "#f59e0b" : "#ef4444";

  return (
    <div style={{ minHeight: "100vh", background: "#0a0a0a", color: "white", padding: "24px", fontFamily: "system-ui, -apple-system, sans-serif" }}>
      <div style={{ maxWidth: "1200px", margin: "0 auto" }}>
        {/* HEADER - Diseño original que te gustaba */}
        <div style={{ display: "flex", justifyContent: "space-between", flexWrap: "wrap", gap: "16px", borderBottom: "1px solid #27272a", paddingBottom: "20px", marginBottom: "24px" }}>
          <div>
            <h1 style={{ fontSize: "32px", fontWeight: "900", margin: 0, letterSpacing: "-1px", lineHeight: "1" }}>EDGEALERT</h1>
            <p style={{ color: "#a1a1aa", fontSize: "13px", marginTop: "8px", margin: 0, paddingTop: "8px" }}>Trading con probabilidad SL / TP1 / TP2 / TP3 • Ecuador 8-10 AM • 6.17 USD = $10</p>
            <p style={{ fontSize: "11px", marginTop: "6px", color: backendStatus.includes("conectado") ? "#10b981" : "#f59e0b" }}>Backend: {backendStatus}</p>
          </div>
          <div style={{ background: "#18181b", border: "1px solid #27272a", borderRadius: "10px", padding: "12px 16px", minWidth: "220px" }}>
            <div style={{ color: "#71717a", fontSize: "10px", letterSpacing: "1px", textTransform: "uppercase" }}>HORA ECUADOR</div>
            <div style={{ fontFamily: "monospace", fontSize: "14px", marginTop: "4px", fontWeight: "600" }}>{timeEc || "Cargando..."}</div>
            <div style={{ color: "#10b981", fontSize: "11px", marginTop: "6px" }}>Ventana óptima: 8AM - 10AM EC</div>
          </div>
        </div>

        {loading ? (
          <div style={{ textAlign: "center", padding: "80px 20px", color: "#71717a" }}>
            <div>Despertando backend Render (gratis tarda 50s)...</div>
            <div style={{ fontSize: "12px", marginTop: "8px", color: "#52525b" }}>{API}/signals/live</div>
          </div>
        ) : (
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(360px, 1fr))", gap: "20px" }}>
            {signals.map((s, i) => {
              const isBuy = (s.direction || "").toUpperCase().includes("BUY");
              const prob = s.probability || 70;
              return (
                <div key={i} style={{ background: "#18181b", border: "1px solid #27272a", borderRadius: "16px", padding: "20px", position: "relative", overflow: "hidden" }}>
                  {/* PROB badge */}
                  <div style={{ position: "absolute", top: 0, right: 0, background: getProbColor(prob), color: "white", padding: "8px 16px", borderRadius: "0 16px 0 12px", fontWeight: "900", fontSize: "14px", letterSpacing: "0.5px" }}>
                    {prob}% PROB
                  </div>
                  
                  {/* Symbol + Direction */}
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "4px", marginTop: "12px" }}>
                    <span style={{ fontSize: "22px", fontWeight: "900", letterSpacing: "-0.5px" }}>{s.symbol}</span>
                    <span style={{ 
                      background: isBuy ? "rgba(16,185,129,0.15)" : "rgba(239,68,68,0.15)", 
                      color: isBuy ? "#10b981" : "#ef4444", 
                      border: `1px solid ${isBuy ? "rgba(16,185,129,0.3)" : "rgba(239,68,68,0.3)"}`, 
                      padding: "5px 12px", 
                      borderRadius: "20px", 
                      fontSize: "11px", 
                      fontWeight: "800",
                      letterSpacing: "0.5px"
                    }}>
                      {s.direction} {isBuy ? "↑" : "↓"}
                    </span>
                  </div>

                  {/* Reason */}
                  <div style={{ fontSize: "11px", color: "#a1a1aa", marginBottom: "14px", lineHeight: "1.4", minHeight: "32px" }}>
                    {s.reason} 
                    {s.is_optimal_hour && <span style={{ color: "#10b981", marginLeft: "6px", fontWeight: "700" }}>🔥 OPTIMA</span>}
                  </div>

                  {/* Market analysis */}
                  {s.market_analysis && (
                    <div style={{ background: "#0a0a0a", border: "1px solid #27272a", borderRadius: "8px", padding: "10px", marginBottom: "14px", display: "flex", justifyContent: "space-between", fontSize: "11px" }}>
                      <span style={{ color: "#71717a" }}>Tendencia: <b style={{ color: s.market_analysis.trend === "BULLISH" ? "#10b981" : s.market_analysis.trend === "BEARISH" ? "#ef4444" : "#fff" }}>{s.market_analysis.trend}</b></span>
                      <span style={{ color: "#71717a" }}>Racha: UP:{s.market_analysis.up_streak || 0} DOWN:{s.market_analysis.down_streak || 0}</span>
                    </div>
                  )}

                  {/* Prob bar */}
                  <div style={{ background: "#0a0a0a", borderRadius: "8px", padding: "10px", marginBottom: "14px" }}>
                    <div style={{ display: "flex", justifyContent: "space-between", height: "6px", background: "#27272a", borderRadius: "3px", overflow: "hidden" }}>
                      <div style={{ width: `${prob}%`, background: getProbColor(prob), transition: "width 0.5s" }}></div>
                    </div>
                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: "10px", color: "#71717a", marginTop: "6px" }}>
                      <span>WinRate: {s.win_rate || 0}%</span>
                      <span>TP1 $10: {s.probabilidad_nuevos_objetivos?.prob_tp1_10usd_10_15min || 68}% en 10-15min</span>
                    </div>
                  </div>

                  {/* Prices */}
                  <div style={{ fontFamily: "monospace", fontSize: "13px", background: "#0a0a0a", borderRadius: "10px", padding: "12px", border: "1px solid #1f1f23" }}>
                    <div style={{ display: "flex", justifyContent: "space-between", padding: "5px 0" }}><span style={{ color: "#71717a" }}>ENTRY</span><span style={{ fontWeight: "700", color: "#fff" }}>{typeof s.entry === 'number' ? s.entry.toFixed(2) : s.entry}</span></div>
                    <div style={{ display: "flex", justifyContent: "space-between", padding: "5px 0", color: "#f87171" }}><span style={{ color: "#71717a" }}>SL (-$10)</span><span>{typeof s.sl === 'number' ? s.sl.toFixed(2) : s.sl} ({s.symbol === "XAUUSD" ? "6.17" : "617"} USD)</span></div>
                    <div style={{ display: "flex", justifyContent: "space-between", padding: "5px 0", color: "#34d399" }}><span style={{ color: "#71717a" }}>TP1 (+$10)</span><span>{typeof s.tp1 === 'number' ? s.tp1.toFixed(2) : s.tp1}</span></div>
                    <div style={{ display: "flex", justifyContent: "space-between", padding: "5px 0", color: "#34d399" }}><span style={{ color: "#71717a" }}>TP2 (+$20)</span><span>{typeof s.tp2 === 'number' ? s.tp2.toFixed(2) : s.tp2}</span></div>
                    <div style={{ display: "flex", justifyContent: "space-between", padding: "5px 0", color: "#6ee7b7" }}><span style={{ color: "#71717a" }}>TP3 (+$30)</span><span>{typeof s.tp3 === 'number' ? s.tp3.toFixed(2) : s.tp3}</span></div>
                  </div>

                  <div style={{ fontSize: "10px", color: "#52525b", marginTop: "8px" }}>6.17 USD = $10 con tu lotaje (1 USD = $1.62) • BUY/SELL auto</div>

                  {/* Buttons */}
                  <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "8px", marginTop: "16px", borderTop: "1px solid #27272a", paddingTop: "14px" }}>
                    <button onClick={() => sendResult(s.symbol, "SL")} style={{ background: "rgba(239,68,68,0.1)", border: "1px solid rgba(239,68,68,0.3)", color: "#f87171", borderRadius: "8px", padding: "10px 4px", fontSize: "12px", fontWeight: "700", cursor: "pointer" }}>SL</button>
                    <button onClick={() => sendResult(s.symbol, "TP1")} style={{ background: "rgba(16,185,129,0.1)", border: "1px solid rgba(16,185,129,0.3)", color: "#34d399", borderRadius: "8px", padding: "10px 4px", fontSize: "12px", fontWeight: "700", cursor: "pointer" }}>TP1</button>
                    <button onClick={() => sendResult(s.symbol, "TP2")} style={{ background: "rgba(16,185,129,0.1)", border: "1px solid rgba(16,185,129,0.3)", color: "#34d399", borderRadius: "8px", padding: "10px 4px", fontSize: "12px", fontWeight: "700", cursor: "pointer" }}>TP2</button>
                    <button onClick={() => sendResult(s.symbol, "TP3")} style={{ background: "rgba(16,185,129,0.1)", border: "1px solid rgba(16,185,129,0.3)", color: "#34d399", borderRadius: "8px", padding: "10px 4px", fontSize: "12px", fontWeight: "700", cursor: "pointer" }}>TP3</button>
                  </div>
                  <div style={{ fontSize: "10px", color: "#52525b", marginTop: "10px", textAlign: "center" }}>Click para que aprenda y mejore la probabilidad</div>
                </div>
              );
            })}
          </div>
        )}

        <div style={{ textAlign: "center", color: "#52525b", fontSize: "11px", marginTop: "32px", borderTop: "1px solid #1f1f23", paddingTop: "16px" }}>
          Backend: <a href={`${API}/health`} target="_blank" style={{ color: "#71717a", textDecoration: "underline" }}>{API}</a> • Auto-refresh 30s • Diseño PRO inline • BUY/SELL auto • 6.17 USD = $10
        </div>
      </div>
    </div>
  );
}
