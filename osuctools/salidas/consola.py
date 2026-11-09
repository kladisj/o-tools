"""Salida por consola: arma tablas de texto con los resultados de stats.

Las funciones format_* solo devuelven líneas de texto (no imprimen), así se
pueden probar. main() es el comando:

    python -m osuctools limpios ~/github/osu/datos/OWC2026
    python -m osuctools duros ~/github/osu/datos/OWC2026/china-francia.jsonl
"""

import argparse
import sys

from ..reader import ReaderError, load
from ..stats import clean_players, hardest_maps


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


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="osuctools",
        description="Estadísticas de partidas de osu! a partir de los archivos .jsonl de livelobby.",
    )
    sub = parser.add_subparsers(dest="comando", required=True)
    limpios = sub.add_parser("limpios", help="jugadores más limpios (menos misses por mapa)")
    duros = sub.add_parser("duros", help="mapas más duros (más jugadores que fallaron)")
    for p in (limpios, duros):
        p.add_argument("rutas", nargs="+", metavar="RUTA",
                       help="archivo .jsonl o carpeta con archivos .jsonl")
        p.add_argument("--top", type=int, default=None, help="cuántos mostrar")
    limpios.add_argument("--min-mapas", type=int, default=1,
                         help="mínimo de mapas pasados para aparecer en el ranking")
    args = parser.parse_args(argv)

    try:
        matches = load(*args.rutas)
    except (ReaderError, FileNotFoundError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    if not matches:
        print("No encontré partidas en las rutas indicadas.", file=sys.stderr)
        return 1

    lines = format_header(matches)
    if args.comando == "limpios":
        lines += format_clean(clean_players(matches, min_maps=args.min_mapas), top=args.top or 10)
    else:
        lines += format_hardest(hardest_maps(matches), top=args.top or 5)
    print("\n".join(lines))
    return 0
