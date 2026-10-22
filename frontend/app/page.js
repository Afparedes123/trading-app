"use client";
import { useEffect, useState } from "react";
const API = process.env.NEXT_PUBLIC_API_URL || "https://trading-app-jn5a.onrender.com";

export default function Page() {
  const [signals, setSignals] = useState([]);
  const [loading, setLoading] = useState(true);
  const [timeEc, setTimeEc] = useState("");

  useEffect(() => {
    const fetchData = async () => {
      try {
        const res = await fetch(`${API}/signals/live`);
        const data = await res.json();
        setSignals(Array.isArray(data) ? data : data.signals || []);
      } catch (e) {}
      finally { setLoading(false); }
    };
    fetchData();
    const id = setInterval(fetchData, 30000);
    const tId = setInterval(() => {
      const now = new Date().toLocaleString("es-EC", { timeZone: "America/Guayaquil", hour: "2-digit", minute: "2-digit", second: "2-digit", weekday: "long", day: "2-digit", month: "short" });
      setTimeEc(now);
    }, 1000);
    return () => { clearInterval(id); clearInterval(tId); };
  }, []);

  const sendResult = async (symbol, result) => {
    await fetch(`${API}/trades/result`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ symbol, result }) });
    alert(`Aprendizaje guardado: ${symbol} -> ${result}`);
  };

  const getProbColor = (p) => p >= 80 ? "#10b981" : p >= 65 ? "#f59e0b" : "#ef4444";

  return (
    <div style={{ minHeight: "100vh", background: "#0a0a0a", color: "white", padding: "24px", fontFamily: "system-ui" }}>
      <div style={{ maxWidth: "1200px", margin: "0 auto" }}>
        <div style={{ display: "flex", justifyContent: "space-between", flexWrap: "wrap", gap: "16px", borderBottom: "1px solid #27272a", paddingBottom: "20px", marginBottom: "24px" }}>
          <div><h1 style={{ fontSize: "32px", fontWeight: "900", margin: 0 }}>EDGEALERT</h1><p style={{ color: "#a1a1aa", fontSize: "13px" }}>Trading con probabilidad SL / TP1 / TP2 / TP3 • Ecuador 8-10 AM</p></div>
          <div style={{ background: "#18181b", border: "1px solid #27272a", borderRadius: "10px", padding: "12px 16px" }}><div style={{ color: "#71717a", fontSize: "10px" }}>HORA ECUADOR</div><div style={{ fontFamily: "monospace", fontSize: "16px" }}>{timeEc}</div><div style={{ color: "#10b981", fontSize: "11px" }}>Ventana óptima: 8AM - 10AM EC</div></div>
        </div>
        {loading ? <div style={{ textAlign: "center", padding: "80px", color: "#71717a" }}>Cargando...</div> :
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(340px, 1fr))", gap: "16px" }}>
            {signals.map((s, i) => (
              <div key={i} style={{ background: "#18181b", border: "1px solid #27272a", borderRadius: "16px", padding: "20px", position: "relative", overflow: "hidden" }}>
                <div style={{ position: "absolute", top: "0", right: "0", background: getProbColor(s.probability || 70), color: "white", padding: "6px 14px", borderRadius: "0 16px 0 12px", fontWeight: "900", fontSize: "14px" }}>{s.probability || s.confidence || 0}% PROB</div>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "6px", marginTop: "10px" }}>
                  <span style={{ fontSize: "20px", fontWeight: "800" }}>{s.symbol}</span>
                  <span style={{ background: s.direction?.includes("BUY") ? "rgba(16,185,129,0.15)" : "rgba(239,68,68,0.15)", color: s.direction?.includes("BUY") ? "#10b981" : "#ef4444", border: "1px solid currentColor", padding: "4px 10px", borderRadius: "20px", fontSize: "11px", fontWeight: "800" }}>{s.direction}</span>
                </div>
                <div style={{ fontSize: "11px", color: "#a1a1aa", marginBottom: "12px" }}>{s.reason} • WinRate: {s.win_rate || 70}% {s.is_optimal_hour ? "🔥 OPTIMA" : ""}</div>
                <div style={{ background: "#0a0a0a", borderRadius: "8px", padding: "8px", marginBottom: "12px" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", height: "6px", background: "#27272a", borderRadius: "3px", overflow: "hidden" }}><div style={{ width: `${s.probability || 70}%`, background: getProbColor(s.probability || 70) }}></div></div>
                  <div style={{ display: "flex", justifyContent: "space-between", fontSize: "10px", color: "#71717a", marginTop: "4px" }}><span>Probabilidad aprendizaje</span><span>{s.probability}%</span></div>
                </div>
                <div style={{ fontFamily: "monospace", fontSize: "13px" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", padding: "5px 0" }}><span style={{ color: "#71717a" }}>ENTRY</span><span style={{ fontWeight: "700" }}>{s.entry?.toFixed ? s.entry.toFixed(2) : s.entry}</span></div>
                  <div style={{ display: "flex", justifyContent: "space-between", padding: "5px 0", color: "#ef4444" }}><span style={{ color: "#71717a" }}>SL</span><span>{s.sl}</span></div>
                  <div style={{ display: "flex", justifyContent: "space-between", padding: "5px 0", color: "#10b981" }}><span style={{ color: "#71717a" }}>TP1</span><span>{s.tp1}</span></div>
                  <div style={{ display: "flex", justifyContent: "space-between", padding: "5px 0", color: "#10b981" }}><span style={{ color: "#71717a" }}>TP2</span><span>{s.tp2}</span></div>
                  <div style={{ display: "flex", justifyContent: "space-between", padding: "5px 0", color: "#6ee7b7" }}><span style={{ color: "#71717a" }}>TP3</span><span>{s.tp3}</span></div>
                </div>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "8px", marginTop: "16px", borderTop: "1px solid #27272a", paddingTop: "14px" }}>
                  <button onClick={() => sendResult(s.symbol, "SL")} style={{ background: "rgba(239,68,68,0.1)", border: "1px solid rgba(239,68,68,0.3)", color: "#f87171", borderRadius: "6px", padding: "8px", fontSize: "12px", cursor: "pointer" }}>SL</button>
                  <button onClick={() => sendResult(s.symbol, "TP1")} style={{ background: "rgba(16,185,129,0.1)", border: "1px solid rgba(16,185,129,0.3)", color: "#34d399", borderRadius: "6px", padding: "8px", fontSize: "12px", cursor: "pointer" }}>TP1</button>
                  <button onClick={() => sendResult(s.symbol, "TP2")} style={{ background: "rgba(16,185,129,0.1)", border: "1px solid rgba(16,185,129,0.3)", color: "#34d399", borderRadius: "6px", padding: "8px", fontSize: "12px", cursor: "pointer" }}>TP2</button>
                  <button onClick={() => sendResult(s.symbol, "TP3")} style={{ background: "rgba(16,185,129,0.1)", border: "1px solid rgba(16,185,129,0.3)", color: "#34d399", borderRadius: "6px", padding: "8px", fontSize: "12px", cursor: "pointer" }}>TP3</button>
                </div>
              </div>
            ))}
          </div>
        }
      </div>
    </div>
  );
}
