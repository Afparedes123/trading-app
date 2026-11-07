from typing import List, Dict, Any, Optional

def aggregate_timeframe_candles(candles_1m: List[Dict[str, Any]], tf_minutes: int) -> List[Dict[str, Any]]:
    """Agrupa velas de 1m en temporalidades superiores (5m, 15m, 60m) sin desalineación temporal"""
    if len(candles_1m) < tf_minutes:
        return []
    agg = []
    rem = len(candles_1m) % tf_minutes
    start = rem if rem > 0 else 0
    for i in range(start, len(candles_1m), tf_minutes):
        chunk = candles_1m[i:i + tf_minutes]
        if not chunk:
            continue
        o = chunk[0]["open"]
        cl = chunk[-1]["close"]
        h = max(c["high"] for c in chunk)
        l = min(c["low"] for c in chunk)
        v = sum(c.get("volume", 0) for c in chunk)
        agg.append({
            "ts": chunk[0]["ts"],
            "open": round(o, 2),
            "high": round(h, 2),
            "low": round(l, 2),
            "close": round(cl, 2),
            "volume": v,
            "tf": f"{tf_minutes}m"
        })
    return agg

class TrendSpiderMTFAEngine:
    """
    Multi-Timeframe Analysis (MTFA) y Alertas Dinámicas con Touch Cushion.
    Superpone la estructura macro de 15m / 1H sobre velas rápidas (1m / 5m) y
    aplica colchón de sensibilidad ATR para evaluar Break Through, Touch y Bounce.
    """
    def __init__(self, touch_cushion_atr_mult: float = 0.30):
        self.touch_cushion_atr_mult = touch_cushion_atr_mult

    def evaluate_touch_cushion_alerts(
        self,
        current_candle: Dict[str, Any],
        prev_candle: Dict[str, Any],
        trendlines: List[Dict[str, Any]],
        fib_levels: Dict[str, float],
        atr: float
    ) -> List[Dict[str, Any]]:
        cushion = max(self.touch_cushion_atr_mult * atr, 0.35)
        alerts = []
        live_p = current_candle["close"]
        high_p = current_candle["high"]
        low_p = current_candle["low"]

        # 1. Alertas sobre Líneas de Tendencia
        for line in trendlines:
            target_y = line.get("current_y", 0.0)
            kind = line.get("kind", "RESISTANCE")
            score = line.get("score", 0.0)

            # Colchón de precio
            upper_bound = target_y + cushion
            lower_bound = target_y - cushion

            # A. Break Through (Ruptura estricta al cierre)
            if kind == "RESISTANCE" and live_p > target_y:
                alerts.append({
                    "trigger": "BREAK_THROUGH",
                    "side": "COMPRA",
                    "target_type": "TRENDLINE_RESISTANCE",
                    "target_price": target_y,
                    "cushion": round(cushion, 2),
                    "score": score,
                    "desc": f"🚀 Ruptura confirmada al cierre sobre Directriz Bajista ({target_y:.2f})."
                })
            elif kind == "SUPPORT" and live_p < target_y:
                alerts.append({
                    "trigger": "BREAK_THROUGH",
                    "side": "VENTA",
                    "target_type": "TRENDLINE_SUPPORT",
                    "target_price": target_y,
                    "cushion": round(cushion, 2),
                    "score": score,
                    "desc": f"📉 Ruptura confirmada al cierre bajo Directriz Alcista ({target_y:.2f})."
                })

            # B. Bounce (Rebote confirmado tras tocar colchón)
            # Resistencia: High entró en colchón pero vela cerró abajo (rechazo limpio)
            if kind == "RESISTANCE" and high_p >= lower_bound and live_p < target_y:
                # Comprobar vela bajista o mecha superior
                if current_candle["close"] < current_candle["open"] or (current_candle["high"] - live_p) > 0.6:
                    alerts.append({
                        "trigger": "BOUNCE",
                        "side": "VENTA",
                        "target_type": "TRENDLINE_RESISTANCE",
                        "target_price": target_y,
                        "cushion": round(cushion, 2),
                        "score": score,
                        "desc": f"🎯 Rebote de Venta en Resistencia ({target_y:.2f}) con rechazo en mecha."
                    })

            # Soporte: Low entró en colchón pero vela cerró arriba (rebote limpio)
            if kind == "SUPPORT" and low_p <= upper_bound and live_p > target_y:
                if current_candle["close"] > current_candle["open"] or (live_p - current_candle["low"]) > 0.6:
                    alerts.append({
                        "trigger": "BOUNCE",
                        "side": "COMPRA",
                        "target_type": "TRENDLINE_SUPPORT",
                        "target_price": target_y,
                        "cushion": round(cushion, 2),
                        "score": score,
                        "desc": f"🎯 Rebote de Compra en Soporte ({target_y:.2f}) con mecha de absorción."
                    })

            # C. Touch (Toque con mecha dentro de la zona de sensibilidad)
            if lower_bound <= high_p <= upper_bound or lower_bound <= low_p <= upper_bound:
                alerts.append({
                    "trigger": "TOUCH",
                    "side": "INFO",
                    "target_type": f"TRENDLINE_{kind}",
                    "target_price": target_y,
                    "cushion": round(cushion, 2),
                    "score": score,
                    "desc": f"📍 Precio dentro del Colchón de Sensibilidad ATR ({lower_bound:.2f} - {upper_bound:.2f})."
                })

        # 2. Alertas sobre Niveles de Fibonacci (Zona OTE 0.5 - 0.618)
        ote_500 = fib_levels.get("0.5", 0.0)
        ote_618 = fib_levels.get("0.618", 0.0)
        if ote_500 > 0 and ote_618 > 0:
            fib_min = min(ote_500, ote_618) - cushion
            fib_max = max(ote_500, ote_618) + cushion
            if fib_min <= live_p <= fib_max:
                alerts.append({
                    "trigger": "TOUCH",
                    "side": "INFO",
                    "target_type": "FIBONACCI_GOLDEN_ZONE",
                    "target_price": round((ote_500 + ote_618) / 2.0, 2),
                    "cushion": round(cushion, 2),
                    "score": 10.0,
                    "desc": f"✨ Precio navegando en la Zona Dorada de Fibonacci ({fib_min:.2f} - {fib_max:.2f})."
                })

        return alerts
