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

    @property
    def fail_rate(self) -> float:
        return self.fails / self.players if self.players else 0.0


def hardest_maps(matches, top: int | None = None) -> list[MapDifficulty]:
    """Mapas del más duro al más fácil.

    Orden: primero los que más gente falló; a igualdad, menor accuracy
    promedio; a igualdad, más misses promedio. Es una definición de "duro"
    entre varias posibles: para cambiarla, se cambia solo la clave del sort.
    """
    out: list[MapDifficulty] = []
    for m in _as_list(matches):
        for g in m.games:
            if not g.scores:
                continue
            passed = [s for s in g.scores if s.passed]
            out.append(
                MapDifficulty(
                    match_id=m.match_id,
                    match_name=m.display_name,
                    game_id=g.id,
                    title=g.title or f"mapa {g.id}",
                    version=g.version,
                    stars=g.stars,
                    players=len(g.scores),
                    fails=len(g.scores) - len(passed),
                    avg_accuracy=(
                        sum(s.accuracy for s in passed) / len(passed) if passed else None
                    ),
                    avg_misses=(
                        sum(s.statistics.get("count_miss", 0) for s in passed) / len(passed)
                        if passed
                        else None
                    ),
                )
            )
    out.sort(
        key=lambda d: (
            -d.fail_rate,
            d.avg_accuracy if d.avg_accuracy is not None else -1.0,
            -(d.avg_misses or 0.0),
        )
    )
    return out[:top] if top else out
