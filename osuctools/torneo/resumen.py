"""Resumen de un torneo: junta muchas partidas (p. ej. toda la fase de grupos).

Funciones puras: reciben la lista de Match que devuelve reader.load() y
devuelven un TournamentSummary. No leen archivos ni imprimen.

Equipos: en cada partida, el equipo rojo/azul se identifica por el país que
tiene la mayoría de sus jugadores (torneos de selecciones: "CN", "FR"). Si no
hay mayoría, queda como "Rojo"/"Azul" y esa partida no entra a las posiciones,
porque no se puede saber qué equipo es cuál entre partidas.

Los promedios de score, accuracy y misses usan solo a quienes pasaron el mapa
(misma regla que stats.py); los scores en 0 no cuentan en ningún cálculo.
"""

import copy
from collections import Counter
from dataclasses import dataclass, field

from ..reader import Match
from ..stats import match_costs, team_series

COLORS = {"red": "Rojo", "blue": "Azul"}


def trim(match: Match, skip_first: int = 0) -> Match:
    """Copia de la partida sin los primeros N mapas (warmups)."""
    m = copy.copy(match)
    m._games = {g.id: g for g in match.games[skip_first:]}
    return m


def team_labels(match: Match) -> dict[str, str]:
    """{"red": "CN", "blue": "FR"}: el país que tiene la mayoría estricta de los
    jugadores de cada equipo. Si no hay mayoría (o los dos equipos darían el
    mismo país), ese color queda como "Rojo"/"Azul" y la partida no entra a
    las posiciones."""
    members: dict[str, dict[int, str]] = {"red": {}, "blue": {}}
    for g in match.games:
        for s in g.scores:
            if s.team in members and s.score > 0 and s.user_id in match.countries:
                members[s.team][s.user_id] = match.countries[s.user_id]
    labels = {}
    for color, who in members.items():
        top = Counter(who.values()).most_common(1)
        labels[color] = top[0][0] if top and top[0][1] * 2 > len(who) else COLORS[color]
    return labels if labels["red"] != labels["blue"] else dict(COLORS)


@dataclass
class MatchResult:
    match_id: int
    name: str
    red: str
    blue: str
    red_maps: int  # mapas ganados por el rojo
    blue_maps: int
    maps: int  # mapas por equipos jugados
    diff: int  # diferencia de score acumulada (rojo menos azul)
    closed: bool

    @property
    def winner(self) -> str | None:
        if self.red_maps == self.blue_maps:
            return None
        return self.red if self.red_maps > self.blue_maps else self.blue


@dataclass
class Standing:
    team: str
    played: int = 0
    won: int = 0
    lost: int = 0
    drawn: int = 0
    maps_for: int = 0
    maps_against: int = 0
    score_diff: int = 0

    @property
    def map_diff(self) -> int:
        return self.maps_for - self.maps_against


@dataclass
class PlayerTotals:
    user_id: int
    username: str
    country: str | None = None
    matches: int = 0
    maps: int = 0  # mapas con score
    mvps: int = 0
    cost_sum: float = 0.0
    ratio_sum: float = 0.0  # suma del ratio promedio de cada partida
    passed_maps: int = 0
    score_sum: int = 0
    acc_sum: float = 0.0
    misses: int = 0
    miss_n: int = 0  # mapas pasados con misses conocidos (sin los cargados a mano)

    @property
    def avg_cost(self) -> float:
        return self.cost_sum / self.matches if self.matches else 0.0

    @property
    def avg_ratio(self) -> float:
        return self.ratio_sum / self.matches if self.matches else 0.0

    @property
    def avg_score(self) -> float:
        return self.score_sum / self.passed_maps if self.passed_maps else 0.0

    @property
    def avg_acc(self) -> float:
        return self.acc_sum / self.passed_maps if self.passed_maps else 0.0

    @property
    def misses_per_map(self) -> float:
        return self.misses / self.miss_n if self.miss_n else 0.0


@dataclass
class MapTotals:
    title: str
    version: str | None
    stars: float | None
    plays: int = 0  # veces que se jugó en el torneo
    passed: int = 0  # scores que pasaron (base de los promedios)
    score_sum: int = 0
    acc_sum: float = 0.0
    miss_sum: int = 0
    miss_n: int = 0  # scores pasados con misses conocidos (sin los cargados a mano)

    @property
    def avg_score(self) -> float:
        return self.score_sum / self.passed if self.passed else 0.0

    @property
    def avg_acc(self) -> float:
        return self.acc_sum / self.passed if self.passed else 0.0

    @property
    def avg_misses(self) -> float:
        return self.miss_sum / self.miss_n if self.miss_n else 0.0


