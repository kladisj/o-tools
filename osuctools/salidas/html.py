"""Genera una página HTML con el gráfico de la diferencia entre equipos mapa por mapa.

La página es autónoma: un solo archivo, sin librerías ni conexión. El gráfico es
un SVG dibujado acá mismo, así se ve igual en un navegador y en OBS (fuente de
navegador con archivo local).

Qué muestra:
  - barras: la diferencia de score de cada mapa (hacia arriba, ventaja del rojo;
    hacia abajo, ventaja del azul)
  - línea: la diferencia acumulada de la serie
  - arriba: el marcador de mapas ganados
"""

import math
from html import escape

RED = "#e5484d"
BLUE = "#3e8ef7"
LINE = "#f5c542"

W, H = 900, 380
MARGIN_L, MARGIN_R, MARGIN_T, MARGIN_B = 84, 24, 36, 40


def _nice_ceiling(x: float) -> float:
    """El número 'redondo' más chico que es mayor o igual a x (1, 1.5, 2, 3, 5, 7.5, 10 por 10^k)."""
    if x <= 0:
        return 1.0
    magnitude = 10 ** math.floor(math.log10(x))
    for step in (1, 1.5, 2, 3, 5, 7.5, 10):
        if step * magnitude >= x:
            return step * magnitude
    return 10 * magnitude


def _signed(v: float) -> str:
    return "0" if v == 0 else f"{int(v):+,}"


def _svg(results, red_name: str, blue_name: str) -> str:
    n = len(results)
    plot_w = W - MARGIN_L - MARGIN_R
    plot_h = H - MARGIN_T - MARGIN_B
    peak = _nice_ceiling(
        max(
            max(abs(r.diff) for r in results),
            max(abs(r.cumulative_diff) for r in results),
            1,
        )
    )

    def y(v: float) -> float:
        return MARGIN_T + plot_h / 2 - v / peak * plot_h / 2

    slot = plot_w / n
    bar_w = min(slot * 0.55, 80)

    def cx(i: int) -> float:
        return MARGIN_L + slot * (i + 0.5)

    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="100%" '
        f'role="img" aria-label="Diferencia de score entre equipos por mapa">'
    ]

    # grilla y números del eje vertical
    for frac in (-1, -0.5, 0, 0.5, 1):
        v = peak * frac
        yy = y(v)
        strong = frac == 0
        out.append(
            f'<line x1="{MARGIN_L}" y1="{yy:.1f}" x2="{W - MARGIN_R}" y2="{yy:.1f}" '
            f'stroke="currentColor" stroke-opacity="{0.55 if strong else 0.15}" '
            f'stroke-width="{1.5 if strong else 1}"/>'
        )
        out.append(
            f'<text x="{MARGIN_L - 8}" y="{yy + 4:.1f}" text-anchor="end" font-size="12" '
            f'fill="currentColor" fill-opacity="0.8">{_signed(v)}</text>'
        )

    # a qué equipo favorece cada mitad, y qué es la línea
    out.append(
        f'<text x="{MARGIN_L + 6}" y="{MARGIN_T + 14}" font-size="13" font-weight="600" '
        f'fill="{RED}">▲ {escape(red_name)}</text>'
    )
    out.append(
        f'<text x="{MARGIN_L + 6}" y="{H - MARGIN_B - 8}" font-size="13" font-weight="600" '
        f'fill="{BLUE}">▼ {escape(blue_name)}</text>'
    )
    out.append(
        f'<text x="{W - MARGIN_R}" y="{MARGIN_T + 14}" text-anchor="end" font-size="13" '
        f'fill="{LINE}">● diferencia acumulada</text>'
    )

    # una barra por mapa
    for i, r in enumerate(results):
        x = cx(i) - bar_w / 2
        y0, y1 = y(0), y(r.diff)
        # una diferencia chica igual se tiene que ver: altura mínima de 2 px
        height = max(abs(y1 - y0), 2.0)
        top = y0 - height if r.diff > 0 else y0
        tip = escape(f"Mapa {i + 1}: {r.title} — {_signed(r.diff)}")
        if r.diff == 0:
            out.append(
                f'<line x1="{x:.1f}" y1="{y0:.1f}" x2="{x + bar_w:.1f}" y2="{y0:.1f}" '
                f'stroke="currentColor" stroke-width="3"><title>{tip}</title></line>'
            )
        else:
            color = RED if r.diff > 0 else BLUE
            out.append(
                f'<rect x="{x:.1f}" y="{top:.1f}" width="{bar_w:.1f}" height="{height:.1f}" '
                f'fill="{color}" rx="2"><title>{tip}</title></rect>'
            )
        if r.flipped:
            ty = top + height + 14 if r.diff < 0 else top - 4
            out.append(
                f'<text x="{cx(i):.1f}" y="{ty:.1f}" text-anchor="middle" font-size="14" '
                f'fill="currentColor">*</text>'
            )
        out.append(
            f'<text x="{cx(i):.1f}" y="{H - MARGIN_B + 18}" text-anchor="middle" '
            f'font-size="12" fill="currentColor" fill-opacity="0.8">{i + 1}</text>'
        )

    # línea de la diferencia acumulada
    if n > 1:
        points = " ".join(f"{cx(i):.1f},{y(r.cumulative_diff):.1f}" for i, r in enumerate(results))
        out.append(
            f'<polyline points="{points}" fill="none" stroke="{LINE}" stroke-width="3" '
            f'stroke-linejoin="round"/>'
        )
    for i, r in enumerate(results):
        tip = escape(f"Acumulado tras el mapa {i + 1}: {_signed(r.cumulative_diff)}")
        out.append(
            f'<circle cx="{cx(i):.1f}" cy="{y(r.cumulative_diff):.1f}" r="4.5" fill="{LINE}">'
            f"<title>{tip}</title></circle>"
        )

    last = results[-1]
    ly = y(last.cumulative_diff)
    label_y = ly - 10 if ly > MARGIN_T + 28 else ly + 22
    out.append(
        f'<text x="{cx(n - 1):.1f}" y="{label_y:.1f}" text-anchor="middle" font-size="13" '
        f'font-weight="700" fill="{LINE}">{_signed(last.cumulative_diff)}</text>'
    )
    out.append("</svg>")
    return "\n".join(out)


