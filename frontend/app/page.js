"use client";
import React, { useEffect, useState, useRef } from "react";

const DEFAULT_API = process.env.NEXT_PUBLIC_API_URL || "https://trading-app-jn5a.onrender.com";

// ==============================================================================
// MOTOR DE AUDIO SINTETIZADO + KEEP-ALIVE ANDROID + WAKE LOCK + VIBRACIÓN
// ==============================================================================
let globalAudioCtx = null;
let keepAliveOsc = null;
let wakeLockSentinel = null;

function getAudioContext() {
  if (typeof window === "undefined") return null;
  const AudioCtx = window.AudioContext || window.webkitAudioContext;
  if (!AudioCtx) return null;
  if (!globalAudioCtx) {
    globalAudioCtx = new AudioCtx();
  }
  if (globalAudioCtx.state === "suspended") {
    globalAudioCtx.resume().catch(() => {});
  }
  return globalAudioCtx;
}

function startSilentAudioKeepAlive() {
  try {
    const ctx = getAudioContext();
    if (!ctx || keepAliveOsc) return;
    // Oscilador ultrasilencioso continuo: evita que Android Chrome suspenda la pestaña o apague el motor de voz
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = "sine";
    osc.frequency.setValueAtTime(55, ctx.currentTime);
    gain.gain.setValueAtTime(0.00015, ctx.currentTime);
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.start();
    keepAliveOsc = osc;
  } catch (e) {}
}

async function requestAndroidWakeLock() {
  if (typeof window === "undefined" || !("wakeLock" in navigator)) return false;
  try {
    if (wakeLockSentinel && !wakeLockSentinel.released) return true;
    wakeLockSentinel = await navigator.wakeLock.request("screen");
    return true;
  } catch (e) {
    return false;
  }
}

function sendAndroidSystemNotification(title, body, isUrgent = false) {
  if (typeof window === "undefined") return;
  try {
    if ("vibrate" in navigator) {
      navigator.vibrate(isUrgent ? [600, 200, 600, 200, 800] : [400, 150, 400]);
    }
    const options = {
      body,
      icon: "/icon-192.png",
      badge: "/icon-192.png",
      vibrate: isUrgent ? [600, 200, 600, 200, 800] : [400, 150, 400],
      tag: "edgealert-signal",
      renotify: true,
      requireInteraction: isUrgent,
      data: { url: "/" }
    };

    if ("serviceWorker" in navigator && navigator.serviceWorker.controller) {
      navigator.serviceWorker.controller.postMessage({
        type: "SHOW_NOTIFICATION",
        title,
        options
      });
    } else if ("serviceWorker" in navigator) {
      navigator.serviceWorker.ready.then((reg) => {
        reg.showNotification(title, options);
      }).catch(() => {});
    } else if ("Notification" in window && Notification.permission === "granted") {
      try {
        new Notification(title, options);
      } catch (e) {}
    }
  } catch (e) {
    console.warn("Notification send warning:", e);
  }
}

function playAlertSound(type = "BUY", voiceMessage = "", notifTitle = "") {
  if (typeof window === "undefined") return;
  try {
    const ctx = getAudioContext();
    startSilentAudioKeepAlive();
    if (ctx) {
      if (ctx.state === "suspended") {
        ctx.resume().catch(() => {});
      }
      const now = ctx.currentTime;

      const makeTone = (freq, start, duration, wave = "sine", gainVal = 0.35) => {
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.type = wave;
        osc.frequency.setValueAtTime(freq, start);
        gain.gain.setValueAtTime(gainVal, start);
        gain.gain.exponentialRampToValueAtTime(0.001, start + duration);
        osc.connect(gain);
        gain.connect(ctx.destination);
        osc.start(start);
        osc.stop(start + duration);
      };

      if (type === "EXIT") {
        // Alarma urgente de salida / protección (sirena doble de alta prioridad)
        makeTone(440.0, now, 0.18, "sawtooth", 0.5);
        makeTone(330.0, now + 0.16, 0.18, "sawtooth", 0.5);
        makeTone(440.0, now + 0.34, 0.22, "sawtooth", 0.55);
        makeTone(260.0, now + 0.56, 0.50, "sawtooth", 0.55);
      } else if (type === "TAKE_PROFIT") {
        // Fanfarria dorada de Take Profit / Ganancia
        makeTone(587.33, now, 0.14, "sine", 0.45);
        makeTone(783.99, now + 0.14, 0.14, "sine", 0.45);
        makeTone(987.77, now + 0.28, 0.18, "sine", 0.45);
        makeTone(1174.66, now + 0.44, 0.60, "triangle", 0.5);
      } else if (type === "BUY") {
        // Acorde ascendente de Compra
        makeTone(523.25, now, 0.16, "triangle", 0.4);
        makeTone(659.25, now + 0.15, 0.16, "triangle", 0.4);
        makeTone(783.99, now + 0.30, 0.22, "triangle", 0.4);
        makeTone(1046.5, now + 0.48, 0.50, "sine", 0.45);
      } else if (type === "SELL") {
        // Acorde descendente de Venta
        makeTone(880.0, now, 0.16, "sawtooth", 0.38);
        makeTone(698.46, now + 0.15, 0.16, "sawtooth", 0.38);
        makeTone(587.33, now + 0.30, 0.20, "sawtooth", 0.38);
        makeTone(440.0, now + 0.48, 0.50, "triangle", 0.45);
      }
    }

    if (notifTitle || voiceMessage) {
      sendAndroidSystemNotification(
        notifTitle || (type === "EXIT" ? "🛑 SALIR AHORA XAU/USD" : type === "TAKE_PROFIT" ? "💰 TOMAR GANANCIA XAU/USD" : `🚨 SEÑAL ${type} XAU/USD`),
        voiceMessage,
        type === "EXIT" || type === "TAKE_PROFIT"
      );
    }

    // Síntesis de Voz en Español (TTS)
    if (voiceMessage && "speechSynthesis" in window) {
      window.speechSynthesis.cancel();
      const utterance = new SpeechSynthesisUtterance(voiceMessage);
      utterance.lang = "es-ES";
      utterance.rate = 1.04;
      utterance.pitch = 1.0;
      setTimeout(() => {
        window.speechSynthesis.speak(utterance);
      }, 450);
    }
  } catch (err) {
    console.warn("Audio warning:", err);
  }
}

