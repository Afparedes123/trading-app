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
        setBackendStatus("Conectado • Feed Spot Institucional v12.0");
      } else throw new Error("vacio");
    } catch (e) {
      setBackendStatus("Reconectando con el servidor...");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
    const id = setInterval(fetchData, 8000);
    const tId = setInterval(() => {
      const now = new Date().toLocaleString("es-EC", {
        timeZone: "America/Guayaquil",
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
        weekday: "short",
        day: "2-digit",
        month: "short"
      });
      setTimeEc(now);
    }, 1000);
    return () => {
      clearInterval(id);
      clearInterval(tId);
    };
  }, []);

  if (loading) {
    return (
      <div style={{ minHeight: "100vh", background: "#0a0a0a", color: "white", display: "flex", alignItems: "center", justifyContent: "center", fontWeight: "700" }}>
        Calibrando Motor Quant Institucional v12.0...
      </div>
    );
  }

  const s = signal;
  if (!s) return null;

  const isBuy = s.direction === "COMPRA";
  const isSell = s.direction === "VENTA";
  const confidence = s.confidence || 50;
  const points = s.points_detail || [];
  const alertText = s.alert || "";
  const alertType = s.alert_type || "WAIT";
  const slDist = s.dist || 3.0;
  const tpDist = s.tp_dist || 3.5;
  const m = s.market_analysis || {};
  const expertFib = m.expert_fib;
  const rsi = m.rsi || 50;

  const getAlertStyle = (type) => {
    if (type === "ENTER") return { bg: "linear-gradient(135deg, rgba(34,197,94,0.16), rgba(16,185,129,0.12))", border: "#22c55e", color: "#4ade80" };
    if (type === "TAKE_PROFIT") return { bg: "linear-gradient(135deg, rgba(234,179,8,0.25), rgba(202,138,4,0.2))", border: "#eab308", color: "#fde047" };
    if (type === "EXIT") return { bg: "linear-gradient(135deg, rgba(239,68,68,0.28), rgba(185,28,28,0.22))", border: "#ef4444", color: "#fca5a5" };
    return { bg: "rgba(24,24,27,0.8)", border: "#52525b", color: "#d4d4d8" };
  };
  const alertStyle = getAlertStyle(alertType);

  return (
    <div style={{ minHeight: "100vh", background: "#09090b", color: "white", padding: "14px", fontFamily: "system-ui" }}>
      <div style={{ maxWidth: "900px", margin: "0 auto" }}>

        {/* CABECERA */}
        <div style={{ display: "flex", justifyContent: "space-between", flexWrap: "wrap", gap: "12px", borderBottom: "1px solid #27272a", paddingBottom: "12px", marginBottom: "12px" }}>
          <div>
            <h1 style={{ fontSize: "22px", fontWeight: "900", margin: 0, color: "#f8fafc" }}>
              EDGEALERT <span style={{ color: "#fbbf24" }}>QUANT v12</span>
            </h1>
            <div style={{ fontSize: "11px", color: "#a1a1aa" }}>{timeEc} • {backendStatus}</div>
            <div style={{ fontSize: "12px", color: "#38bdf8", fontWeight: "800", marginTop: "4px" }}>
              Precio Spot XAU/USD: {s.live_price?.toFixed(2)} • <span style={{ color: "#fbbf24" }}>Lotaje máx cuenta $50: 0.01</span>
            </div>
          </div>
          <div style={{ textAlign: "right" }}>
            <div style={{
              fontSize: "15px", padding: "8px 18px", borderRadius: "8px",
              background: isBuy ? "rgba(34,197,94,0.2)" : isSell ? "rgba(239,68,68,0.2)" : "rgba(161,161,170,0.15)",
              border: `2px solid ${isBuy ? "#22c55e" : isSell ? "#ef4444" : "#71717a"}`,
              color: isBuy ? "#4ade80" : isSell ? "#f87171" : "#d4d4d8",
              fontWeight: "900", letterSpacing: "1px"
            }}>
              {s.direction} {isBuy ? "↑" : isSell ? "↓" : "⏸"}
            </div>
            <div style={{ fontSize: "10px", marginTop: "5px", color: "#a1a1aa" }}>{s.flip_reason}</div>
          </div>
        </div>

        {/* CAJA DE ORDEN DIRECTA (CEREBRO QUANT) */}
        <div style={{
          background: alertStyle.bg,
          border: `2px solid ${alertStyle.border}`,
          borderRadius: "12px",
          padding: "16px",
          marginBottom: "12px",
          boxShadow: (alertType === "TAKE_PROFIT" || alertType === "EXIT") ? `0 0 22px ${alertStyle.border}55` : "none"
        }}>
          <div style={{ fontWeight: "900", fontSize: "18px", color: alertStyle.color, textAlign: "center", textTransform: "uppercase" }}>
            {alertText}
          </div>
          <div style={{ fontSize: "12px", color: "#e4e4e7", textAlign: "center", marginTop: "6px", marginBottom: "14px" }}>
            {s.alert_desc}
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: "8px" }}>
            <div style={{ background: "rgba(0,0,0,0.5)", borderRadius: "8px", padding: "10px", textAlign: "center", border: "1px solid #27272a" }}>
              <div style={{ fontSize: "10px", color: "#a1a1aa", fontWeight: "700" }}>PUNTUACIÓN</div>
              <div style={{ fontSize: "18px", fontWeight: "900", marginTop: "2px" }}>
                <span style={{ color: "#22c55e" }}>{m.buy_score || 0}C</span> <span style={{ color: "#52525b" }}>/</span> <span style={{ color: "#ef4444" }}>{m.sell_score || 0}V</span>
              </div>
            </div>
            <div style={{ background: "rgba(0,0,0,0.5)", borderRadius: "8px", padding: "10px", textAlign: "center", border: "1px solid #27272a" }}>
              <div style={{ fontSize: "10px", color: "#a1a1aa", fontWeight: "700" }}>RSI (14)</div>
              <div style={{ fontSize: "18px", fontWeight: "900", marginTop: "2px", color: rsi >= 68 ? "#ef4444" : rsi <= 32 ? "#22c55e" : "#38bdf8" }}>
                {rsi.toFixed(1)} {rsi >= 68 ? "(Techo)" : rsi <= 32 ? "(Suelo)" : ""}
              </div>
            </div>
            <div style={{ background: "rgba(0,0,0,0.5)", borderRadius: "8px", padding: "10px", textAlign: "center", border: "1px solid #27272a" }}>
              <div style={{ fontSize: "10px", color: "#a1a1aa", fontWeight: "700" }}>CONFIANZA</div>
              <div style={{ fontSize: "18px", fontWeight: "900", marginTop: "2px", color: confidence >= 80 ? "#4ade80" : "#fbbf24" }}>
                {confidence.toFixed(0)}%
              </div>
            </div>
          </div>
        </div>

        {/* MEDIDOR DE ESPACIO LIBRE (ANTI-COMPRAS EN TECHO / ANTI-VENTAS EN SUELO) */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "8px", marginBottom: "12px" }}>
          <div style={{ background: "#141417", border: "1px solid #27272a", borderRadius: "8px", padding: "10px", fontSize: "11px" }}>
            <div style={{ color: "#a1a1aa", fontWeight: "700" }}>TECHO / RESISTENCIA: <b style={{ color: "#f87171" }}>{s.resistance?.toFixed(2)}</b></div>
            <div style={{ marginTop: "4px", color: (m.room_up || 0) < 2.8 ? "#ef4444" : "#4ade80", fontWeight: "800" }}>
              Espacio libre arriba: +${(m.room_up || 0).toFixed(2)} USD {(m.room_up || 0) < 2.8 ? "⛔ (MUY CERCA)" : "✅ (LIBRE)"}
            </div>
          </div>
          <div style={{ background: "#141417", border: "1px solid #27272a", borderRadius: "8px", padding: "10px", fontSize: "11px" }}>
            <div style={{ color: "#a1a1aa", fontWeight: "700" }}>SUELO / SOPORTE: <b style={{ color: "#4ade80" }}>{s.support?.toFixed(2)}</b></div>
            <div style={{ marginTop: "4px", color: (m.room_down || 0) < 2.8 ? "#ef4444" : "#4ade80", fontWeight: "800" }}>
              Espacio libre abajo: -${(m.room_down || 0).toFixed(2)} USD {(m.room_down || 0) < 2.8 ? "⛔ (MUY CERCA)" : "✅ (LIBRE)"}
            </div>
          </div>
        </div>

        {/* MAPA DE ESTRUCTURA Y FIBONACCI */}
        {expertFib && (
          <div style={{ background: "#141417", border: "1px solid #fbbf24", borderRadius: "8px", padding: "12px", marginBottom: "12px" }}>
            <div style={{ fontSize: "10px", color: "#fbbf24", fontWeight: "900", letterSpacing: "1px", marginBottom: "6px" }}>
              ESTRUCTURA INSTITUCIONAL & FIBONACCI ({expertFib.dir} • Rango {expertFib.range} USD)
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: "12px", marginBottom: "4px" }}>
              <span style={{ color: "#a1a1aa" }}>Estado del Mercado:</span>
              <span style={{ fontWeight: "800", color: "#f8fafc" }}>{expertFib.state}</span>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: "12px" }}>
              <span style={{ color: "#a1a1aa" }}>Plan del Experto:</span>
              <span style={{ fontWeight: "800", color: "#38bdf8" }}>{expertFib.action}</span>
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: "6px", marginTop: "8px", textAlign: "center", fontSize: "10px" }}>
              <div style={{ background: "#27272a", padding: "5px", borderRadius: "4px" }}>
                Fib 0.0 (Meta):<br /><b style={{ color: "#fff" }}>{expertFib.levels?.["0"]?.toFixed(2)}</b>
              </div>
              <div style={{ background: "rgba(234,179,8,0.12)", padding: "5px", borderRadius: "4px", border: "1px solid #eab308" }}>
                Zona OTE (0.5 - 0.618):<br /><b style={{ color: "#fde047" }}>{expertFib.levels?.["0.5"]?.toFixed(2)} / {expertFib.levels?.["0.618"]?.toFixed(2)}</b>
              </div>
              <div style={{ background: "#27272a", padding: "5px", borderRadius: "4px" }}>
                Fib 1.0 (Origen):<br /><b style={{ color: "#fff" }}>{expertFib.levels?.["1"]?.toFixed(2)}</b>
              </div>
            </div>
          </div>
        )}

        {/* PARÁMETROS DE EJECUCIÓN (SOLO CUANDO HAY OPERACIÓN ACTIVA) */}
        {s.direction !== "ESPERA" && (
          <div style={{
            fontFamily: "monospace", fontSize: "13px", background: "rgba(0,0,0,0.75)",
            borderRadius: "10px", padding: "14px", marginBottom: "12px",
            border: `1px solid ${isBuy ? "#059669" : "#dc2626"}`,
            borderLeft: `6px solid ${isBuy ? "#10b981" : "#ef4444"}`
          }}>
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "6px" }}>
              <span style={{ color: "#a1a1aa" }}>ENTRADA SPOT (0.01 Lotes):</span>
              <span style={{ fontWeight: "900", color: "#fff", fontSize: "15px" }}>{s.entry?.toFixed(2)}</span>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", color: "#f87171", marginBottom: "6px" }}>
              <span>STOP LOSS DE SEGURIDAD ({isBuy ? "-" : "+"}${slDist.toFixed(2)} USD de tu entrada):</span>
              <span style={{ fontWeight: "800" }}>{s.sl?.toFixed(2)}</span>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", color: "#34d399" }}>
              <span>TAKE PROFIT ESTRUCTURAL ({isBuy ? "+" : "-"}${tpDist.toFixed(2)} USD de tu entrada):</span>
              <span style={{ fontWeight: "800" }}>{s.tp1?.toFixed(2)}</span>
            </div>
          </div>
        )}

        {/* REGISTRO DE CONFLUENCIAS */}
        <div style={{ background: "#141417", border: "1px solid #27272a", borderRadius: "12px", padding: "12px" }}>
          <div style={{ fontWeight: "800", fontSize: "11px", marginBottom: "8px", color: "#a1a1aa", textTransform: "uppercase" }}>
            Auditoría de Confluencias y Filtros de Protección
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
            {points.length === 0 && (
              <div style={{ fontSize: "11px", color: "#71717a", textAlign: "center", padding: "8px" }}>
                Sin gatillos limpios en este segundo. Esperando que el precio llegue a una zona institucional.
              </div>
            )}
            {points.map((p, i) => (
              <div key={i} style={{
                display: "flex", justifyContent: "space-between",
                background: p.side === "COMPRA" ? "rgba(34,197,94,0.08)" : p.side === "VENTA" ? "rgba(239,68,68,0.08)" : "rgba(234,179,8,0.12)",
                border: `1px solid ${p.side === "COMPRA" ? "rgba(34,197,94,0.25)" : p.side === "VENTA" ? "rgba(239,68,68,0.25)" : "rgba(234,179,8,0.35)"}`,
                borderRadius: "8px", padding: "8px", fontSize: "11px"
              }}>
                <div>
                  <b style={{ color: p.side === "COMPRA" ? "#4ade80" : p.side === "VENTA" ? "#f87171" : "#fde047" }}>
                    {p.side !== "INFO" ? `${p.side} (+${p.points})` : "FILTRO DE PROTECCIÓN"}: {p.name}
                  </b>
                  <div style={{ fontSize: "10px", color: "#a1a1aa", marginTop: "2px" }}>{p.reason}</div>
                </div>
              </div>
            ))}
          </div>
        </div>

      </div>
    </div>
  );
}
