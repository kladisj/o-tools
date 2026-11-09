"""Salida por consola: arma tablas de texto con los resultados de stats.

Las funciones format_* solo devuelven líneas de texto (no imprimen), así se
pueden probar. El comando que las usa está en cli.py.
"""


def _trunc(text: str, width: int) -> str:
    return text if len(text) <= width else text[: width - 1] + "…"


def format_header(matches) -> list[str]:
    """Qué partidas se están combinando, para que nunca se mezclen sin saberlo."""
    games = sum(len(m.games) for m in matches)
    names = [m.display_name for m in matches]
    shown = "; ".join(names[:3])
    if len(names) > 3:
        shown += f"; y {len(names) - 3} más"
    return [f"{len(matches)} partida(s), {games} mapas: {shown}", ""]


def format_clean(players, top: int = 10) -> list[str]:
    if not players:
        return ["No hay jugadores con mapas pasados."]
    lines = [
        "Jugadores más limpios (solo mapas pasados; ordenados por misses por mapa)",
        f"  {'#':>2}  {'jugador':<18} {'mapas':>5} {'misses':>6} {'miss/mapa':>9}"
        f"  {'sin miss':>12} {'100+50/mapa':>11} {'fallos':>6}",
    ]
    for i, p in enumerate(players[:top], 1):
        clean = f"{p.clean_maps}/{p.maps} ({p.clean_pct:.0%})"
        lines.append(
            f"  {i:>2}  {_trunc(p.username, 18):<18} {p.maps:>5} {p.misses:>6}"
            f" {p.misses_per_map:>9.2f}  {clean:>12} {p.hits_100_50_per_map:>11.1f}"
            f" {p.failed_maps:>6}"
        )
    return lines


def format_hardest(maps, top: int = 5) -> list[str]:
    if not maps:
        return ["No hay mapas jugados."]
    multi = len({d.match_id for d in maps}) > 1  # con varias partidas, se aclara cuál
    width = 52 if multi else 36
    lines = [
        "Mapas más duros (primero los que más jugadores fallaron)",
        f"  {'#':>2}  {'mapa':<{width}} {'★':>4} {'fallos':>7} {'acc prom':>9} {'miss prom':>9}",
    ]
    for i, d in enumerate(maps[:top], 1):
        name = d.title + (f" [{d.version}]" if d.version else "")
        if multi:
            name += f" · {d.match_name}"
        stars = f"{d.stars:.1f}" if d.stars is not None else "-"
        fails = f"{d.fails}/{d.players}"
        acc = f"{d.avg_accuracy * 100:.2f}%" if d.avg_accuracy is not None else "-"
        miss = f"{d.avg_misses:.1f}" if d.avg_misses is not None else "-"
        lines.append(
            f"  {i:>2}  {_trunc(name, width):<{width}} {stars:>4} {fails:>7} {acc:>9} {miss:>9}"
        )
    return lines