export default function TrendSpiderPage() {
  // Inicializar estado con caché local si existe para carga instantánea en móviles (0 segundos de espera)
  const [signal, setSignal] = useState(() => {
    if (typeof window !== "undefined") {
      try {
        const cached = localStorage.getItem("ts_quant_signal_cache");
        if (cached) return JSON.parse(cached);
      } catch (e) {}
    }
    return null;
  });

  const [loading, setLoading] = useState(false);
  const [timeEc, setTimeEc] = useState("");
  const [backendStatus, setBackendStatus] = useState("Sincronizando con servidor...");
  const [customApi, setCustomApi] = useState(DEFAULT_API);

  // Control de Alertas Sonoras y Modo Continuo Android
  const [soundEnabled, setSoundEnabled] = useState(true);
  const [androidKeepAwake, setAndroidKeepAwake] = useState(false);
  const [heartbeatCount, setHeartbeatCount] = useState(0);
  const [deferredPrompt, setDeferredPrompt] = useState(null);
  const [isInstallable, setIsInstallable] = useState(false);
  const isFetchingRef = useRef(false);
  const lastFetchStartRef = useRef(0);
  const lastSuccessfulFetchRef = useRef(Date.now());
  const lastAlertRef = useRef({ direction: null, alertType: null, alertText: null });

  // Parámetros de Control TrendSpider
  const [analysisType, setAnalysisType] = useState("Standard");
  const [drawingInput, setDrawingInput] = useState("Wick");
  const [islandGaps, setIslandGaps] = useState("Respect");
  const [qualityFilter, setQualityFilter] = useState("Most Relevant");
  const [heatmapMode, setHeatmapMode] = useState("Horizontal");
  const [truthLocked, setTruthLocked] = useState(false);
  const [lockTimestamp, setLockTimestamp] = useState("");

  // AI Strategy Lab (Pronóstico 20 min)
  const [aiModel, setAiModel] = useState("Ensemble");
  const [tpPct, setTpPct] = useState(0.15);
  const [slPct, setSlPct] = useState(0.10);
  const [horizon, setHorizon] = useState(20);

  // Pestaña visual activa
  const [activeTab, setActiveTab] = useState("chart");

  // Registro del Service Worker y captura del evento de instalación nativa WebAPK
  useEffect(() => {
    if (typeof window !== "undefined" && "serviceWorker" in navigator) {
      navigator.serviceWorker.register("/sw.js").then((reg) => {
        console.log("Service Worker EdgeAlert activo:", reg.scope);
      }).catch((e) => {
        console.warn("SW error:", e);
      });
    }

    const handleBeforeInstall = (e) => {
      e.preventDefault();
      setDeferredPrompt(e);
      setIsInstallable(true);
    };
    window.addEventListener("beforeinstallprompt", handleBeforeInstall);
    return () => {
      window.removeEventListener("beforeinstallprompt", handleBeforeInstall);
    };
  }, []);

  const installPwaApp = async () => {
    if (deferredPrompt) {
      deferredPrompt.prompt();
      const { outcome } = await deferredPrompt.userChoice;
      if (outcome === "accepted") {
        setIsInstallable(false);
        setDeferredPrompt(null);
      }
    } else {
      alert("Para instalar en Android como App Nativa:\n1. Toca los tres puntos (⋮) en Chrome.\n2. Selecciona 'Instalar aplicación' o 'Agregar a la pantalla principal'.");
    }
  };

  const activateAndroidContinuousMode = async (speakConfirmation = false) => {
    const ctx = getAudioContext();
    if (ctx && ctx.state === "suspended") {
      ctx.resume().catch(() => {});
    }
    startSilentAudioKeepAlive();
    const locked = await requestAndroidWakeLock();
    setAndroidKeepAwake(true);
    setSoundEnabled(true);
    if (typeof window !== "undefined" && "Notification" in window) {
      if (Notification.permission === "default") {
        Notification.requestPermission().catch(() => {});
      }
    }
    if (speakConfirmation) {
      playAlertSound(
        "BUY",
        "Modo continuo Android activado. La pantalla y las alertas de voz permanecerán encendidas.",
        "📱 Modo Continuo Android Activo"
      );
    }
    return locked;
  };

  // Desbloqueo universal de audio + Screen Wake Lock en móviles al primer toque y al volver a la app
  useEffect(() => {
    const unlockOnTouch = () => {
      activateAndroidContinuousMode(false);
    };
    const handleVisibility = () => {
      if (document.visibilityState === "visible") {
        requestAndroidWakeLock();
        const ctx = getAudioContext();
        if (ctx && ctx.state === "suspended") ctx.resume().catch(() => {});
        isFetchingRef.current = false;
        lastFetchStartRef.current = 0;
        fetchData();
      }
    };
    const handleOnline = () => {
      isFetchingRef.current = false;
      lastFetchStartRef.current = 0;
      fetchData();
    };
    requestAndroidWakeLock().then((ok) => {
      if (ok) setAndroidKeepAwake(true);
    });
    window.addEventListener("touchstart", unlockOnTouch, { passive: true });
    window.addEventListener("click", unlockOnTouch, { passive: true });
    window.addEventListener("online", handleOnline);
    document.addEventListener("visibilitychange", handleVisibility);
    return () => {
      window.removeEventListener("touchstart", unlockOnTouch);
      window.removeEventListener("click", unlockOnTouch);
      window.removeEventListener("online", handleOnline);
      document.removeEventListener("visibilitychange", handleVisibility);
    };
  }, []);

  const fetchData = async () => {
    const now = Date.now();
    if (isFetchingRef.current) {
      if (now - lastFetchStartRef.current < 12000) {
        return;
      }
      // Si el fetch previo lleva más de 12s pendiente (bloqueado por red o móvil), forzar desbloqueo
      isFetchingRef.current = false;
    }
    isFetchingRef.current = true;
    lastFetchStartRef.current = Date.now();

    setBackendStatus((prev) => (prev.startsWith("🟢") ? prev : "🟡 Conectando con servidor..."));

    try {
      const queryParams = new URLSearchParams({
        analysis_type: analysisType,
        drawing_input: drawingInput,
        island_gaps: islandGaps,
        quality_filter: qualityFilter,
        heatmap_mode: heatmapMode,
        ai_model: aiModel,
        tp_pct: String(tpPct),
        sl_pct: String(slPct),
        horizon: String(horizon),
        truth_lock_ts: truthLocked && lockTimestamp ? String(lockTimestamp) : ""
      });

      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 12000);

      const fetchPromise = (async () => {
        try {
          return await fetch(`${customApi}/signals/live?${queryParams.toString()}`, {
            cache: "no-store",
            signal: controller.signal
          });
        } catch (fetchErr) {
          const isLocalHost = typeof window !== "undefined" && (window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1");
          if (isLocalHost && !customApi.includes("localhost")) {
            try {
              const localRes = await fetch(`http://localhost:8000/signals/live?${queryParams.toString()}`, {
                cache: "no-store",
                signal: controller.signal
              });
              setCustomApi("http://localhost:8000");
              return localRes;
            } catch (e) {}
          }
          throw fetchErr;
        }
      })();

      const hardTimeoutPromise = new Promise((_, reject) =>
        setTimeout(() => reject(new Error("Tiempo de espera agotado (12s)")), 12500)
      );

      let res;
      try {
        res = await Promise.race([fetchPromise, hardTimeoutPromise]);
      } catch (err) {
        // Intento de rescate rápido despertando backend /health
        try {
          const pingCtrl = new AbortController();
          const pingTimer = setTimeout(() => pingCtrl.abort(), 3500);
          const health = await fetch(`${customApi}/health`, { signal: pingCtrl.signal, cache: "no-store" });
          clearTimeout(pingTimer);
          if (health.ok) {
            res = await fetch(`${customApi}/signals/live?${queryParams.toString()}`, { cache: "no-store" });
          }
        } catch (pingErr) {}
        if (!res) throw err;
      } finally {
        clearTimeout(timeoutId);
      }

      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      const sig = Array.isArray(data) && data.length > 0 ? data[0] : data.symbol ? data : null;

      if (sig && sig.symbol?.includes("XAU")) {
        lastSuccessfulFetchRef.current = Date.now();
        const prev = lastAlertRef.current;
        const currDir = sig.direction;
        const currType = sig.alert_type;

        // Evaluar disparo de Alerta Sonora + Vibración + Notificación Android por orden estricto de prioridad
        if (prev.direction !== null && soundEnabled) {
          if (currType === "EXIT" && prev.alertType !== "EXIT") {
            playAlertSound(
              "EXIT",
              `¡Atención! Salir de la operación ahora a ${sig.live_price?.toFixed(0)} dólares para proteger capital. Cierra la posición de inmediato.`,
              `🛑 SALIR AHORA ($${sig.live_price?.toFixed(2)})`
            );
          } else if (currType === "TAKE_PROFIT" && prev.alertType !== "TAKE_PROFIT") {
            playAlertSound(
              "TAKE_PROFIT",
              `¡Objetivo del pronóstico de 20 minutos alcanzado! Salir en ganancia ahora a ${sig.live_price?.toFixed(0)} dólares. Cierra y asegura tu ganancia.`,
              `💰 SALIR EN GANANCIA ($${sig.live_price?.toFixed(2)})`
            );
          } else if (currDir === "COMPRA" && prev.direction !== "COMPRA") {
            playAlertSound(
              "BUY",
              `Atención. Pronóstico de compra a 20 minutos confirmado en oro a ${sig.live_price?.toFixed(0)} dólares. Objetivo en ${sig.tp1?.toFixed(0)} y stop loss estructural en ${sig.sl?.toFixed(0)}. Mantén la posición ante fluctuaciones menores.`,
              `🚀 COMPRA 20 MIN XAU/USD ($${sig.live_price?.toFixed(2)})`
            );
          } else if (currDir === "VENTA" && prev.direction !== "VENTA") {
            playAlertSound(
              "SELL",
              `Atención. Pronóstico de venta a 20 minutos confirmado en oro a ${sig.live_price?.toFixed(0)} dólares. Objetivo en ${sig.tp1?.toFixed(0)} y stop loss estructural en ${sig.sl?.toFixed(0)}. Mantén la posición ante fluctuaciones menores.`,
              `📉 VENTA 20 MIN XAU/USD ($${sig.live_price?.toFixed(2)})`
            );
          }
        }

        lastAlertRef.current = {
          direction: currDir,
          alertType: currType,
          alertText: sig.alert
        };

        setSignal(sig);
        setHeartbeatCount((c) => c + 1);
        setBackendStatus(`🟢 Flujo Activo 0s Lag • ${sig.feed_source || "Spot Institucional"} • M5 Anti-Trampas`);

        try {
          localStorage.setItem("ts_quant_signal_cache", JSON.stringify(sig));
        } catch (e) {}
      } else {
        throw new Error("Datos incompletos");
      }
    } catch (e) {
      const msg = e.name === "AbortError" ? "Servidor respondiendo..." : (e.message || "reconectando");
      setBackendStatus(`🟡 ${msg}`);
    } finally {
      isFetchingRef.current = false;
      setLoading(false);
    }
  };

  useEffect(() => {
    let timerId = null;
    let isMounted = true;

    const pollLoop = async () => {
      try {
        await fetchData();
      } catch (err) {
        console.warn("Poll loop error:", err);
      } finally {
        if (isMounted) {
          timerId = setTimeout(pollLoop, 3000);
        }
      }
    };

    pollLoop();

    // Guardián watchdog: si no se ha recibido señal exitosa en más de 8s, fuerza un nuevo intento
    const watchdogInterval = setInterval(() => {
      if (!isMounted) return;
      const elapsed = Date.now() - lastSuccessfulFetchRef.current;
      if (elapsed > 8000) {
        isFetchingRef.current = false;
        lastFetchStartRef.current = 0;
        fetchData();
      }
    }, 4000);

    const clockInterval = setInterval(() => {
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
      isMounted = false;
      if (timerId) clearTimeout(timerId);
      clearInterval(watchdogInterval);
      clearInterval(clockInterval);
    };
  }, [analysisType, drawingInput, islandGaps, qualityFilter, heatmapMode, aiModel, tpPct, slPct, horizon, truthLocked, lockTimestamp]);

  const toggleTruthLock = () => {
    if (truthLocked) {
      setTruthLocked(false);
      setLockTimestamp("");
    } else {
      if (signal?.recent_candles?.length > 0) {
        const midCandle = signal.recent_candles[Math.max(0, signal.recent_candles.length - 12)];
        setLockTimestamp(String(midCandle.ts));
        setTruthLocked(true);
      }
    }
  };

  const s = signal || {};
  const isBuy = s.direction === "COMPRA";
  const isSell = s.direction === "VENTA";
  const isWait = s.direction === "ESPERA";
  const alertType = s.alert_type || "WAIT";

  const getAlertColor = (type) => {
    if (type === "TAKE_PROFIT") return { bg: "rgba(234,179,8,0.18)", border: "#eab308", text: "#fde047" };
    if (type === "EXIT") return { bg: "rgba(239,68,68,0.22)", border: "#ef4444", text: "#fca5a5" };
    if (type === "ENTER") return { bg: "rgba(34,197,94,0.18)", border: "#22c55e", text: "#4ade80" };
    return { bg: "rgba(39,39,42,0.6)", border: "#52525b", text: "#d4d4d8" };
  };
  const alertColor = getAlertColor(alertType);

  const trendlines = s.trendlines || [];
  const fib = s.fibonacci || {};
  const heatmap = s.heatmap || {};
  const ai = s.ai_strategy || {};
  const candles = s.recent_candles || [];
  const pointsDetail = s.points_detail || [];
  const signalHistory = s.signal_history || [];
  const m5Struct = s.m5_structure || {};
  const forecast = s.forecast_20m || {};

  return (
    <div style={{
      minHeight: "100vh",
      background: "#08090c",
      color: "#f8fafc",
      padding: "16px",
      fontFamily: "system-ui, -apple-system, sans-serif"
    }}>
      <div style={{ maxWidth: "1150px", margin: "0 auto" }}>

        {/* Banner de Sincronización en Vivo / Reconexión */}
        {!signal && (
          <div style={{
            background: "rgba(245, 158, 11, 0.14)",
            border: "1px solid #f59e0b",
            color: "#fde047",
            padding: "12px 18px",
            borderRadius: "10px",
            marginBottom: "16px",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            flexWrap: "wrap",
            gap: "10px",
            fontSize: "13px"
          }}>
            <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
              <div style={{
                width: "14px",
                height: "14px",
                border: "2px solid #f59e0b",
                borderTop: "2px solid transparent",
                borderRadius: "50%",
                animation: "spin 1s linear infinite"
              }} />
              <span>
                <strong>Iniciando conexión con Render:</strong> {backendStatus}
              </span>
            </div>
            <button
              onClick={() => {
                isFetchingRef.current = false;
                lastFetchStartRef.current = 0;
                setLoading(true);
                setBackendStatus("🟡 Reconectando ahora...");
                fetchData();
              }}
              style={{
                background: "#f59e0b",
                color: "#000",
                border: "none",
                padding: "6px 14px",
                borderRadius: "6px",
                fontWeight: "800",
                cursor: "pointer",
                fontSize: "12px"
              }}
            >
              🔄 Reconectar Ahora
            </button>
          </div>
        )}

        {/* ============================================================== */}
        {/* CABECERA INSTITUCIONAL + MODO CONTINUO ANDROID + AUDIO */}
        {/* ============================================================== */}
        <header style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          flexWrap: "wrap",
          gap: "12px",
          borderBottom: "1px solid #1e2430",
          paddingBottom: "14px",
          marginBottom: "14px"
        }}>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: "8px", flexWrap: "wrap" }}>
              <div style={{
                width: "12px", height: "12px", borderRadius: "50%",
                background: truthLocked ? "#eab308" : "#22c55e",
                boxShadow: `0 0 10px ${truthLocked ? "#eab308" : "#22c55e"}`
              }} />
              <h1 style={{ fontSize: "20px", fontWeight: "900", margin: 0, letterSpacing: "-0.5px" }}>
                EDGEALERT <span style={{ color: "#f59e0b" }}>TRENDSPIDER</span> <span style={{ fontSize: "11px", color: "#4ade80", fontWeight: "700", background: "rgba(34,197,94,0.12)", padding: "2px 7px", borderRadius: "5px", border: "1px solid rgba(34,197,94,0.3)" }}>ANDROID CONTINUO 0s LAG</span>
              </h1>
            </div>
            <div style={{ fontSize: "11px", color: "#94a3b8", marginTop: "4px", display: "flex", alignItems: "center", gap: "8px", flexWrap: "wrap" }}>
              <span>{timeEc} • {backendStatus} • <strong style={{ color: "#4ade80" }}>Latido #{heartbeatCount} (3s)</strong></span>
              <button
                onClick={() => {
                  isFetchingRef.current = false;
                  lastFetchStartRef.current = 0;
                  setLoading(true);
                  setBackendStatus("🟡 Reconectando ahora...");
                  fetchData();
                }}
                style={{
                  background: "rgba(245, 158, 11, 0.2)",
                  color: "#facc15",
                  border: "1px solid #f59e0b",
                  borderRadius: "4px",
                  padding: "2px 8px",
                  fontSize: "10px",
                  fontWeight: "700",
                  cursor: "pointer"
                }}
              >
                🔄 Reconectar
              </button>
            </div>
            <div style={{ fontSize: "12px", color: "#38bdf8", fontWeight: "700", marginTop: "4px" }}>
              XAU/USD SPOT: <span style={{ color: "#fff", fontSize: "15px", fontWeight: "900" }}>${s.live_price ? s.live_price.toFixed(2) : "4142.00"}</span>
              <span style={{ color: "#64748b", marginLeft: "8px" }}>| ATR(14): ${s.atr ? s.atr.toFixed(2) : "2.80"}</span>
              <span style={{ color: "#f59e0b", marginLeft: "8px" }}>| {m5Struct.structure || "M5 Activa"}</span>
            </div>
          </div>

          {/* Botones de Modo Continuo Android, Audio y Estado */}
          <div style={{ display: "flex", alignItems: "center", gap: "8px", flexWrap: "wrap" }}>
            <button
              onClick={installPwaApp}
              style={{
                background: "linear-gradient(135deg, #10b981, #059669)",
                color: "#ffffff",
                border: "1px solid #34d399",
                borderRadius: "8px",
                padding: "8px 12px",
                fontSize: "11px",
                fontWeight: "900",
                cursor: "pointer",
                display: "flex",
                alignItems: "center",
                gap: "6px",
                boxShadow: "0 2px 8px rgba(16, 185, 129, 0.3)"
              }}
            >
              📲 INSTALAR APP EN ANDROID (WebAPK)
            </button>

            <button
              onClick={() => activateAndroidContinuousMode(true)}
              style={{
                background: androidKeepAwake ? "rgba(14, 165, 233, 0.2)" : "linear-gradient(135deg, #f59e0b, #ea580c)",
                color: androidKeepAwake ? "#38bdf8" : "#000",
                border: `1px solid ${androidKeepAwake ? "#0ea5e9" : "#facc15"}`,
                borderRadius: "8px",
                padding: "8px 12px",
                fontSize: "11px",
                fontWeight: "900",
                cursor: "pointer",
                display: "flex",
                alignItems: "center",
                gap: "6px"
              }}
            >
              {androidKeepAwake ? "📱 PANTALLA SIEMPRE ENCENDIDA (Activo)" : "📱 ACTIVAR MODO CONTINUO ANDROID"}
            </button>

            <button
              onClick={() => {
                const nextState = !soundEnabled;
                setSoundEnabled(nextState);
                if (nextState) {
                  activateAndroidContinuousMode(true);
                }
              }}
              style={{
                background: soundEnabled ? "rgba(34, 197, 94, 0.18)" : "#1e293b",
                color: soundEnabled ? "#4ade80" : "#94a3b8",
                border: `1px solid ${soundEnabled ? "#22c55e" : "#475569"}`,
                borderRadius: "8px",
                padding: "8px 12px",
                fontSize: "11px",
                fontWeight: "800",
                cursor: "pointer",
                display: "flex",
                alignItems: "center",
                gap: "6px"
              }}
            >
              {soundEnabled ? "🔊 VOZ + ALARMA + VIBRACIÓN" : "🔇 AUDIO SILENCIADO"}
            </button>

            <button
              onClick={() => playAlertSound("TAKE_PROFIT", "Prueba de sonido y vibración en Android. El sistema avisará cada entrada y salida en tiempo real.", "🔔 Prueba de Alerta Android")}
              style={{
                background: "#1e293b",
                color: "#facc15",
                border: "1px solid #f59e0b",
                borderRadius: "8px",
                padding: "8px 12px",
                fontSize: "11px",
                fontWeight: "800",
                cursor: "pointer"
              }}
            >
              🔔 PROBAR ALERTA
            </button>

            <div style={{
              padding: "8px 18px",
              borderRadius: "10px",
              background: isBuy ? "rgba(34,197,94,0.18)" : isSell ? "rgba(239,68,68,0.18)" : "rgba(39,39,42,0.7)",
              border: `2px solid ${isBuy ? "#22c55e" : isSell ? "#ef4444" : "#71717a"}`,
              color: isBuy ? "#4ade80" : isSell ? "#f87171" : "#e4e4e7",
              textAlign: "center"
            }}>
              <div style={{ fontSize: "15px", fontWeight: "900", letterSpacing: "1px" }}>
                {s.direction} {isBuy ? "▲" : isSell ? "▼" : "⏸"}
              </div>
              <div style={{ fontSize: "10px", opacity: 0.85 }}>
                Confianza: {s.confidence}%
              </div>
            </div>
          </div>
        </header>

        {/* ============================================================== */}
        {/* BARRA DE PREFERENCIAS DE CONTROL TRENDSPIDER */}
        {/* ============================================================== */}
        <section style={{
          background: "#0f131a",
          border: "1px solid #1e2638",
          borderRadius: "12px",
          padding: "12px 14px",
          marginBottom: "14px",
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))",
          gap: "10px",
          fontSize: "11px"
        }}>
          <div>
            <label style={{ color: "#94a3b8", display: "block", marginBottom: "4px", fontWeight: "700" }}>
              1. SENSIBILIDAD VENTANA
            </label>
            <select
              value={analysisType}
              onChange={(e) => setAnalysisType(e.target.value)}
              style={{
                width: "100%", background: "#1a2130", color: "#fff", border: "1px solid #334155",
                borderRadius: "6px", padding: "6px 8px", fontSize: "11px", fontWeight: "600", outline: "none"
              }}
            >
              <option value="Standard">Standard (Impulso + Retroceso M5)</option>
              <option value="Original">Original (Macro / Tendencias Largas)</option>
              <option value="Enhanced">Enhanced (Micro / Scalping Rápido)</option>
            </select>
          </div>

          <div>
            <label style={{ color: "#94a3b8", display: "block", marginBottom: "4px", fontWeight: "700" }}>
              2. ANCLAJE DE VELA
            </label>
            <select
              value={drawingInput}
              onChange={(e) => setDrawingInput(e.target.value)}
              style={{
                width: "100%", background: "#1a2130", color: "#fff", border: "1px solid #334155",
                borderRadius: "6px", padding: "6px 8px", fontSize: "11px", fontWeight: "600", outline: "none"
              }}
            >
              <option value="Wick">Wick (Mechas H/L Extremas)</option>
              <option value="Body">Body (Cuerpos O/C Apertura/Cierre)</option>
            </select>
          </div>

          <div>
            <label style={{ color: "#94a3b8", display: "block", marginBottom: "4px", fontWeight: "700" }}>
              3. GAPS (3x ATR)
            </label>
            <select
              value={islandGaps}
              onChange={(e) => setIslandGaps(e.target.value)}
              style={{
                width: "100%", background: "#1a2130", color: "#fff", border: "1px solid #334155",
                borderRadius: "6px", padding: "6px 8px", fontSize: "11px", fontWeight: "600", outline: "none"
              }}
            >
              <option value="Respect">Respect (Bloquear sobre Gaps)</option>
              <option value="Ignore">Ignore (Conectar cruzando vacíos)</option>
            </select>
          </div>

          <div>
            <label style={{ color: "#94a3b8", display: "block", marginBottom: "4px", fontWeight: "700" }}>
              4. FILTRO DE CALIDAD
            </label>
            <select
              value={qualityFilter}
              onChange={(e) => setQualityFilter(e.target.value)}
              style={{
                width: "100%", background: "#1a2130", color: "#fff", border: "1px solid #334155",
                borderRadius: "6px", padding: "6px 8px", fontSize: "11px", fontWeight: "600", outline: "none"
              }}
            >
              <option value="Most Relevant">Most Relevant (Top 1% Score)</option>
              <option value="Moderately Relevant">Moderately Relevant (Top 10%)</option>
              <option value="Unfiltered">Unfiltered (Todas)</option>
            </select>
          </div>

          <div>
            <label style={{ color: "#94a3b8", display: "block", marginBottom: "4px", fontWeight: "700" }}>
              5. MAPA DE CALOR 40x60
            </label>
            <select
              value={heatmapMode}
              onChange={(e) => setHeatmapMode(e.target.value)}
              style={{
                width: "100%", background: "#1a2130", color: "#fff", border: "1px solid #334155",
                borderRadius: "6px", padding: "6px 8px", fontSize: "11px", fontWeight: "600", outline: "none"
              }}
            >
              <option value="Horizontal">Horizontal (Order Blocks)</option>
              <option value="Depth">Depth (Difusión 2D Confluencia)</option>
              <option value="Trends">Trends (Intersecciones Crudas)</option>
              <option value="Off">Desactivado</option>
            </select>
          </div>

          <div>
            <label style={{ color: "#94a3b8", display: "block", marginBottom: "4px", fontWeight: "700" }}>
              6. TRUTH IN ANALYSIS
            </label>
            <button
              onClick={toggleTruthLock}
              style={{
                width: "100%",
                background: truthLocked ? "#eab308" : "#1e293b",
                color: truthLocked ? "#000" : "#cbd5e1",
                border: `1px solid ${truthLocked ? "#facc15" : "#475569"}`,
                borderRadius: "6px",
                padding: "6px 8px",
                fontSize: "11px",
                fontWeight: "800",
                cursor: "pointer"
              }}
            >
              {truthLocked ? "🟡 BLOQUEADO (OOS Test)" : "🔴 DESBLOQUEADO (En Vivo)"}
            </button>
          </div>
        </section>

        {/* ============================================================== */}
        {/* BANNER DE ORDEN Y CONTROL ANTI-RUIDO */}
        {/* ============================================================== */}
        <section style={{
          background: alertColor.bg,
          border: `2px solid ${alertColor.border}`,
          borderRadius: "12px",
          padding: "16px",
          marginBottom: "14px",
          boxShadow: `0 4px 20px ${alertColor.border}22`
        }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "8px" }}>
            <div style={{ fontWeight: "900", fontSize: "17px", color: alertColor.text, textTransform: "uppercase" }}>
              {s.alert}
            </div>
            <div style={{ fontSize: "11px", color: "#cbd5e1", background: "rgba(0,0,0,0.4)", padding: "4px 10px", borderRadius: "6px" }}>
              {s.flip_reason}
            </div>
          </div>
          <div style={{ fontSize: "12px", color: "#e2e8f0", marginTop: "6px", lineHeight: "1.5" }}>
            {s.alert_desc}
          </div>

          <div style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(130px, 1fr))",
            gap: "8px",
            marginTop: "12px"
          }}>
            <div style={{ background: "rgba(0,0,0,0.45)", borderRadius: "8px", padding: "8px 10px", border: "1px solid #1e293b", textAlign: "center" }}>
              <div style={{ fontSize: "10px", color: "#94a3b8", fontWeight: "700" }}>PUNTUACIÓN QUANT</div>
              <div style={{ fontSize: "16px", fontWeight: "900", marginTop: "2px" }}>
                <span style={{ color: "#4ade80" }}>{s.buy_score || 0}C</span> <span style={{ color: "#475569" }}>/</span> <span style={{ color: "#f87171" }}>{s.sell_score || 0}V</span>
              </div>
            </div>

            <div style={{ background: "rgba(0,0,0,0.45)", borderRadius: "8px", padding: "8px 10px", border: "1px solid #1e293b", textAlign: "center" }}>
              <div style={{ fontSize: "10px", color: "#94a3b8", fontWeight: "700" }}>RETROCESO FIB M5</div>
              <div style={{ fontSize: "16px", fontWeight: "900", marginTop: "2px", color: "#facc15" }}>
                {((m5Struct.fib_ret || 0.5) * 100).toFixed(0)}%
              </div>
            </div>

            <div style={{ background: "rgba(0,0,0,0.45)", borderRadius: "8px", padding: "8px 10px", border: "1px solid #1e293b", textAlign: "center" }}>
              <div style={{ fontSize: "10px", color: "#94a3b8", fontWeight: "700" }}>TECHO M5 / RESISTENCIA</div>
              <div style={{ fontSize: "15px", fontWeight: "900", marginTop: "2px", color: "#f87171" }}>
                ${s.resistance?.toFixed(2)} (+${s.room_up?.toFixed(1)})
              </div>
            </div>

            <div style={{ background: "rgba(0,0,0,0.45)", borderRadius: "8px", padding: "8px 10px", border: "1px solid #1e293b", textAlign: "center" }}>
              <div style={{ fontSize: "10px", color: "#94a3b8", fontWeight: "700" }}>PISO M5 / SOPORTE</div>
              <div style={{ fontSize: "15px", fontWeight: "900", marginTop: "2px", color: "#4ade80" }}>
                ${s.support?.toFixed(2)} (-${s.room_down?.toFixed(1)})
              </div>
            </div>

            <div style={{ background: "rgba(0,0,0,0.45)", borderRadius: "8px", padding: "8px 10px", border: "1px solid #1e293b", textAlign: "center" }}>
              <div style={{ fontSize: "10px", color: "#94a3b8", fontWeight: "700" }}>ALERTAS HOY</div>
              <div style={{ fontSize: "16px", fontWeight: "900", marginTop: "2px", color: "#38bdf8" }}>
                {signalHistory.length} registradas
              </div>
            </div>
          </div>
        </section>

        {/* ============================================================== */}
        {/* PRONÓSTICO DE MERCADO ~20 MINUTOS (ESTRUCTURAL + NUMÉRICO IA) */}
        {/* ============================================================== */}
        <section style={{
          background: "linear-gradient(135deg, #0b1120 0%, #111827 100%)",
          border: `2px solid ${isBuy ? "#059669" : isSell ? "#dc2626" : "#2563eb"}`,
          borderRadius: "14px",
          padding: "16px",
          marginBottom: "14px",
          boxShadow: `0 8px 24px rgba(0,0,0,0.5)`
        }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "10px", marginBottom: "12px" }}>
            <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
              <div style={{
                background: isBuy ? "#10b981" : isSell ? "#ef4444" : "#3b82f6",
                color: "#fff",
                width: "36px",
                height: "36px",
                borderRadius: "10px",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                fontSize: "18px",
                fontWeight: "900",
                boxShadow: `0 0 12px ${isBuy ? "#10b98188" : isSell ? "#ef444488" : "#3b82f688"}`
              }}>
                {isBuy ? "▲" : isSell ? "▼" : "⏳"}
              </div>
              <div>
                <div style={{ fontSize: "14px", fontWeight: "900", color: "#f8fafc", letterSpacing: "-0.2px" }}>
                  PRONÓSTICO DE DIRECCIÓN ~20 MINUTOS
                </div>
                <div style={{ fontSize: "11px", color: "#94a3b8" }}>
                  Estructuras previas + Modelos Numéricos (Protegido contra fluctuaciones de 1 vela)
                </div>
              </div>
            </div>

            <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
              <div style={{
                background: isBuy ? "rgba(34, 197, 94, 0.16)" : isSell ? "rgba(239, 68, 68, 0.16)" : "rgba(59, 130, 246, 0.16)",
                border: `1px solid ${isBuy ? "#22c55e" : isSell ? "#ef4444" : "#3b82f6"}`,
                color: isBuy ? "#4ade80" : isSell ? "#f87171" : "#60a5fa",
                padding: "6px 12px",
                borderRadius: "20px",
                fontSize: "12px",
                fontWeight: "900",
                letterSpacing: "0.5px"
              }}>
                {forecast.direction || s.direction} • {forecast.ai_probability || s.confidence || 75}% IA
              </div>
            </div>
          </div>

          {/* Barra de progreso de tiempo de maduración 20 Minutos */}
          {!isWait && (
            <div style={{
              background: "rgba(0,0,0,0.5)",
              border: "1px solid #1e293b",
              borderRadius: "10px",
              padding: "10px 14px",
              marginBottom: "12px"
            }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", fontSize: "11px", marginBottom: "6px" }}>
                <span style={{ color: "#e2e8f0" }}>
                  ⏱️ <strong>Maduración del Pronóstico:</strong> Minuto <b style={{ color: "#facc15", fontSize: "13px" }}>{forecast.elapsed_minutes || 0}</b> de 20 min
                </span>
                <span style={{ color: "#38bdf8", fontWeight: "800" }}>
                  ~{forecast.remaining_minutes !== undefined ? forecast.remaining_minutes : 20} min restantes
                </span>
              </div>
              <div style={{ width: "100%", height: "9px", background: "#1e293b", borderRadius: "5px", overflow: "hidden" }}>
                <div style={{
                  width: `${Math.min(100, Math.max(5, ((forecast.elapsed_minutes || 0) / 20) * 100))}%`,
                  height: "100%",
                  background: isBuy ? "linear-gradient(90deg, #10b981, #34d399)" : "linear-gradient(90deg, #ef4444, #f87171)",
                  borderRadius: "5px",
                  transition: "width 0.4s ease"
                }} />
              </div>
              <div style={{ fontSize: "10px", color: "#94a3b8", marginTop: "6px" }}>
                🛡️ Si el precio retrocede dentro del canal, mantén la posición. El sistema no saldrá por mechas aisladas.
              </div>
            </div>
          )}

          {/* Grid de 4 Pilares del Pronóstico Cuantitativo */}
          <div style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(130px, 1fr))",
            gap: "8px"
          }}>
            <div style={{ background: "rgba(0,0,0,0.4)", borderRadius: "8px", padding: "10px", border: "1px solid #1e293b" }}>
              <div style={{ fontSize: "10px", color: "#94a3b8", fontWeight: "700" }}>GANANCIA A 20 MIN</div>
              <div style={{ fontSize: "16px", fontWeight: "900", color: "#34d399", marginTop: "2px" }}>
                +${(forecast.expected_gain_usd || s.tp_dist || 5.5).toFixed(2)} USD
              </div>
              <div style={{ fontSize: "10px", color: "#64748b", marginTop: "2px" }}>
                Precio Meta: ${forecast.target_price?.toFixed(2) || s.tp1?.toFixed(2)}
              </div>
            </div>

            <div style={{ background: "rgba(0,0,0,0.4)", borderRadius: "8px", padding: "10px", border: "1px solid #1e293b" }}>
              <div style={{ fontSize: "10px", color: "#94a3b8", fontWeight: "700" }}>SL ESTRUCTURAL</div>
              <div style={{ fontSize: "16px", fontWeight: "900", color: "#f87171", marginTop: "2px" }}>
                ${forecast.structural_sl?.toFixed(2) || s.sl?.toFixed(2)}
              </div>
              <div style={{ fontSize: "10px", color: "#64748b", marginTop: "2px" }}>
                Anclado a pivote mayor
              </div>
            </div>

            <div style={{ background: "rgba(0,0,0,0.4)", borderRadius: "8px", padding: "10px", border: "1px solid #1e293b" }}>
              <div style={{ fontSize: "10px", color: "#94a3b8", fontWeight: "700" }}>PROBABILIDAD IA</div>
              <div style={{ fontSize: "16px", fontWeight: "900", color: "#38bdf8", marginTop: "2px" }}>
                {forecast.ai_probability || s.confidence || 75}%
              </div>
              <div style={{ fontSize: "10px", color: "#64748b", marginTop: "2px" }}>
                Horizonte 20 velas
              </div>
            </div>

            <div style={{ background: "rgba(0,0,0,0.4)", borderRadius: "8px", padding: "10px", border: "1px solid #1e293b" }}>
              <div style={{ fontSize: "10px", color: "#94a3b8", fontWeight: "700" }}>ESTADO ANTI-RUIDO</div>
              <div style={{ fontSize: "12px", fontWeight: "800", color: "#facc15", marginTop: "4px" }}>
                {forecast.in_cooldown ? `⏳ Enfriamiento (${forecast.cooldown_remaining_sec}s)` : "🛡️ Inmune a 1 vela"}
              </div>
              <div style={{ fontSize: "10px", color: "#64748b", marginTop: "2px" }}>
                Filtro Whipsaw activo
              </div>
            </div>
          </div>
        </section>

        {/* ============================================================== */}
        {/* PARÁMETROS DE EJECUCIÓN (CUANDO HAY OPERACIÓN ACTIVA) */}
        {/* ============================================================== */}
        {!isWait && (
          <section style={{
            background: "rgba(15, 23, 42, 0.75)",
            border: `1px solid ${isBuy ? "#059669" : "#dc2626"}`,
            borderLeft: `6px solid ${isBuy ? "#10b981" : "#ef4444"}`,
            borderRadius: "10px",
            padding: "14px",
            marginBottom: "14px",
            fontFamily: "monospace",
            fontSize: "13px"
          }}>
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "6px" }}>
              <span style={{ color: "#94a3b8" }}>PRECIO ENTRADA (0.01 lotes):</span>
              <span style={{ fontWeight: "900", color: "#fff", fontSize: "15px" }}>${s.entry?.toFixed(2)}</span>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", color: "#f87171", marginBottom: "6px" }}>
              <span>STOP LOSS DE SEGURIDAD (Riesgo ${s.dist?.toFixed(2)}):</span>
              <span style={{ fontWeight: "800" }}>${s.sl?.toFixed(2)}</span>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", color: "#34d399", marginBottom: "6px" }}>
              <span>TAKE PROFIT 1 - OBJETIVO IMPULSO (+${s.tp_dist?.toFixed(2)}):</span>
              <span style={{ fontWeight: "800" }}>${s.tp1?.toFixed(2)}</span>
            </div>
            {s.tp2 > 0 && (
              <div style={{ display: "flex", justifyContent: "space-between", color: "#6ee7b7" }}>
                <span>TAKE PROFIT 2 - EXTENSIÓN FIB 1.618:</span>
                <span style={{ fontWeight: "800" }}>${s.tp2?.toFixed(2)}</span>
              </div>
            )}
          </section>
        )}

        {/* ============================================================== */}
        {/* PESTAÑAS DE VISUALIZACIÓN */}
        {/* ============================================================== */}
        <div style={{ display: "flex", flexWrap: "wrap", gap: "6px", marginBottom: "12px", borderBottom: "1px solid #1e2638", paddingBottom: "6px" }}>
          {[
            { id: "chart", label: "📊 GRÁFICO VECTORIAL TRENDSPIDER" },
            { id: "history", label: `🕒 BITÁCORA DE ALERTAS (${signalHistory.length})` },
            { id: "strategy_lab", label: "🧬 AI STRATEGY LAB (ML)" },
            { id: "audit", label: "🛡️ AUDITORÍA DE CONFLUENCIAS" }
          ].map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              style={{
                background: activeTab === tab.id ? "#1e293b" : "transparent",
                color: activeTab === tab.id ? "#f59e0b" : "#94a3b8",
                border: activeTab === tab.id ? "1px solid #f59e0b" : "1px solid transparent",
                borderRadius: "6px",
                padding: "8px 14px",
                fontSize: "11px",
                fontWeight: "800",
                cursor: "pointer"
              }}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* ============================================================== */}
        {/* CONTENIDO 1: GRÁFICO VECTORIAL (SVG INTERACTIVO) */}
        {/* ============================================================== */}
        {activeTab === "chart" && (
          <section style={{
            background: "#0c0f17",
            border: "1px solid #1e2638",
            borderRadius: "12px",
            padding: "14px",
            marginBottom: "14px"
          }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "10px", flexWrap: "wrap", gap: "6px" }}>
              <div style={{ fontSize: "12px", fontWeight: "800", color: "#f8fafc" }}>
                Estructura Impulso/Retroceso + Vectores Auto-Trendlines + Zona Dorada Fibonacci (0.382 - 0.618)
              </div>
              <div style={{ fontSize: "10px", color: "#94a3b8" }}>
                Líneas activas: <b style={{ color: "#38bdf8" }}>{trendlines.length}</b> • Zona Dorada: <b style={{ color: "#facc15" }}>0.382 - 0.618 OTE</b>
              </div>
            </div>

            <TrendSpiderChartCanvas
              candles={candles}
              trendlines={trendlines}
              fib={fib}
              heatmap={heatmap}
              livePrice={s.live_price}
              truthLocked={truthLocked}
              lockTimestamp={lockTimestamp}
            />
          </section>
        )}

        {/* ============================================================== */}
        {/* CONTENIDO 2: BITÁCORA HISTÓRICA DE ALERTAS (VERIFICACIÓN 8AM-11AM) */}
        {/* ============================================================== */}
        {activeTab === "history" && (
          <section style={{
            background: "#0c0f17",
            border: "1px solid #1e2638",
            borderRadius: "12px",
            padding: "16px",
            marginBottom: "14px"
          }}>
            <div style={{ fontSize: "14px", fontWeight: "900", color: "#f59e0b", marginBottom: "4px" }}>
              BITÁCORA HISTÓRICA DE ENTRADAS Y SALIDAS (GUARDADO AUTOMÁTICO)
            </div>
            <div style={{ fontSize: "12px", color: "#94a3b8", marginBottom: "14px" }}>
              Aquí puedes verificar todas las señales de Compra, Venta, Break-Even y Take Profit que el motor disparó durante las estructuras previas aunque no estuvieras mirando la pantalla.
            </div>

            <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
              {signalHistory.length === 0 ? (
                <div style={{ fontSize: "12px", color: "#64748b", textAlign: "center", padding: "20px" }}>
                  No hay eventos registrados todavía en esta sesión.
                </div>
              ) : (
                signalHistory.map((h, i) => {
                  const isEnter = h.event_type === "ENTER";
                  const isTp = h.event_type === "TAKE_PROFIT";
                  const isBe = h.event_type === "BREAK_EVEN";
                  const badgeColor = isTp
                    ? "#eab308"
                    : isBe
                    ? "#38bdf8"
                    : h.direction === "COMPRA"
                    ? "#22c55e"
                    : "#ef4444";

                  return (
                    <div
                      key={h.id || i}
                      style={{
                        background: "#131824",
                        border: "1px solid #1e293b",
                        borderLeft: `4px solid ${badgeColor}`,
                        borderRadius: "8px",
                        padding: "10px 12px",
                        display: "flex",
                        justifyContent: "space-between",
                        alignItems: "center",
                        flexWrap: "wrap",
                        gap: "8px"
                      }}
                    >
                      <div>
                        <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                          <span style={{
                            fontSize: "10px",
                            fontWeight: "900",
                            padding: "2px 7px",
                            borderRadius: "4px",
                            background: `${badgeColor}22`,
                            color: badgeColor
                          }}>
                            {h.event_type} • {h.direction}
                          </span>
                          <span style={{ fontSize: "12px", fontWeight: "800", color: "#fff" }}>
                            Precio: ${h.price?.toFixed(2)}
                          </span>
                          {isEnter && (
                            <span style={{ fontSize: "11px", color: "#94a3b8" }}>
                              (SL: ${h.sl?.toFixed(2)} | TP1: ${h.tp1?.toFixed(2)})
                            </span>
                          )}
                        </div>
                        <div style={{ fontSize: "11px", color: "#cbd5e1", marginTop: "4px" }}>
                          {h.reason}
                        </div>
                      </div>
                      <div style={{ fontSize: "11px", fontFamily: "monospace", color: "#94a3b8", fontWeight: "700" }}>
                        🕒 {h.time_ec} EC
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          </section>
        )}

        {/* ============================================================== */}
        {/* CONTENIDO 3: AI STRATEGY LAB DASHBOARD */}
        {/* ============================================================== */}
        {activeTab === "strategy_lab" && (
          <section style={{
            background: "#0c0f17",
            border: "1px solid #1e2638",
            borderRadius: "12px",
            padding: "16px",
            marginBottom: "14px"
          }}>
            <div style={{ fontSize: "14px", fontWeight: "900", color: "#f59e0b", marginBottom: "6px" }}>
              AI STRATEGY LAB (CLASIFICADORES ESTADÍSTICOS & MACHINE LEARNING)
            </div>
            <div style={{ display: " grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: "14px", marginBottom: "16px" }}>
              <div style={{ background: "#131824", padding: "12px", borderRadius: "8px", border: "1px solid #1e293b" }}>
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: "11px", fontWeight: "700", marginBottom: "6px" }}>
                  <span style={{ color: "#94a3b8" }}>TAKE PROFIT OBJETIVO:</span>
                  <span style={{ color: "#34d399" }}>{tpPct}% (~${(tpPct * (s.live_price || 4120) / 100).toFixed(2)})</span>
                </div>
                <input
                  type="range" min="0.06" max="0.25" step="0.01" value={tpPct}
                  onChange={(e) => setTpPct(parseFloat(e.target.value))}
                  style={{ width: "100%", accentColor: "#10b981" }}
                />
              </div>

              <div style={{ background: "#131824", padding: "12px", borderRadius: "8px", border: "1px solid #1e293b" }}>
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: "11px", fontWeight: "700", marginBottom: "6px" }}>
                  <span style={{ color: "#94a3b8" }}>STOP LOSS MÁXIMO:</span>
                  <span style={{ color: "#f87171" }}>{slPct}% (~${(slPct * (s.live_price || 4120) / 100).toFixed(2)})</span>
                </div>
                <input
                  type="range" min="0.04" max="0.18" step="0.01" value={slPct}
                  onChange={(e) => setSlPct(parseFloat(e.target.value))}
                  style={{ width: "100%", accentColor: "#ef4444" }}
                />
              </div>
            </div>
          </section>
        )}

        {/* ============================================================== */}
        {/* CONTENIDO 4: AUDITORÍA DE CONFLUENCIAS */}
        {/* ============================================================== */}
        {activeTab === "audit" && (
          <section style={{
            background: "#0c0f17",
            border: "1px solid #1e2638",
            borderRadius: "12px",
            padding: "16px",
            marginBottom: "14px"
          }}>
            <div style={{ fontSize: "13px", fontWeight: "900", color: "#f8fafc", marginBottom: "8px", textTransform: "uppercase" }}>
              Auditoría Matemática de Confluencias
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
              {pointsDetail.length === 0 ? (
                <div style={{ fontSize: "12px", color: "#64748b", textAlign: "center", padding: "16px" }}>
                  Monitoreando el mercado en busca del siguiente cierre de confirmación en zona Fibonacci.
                </div>
              ) : (
                pointsDetail.map((item, idx) => (
                  <div
                    key={idx}
                    style={{
                      background: item.side === "COMPRA" ? "rgba(34,197,94,0.08)" : "rgba(239,68,68,0.08)",
                      border: `1px solid ${item.side === "COMPRA" ? "rgba(34,197,94,0.3)" : "rgba(239,68,68,0.3)"}`,
                      borderRadius: "8px",
                      padding: "10px 12px"
                    }}
                  >
                    <div style={{
                      fontSize: "12px",
                      fontWeight: "800",
                      color: item.side === "COMPRA" ? "#4ade80" : "#f87171"
                    }}>
                      [{item.module}] {item.title} (+{item.weight} pts)
                    </div>
                    <div style={{ fontSize: "11px", color: "#94a3b8", marginTop: "3px" }}>
                      {item.desc}
                    </div>
                  </div>
                ))
              )}
            </div>
          </section>
        )}

      </div>
    </div>
  );
}

// ==============================================================================
// COMPONENTE: RENDERIZADOR DE GRÁFICO VECTORIAL TRENDSPIDER
// ==============================================================================
function TrendSpiderChartCanvas({ candles, trendlines, fib, heatmap, livePrice, truthLocked, lockTimestamp }) {
  if (!candles || candles.length === 0) {
    return <div style={{ height: "340px", display: "flex", alignItems: "center", justifyContent: "center", color: "#64748b" }}>Cargando gráfico...</div>;
  }

  const width = 1000;
  const height = 360;
  const paddingY = 25;
  const paddingRight = 65;

  const highs = candles.map((c) => c.high);
  const lows = candles.map((c) => c.low);
  const maxP = Math.max(...highs, livePrice || 0) + 0.8;
  const minP = Math.min(...lows, livePrice || 999999) - 0.8;
  const priceSpan = Math.max(maxP - minP, 1.0);

  const priceToY = (price) => {
    return paddingY + ((maxP - price) / priceSpan) * (height - paddingY * 2);
  };

  const candleWidth = (width - paddingRight) / Math.max(candles.length, 1);

  let lockX = null;
  if (truthLocked && lockTimestamp) {
    const lockTsNum = parseInt(lockTimestamp);
    const idx = candles.findIndex((c) => c.ts >= lockTsNum);
    if (idx !== -1) {
      lockX = idx * candleWidth + candleWidth / 2;
    }
  }

  const fibLevels = fib.levels || {};
  const fib382 = fibLevels["0.382"];
  const fib618 = fibLevels["0.618"];

  const gzTopY = fib382 && fib618 ? Math.min(priceToY(fib382), priceToY(fib618)) : null;
  const gzBottomY = fib382 && fib618 ? Math.max(priceToY(fib382), priceToY(fib618)) : null;
  const gzHeight = gzTopY !== null && gzBottomY !== null ? Math.max(gzBottomY - gzTopY, 2) : 0;

  return (
    <div style={{ position: "relative", width: "100%", overflowX: "auto" }}>
      <svg viewBox={`0 0 ${width} ${height}`} style={{ width: "100%", height: "auto", display: "block" }}>
        <rect width={width} height={height} fill="#0b0e14" />

        {[0, 0.25, 0.5, 0.75, 1].map((pct, i) => {
          const y = paddingY + pct * (height - paddingY * 2);
          const p = maxP - pct * priceSpan;
          return (
            <g key={i}>
              <line x1={0} y1={y} x2={width - paddingRight} y2={y} stroke="#171d29" strokeDasharray="3 3" />
              <text x={width - paddingRight + 6} y={y + 4} fill="#64748b" fontSize="10" fontFamily="monospace">
                {p.toFixed(2)}
              </text>
            </g>
          );
        })}

        {gzTopY !== null && (
          <g>
            <rect
              x={0}
              y={gzTopY}
              width={width - paddingRight}
              height={gzHeight}
              fill="rgba(245, 158, 11, 0.08)"
              stroke="rgba(245, 158, 11, 0.35)"
              strokeDasharray="4 4"
            />
            <text x={10} y={gzTopY + 14} fill="#f59e0b" fontSize="10" fontWeight="800">
              ZONA DORADA FIBONACCI (0.382 - 0.618 OTE)
            </text>
          </g>
        )}

        {["0.0", "0.5", "1.0"].map((lvl) => {
          if (!fibLevels[lvl]) return null;
          const y = priceToY(fibLevels[lvl]);
          return (
            <g key={lvl}>
              <line x1={0} y1={y} x2={width - paddingRight} y2={y} stroke="#eab308" strokeWidth="1" strokeDasharray="2 4" opacity="0.6" />
              <text x={width - paddingRight - 65} y={y - 3} fill="#eab308" fontSize="9" fontWeight="700">
                Fib {lvl} (${fibLevels[lvl].toFixed(1)})
              </text>
            </g>
          );
        })}

        {heatmap.mode === "Horizontal" && heatmap.horizontal_profile?.map((hp, i) => {
          if (hp.score < 25) return null;
          const y = priceToY(hp.price);
          const barW = (hp.score / 100) * 120;
          return (
            <rect
              key={i}
              x={0}
              y={y - 2}
              width={barW}
              height={4}
              fill="rgba(56, 189, 248, 0.18)"
              rx="2"
            />
          );
        })}

        {candles.map((c, i) => {
          const x = i * candleWidth + candleWidth / 2;
          const openY = priceToY(c.open);
          const closeY = priceToY(c.close);
          const highY = priceToY(c.high);
          const lowY = priceToY(c.low);
          const isBull = c.close >= c.open;
          const bodyY = Math.min(openY, closeY);
          const bodyH = Math.max(Math.abs(closeY - openY), 1.5);
          const color = isBull ? "#22c55e" : "#ef4444";

          return (
            <g key={c.ts || i}>
              <line x1={x} y1={highY} x2={x} y2={lowY} stroke={color} strokeWidth="1.2" opacity="0.8" />
              <rect
                x={x - candleWidth * 0.35}
                y={bodyY}
                width={Math.max(candleWidth * 0.7, 2)}
                height={bodyH}
                fill={color}
                rx="1"
              />
            </g>
          );
        })}

        {trendlines.map((line, idx) => {
          const isRes = line.kind === "RESISTANCE";
          const lineColor = isRes ? "#38bdf8" : "#4ade80";

          const startCandleIdx = candles.findIndex((c) => c.ts === line.origin_ts);
          const x1 = (startCandleIdx !== -1 ? startCandleIdx : 0) * candleWidth + candleWidth / 2;
          const y1 = priceToY(line.y1);

          const x2 = (candles.length - 1) * candleWidth + candleWidth / 2;
          const y2 = priceToY(line.current_y);

          const hasBreakout = line.breakout === "BULLISH_BREAKOUT" || line.breakout === "BEARISH_BREAKOUT";

          return (
            <g key={idx}>
              <line
                x1={x1}
                y1={y1}
                x2={x2}
                y2={y2}
                stroke={lineColor}
                strokeWidth="2.2"
                strokeLinecap="round"
                opacity="0.9"
              />
              <rect x={x2 - 50} y={y2 - 16} width="46" height="13" fill="#000" rx="3" stroke={lineColor} strokeWidth="1" />
              <text x={x2 - 27} y={y2 - 6} fill={lineColor} fontSize="9" fontWeight="900" textAnchor="middle">
                ★ {line.score?.toFixed(0)}
              </text>
              {hasBreakout && (
                <circle
                  cx={x2}
                  cy={y2}
                  r="6"
                  fill={line.breakout === "BULLISH_BREAKOUT" ? "#22c55e" : "#ef4444"}
                  stroke="#fff"
                  strokeWidth="2"
                />
              )}
            </g>
          );
        })}

        {livePrice && (
          <g>
            <line
              x1={0}
              y1={priceToY(livePrice)}
              x2={width - paddingRight}
              y2={priceToY(livePrice)}
              stroke="#fbbf24"
              strokeWidth="1.2"
              strokeDasharray="4 3"
            />
            <rect
              x={width - paddingRight + 2}
              y={priceToY(livePrice) - 9}
              width="60"
              height="18"
              fill="#fbbf24"
              rx="3"
            />
            <text
              x={width - paddingRight + 32}
              y={priceToY(livePrice) + 4}
              fill="#000"
              fontSize="10"
              fontWeight="900"
              textAnchor="middle"
              fontFamily="monospace"
            >
              {livePrice.toFixed(2)}
            </text>
          </g>
        )}

        {lockX !== null ? (
          <g>
            <line x1={lockX} y1={0} x2={lockX} y2={height} stroke="#eab308" strokeWidth="2" strokeDasharray="5 3" />
            <text x={lockX + 5} y={15} fill="#eab308" fontSize="10" fontWeight="900">
              TRUTH IN ANALYSIS (CONGELADO OOS)
            </text>
          </g>
        ) : (
          <g>
            <line x1={width - paddingRight - 8} y1={0} x2={width - paddingRight - 8} y2={height} stroke="#ef4444" strokeWidth="1.5" />
            <text x={width - paddingRight - 110} y={15} fill="#ef4444" fontSize="9" fontWeight="800">
              LIVE (DINÁMICO)
            </text>
          </g>
        )}
      </svg>
    </div>
  );
}
