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
      let sigs = Array.isArray(data) ? data : data.signals || [data];
      sigs = sigs.filter(s => s && (s.symbol || s.ticker));
      if (sigs.length > 0) { setSignals(sigs); setBackendStatus("conectado"); }
      else throw new Error("vacio");
    } catch (e) {
      setBackendStatus("demo - Render durmiendo 50s");
      const demoPriceXAU = 4015 + Math.random() * 20;
      const demoPriceBTC = 81500 + Math.random() * 1000;
      const distXAU = 6.17; const distBTC = 617.28;
      setSignals([
        { symbol: "XAUUSD", direction: Math.random() > 0.5 ? "BUY" : "SELL", entry: parseFloat(demoPriceXAU.toFixed(2)), sl: parseFloat((demoPriceXAU - distXAU).toFixed(2)), tp1: parseFloat((demoPriceXAU + distXAU).toFixed(2)), tp2: parseFloat((demoPriceXAU + distXAU*2).toFixed(2)), tp3: parseFloat((demoPriceXAU + distXAU*3).toFixed(2)), probability: 75 + Math.floor(Math.random()*15), win_rate: 76.5, is_optimal_hour: true, market_analysis: { trend: "BULLISH", up_streak: 3 }, probabilidad_nuevos_objetivos: { prob_tp1_10usd_10_15min: 68, prob_tp2_20usd_15min: 45, prob_tp3_30usd_15min: 28 }, reason: "Demo - Backend Render despertando", source: "demo" },
        { symbol: "BTCUSDT", direction: Math.random() > 0.5 ? "BUY" : "SELL", entry: parseFloat(demoPriceBTC.toFixed(2)), sl: parseFloat((demoPriceBTC - distBTC).toFixed(2)), tp1: parseFloat((demoPriceBTC + distBTC).toFixed(2)), tp2: parseFloat((demoPriceBTC + distBTC*2).toFixed(2)), tp3: parseFloat((demoPriceBTC + distBTC*3).toFixed(2)), probability: 72 + Math.floor(Math.random()*15), win_rate: 71.2, market_analysis: { trend: "BEARISH", down_streak: 2 }, probabilidad_nuevos_objetivos: { prob_tp1_10usd_10_15min: 62, prob_tp2_20usd_15min: 38, prob_tp3_30usd_15min: 22 }, reason: "Demo - Backend despertando", source: "demo" }
      ]);
    } finally { setLoading(false); }
  };
  useEffect(() => {
    fetchData();
    const id = setInterval(fetchData, 30000);
    const tId = setInterval(() => {
      const now = new Date().toLocaleString("es-EC", { timeZone: "America/Guayaquil", hour: "2-digit", minute: "2-digit", second: "2-digit", weekday: "short", day: "2-digit", month: "short" });
      setTimeEc(now);
    }, 1000);
    return () => { clearInterval(id); clearInterval(tId); };
  }, []);
  const sendResult = async (symbol, result) => {
    try { await fetch(`${API}/trades/result`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ symbol, result }) }); alert(`Aprendizaje: ${symbol} -> ${result}`); } catch {}
  };
  const getProbColor = (p) => p >= 80 ? "#10b981" : p >= 65 ? "#f59e0b" : "#ef4444";
  return (
    <div className="min-h-screen bg-[#0a0a0a] text-white p-4 md:p-8">
      <div className="max-w-7xl mx-auto">
        <div className="flex flex-col md:flex-row justify-between gap-4 mb-8 border-b border-zinc-800 pb-6">
          <div>
            <h1 className="text-3xl font-black">EDGEALERT</h1>
            <p className="text-zinc-400 text-sm">Trading con probabilidad - 6.17 USD = $10 oro - BUY/SELL auto</p>
            <p className="text-xs mt-1" style={{color: backendStatus.includes("conectado") ? "#10b981" : "#f59e0b"}}>Backend: {backendStatus}</p>
          </div>
          <div className="bg-zinc-900 border border-zinc-800 rounded-lg px-4 py-2 text-sm">
            <div className="text-zinc-500 text-[10px]">HORA ECUADOR</div>
            <div className="font-mono">{timeEc}</div>
            <div className="text-emerald-400 text-xs">8AM-10AM OPTIMA</div>
          </div>
        </div>
        {loading ? <div className="text-center py-20 text-zinc-500">Cargando...</div> : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {signals.map((s, i) => {
              const isBuy = (s.direction || "").includes("BUY");
              return (
                <div key={i} className="bg-zinc-900 border border-zinc-800 rounded-2xl p-6 relative">
                  <div className="absolute top-0 right-0 px-4 py-2 rounded-bl-xl font-black text-sm" style={{background: getProbColor(s.probability)}}>{s.probability}% PROB</div>
                  <div className="flex justify-between mt-2 mb-2">
                    <span className="text-xl font-black">{s.symbol}</span>
                    <span className={`px-3 py-1 rounded-full text-xs font-black ${isBuy ? "bg-emerald-500/20 text-emerald-400" : "bg-red-500/20 text-red-400"}`}>{s.direction} {isBuy ? "↑" : "↓"}</span>
                  </div>
                  <div className="text-[11px] text-zinc-400 mb-3">{s.reason}</div>
                  <div className="space-y-1 text-sm font-mono bg-zinc-950 rounded-lg p-3">
                    <div className="flex justify-between"><span className="text-zinc-500">ENTRY</span><span>{s.entry?.toFixed ? s.entry.toFixed(2) : s.entry}</span></div>
                    <div className="flex justify-between text-red-400"><span className="text-zinc-500">SL -$10</span><span>{s.sl?.toFixed ? s.sl.toFixed(2) : s.sl}</span></div>
                    <div className="flex justify-between text-emerald-400"><span className="text-zinc-500">TP1 +$10</span><span>{s.tp1?.toFixed ? s.tp1.toFixed(2) : s.tp1}</span></div>
                    <div className="flex justify-between text-emerald-400"><span className="text-zinc-500">TP2 +$20</span><span>{s.tp2?.toFixed ? s.tp2.toFixed(2) : s.tp2}</span></div>
                    <div className="flex justify-between text-emerald-300"><span className="text-zinc-500">TP3 +$30</span><span>{s.tp3?.toFixed ? s.tp3.toFixed(2) : s.tp3}</span></div>
                  </div>
                  <div className="mt-4 grid grid-cols-4 gap-2">
                    <button onClick={() => sendResult(s.symbol, "SL")} className="bg-red-500/10 border border-red-500/30 text-red-400 rounded-lg py-2 text-xs">SL</button>
                    <button onClick={() => sendResult(s.symbol, "TP1")} className="bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 rounded-lg py-2 text-xs">TP1</button>
                    <button onClick={() => sendResult(s.symbol, "TP2")} className="bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 rounded-lg py-2 text-xs">TP2</button>
                    <button onClick={() => sendResult(s.symbol, "TP3")} className="bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 rounded-lg py-2 text-xs">TP3</button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
        <div className="mt-8 text-center text-xs text-zinc-600">Backend: {API} - BUY/SELL auto - 6.17 USD = $10 oro con tu lotaje</div>
      </div>
    </div>
  );
}
