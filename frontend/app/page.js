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
        // backend puede devolver {signals: [...]} o directamente [...]
        if (Array.isArray(data)) setSignals(data);
        else if (data.signals) setSignals(data.signals);
        else if (data.data) setSignals(data.data);
        else setSignals([data]);
      } catch (e) {
        console.error(e);
      } finally {
        setLoading(false);
      }
    };
    fetchData();
    const id = setInterval(fetchData, 30000);
    // Hora Ecuador
    const tId = setInterval(() => {
      const now = new Date().toLocaleString("es-EC", { timeZone: "America/Guayaquil", hour: "2-digit", minute: "2-digit", second: "2-digit", weekday: "short", day: "2-digit", month: "short" });
      setTimeEc(now);
    }, 1000);
    return () => { clearInterval(id); clearInterval(tId); };
  }, []);

  const sendResult = async (symbol, result) => {
    try {
      await fetch(`${API}/trades/result`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ symbol, result, timestamp: new Date().toISOString() })
      });
      alert(`Aprendizaje guardado: ${symbol} -> ${result}`);
    } catch {}
  };

  return (
    <div className="min-h-screen bg-[#0a0a0a] text-white p-4 md:p-8">
      <div className="max-w-7xl mx-auto">
        <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 mb-8 border-b border-zinc-800 pb-6">
          <div>
            <h1 className="text-3xl font-bold tracking-tight">EDGEALERT</h1>
            <p className="text-zinc-400 text-sm mt-1">Trading con aprendizaje SL / TP1 / TP2 / TP3 • Ecuador 8-10 AM</p>
          </div>
          <div className="bg-zinc-900 border border-zinc-800 rounded-lg px-4 py-2 text-sm">
            <div className="text-zinc-400 text-xs">HORA ECUADOR</div>
            <div className="font-mono text-lg">{timeEc || "Cargando..."}</div>
            <div className="text-xs text-emerald-400 mt-1">Ventana óptima: 8AM - 10AM EC</div>
          </div>
        </div>

        {loading ? (
          <div className="text-center py-20 text-zinc-500">Cargando señales desde {API}...</div>
        ) : signals.length === 0 ? (
          <div className="text-center py-20">
            <div className="text-zinc-500">No hay señales ahora</div>
            <div className="text-xs text-zinc-600 mt-2">Backend: {API}/signals/live</div>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            {signals.map((s, i) => (
              <div key={i} className="bg-zinc-900 border border-zinc-800 rounded-xl p-5 hover:border-zinc-700 transition">
                <div className="flex justify-between items-center mb-4">
                  <span className="text-xl font-bold">{s.symbol || s.ticker || "XAUUSD"}</span>
                  <span className={`px-2 py-1 rounded text-xs font-bold ${ (s.direction || s.side || "BUY").toUpperCase().includes("BUY") ? "bg-emerald-500/20 text-emerald-400 border border-emerald-500/30" : "bg-red-500/20 text-red-400 border border-red-500/30"}`}>{s.direction || s.side || s.signal || "BUY"}</span>
                </div>
                <div className="space-y-2 text-sm font-mono">
                  <div className="flex justify-between"><span className="text-zinc-500">ENTRY</span><span>{s.entry || s.price || "-"}</span></div>
                  <div className="flex justify-between text-red-400"><span className="text-zinc-500">SL</span><span>{s.sl || s.stopLoss || "-"}</span></div>
                  <div className="flex justify-between text-emerald-400"><span className="text-zinc-500">TP1</span><span>{s.tp1 || s.takeProfit1 || "-"}</span></div>
                  <div className="flex justify-between text-emerald-400"><span className="text-zinc-500">TP2</span><span>{s.tp2 || s.takeProfit2 || "-"}</span></div>
                  <div className="flex justify-between text-emerald-300"><span className="text-zinc-500">TP3</span><span>{s.tp3 || s.takeProfit3 || "-"}</span></div>
                </div>
                <div className="mt-4 pt-4 border-t border-zinc-800 grid grid-cols-4 gap-2">
                  <button onClick={() => sendResult(s.symbol, "SL")} className="bg-red-500/10 hover:bg-red-500/20 border border-red-500/30 text-red-400 rounded py-1.5 text-xs">SL</button>
                  <button onClick={() => sendResult(s.symbol, "TP1")} className="bg-emerald-500/10 hover:bg-emerald-500/20 border border-emerald-500/30 text-emerald-400 rounded py-1.5 text-xs">TP1</button>
                  <button onClick={() => sendResult(s.symbol, "TP2")} className="bg-emerald-500/10 hover:bg-emerald-500/20 border border-emerald-500/30 text-emerald-400 rounded py-1.5 text-xs">TP2</button>
                  <button onClick={() => sendResult(s.symbol, "TP3")} className="bg-emerald-500/10 hover:bg-emerald-500/20 border border-emerald-500/30 text-emerald-400 rounded py-1.5 text-xs">TP3</button>
                </div>
                <div className="text-[10px] text-zinc-600 mt-3">Click TP/SL para que aprenda</div>
              </div>
            ))}
          </div>
        )}

        <div className="mt-8 text-center text-xs text-zinc-600">
          Backend: <a href={`${API}/health`} target="_blank" className="underline hover:text-zinc-400">{API}</a> • Auto-refresh 30s
        </div>
      </div>
    </div>
  );
}
