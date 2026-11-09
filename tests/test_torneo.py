import json

from osuctools.reader import Game, Match, Score, load
from osuctools.salidas.consola import format_torneo
from osuctools.torneo.resumen import summarize, team_labels

CN, FR = {1: "CN", 2: "CN"}, {3: "FR", 4: "FR"}


def sc(uid, pts, team, miss=0):
    return Score(user_id=uid, score=pts, accuracy=0.98, max_combo=500, passed=True, team=team,
                 statistics={"count_miss": miss})


def game(gid, bm, scores, title="Mapa"):
    return Game(id=gid, scores=scores, beatmap_id=bm, title=title, version="Insane", stars=5.0,
                team_type="team-vs", start_time=f"2026-01-01T10:{gid:02d}:00Z")


def match(mid, name, games, countries=None, closed=True):
    m = Match(match_id=mid, name=name, closed=closed, countries=countries or {},
              players={1: "ana", 2: "beto", 3: "cami", 4: "dani"})
    for g in games:
        m._games[g.id] = g
    return m


def match_a():  # CN (rojo) le gana 2-0 a FR (azul): rojo 2000 vs azul 1000 en cada mapa
    red = lambda: [sc(1, 1000, "red"), sc(2, 1000, "red")]  # noqa: E731
    blue = lambda: [sc(3, 500, "blue"), sc(4, 500, "blue")]  # noqa: E731
    return match(1, "A", [game(1, 10, red() + blue()), game(2, 11, red() + blue())],
                 countries={**CN, **FR})


def match_b():  # colores invertidos: FR rojo, CN azul. 1-1 (CN +200 y -200)
    g1 = game(3, 10, [sc(3, 800, "red"), sc(4, 800, "red"), sc(1, 900, "blue"), sc(2, 900, "blue")])
    g2 = game(4, 12, [sc(3, 900, "red"), sc(4, 900, "red"), sc(1, 800, "blue"), sc(2, 800, "blue")])
    return match(2, "B", [g1, g2], countries={**CN, **FR})


def test_posiciones_suman_partidas_aunque_cambien_los_colores():
    s = summarize([match_a(), match_b()])
    cn, fr = s.standings
    assert (cn.team, cn.played, cn.won, cn.drawn, cn.lost) == ("CN", 2, 1, 1, 0)
    assert (fr.team, fr.played, fr.won, fr.drawn, fr.lost) == ("FR", 2, 0, 1, 1)
    assert (cn.maps_for, cn.maps_against, cn.score_diff) == (3, 1, 2000)
    assert fr.score_diff == -2000


def test_totales_y_mapas_repetidos_se_agrupan_por_beatmap():
    s = summarize([match_a(), match_b()])
    assert (s.matches, s.games, s.players, s.beatmaps) == (2, 4, 4, 3)
    assert s.map_totals[0].plays == 2  # el beatmap 10 se jugó en las dos partidas


def test_jugadores_partidas_y_mvps():
    s = summarize([match_a(), match_b()])
    assert all(p.matches == 2 for p in s.player_totals)
    assert sum(p.mvps for p in s.player_totals) == 2  # un MVP por partida
    assert summarize([match_a()], min_matches=2).player_totals == []


def test_sin_pais_unico_no_entra_a_las_posiciones():
    s = summarize([match_a(), match_b(), match(9, "C", match_a().games, countries={})])
    assert s.skipped_standings == 1
    assert [t.played for t in s.standings] == [2, 2]  # la partida C no cuenta
    assert s.results[2].red == "Rojo"


def test_omitir_warmups_y_partidas_sin_cierre():
    s = summarize([match_a()], skip_first=1)
    assert s.games == 1
    assert summarize([match(1, "A", match_a().games, closed=False)]).open_matches == ["A"]


def test_registros_y_texto():
    s = summarize([match_a(), match_b()])
    text = "\n".join(format_torneo(s))
    assert "CN" in text and "POSICIONES" in text and "RÉCORDS" in text
    assert "1,000" in text  # paliza o ajuste: la diferencia por mapa en A es 1,000
    assert "No hay mapas" in "\n".join(format_torneo(summarize([match(1, "X", [])])))


def test_el_lector_guarda_el_pais(tmp_path):
    f = tmp_path / "a.jsonl"
    f.write_text(json.dumps({"schema_version": 1, "match_id": 1, "kind": "player",
                             "player": {"id": 7, "username": "x", "country_code": "AR"}}) + "\n")
    assert load(f)[0].countries == {7: "AR"}


def test_equipo_se_detecta_por_el_pais_mayoritario():
    # rojo: 3 CN + 1 FR -> CN; azul: 2 FR + 2 CN -> sin mayoría -> "Azul"
    g = game(1, 10, [sc(1, 900, "red"), sc(2, 900, "red"), sc(3, 900, "red"), sc(4, 900, "red"),
                     sc(5, 500, "blue"), sc(6, 500, "blue"), sc(7, 500, "blue"), sc(8, 500, "blue")])
    m = match(1, "X", [g], countries={1: "CN", 2: "CN", 3: "CN", 4: "FR",
                                      5: "FR", 6: "FR", 7: "CN", 8: "CN"})
    assert team_labels(m) == {"red": "CN", "blue": "Azul"}
    m.countries.update({7: "FR"})  # azul pasa a 3 FR + 1 CN
    assert team_labels(m) == {"red": "CN", "blue": "FR"}
