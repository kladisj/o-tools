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
    titles = {
        "fallos": "primero los que más jugadores no pasaron",
        "misses": "ordenados por misses promedio; a igualdad, menor accuracy",
        "accuracy": "ordenados por menor accuracy promedio",
    }
    lines = [
        f"Mapas más duros ({titles.get(maps[0].order, titles['fallos'])})",
        f"  {'#':>2}  {'mapa':<{width}} {'★':>4} {'no pasaron':>10} {'acc prom':>9} {'miss prom':>9}",
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
            f"  {i:>2}  {_trunc(name, width):<{width}} {stars:>4} {fails:>10} {acc:>9} {miss:>9}"
        )
    return lines


TEAM_NAMES = {"red": "rojo", "blue": "azul"}


def _team_cell(team, labels) -> str:
    """Lo que se muestra en la columna del equipo: el país si se identificó
    ("CN"), y si no, el color ("rojo"/"azul")."""
    label = (labels or {}).get(team)
    if label and label.lower() not in TEAM_NAMES.values():
        return label
    return TEAM_NAMES.get(team, "-")


def format_mvp(match, costs, top: int = 10, labels=None) -> list[str]:
    """MVP y ranking de match cost de una partida.

    `labels`: {"red": "CN", "blue": "FR"} (ver torneo.resumen.team_labels). Si no se
    pasa, la columna del equipo muestra el color.
    """
    if not costs:
        return [f"{match.display_name}: no hay mapas con scores."]
    best = costs[0]
    lines = [
        f"{match.display_name} — {best.total_maps} mapas contados",
        f"MVP: {best.username} (match cost {best.match_cost:.2f})",
        "",
        f"  {'#':>2}  {'jugador':<18} {'equipo':<6} {'mapas':>5} {'match cost':>10} {'ratio prom':>10}",
    ]
    for i, p in enumerate(costs[:top], 1):
        lines.append(
            f"  {i:>2}  {_trunc(p.username, 18):<18} {_team_cell(p.team, labels):<6}"
            f" {p.maps:>2}/{p.total_maps:<2} {p.match_cost:>10.2f} {p.avg_ratio:>10.2f}"
        )
    return lines


def format_torneo(s, top: int = 10) -> list[str]:
    """Resumen general de un torneo (ver torneo/resumen.py)."""
    lines = [f"TORNEO: {s.matches} partida(s), {s.games} mapas, {s.players} jugadores, "
             f"{s.beatmaps} mapas distintos"]
    if s.open_matches:
        lines.append(f"  aviso: {len(s.open_matches)} partida(s) sin cierre registrado (¿en juego "
                     f"o incompletas?): " + "; ".join(_trunc(n, 30) for n in s.open_matches[:3])
                     + ("…" if len(s.open_matches) > 3 else ""))
    if not s.games:
        return lines + ["", "No hay mapas jugados."]

    lines += ["", "POSICIONES (equipos identificados por país)"]
    if s.standings:
        lines.append(f"  {'#':>2}  {'equipo':<8} {'PJ':>3} {'PG':>3} {'PP':>3} {'PE':>3}"
                     f" {'mapas':>7} {'dif mapas':>9} {'dif score':>11}")
        for i, t in enumerate(s.standings, 1):
            lines.append(f"  {i:>2}  {_trunc(t.team, 8):<8} {t.played:>3} {t.won:>3} {t.lost:>3} {t.drawn:>3}"
                         f" {t.maps_for:>3}-{t.maps_against:<3} {t.map_diff:>+9} {t.score_diff:>+11,}")
    else:
        lines.append("  (no se pudieron identificar los equipos por país en ninguna partida)")
    if s.skipped_standings:
        lines.append(f"  ({s.skipped_standings} partida(s) fuera de la tabla: equipos sin país único)")

    lines += ["", "RESULTADOS"]
    for r in s.results:
        if not r.maps:
            lines.append(f"  {_trunc(r.name, 36):<36} sin mapas por equipos")
            continue
        win = f"gana {r.winner}" if r.winner else "empate"
        live = "" if r.closed else "  (sin cierre)"
        lines.append(f"  {_trunc(r.name, 36):<36} {r.red} {r.red_maps}-{r.blue_maps} {r.blue:<6}"
                     f" {win:<10} dif {r.diff:+,}{live}")

    lines += ["", "JUGADORES (por match cost promedio de cada partida)",
              f"  {'#':>2}  {'jugador':<16} {'país':<4} {'part':>4} {'mapas':>5} {'MVP':>3}"
              f" {'cost prom':>9} {'ratio':>6} {'score prom':>10} {'acc':>7} {'miss/mapa':>9}"]
    for i, p in enumerate(s.player_totals[:top], 1):
        lines.append(f"  {i:>2}  {_trunc(p.username, 16):<16} {p.country or '-':<4} {p.matches:>4} {p.maps:>5}"
                     f" {p.mvps:>3} {p.avg_cost:>9.2f} {p.avg_ratio:>6.2f} {p.avg_score:>10,.0f}"
                     f" {p.avg_acc * 100:>6.2f}% {p.misses_per_map:>9.2f}")

    lines += ["", "MAPAS DEL POOL (más jugados primero)",
              f"  {'#':>2}  {'mapa':<38} {'★':>4} {'veces':>5} {'score prom':>10} {'acc':>7} {'miss prom':>9}"]
    for i, t in enumerate(s.map_totals[:top], 1):
        name = t.title + (f" [{t.version}]" if t.version else "")
        stars = f"{t.stars:.1f}" if t.stars is not None else "-"
        lines.append(f"  {i:>2}  {_trunc(name, 38):<38} {stars:>4} {t.plays:>5} {t.avg_score:>10,.0f}"
                     f" {t.avg_acc * 100:>6.2f}% {t.avg_misses:>9.1f}")

    if s.records:
        lines += ["", "RÉCORDS"] + [f"  {k}: {v}" for k, v in s.records]
    return lines