@dataclass
class TournamentSummary:
    matches: int = 0
    open_matches: list[str] = field(default_factory=list)  # sin cierre registrado
    games: int = 0
    players: int = 0
    beatmaps: int = 0
    results: list[MatchResult] = field(default_factory=list)
    standings: list[Standing] = field(default_factory=list)
    skipped_standings: int = 0  # partidas con equipos sin identificar
    player_totals: list[PlayerTotals] = field(default_factory=list)
    map_totals: list[MapTotals] = field(default_factory=list)
    records: list[tuple[str, str]] = field(default_factory=list)


def summarize(matches, skip_first: int = 0, min_matches: int = 1) -> TournamentSummary:
    if "countries" not in Match.__dataclass_fields__:
        raise RuntimeError(
            "reader.py está desactualizado: le falta el campo 'countries' (el país de cada "
            "jugador). Reemplazalo por la versión nueva de reader.py y volvé a correr.")
    ms = [trim(m, skip_first) for m in matches]
    out = TournamentSummary(matches=len(ms), open_matches=[m.display_name for m in ms if not m.closed])
    players: dict[int, PlayerTotals] = {}
    maps: dict[object, MapTotals] = {}
    standings: dict[str, Standing] = {}
    best_score = best_acc = tight = blowout = None

    for m in ms:
        labels = team_labels(m)
        series = team_series(m)
        last = series[-1] if series else None
        out.results.append(MatchResult(
            m.match_id, m.display_name, labels["red"], labels["blue"],
            last.red_wins if last else 0, last.blue_wins if last else 0,
            len(series), last.cumulative_diff if last else 0, m.closed))

        for r in series:
            if tight is None or abs(r.diff) < abs(tight[0].diff):
                tight = (r, m)
            if blowout is None or abs(r.diff) > abs(blowout[0].diff):
                blowout = (r, m)

        res = out.results[-1]
        if res.maps and labels["red"] not in COLORS.values():
            for label, mine, theirs, d in ((res.red, res.red_maps, res.blue_maps, res.diff),
                                           (res.blue, res.blue_maps, res.red_maps, -res.diff)):
                st = standings.setdefault(label, Standing(label))
                st.played += 1
                st.maps_for += mine
                st.maps_against += theirs
                st.score_diff += d
                if mine > theirs:
                    st.won += 1
                elif mine < theirs:
                    st.lost += 1
                else:
                    st.drawn += 1
        elif res.maps:
            out.skipped_standings += 1

        costs = match_costs(m)
        for i, c in enumerate(costs):
            p = players.setdefault(c.user_id, PlayerTotals(
                c.user_id, c.username, m.countries.get(c.user_id)))
            p.matches += 1
            p.maps += c.maps
            p.cost_sum += c.match_cost
            p.ratio_sum += c.avg_ratio
            p.mvps += i == 0

        for g in m.games:
            valid = [s for s in g.scores if s.score > 0]
            if not valid:
                continue
            out.games += 1
            key = g.beatmap_id if g.beatmap_id is not None else (g.title, g.version)
            mt = maps.setdefault(key, MapTotals(g.title or f"mapa {g.id}", g.version, g.stars))
            mt.plays += 1
            for s in valid:
                if not s.passed:
                    continue
                misses = s.statistics.get("count_miss", 0)
                mt.passed += 1
                mt.score_sum += s.score
                mt.acc_sum += s.accuracy
                if not s.manual:
                    mt.miss_sum += misses
                    mt.miss_n += 1
                p = players[s.user_id]
                p.passed_maps += 1
                p.score_sum += s.score
                p.acc_sum += s.accuracy
                if not s.manual:
                    p.misses += misses
                    p.miss_n += 1
                where = f"{g.title or g.id} [{g.version}] · {m.display_name}"
                if best_score is None or s.score > best_score[0]:
                    best_score = (s.score, m.username(s.user_id), where)
                if best_acc is None or s.accuracy > best_acc[0]:
                    best_acc = (s.accuracy, m.username(s.user_id), where)

    out.players = len(players)
    out.beatmaps = len(maps)
    out.standings = sorted(standings.values(), key=lambda t: (-t.won, -t.map_diff, -t.score_diff, t.team))
    out.player_totals = sorted(
        (p for p in players.values() if p.matches >= min_matches),
        key=lambda p: (-p.avg_cost, -p.mvps, p.username))
    out.map_totals = sorted(maps.values(), key=lambda t: (-t.plays, -t.avg_misses, t.title))

    if best_score:
        out.records.append(("Mayor score individual", f"{best_score[1]}: {best_score[0]:,} en {best_score[2]}"))
    if best_acc:
        out.records.append(("Mejor accuracy individual", f"{best_acc[1]}: {best_acc[0] * 100:.2f}% en {best_acc[2]}"))
    for label, rec in (("Mapa por equipos más ajustado", tight), ("Mayor paliza en un mapa", blowout)):
        if rec:
            r, m = rec
            out.records.append((label, f"{abs(r.diff):,} de diferencia en {r.title} · {m.display_name}"))
    return out
