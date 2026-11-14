"""Cálculos sobre los datos que entrega el reader.

Son funciones puras: reciben un Match (o una lista de Match) y devuelven
resultados. No leen archivos ni imprimen nada.

Regla común: el score de quien NO pasó el mapa no cuenta para promedios ni
rankings de rendimiento, porque se corta en el momento de fallar y no es
comparable. Los fallos se cuentan aparte.
"""

from dataclasses import dataclass

from .reader import Match


def _as_list(matches) -> list[Match]:
    return [matches] if isinstance(matches, Match) else list(matches)


def _names(matches: list[Match]) -> dict[int, str]:
    names: dict[int, str] = {}
    for m in matches:
        names.update(m.players)
    return names


# --- jugadores más limpios -----------------------------------------------------


@dataclass
class CleanPlayer:
    user_id: int
    username: str
    maps: int = 0  # mapas que pasó (los únicos que cuentan)
    failed_maps: int = 0  # mapas que falló (no cuentan en lo demás)
    misses: int = 0
    hits_100: int = 0
    hits_50: int = 0
    clean_maps: int = 0  # mapas pasados sin ningún miss

    @property
    def misses_per_map(self) -> float:
        return self.misses / self.maps if self.maps else 0.0

    @property
    def hits_100_50_per_map(self) -> float:
        return (self.hits_100 + self.hits_50) / self.maps if self.maps else 0.0

    @property
    def clean_pct(self) -> float:
        return self.clean_maps / self.maps if self.maps else 0.0


def clean_players(matches, min_maps: int = 1) -> list[CleanPlayer]:
    """Jugadores del más limpio al menos limpio.

    Orden: menos misses por mapa; a igualdad, menos 100 y 50 por mapa; a
    igualdad, más mapas jugados. `min_maps` deja afuera a quien pasó menos
    mapas que eso (un solo mapa perfecto no alcanza para encabezar la lista).
    """
    ms = _as_list(matches)
    names = _names(ms)
    acc: dict[int, CleanPlayer] = {}
    for m in ms:
        for g in m.games:
            for s in g.scores:
                p = acc.get(s.user_id)
                if p is None:
                    p = acc[s.user_id] = CleanPlayer(
                        user_id=s.user_id, username=names.get(s.user_id, str(s.user_id))
                    )
                if not s.passed:
                    p.failed_maps += 1
                    continue
                if s.manual:  # sin misses reales: no puede entrar al ranking de limpieza
                    continue
                misses = s.statistics.get("count_miss", 0)
                p.maps += 1
                p.misses += misses
                p.hits_100 += s.statistics.get("count_100", 0)
                p.hits_50 += s.statistics.get("count_50", 0)
                if misses == 0:
                    p.clean_maps += 1

    ranked = [p for p in acc.values() if p.maps >= min_maps]
    ranked.sort(key=lambda p: (p.misses_per_map, p.hits_100_50_per_map, -p.maps))
    return ranked


# --- mapas más duros -------------------------------------------------------------


@dataclass
class MapDifficulty:
    match_id: int
    match_name: str
    game_id: int
    title: str
    version: str | None
    stars: float | None
    players: int  # cantidad de scores en el mapa
    fails: int  # cuántos no lo pasaron
    avg_accuracy: float | None  # promedio de quienes lo pasaron (fracción 0-1)
    avg_misses: float | None  # ídem
    order: str = "fallos"  # criterio con el que se ordenó: fallos, misses o accuracy
    beatmapset_id: int | None = None  # para mostrar la imagen del mapa

    @property
    def fail_rate(self) -> float:
        return self.fails / self.players if self.players else 0.0


def hardest_maps(matches, top: int | None = None, by: str = "auto") -> list[MapDifficulty]:
    """Mapas del más duro al más fácil.

    Criterios (`by`):
      - "fallos":   más jugadores que no pasaron el mapa; a igualdad, menor
                    accuracy promedio; a igualdad, más misses promedio.
      - "misses":   más misses promedio; a igualdad, menor accuracy promedio.
      - "accuracy": menor accuracy promedio; a igualdad, más misses promedio.
      - "auto" (por defecto): "fallos" si en algún mapa alguien no pasó; si
        nadie falló nunca (partidas con NoFail), "misses", porque ahí los
        fallos valen 0 en todos los mapas y no distinguen nada.
    Quien no pasó el mapa no entra en los promedios de accuracy ni de misses.
    """
    if by not in ("auto", "fallos", "misses", "accuracy"):
        raise ValueError(f"criterio desconocido: {by!r}")
    out: list[MapDifficulty] = []
    for m in _as_list(matches):
        for g in m.games:
            if not g.scores:
                continue
            passed = [s for s in g.scores if s.passed]
            with_misses = [s for s in passed if not s.manual]  # los manuales no traen misses
            out.append(
                MapDifficulty(
                    match_id=m.match_id,
                    match_name=m.display_name,
                    game_id=g.id,
                    title=g.title or f"mapa {g.id}",
                    version=g.version,
                    stars=g.stars,
                    beatmapset_id=g.beatmapset_id,
                    players=len(g.scores),
                    fails=len(g.scores) - len(passed),
                    avg_accuracy=(
                        sum(s.accuracy for s in passed) / len(passed) if passed else None
                    ),
                    avg_misses=(
                        sum(s.statistics.get("count_miss", 0) for s in with_misses) / len(with_misses)
                        if with_misses
                        else None
                    ),
                )
            )
    if by == "auto":
        by = "fallos" if any(d.fails for d in out) else "misses"
    acc = lambda d: d.avg_accuracy if d.avg_accuracy is not None else -1.0  # noqa: E731
    mis = lambda d: d.avg_misses if d.avg_misses is not None else float("inf")  # noqa: E731
    keys = {
        "fallos": lambda d: (-d.fail_rate, acc(d), -(d.avg_misses or 0.0)),
        "misses": lambda d: (-mis(d), acc(d)),
        "accuracy": lambda d: (acc(d), -mis(d)),
    }
    for d in out:
        d.order = by
    out.sort(key=keys[by])
    return out[:top] if top else out


