"""Lee los archivos .jsonl que genera livelobby y los convierte en objetos.

Es la única parte de osuctools que conoce el formato del archivo: el resto
(stats, salidas, torneo) trabaja con Match, Game y Score. Si el formato cambia,
se arregla acá.

Correcciones a mano: una línea {"kind": "manual_score", "match_id": ..., "game_id": ...,
"score": {...}} en cualquier .jsonl agrega el score de alguien que se desconectó (la API
no lo guarda). Se aplica al final de load(), sin tocar los archivos originales; ver
_parse_manual para los campos.

Uso rápido, para ver qué hay en una carpeta o archivo:
    python -m osuctools.reader ~/github/osu/datos/OWC2026
"""

import json
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)

SUPPORTED_SCHEMA = 1  # versión más nueva del formato que este lector entiende


class ReaderError(Exception):
    """El archivo no se puede leer con esta versión del lector."""


@dataclass
class Score:
    user_id: int
    score: int
    accuracy: float  # fracción entre 0 y 1 (0.98 = 98 %)
    max_combo: int | None  # None en los scores cargados a mano
    passed: bool
    team: str | None = None  # "red" / "blue" en partidas por equipos
    mods: list[str] = field(default_factory=list)
    statistics: dict = field(default_factory=dict)  # count_300, count_miss, etc.
    rank: str | None = None
    manual: bool = False  # cargado a mano: score y accuracy valen, misses y combo no se conocen


@dataclass
class Game:
    """Un mapa jugado (siempre terminado: livelobby solo guarda los terminados)."""

    id: int
    scores: list[Score]
    beatmap_id: int | None = None
    title: str | None = None
    artist: str | None = None
    version: str | None = None  # nombre de la dificultad
    stars: float | None = None
    length_seconds: int | None = None
    start_time: str | None = None  # ISO 8601, UTC
    end_time: str | None = None
    team_type: str = ""
    scoring_type: str = ""
    mods: list[str] = field(default_factory=list)


@dataclass
class Match:
    match_id: int
    name: str | None = None  # None en archivos viejos, que no guardaban el nombre
    start_time: str | None = None
    end_time: str | None = None
    closed: bool = False  # se vio el evento match-disbanded
    players: dict[int, str] = field(default_factory=dict)  # id -> username
    countries: dict[int, str] = field(default_factory=dict)  # id -> código de país (CN, FR...)
    sources: list[str] = field(default_factory=list)  # archivos de donde salió
    _games: dict[int, Game] = field(default_factory=dict, repr=False)

    @property
    def games(self) -> list[Game]:
        """Los mapas en orden cronológico (no en el orden del archivo)."""
        return sorted(self._games.values(), key=lambda g: (g.start_time or "", g.id))

    @property
    def display_name(self) -> str:
        """El nombre de la partida; si no lo tiene, el del archivo."""
        if self.name:
            return self.name
        if self.sources:
            return Path(self.sources[0]).stem
        return f"partida {self.match_id}"

    def username(self, user_id: int) -> str:
        return self.players.get(user_id, str(user_id))


# --- interpretación de cada línea -------------------------------------------


def _parse_score(s: dict) -> Score:
    return Score(
        user_id=s["user_id"],
        score=s["score"],
        accuracy=s["accuracy"],
        max_combo=s["max_combo"],
        passed=s["passed"],
        team=s.get("team"),
        mods=s.get("mods") or [],
        statistics=s.get("statistics") or {},
        rank=s.get("rank"),
    )


def _parse_manual(rec: dict) -> Score:
    """Score de un jugador que se desconectó, cargado a mano.

    Campos de rec["score"]: user_id, score, accuracy (fracción 0-1), team ("red"/"blue"),
    passed (por defecto True; False si el jugador falló el mapa), rank y mods (opcionales).
    No tiene misses ni combo: se marca manual y esas estadísticas lo ignoran.
    """
    s = rec["score"]
    return Score(
        user_id=s["user_id"],
        score=s["score"],
        accuracy=s["accuracy"],
        max_combo=None,
        passed=s.get("passed", True),
        team=s.get("team"),
        mods=s.get("mods") or [],
        statistics={},
        rank=s.get("rank"),
        manual=True,
    )


def _parse_game(g: dict) -> Game:
    b = g.get("beatmap") or {}
    return Game(
        id=g["id"],
        scores=[_parse_score(s) for s in g["scores"]],
        beatmap_id=b.get("id"),
        title=b.get("title"),
        artist=b.get("artist"),
        version=b.get("version"),
        stars=b.get("difficulty_rating"),
        length_seconds=b.get("length_seconds"),
        start_time=g.get("start_time"),
        end_time=g.get("end_time"),
        team_type=g.get("team_type", ""),
        scoring_type=g.get("scoring_type", ""),
        mods=g.get("mods") or [],
    )


