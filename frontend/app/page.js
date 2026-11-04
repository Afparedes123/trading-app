"use client";
import { useEffect, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL || "https://trading-app-jn5a.onrender.com";

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
        setBackendStatus("Conectado - MODO EXPERTO");
      } else throw new Error("vacio");
    } catch (e) {
      setBackendStatus("Error de conexión - Reconectando...");
    } finally { 
      setLoading(false); 
    }
  };

  useEffect(() => {
    fetchData();
    const id = setInterval(fetchData, 8000); // 8 Segundos: Ultra rápido para cazar los quiebres de estructura
    const tId = setInterval(() => {
      const now = new Date().toLocaleString("es-EC", { timeZone: "America/Guayaquil", hour: "2-digit", minute: "2-digit", second: "2-digit", weekday: "long", day: "2-digit", month: "short" });
      setTimeEc(now);
    }, 1000);
    return () => { clearInterval(id); clearInterval(tId); };
  }, []);

  if (loading) return <div style={{ minHeight: "100vh", background: "#0a0a0a", color: "white", display: "flex", alignItems: "center", justifyContent: "center" }}>Iniciando Motor de Trading Experto...</div>;
  const s = signal; if (!s) return null;
  const isBuy = s.direction === "COMPRA";
  const isSell = s.direction === "VENTA";
  const confidence = s.confidence || 50;
  const points = s.points_detail || [];
  const alertText = s.alert || "";
  const alertType = s.alert_type || "WAIT";
  const dynamicDist = s.dist || 4.0;
  const expertFib = s.market_analysis?.expert_fib;
  
  // Lógica de colores institucional basada en Estados
  const getAlertStyle = (type) => {
    if (type === "ENTER") return { bg: "linear-gradient(135deg, rgba(34,197,94,0.15), rgba(16,185,129,0.15))", border: "#22c55e", color: "#22c55e" };
    if (type === "TAKE_PROFIT") return { bg: "linear-gradient(135deg, rgba(234,179,8,0.2), rgba(202,138,4,0.2))", border: "#eab308", color: "#fde047", animation: "pulse 2s infinite" }; // Dorado para Ganancias
    if (type === "RE_ENTRY") return { bg: "linear-gradient(135deg, rgba(6,182,212,0.2), rgba(8,145,178,0.2))", border: "#06b6d4", color: "#67e8f9" }; // Cian para Rupturas
    if (type === "EXIT") return { bg: "linear-gradient(135deg, rgba(249,115,22,0.25), rgba(220,38,38,0.25))", border: "#ef4444", color: "#f87171" };
    return { bg: "rgba(0,0,0,0)", border: "#71717a", color: "#a1a1aa" };
  };
  const alertStyle = getAlertStyle(alertType);

  return (
    <div style={{ minHeight: "100vh", background: "#0a0a0a", color: "white", padding: "14px", fontFamily: "system-ui" }}>
      <div style={{ maxWidth: "920px", margin: "0 auto" }}>
        
        {/* CABECERA */}
        <div style={{ display: "flex", justifyContent: "space-between", flexWrap: "wrap", gap: "12px", borderBottom: "1px solid #3f3f46", paddingBottom: "14px", marginBottom: "14px" }}>
          <div>
            <h1 style={{ fontSize: "24px", fontWeight: "900", margin: 0, color: "#f8fafc" }}>EDGEALERT <span style={{ color: "#fbbf24" }}>ORO</span></h1>
            <div style={{ fontSize: "11px", color: "#a8a29e" }}>{timeEc} • {backendStatus}</div>
            <div style={{ fontSize: "11px", color: "#38bdf8", fontWeight: "700", marginTop: "4px" }}>Tick Vivo: {s.live_price?.toFixed(2)}</div>
          </div>
          <div style={{ textAlign: "right" }}>
            <div style={{ fontSize: "16px", padding: "10px 20px", borderRadius: "8px", background: isBuy ? "rgba(34,197,94,0.2)" : isSell ? "rgba(239,68,68,0.2)" : "rgba(161,161,170,0.2)", border: `1px solid ${isBuy ? "#22c55e" : isSell ? "#ef4444" : "#a1a1aa"}`, color: isBuy ? "#22c55e" : isSell ? "#ef4444" : "#a1a1aa", fontWeight: "900", letterSpacing: "1px" }}>
              {s.direction} {isBuy ? "↑" : isSell ? "↓" : "⏸"}
            </div>
            <div style={{ fontSize: "9px", marginTop: "6px", color: "#a1a1aa", background: "rgba(255,255,255,0.05)", padding: "4px", borderRadius: "4px" }}>{s.flip_reason}</div>
          </div>
        </div>

        {/* CEREBRO EXPERTO (ALERTA PRINCIPAL) */}
        <div style={{ background: alertStyle.bg, border: `2px solid ${alertStyle.border}`, borderRadius: "12px", padding: "18px", marginBottom: "12px", boxShadow: (alertType === "TAKE_PROFIT" || alertType === "RE_ENTRY") ? `0 0 20px ${alertStyle.border}40` : "none" }}>
          <div style={{ fontWeight: "900", fontSize: "18px", color: alertStyle.color, textAlign: "center", textTransform: "uppercase" }}>{alertText}</div>
          <div style={{ fontSize: "11px", color: "#d4d4d8", textAlign: "center", marginTop: "6px", marginBottom: "14px" }}>{s.alert_desc}</div>
          
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "10px" }}>
            <div style={{ background: "rgba(0,0,0,0.5)", borderRadius: "8px", padding: "12px", textAlign: "center", border: "1px solid #3f3f46" }}>
              <div style={{ fontSize: "10px", color: "#a1a1aa", marginBottom: "4px", fontWeight: "700" }}>VOLUMEN NETO</div>
              <div style={{ fontSize: "22px", fontWeight: "900" }}>
                <span style={{ color: "#22c55e" }}>{s.market_analysis?.buy_score} C</span> <span style={{ color: "#52525b" }}>|</span> <span style={{ color: "#ef4444" }}>{s.market_analysis?.sell_score} V</span>
              </div>
            </div>
            <div style={{ background: "rgba(0,0,0,0.5)", borderRadius: "8px", padding: "12px", textAlign: "center", border: "1px solid #3f3f46" }}>
              <div style={{ fontSize: "10px", color: "#a1a1aa", marginBottom: "4px", fontWeight: "700" }}>PROBABILIDAD</div>
              <div style={{ fontSize: "22px", fontWeight: "900", color: confidence >= 80 ? "#22c55e" : confidence >= 65 ? "#fbbf24" : "#ef4444" }}>{confidence.toFixed(0)}%</div>
            </div>
          </div>
        </div>

        {/* MAPA DE ESTRUCTURA Y FIBONACCI */}
        {expertFib && expertFib.state !== "RANGO" && (
          <div style={{ background: "#171717", border: "1px solid #fbbf24", borderRadius: "8px", padding: "12px", marginBottom: "12px" }}>
            <div style={{ fontSize: "10px", color: "#fbbf24", fontWeight: "900", letterSpacing: "1px", marginBottom: "8px" }}>MAPA DE ESTRUCTURA INSTITUCIONAL</div>
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: "12px", marginBottom: "4px" }}>
              <span style={{ color: "#a1a1aa" }}>Fase Actual:</span>
              <span style={{ fontWeight: "800", color: expertFib.state.includes("IMPULSO") ? "#22c55e" : "#f43f5e" }}>{expertFib.state}</span>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: "12px" }}>
              <span style={{ color: "#a1a1aa" }}>Acción Sugerida:</span>
              <span style={{ fontWeight: "800", color: "#38bdf8" }}>{expertFib.action}</span>
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: "5px", marginTop: "10px", textAlign: "center", fontSize: "10px" }}>
              <div style={{ background: "#27272a", padding: "4px", borderRadius: "4px" }}>Fib 0: <br/><b style={{ color: "#fff" }}>{expertFib.levels["0"].toFixed(2)}</b></div>
              <div style={{ background: "rgba(234,179,8,0.1)", padding: "4px", borderRadius: "4px", border: "1px solid #eab308" }}>Zona Dorada:<br/><b style={{ color: "#fde047" }}>{expertFib.levels["0.5"].toFixed(2)}</b></div>
              <div style={{ background: "#27272a", padding: "4px", borderRadius: "4px" }}>Origen Fib:<br/><b style={{ color: "#fff" }}>{expertFib.levels["1"].toFixed(2)}</b></div>
            </div>
          </div>
        )}

        {/* DESGLOSE DE DECISIÓN DE LA IA */}
        <div style={{ background: "#18181b", border: "1px solid #27272a", borderRadius: "12px", padding: "12px", marginBottom: "12px" }}>
          <div style={{ fontWeight: "800", fontSize: "11px", marginBottom: "8px", color: "#71717a", textTransform: "uppercase" }}>Registro de Decisiones (Algoritmo)</div>
          <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
            {points.length === 0 && <div style={{ fontSize: "11px", color: "#52525b", textAlign: "center", padding: "10px" }}>Esperando volatilidad estructural...</div>}
            {points.map((p,i) => (
              <div key={i} style={{ display: "flex", justifyContent: "space-between", background: p.side==="COMPRA" ? "rgba(34,197,94,0.08)" : p.side==="VENTA" ? "rgba(239,68,68,0.08)" : "rgba(234,179,8,0.08)", border: `1px solid ${p.side==="COMPRA" ? "rgba(34,197,94,0.2)" : p.side==="VENTA" ? "rgba(239,68,68,0.2)" : "rgba(234,179,8,0.2)"}`, borderRadius: "8px", padding: "8px", fontSize: "11px" }}>
                <div>
                  <b style={{ color: p.side==="COMPRA" ? "#22c55e" : p.side==="VENTA" ? "#ef4444" : "#eab308" }}>
                    {p.side !== "INFO" ? `${p.side} +${p.points}` : "MANDATO EXPERTO"} : {p.name}
                  </b>
                  <div style={{ fontSize: "10px", color: "#9ca3af", marginTop: "2px" }}>{p.reason}</div>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* PARÁMETROS DE GESTIÓN DE RIESGO */}
        {s.direction !== "ESPERA" && (
          <div style={{ fontFamily: "monospace", fontSize: "14px", background: "rgba(0,0,0,0.7)", borderRadius: "10px", padding: "16px", border: `1px solid ${isBuy ? "#059669" : "#dc2626"}`, borderLeft: `6px solid ${isBuy ? "#10b981" : "#ef4444"}` }}>
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "8px" }}><span style={{ color: "#a8a29e" }}>EJECUTAR EN:</span><span style={{ fontWeight: "900", color: "#fff", fontSize: "16px" }}>{s.entry?.toFixed(2)}</span></div>
            <div style={{ display: "flex", justifyContent: "space-between", color: "#f87171", marginBottom: "6px", borderBottom: "1px dotted #3f3f46", paddingBottom: "6px" }}><span style={{ color: "#a8a29e" }}>SL (-${dynamicDist.toFixed(1)})</span><span style={{ fontWeight: "700" }}>{s.sl?.toFixed(2)}</span></div>
            <div style={{ display: "flex", justifyContent: "space-between", color: "#34d399" }}><span style={{ color: "#a8a29e" }}>TP DINÁMICO</span><span style={{ fontWeight: "700" }}>{s.tp1?.toFixed(2)}</span></div>
            {alertType === "TAKE_PROFIT" && <div style={{ marginTop: "10px", color: "#fde047", fontSize: "11px", textAlign: "center", fontWeight: "800", background: "rgba(234,179,8,0.1)", padding: "4px", borderRadius: "4px" }}>Cierra la posición manualmente AHORA. El TP Dinámico es una sugerencia.</div>}
          </div>
        )}

      </div>
    </div>
  );
}
