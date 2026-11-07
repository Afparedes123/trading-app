import numpy as np
from typing import List, Dict, Any, Tuple

class TrendSpiderHeatmapEngine:
    """
    Arquitectura del Mapa de Calor (Heatmaps: Liquidez y S/R).
    Superpone una malla matricial fija de 40 (precios) x 60 (tiempo) celdas (2,400 sub-regiones)
    para mapear confluencias matemáticas y bloques de liquidez institucional.
    """
    ROWS = 40  # Niveles discretos de precio vertical
    COLS = 60  # Barras o divisiones temporales horizontales

    def __init__(self, mode: str = "Horizontal"):
        """
        mode: "Horizontal", "Depth", "Trends", o "Off"
        """
        self.mode = mode

    def compute_heatmaps(
        self,
        candles: List[Dict[str, Any]],
        trendlines: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        n = len(candles)
        if n < 5:
            return {"mode": self.mode, "grid": [], "clusters": [], "horizontal_profile": []}

        # Tomar las últimas COLS velas (hasta 60 velas)
        window = candles[-self.COLS:] if n >= self.COLS else candles
        num_cols = len(window)

        # Determinar rango de precios de la ventana con un margen
        highs = [c["high"] for c in window]
        lows = [c["low"] for c in window]
        max_p = max(highs)
        min_p = min(lows)
        price_span = max(max_p - min_p, 1.0)
        padding = price_span * 0.05
        grid_max = max_p + padding
        grid_min = min_p - padding
        step_p = (grid_max - grid_min) / float(self.ROWS)

        def price_to_row(price: float) -> int:
            r = int((price - grid_min) / step_p)
            return max(0, min(self.ROWS - 1, r))

        def row_to_price(row: int) -> float:
            return round(grid_min + (row + 0.5) * step_p, 2)

        # 1. Puntos Especiales TrendSpider:
        # Punto Especial 1: El Low de una vela bajista (roja: close < open)
        # Punto Especial 2: El High de una vela alcista (verde: close >= open)
        special_points = []
        special_points_grid = np.zeros((self.ROWS, num_cols), dtype=np.float32)

        for col_idx, c in enumerate(window):
            if c["close"] < c["open"]: # Vela bajista (roja) -> Punto Especial 1 (Low)
                p_val = c["low"]
                r_idx = price_to_row(p_val)
                special_points_grid[r_idx, col_idx] += 1.0
                special_points.append({"col": col_idx, "row": r_idx, "type": "BEARISH_LOW", "price": p_val})
            else: # Vela alcista (verde) -> Punto Especial 2 (High)
                p_val = c["high"]
                r_idx = price_to_row(p_val)
                special_points_grid[r_idx, col_idx] += 1.0
                special_points.append({"col": col_idx, "row": r_idx, "type": "BULLISH_HIGH", "price": p_val})

        # 2. Trends Heatmap (Intersecciones crudas de líneas de tendencia)
        trends_raw_grid = np.zeros((self.ROWS, num_cols), dtype=np.float32)
        offset = len(candles) - num_cols

        for line in trendlines:
            origin_idx = line.get("origin_idx", 0)
            slope = line.get("slope", 0.0)
            y1 = line.get("y1", 0.0)

            for col_idx in range(num_cols):
                global_bar_idx = offset + col_idx
                if global_bar_idx >= origin_idx:
                    proj_y = y1 + slope * (global_bar_idx - origin_idx)
                    if grid_min <= proj_y <= grid_max:
                        r_idx = price_to_row(proj_y)
                        trends_raw_grid[r_idx, col_idx] += 1.0

        # 3. Depth Heatmap (Profundidad de Confluencia con Difusión Gaussiana 2D)
        depth_grid = np.copy(trends_raw_grid)
        # Aplicar convolución / difusión espacial hacia celdas vecinas (+- 1 celda en radio)
        diffused_grid = np.zeros_like(depth_grid)
        kernel = np.array([
            [0.05, 0.10, 0.05],
            [0.10, 0.40, 0.10],
            [0.05, 0.10, 0.05]
        ], dtype=np.float32)

        for r in range(self.ROWS):
            for c_i in range(num_cols):
                val = 0.0
                for dr in [-1, 0, 1]:
                    for dc in [-1, 0, 1]:
                        nr, nc = r + dr, c_i + dc
                        if 0 <= nr < self.ROWS and 0 <= nc < num_cols:
                            val += depth_grid[nr, nc] * kernel[dr + 1, dc + 1]
                diffused_grid[r, c_i] = val

        # 4. Horizontal Heatmap:
        # Proyecta horizontalmente la densidad de Puntos Especiales + giros de precio para mapear Order Blocks
        horizontal_density = np.sum(special_points_grid, axis=1)
        # Añadir también peso de giros de pivotes
        for c in window:
            r_hi = price_to_row(c["high"])
            r_lo = price_to_row(c["low"])
            horizontal_density[r_hi] += 0.5
            horizontal_density[r_lo] += 0.5

        # Normalizar perfil horizontal entre 0 y 100
        max_h = float(np.max(horizontal_density)) if np.max(horizontal_density) > 0 else 1.0
        horizontal_profile = []
        for r in range(self.ROWS):
            price_val = row_to_price(r)
            norm_score = round(float(horizontal_density[r]) / max_h * 100.0, 1)
            horizontal_profile.append({
                "row": r,
                "price": price_val,
                "score": norm_score
            })

        # Extraer Clusters clave (Soportes y Resistencias de mayor liquidez)
        clusters = []
        # Buscar picos locales en el perfil horizontal
        for r in range(1, self.ROWS - 1):
            if (horizontal_density[r] > horizontal_density[r - 1] and
                horizontal_density[r] >= horizontal_density[r + 1] and
                horizontal_density[r] >= max_h * 0.40):
                clusters.append({
                    "price": row_to_price(r),
                    "intensity": round(float(horizontal_density[r]) / max_h * 100.0, 1),
                    "type": "LIQUIDITY_CLUSTER"
                })

        clusters.sort(key=lambda x: x["intensity"], reverse=True)
        top_clusters = clusters[:5]

        # Seleccionar la matriz de salida según el modo solicitado
        selected_matrix = []
        if self.mode.lower() == "trends":
            mat = trends_raw_grid
        elif self.mode.lower() == "depth":
            mat = diffused_grid
        else: # "Horizontal" por defecto
            # En modo horizontal proyectamos horizontal_density repetida a lo largo de columnas
            # multiplicada por la presencia de puntos especiales
            mat = np.zeros((self.ROWS, num_cols), dtype=np.float32)
            for r in range(self.ROWS):
                mat[r, :] = horizontal_density[r]

        # Normalizar entre 0 y 1 para renderizado web
        max_val = float(np.max(mat)) if np.max(mat) > 0 else 1.0
        compact_grid = []
        for r in range(self.ROWS):
            row_data = [round(float(mat[r, c_i]) / max_val, 2) for c_i in range(num_cols)]
            compact_grid.append(row_data)

        return {
            "mode": self.mode,
            "rows": self.ROWS,
            "cols": num_cols,
            "grid_min": round(grid_min, 2),
            "grid_max": round(grid_max, 2),
            "step_price": round(step_p, 2),
            "grid": compact_grid,
            "horizontal_profile": horizontal_profile,
            "top_clusters": top_clusters,
            "special_points_count": len(special_points)
        }