def _apply(m: Match, rec: dict) -> None:
    """Suma a la partida lo que dice una línea del archivo."""
    kind = rec.get("kind")
    if kind == "match":
        info = rec["match"]
        m.name = info.get("name") or m.name
        m.start_time = info.get("start_time") or m.start_time
        m.end_time = info.get("end_time") or m.end_time
    elif kind == "player":
        p = rec["player"]
        m.players[p["id"]] = p.get("username") or str(p["id"])
        if p.get("country_code"):
            m.countries[p["id"]] = p["country_code"]
    elif kind == "event":
        e = rec["event"]
        if e.get("game"):
            game = _parse_game(e["game"])
            m._games[game.id] = game  # mismo id = mismo mapa: no se duplica
        elif e.get("type") == "match-disbanded":
            m.closed = True
            m.end_time = m.end_time or e.get("timestamp")
        elif e.get("type") == "match-created":
            m.start_time = m.start_time or e.get("timestamp")
    # cualquier otro "kind" se ignora: así un archivo con registros nuevos
    # (agregados sin cambiar schema_version) no rompe este lector


def _parse_file(path: Path, manual: list | None = None) -> dict[int, Match]:
    """Las líneas manual_score no crean partidas: se juntan en `manual` y se aplican
    al final, cuando ya están todos los mapas cargados."""
    matches: dict[int, Match] = {}
    with open(path, encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                log.warning("%s: la línea %d es ilegible, se ignora", path, n)
                continue
            if not isinstance(rec, dict):
                continue

            version = rec.get("schema_version", 1)
            if isinstance(version, int) and version > SUPPORTED_SCHEMA:
                raise ReaderError(
                    f"{path}: formato versión {version}, este lector entiende "
                    f"hasta la {SUPPORTED_SCHEMA}"
                )

            if rec.get("kind") == "manual_score":
                if manual is not None:
                    manual.append((path, n, rec))
                continue

            match_id = rec.get("match_id")
            if match_id is None:
                continue
            if match_id not in matches:
                matches[match_id] = Match(match_id=match_id, sources=[str(path)])
            try:
                _apply(matches[match_id], rec)
            except (KeyError, TypeError):
                log.warning("%s: la línea %d tiene un formato inesperado, se ignora", path, n)
    return matches


def _merge(into: Match, other: Match) -> None:
    """Une dos lecturas de la MISMA partida (por ejemplo, de dos archivos)."""
    into.name = into.name or other.name
    into.start_time = into.start_time or other.start_time
    into.end_time = into.end_time or other.end_time
    into.closed = into.closed or other.closed
    into.players.update(other.players)
    into.countries.update(other.countries)
    into._games.update(other._games)
    into.sources.extend(s for s in other.sources if s not in into.sources)


def _apply_manual(merged: dict[int, Match], manual: list) -> None:
    """Agrega los scores cargados a mano al mapa que dicen. Si el jugador ya tiene score
    en ese mapa (la API sí lo tenía), manda la API y la corrección se ignora."""
    for path, n, rec in manual:
        try:
            match = merged.get(rec["match_id"])
            game_id = rec["game_id"]
            score = _parse_manual(rec)
        except (KeyError, TypeError):
            log.warning("%s: la línea %d (manual_score) tiene un formato inesperado, se ignora", path, n)
            continue
        game = match._games.get(game_id) if match else None
        if game is None:
            log.warning("%s: la línea %d apunta a la partida %s, mapa %s, que no está en los "
                        "datos; se ignora", path, n, rec.get("match_id"), game_id)
            continue
        if any(s.user_id == score.user_id for s in game.scores):
            log.warning("%s: la línea %d: el jugador %s ya tiene score en ese mapa; se ignora",
                        path, n, score.user_id)
            continue
        game.scores.append(score)
        if str(path) not in match.sources:
            match.sources.append(str(path))


# --- API pública ----------------------------------------------------------------


def find_files(path) -> list[Path]:
    """Un archivo, o todos los .jsonl de una carpeta (incluidas sus subcarpetas)."""
    p = Path(path).expanduser()
    if p.is_dir():
        return sorted(p.rglob("*.jsonl"))
    if p.is_file():
        return [p]
    raise FileNotFoundError(f"no existe: {p}")


def load(*paths) -> list[Match]:
    """Lee archivos o carpetas y devuelve las partidas que encuentre.

    Las partidas se identifican por su match_id: si la misma partida aparece en
    más de un archivo, se une (sin duplicar mapas); partidas distintas nunca se
    mezclan. Para mantener separados dos conjuntos (por ejemplo, torneo y
    pruebas), llamá a load() por separado para cada uno.
    """
    merged: dict[int, Match] = {}
    manual: list = []
    for path in paths:
        for file in find_files(path):
            for match_id, m in _parse_file(file, manual).items():
                if match_id in merged:
                    _merge(merged[match_id], m)
                else:
                    merged[match_id] = m
    _apply_manual(merged, manual)
    return sorted(merged.values(), key=lambda m: (m.start_time or "", m.match_id))


def main(argv=None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if not args:
        print("uso: python -m osuctools.reader ARCHIVO_O_CARPETA [...]")
        return 2
    try:
        matches = load(*args)
    except (ReaderError, FileNotFoundError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    for m in matches:
        estado = "cerrada" if m.closed else "sin cierre registrado"
        print(f"{m.match_id} | {m.display_name}")
        print(f"   {len(m.games)} mapas, {len(m.players)} jugadores | {estado}")
        print(f"   archivos: {', '.join(Path(s).name for s in m.sources)}")
    print(f"\n{len(matches)} partida(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