def _table(results, red_name: str, blue_name: str) -> str:
    rows = []
    for i, r in enumerate(results, 1):
        name = escape(r.title + (f" [{r.version}]" if r.version else ""))
        if r.winner == "red":
            who = f'<span class="red">{escape(red_name)}</span>'
        elif r.winner == "blue":
            who = f'<span class="blue">{escape(blue_name)}</span>'
        else:
            who = "Empate"
        star = "*" if r.flipped else ""
        rows.append(
            f'<tr><td>{i}</td><td>{name}</td><td>{who}{star}</td>'
            f'<td class="num">{abs(r.diff):,}</td>'
            f'<td class="num">{r.red_wins}–{r.blue_wins}</td></tr>'
        )
    return (
        "<table><thead><tr><th>#</th><th>Mapa</th><th>Ganó</th>"
        '<th class="num">Diferencia</th><th class="num">Marcador</th></tr></thead>'
        "<tbody>" + "".join(rows) + "</tbody></table>"
    )


def render(
    title: str,
    results,
    red_name: str = "Rojo",
    blue_name: str = "Azul",
    refresh: float | None = None,
    transparent: bool = False,
    table: bool = True,
) -> str:
    """Devuelve la página HTML completa.

    `refresh`: si se indica, la página se recarga sola cada tantos segundos (para
    verla actualizarse en OBS mientras se regenera el archivo).
    `transparent`: fondo transparente, para superponer en el stream.
    """
    background = "transparent" if transparent else "#14161a"
    meta = f'<meta http-equiv="refresh" content="{refresh:g}">' if refresh else ""

    if results:
        last = results[-1]
        header = (
            f'<span class="red">{escape(red_name)} {last.red_wins}</span> – '
            f'<span class="blue">{last.blue_wins} {escape(blue_name)}</span>'
            f" · {len(results)} mapas"
        )
        body = _svg(results, red_name, blue_name)
        if table:
            body += "\n" + _table(results, red_name, blue_name)
        if any(r.flipped for r in results):
            body += (
                '\n<p class="nota">* Si contaran también los jugadores que fallaron, '
                "el resultado de ese mapa sería otro.</p>"
            )
    else:
        header = "Todavía no hay mapas por equipos"
        body = ""

    return f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
{meta}
<title>{escape(title)}</title>
<style>
  :root {{ color-scheme: dark; }}
  body {{ margin: 0; padding: 16px; font-family: system-ui, sans-serif;
         color: #e6e6e6; background: {background}; }}
  h1 {{ font-size: 22px; margin: 0 0 4px; }}
  .marcador {{ font-size: 18px; margin-bottom: 12px; }}
  .red {{ color: {RED}; font-weight: 600; }}
  .blue {{ color: {BLUE}; font-weight: 600; }}
  table {{ border-collapse: collapse; width: 100%; margin-top: 12px; font-size: 14px; }}
  th, td {{ padding: 4px 8px; text-align: left; border-bottom: 1px solid rgba(255,255,255,.15); }}
  .num {{ text-align: right; font-variant-numeric: tabular-nums; }}
  .nota {{ font-size: 12px; opacity: .75; }}
</style>
</head>
<body>
<h1>{escape(title)}</h1>
<div class="marcador">{header}</div>
{body}
</body>
</html>
"""
