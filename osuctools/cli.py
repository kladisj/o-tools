"""El comando osuctools: lee los .jsonl de livelobby y muestra estadísticas.

    python -m osuctools limpios RUTA
    python -m osuctools duros RUTA
    python -m osuctools mvp RUTA [--omitir 2]
    python -m osuctools torneo CARPETA [--omitir 2] [--top 15]
    python -m osuctools grafico ARCHIVO --out grafico.html --seguir 5
"""

import argparse
import os
import sys
import time
from pathlib import Path

from .reader import ReaderError, load
from .salidas.consola import format_clean, format_hardest, format_header, format_mvp, format_torneo
from .salidas.html import render
from .torneo.resumen import summarize, team_labels, trim
from .stats import clean_players, hardest_maps, match_costs, team_series


def _write_atomic(path: Path, text: str) -> None:
    """Escribe el archivo de golpe: OBS nunca lo ve a medio escribir."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def _say(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def _text_command(args) -> int:
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
        lines += format_hardest(hardest_maps(matches, by=args.orden), top=args.top or 5)
    print("\n".join(lines))
    return 0


def _mvp_command(args) -> int:
    try:
        matches = load(*args.rutas)
    except (ReaderError, FileNotFoundError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    if not matches:
        print("No encontré partidas en las rutas indicadas.", file=sys.stderr)
        return 1
    lines: list[str] = []
    for m in matches:  # el match cost es por partida: nunca se mezclan
        labels = team_labels(trim(m, args.omitir))  # el país de cada equipo, si se puede saber
        lines += format_mvp(m, match_costs(m, skip_first=args.omitir), top=args.top or 10,
                            labels=labels) + [""]
    print("\n".join(lines).rstrip())
    return 0


def _torneo_command(args) -> int:
    try:
        matches = load(*args.rutas)
    except (ReaderError, FileNotFoundError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    if not matches:
        print("No encontré partidas en las rutas indicadas.", file=sys.stderr)
        return 1
    try:
        summary = summarize(matches, skip_first=args.omitir, min_matches=args.min_partidas)
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    print("\n".join(format_torneo(summary, top=args.top or 10)))
    return 0


def _chart_command(args) -> int:
    out = Path(args.out).expanduser()
    following = args.seguir is not None
    last_count = None
    waiting_said = False

    try:
        while True:
            matches = None
            try:
                matches = load(args.ruta)
            except FileNotFoundError as e:
                if not following:
                    print(f"Error: {e}", file=sys.stderr)
                    return 1
                if not waiting_said:
                    _say(f"esperando que exista {args.ruta} ...")
                    waiting_said = True
            except ReaderError as e:
                print(f"Error: {e}", file=sys.stderr)
                return 1

            if matches is not None:
                if len(matches) > 1:
                    print(
                        f"Error: {args.ruta} tiene {len(matches)} partidas y el gráfico es de "
                        "una sola. Indicá un archivo con una partida.",
                        file=sys.stderr,
                    )
                    return 1
                if not matches:
                    if not following:
                        print("No encontré ninguna partida en esa ruta.", file=sys.stderr)
                        return 1
                else:
                    m = matches[0]
                    results = team_series(m)
                    page = render(
                        m.display_name,
                        results,
                        red_name=args.rojo,
                        blue_name=args.azul,
                        refresh=args.seguir,
                        transparent=args.transparente,
                        table=not args.sin_tabla,
                    )
                    _write_atomic(out, page)
                    if len(results) != last_count:
                        _say(f"{len(results)} mapas por equipos -> {out.resolve()}")
                        last_count = len(results)

            if not following:
                return 0
            time.sleep(args.seguir)
    except KeyboardInterrupt:
        _say("cortado")
        return 130


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
    duros.add_argument("--orden", choices=["auto", "fallos", "misses", "accuracy"], default="auto",
                       help="criterio de dureza (auto: misses si nadie falló, p. ej. con NoFail)")
    limpios.add_argument("--min-mapas", type=int, default=1,
                         help="mínimo de mapas pasados para aparecer en el ranking")

    mvp = sub.add_parser("mvp", help="MVP de cada partida según el match cost")
    mvp.add_argument("rutas", nargs="+", metavar="RUTA", help="archivo .jsonl o carpeta")
    mvp.add_argument("--top", type=int, default=None, help="cuántos mostrar por partida")
    mvp.add_argument("--omitir", type=int, default=0, metavar="N",
                     help="omitir los primeros N mapas (warmups)")

    torneo = sub.add_parser("torneo", help="resumen general de varias partidas (p. ej. la fase de grupos)")
    torneo.add_argument("rutas", nargs="+", metavar="RUTA", help="archivos .jsonl o carpetas")
    torneo.add_argument("--top", type=int, default=None, help="filas de jugadores y mapas (por defecto 10)")
    torneo.add_argument("--omitir", type=int, default=0, metavar="N",
                        help="omitir los primeros N mapas de cada partida (warmups)")
    torneo.add_argument("--min-partidas", type=int, default=1,
                        help="mínimo de partidas jugadas para aparecer en el ranking de jugadores")

    grafico = sub.add_parser(
        "grafico", help="página HTML con la diferencia entre equipos mapa por mapa"
    )
    grafico.add_argument("ruta", metavar="ARCHIVO", help="archivo .jsonl de UNA partida")
    grafico.add_argument("--out", default="grafico.html",
                         help="dónde guardar la página (por defecto grafico.html)")
    grafico.add_argument("--rojo", default="Rojo", help="nombre del equipo rojo")
    grafico.add_argument("--azul", default="Azul", help="nombre del equipo azul")
    grafico.add_argument("--seguir", type=float, default=None, metavar="SEGUNDOS",
                         help="regenerar la página cada tantos segundos (y que se recargue sola)")
    grafico.add_argument("--transparente", action="store_true",
                         help="fondo transparente, para superponer en el stream")
    grafico.add_argument("--sin-tabla", action="store_true",
                         help="mostrar solo el gráfico, sin la tabla de mapas")

    args = parser.parse_args(argv)
    if args.comando == "torneo":
        return _torneo_command(args)
    if args.comando == "mvp":
        return _mvp_command(args)
    if args.comando == "grafico":
        if args.seguir is not None and args.seguir < 1:
            parser.error("--seguir tiene que ser de al menos 1 segundo")
        return _chart_command(args)
    return _text_command(args)