# --- diferencia entre equipos mapa por mapa ---------------------------------------

TEAM_TYPES = ("team-vs", "tag-team-vs")


@dataclass
class MapResult:
    """Resultado de un mapa jugado por equipos."""

    game_id: int
    title: str
    version: str | None
    red: int  # total del equipo rojo (solo suma a quienes pasaron el mapa)
    blue: int
    diff: int  # rojo menos azul: positivo, ventaja roja; negativo, ventaja azul
    winner: str | None  # "red", "blue", o None si empatan
    cumulative_diff: int  # suma de las diferencias hasta este mapa, incluido
    red_wins: int  # mapas ganados por el rojo hasta acá, incluido este
    blue_wins: int
    flipped: bool  # contando también a quienes fallaron, ganaría el otro equipo
    beatmapset_id: int | None = None  # para mostrar la imagen del mapa


def _team_totals(game, only_passed: bool) -> dict[str, int]:
    totals = {"red": 0, "blue": 0}
    for s in game.scores:
        if s.team in totals and (s.passed or not only_passed):
            totals[s.team] += s.score
    return totals


def _winner(red: int, blue: int) -> str | None:
    if red > blue:
        return "red"
    if blue > red:
        return "blue"
    return None


def team_series(match: Match) -> list[MapResult]:
    """Resultado de cada mapa por equipos de la partida, en orden cronológico.

    El total de cada equipo suma solo a quienes pasaron el mapa; si contar a los
    que fallaron cambia el ganador, el resultado queda marcado (`flipped`). Los
    mapas sin equipos (head-to-head) se saltean.
    """
    results: list[MapResult] = []
    cumulative = red_wins = blue_wins = 0
    for g in match.games:
        if g.team_type not in TEAM_TYPES or not g.scores:
            continue
        if not all(s.team in ("red", "blue") for s in g.scores):
            continue
        counted = _team_totals(g, only_passed=True)
        everyone = _team_totals(g, only_passed=False)
        winner = _winner(counted["red"], counted["blue"])
        diff = counted["red"] - counted["blue"]
        cumulative += diff
        if winner == "red":
            red_wins += 1
        elif winner == "blue":
            blue_wins += 1
        results.append(
            MapResult(
                game_id=g.id,
                title=g.title or f"mapa {g.id}",
                version=g.version,
                beatmapset_id=g.beatmapset_id,
                red=counted["red"],
                blue=counted["blue"],
                diff=diff,
                winner=winner,
                cumulative_diff=cumulative,
                red_wins=red_wins,
                blue_wins=blue_wins,
                flipped=_winner(everyone["red"], everyone["blue"]) != winner,
            )
        )
    return results


# --- MVP por match cost ---------------------------------------------------------------


@dataclass
class PlayerCost:
    """Match cost de un jugador en UNA partida.

    n  = total_maps: mapas jugados en toda la partida.
    n' = maps: mapas en los que participó el jugador.
    """

    user_id: int
    username: str
    maps: int
    total_maps: int
    ratio_sum: float  # suma de (score del jugador / score promedio del mapa)
    team: str | None = None

    @property
    def avg_ratio(self) -> float:
        """Promedio de los cocientes: 1.0 = rindió igual que el promedio."""
        return self.ratio_sum / self.maps if self.maps else 0.0

    @property
    def match_cost(self) -> float:
        """(2/n' + 2) x suma(score / score promedio) / (2/n + 2), tal cual la fórmula."""
        if not self.maps or not self.total_maps:
            return 0.0
        return (2 / self.maps + 2) * self.ratio_sum / (2 / self.total_maps + 2)


def match_costs(match: Match, skip_first: int = 0) -> list[PlayerCost]:
    """Match cost de cada jugador de la partida, del mejor (MVP) al peor.

    - Score promedio de un mapa: promedio de todos los scores de ese mapa.
    - Los scores en 0 no cuentan (ni para el promedio ni como mapa jugado).
    - skip_first omite los primeros N mapas (warmups), que no son de la serie.
    - Los scores de quienes fallaron SÍ cuentan, como dice la fórmula
      ("todos los jugadores que jugaron ese mapa").
    """
    games = [g for g in match.games[skip_first:] if any(s.score > 0 for s in g.scores)]
    n = len(games)
    acc: dict[int, PlayerCost] = {}
    for g in games:
        valid = [s for s in g.scores if s.score > 0]
        avg = sum(s.score for s in valid) / len(valid)
        for s in valid:
            p = acc.get(s.user_id)
            if p is None:
                p = acc[s.user_id] = PlayerCost(
                    user_id=s.user_id, username=match.username(s.user_id),
                    maps=0, total_maps=n, ratio_sum=0.0)
            p.maps += 1
            p.ratio_sum += s.score / avg
            p.team = s.team or p.team
    return sorted(acc.values(), key=lambda p: (-p.match_cost, -p.avg_ratio, p.username))
