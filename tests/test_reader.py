import json

import pytest

from osuctools.reader import ReaderError, load


def rec(match_id, kind, **payload):
    return {"schema_version": 1, "match_id": match_id, "kind": kind, **payload}


def match_rec(mid=1, name="OWC2026: (A) VS (B)", start="2026-01-01T10:00:00Z", end=None):
    return rec(mid, "match", match={"name": name, "start_time": start, "end_time": end})


def player_rec(mid, uid, name):
    return rec(mid, "player", player={"id": uid, "username": name, "country_code": "AR"})


def score(uid, pts, acc=0.98, combo=500, passed=True, team="red"):
    return {"user_id": uid, "score": pts, "accuracy": acc, "max_combo": combo,
            "passed": passed, "rank": "A", "mods": [], "team": team, "slot": 0,
            "statistics": {"count_miss": 0}}


def game_rec(mid, event_id, game_id, start, scores, title="Mapa"):
    beatmap = {"id": 9, "title": title, "artist": "X", "version": "Insane",
               "difficulty_rating": 5.5, "length_seconds": 100}
    game = {"id": game_id, "match_id": mid, "beatmap": beatmap, "start_time": start,
            "end_time": start, "mode": "osu", "scoring_type": "scorev2",
            "team_type": "team-vs", "mods": [], "scores": scores}
    return rec(mid, "event", event={"id": event_id, "type": "game", "timestamp": start,
                                    "user_id": None, "text": None, "game": game})


def event_rec(mid, event_id, type_, ts="2026-01-01T12:00:00Z"):
    return rec(mid, "event", event={"id": event_id, "type": type_, "timestamp": ts,
                                    "user_id": 1, "text": None, "game": None})


def write(path, records, extra=""):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
        f.write(extra)
    return path


def test_lee_nombre_jugadores_y_mapas_ordenados(tmp_path):
    f = write(tmp_path / "a.jsonl", [
        match_rec(),
        player_rec(1, 7, "ana"), player_rec(1, 8, "beto"),
        game_rec(1, 20, 101, "2026-01-01T10:20:00Z",
                 [score(7, 900), score(8, 800, team="blue")], title="Segundo"),
        game_rec(1, 10, 100, "2026-01-01T10:10:00Z", [score(7, 700)], title="Primero"),
    ])
    [m] = load(f)
    assert m.name == "OWC2026: (A) VS (B)"
    assert m.username(7) == "ana"
    # por hora de inicio, no por el orden en que están escritos en el archivo
    assert [g.title for g in m.games] == ["Primero", "Segundo"]
    g = m.games[1]
    assert g.stars == 5.5
    assert g.scores[0].user_id == 7
    assert g.scores[0].accuracy == 0.98
    assert g.scores[1].team == "blue"


def test_ignora_lineas_rotas_y_tipos_desconocidos(tmp_path):
    f = write(
        tmp_path / "a.jsonl",
        [match_rec(), rec(1, "algo_futuro", x=1),
         game_rec(1, 10, 100, "2026-01-01T10:10:00Z", [score(7, 700)])],
        extra='{"schema_version": 1, "match_id": 1, "kind": "ev',  # línea cortada
    )
    [m] = load(f)
    assert len(m.games) == 1


def test_misma_partida_en_dos_archivos_se_une_sin_duplicar(tmp_path):
    g1 = game_rec(1, 10, 100, "2026-01-01T10:10:00Z", [score(7, 700)])
    g2 = game_rec(1, 20, 101, "2026-01-01T10:20:00Z", [score(7, 800)])
    a = write(tmp_path / "a.jsonl", [match_rec(), player_rec(1, 7, "ana"), g1])
    b = write(tmp_path / "b.jsonl", [match_rec(), player_rec(1, 7, "ana"), g1, g2])
    [m] = load(a, b)
    assert len(m.games) == 2
    assert len(m.sources) == 2


def test_partidas_distintas_no_se_mezclan_y_se_lee_la_carpeta_completa(tmp_path):
    write(tmp_path / "torneo" / "a.jsonl", [
        match_rec(1, name="Uno"),
        game_rec(1, 10, 100, "2026-01-01T10:10:00Z", [score(7, 700)]),
    ])
    write(tmp_path / "torneo" / "fase2" / "b.jsonl", [  # una subcarpeta
        match_rec(2, name="Dos"),
        game_rec(2, 10, 200, "2026-01-01T10:10:00Z", [score(7, 700)]),
    ])
    matches = load(tmp_path / "torneo")
    assert [m.name for m in matches] == ["Uno", "Dos"]
    assert all(len(m.games) == 1 for m in matches)


def test_detecta_el_cierre_de_la_sala(tmp_path):
    f = write(tmp_path / "a.jsonl", [
        match_rec(),
        event_rec(1, 30, "match-disbanded", ts="2026-01-01T13:00:00Z"),
    ])
    [m] = load(f)
    assert m.closed
    assert m.end_time == "2026-01-01T13:00:00Z"


def test_sin_cierre_queda_abierta(tmp_path):
    f = write(tmp_path / "a.jsonl", [match_rec(), event_rec(1, 5, "player-joined")])
    [m] = load(f)
    assert not m.closed
    assert m.end_time is None


def test_rechaza_un_formato_mas_nuevo_que_el_soportado(tmp_path):
    f = write(tmp_path / "a.jsonl", [{**match_rec(), "schema_version": 99}])
    with pytest.raises(ReaderError):
        load(f)


def test_archivo_viejo_sin_nombre_usa_el_nombre_del_archivo(tmp_path):
    f = write(tmp_path / "china-francia.jsonl",
              [game_rec(1, 10, 100, "2026-01-01T10:10:00Z", [score(7, 700)])])
    [m] = load(f)
    assert m.name is None
    assert m.display_name == "china-francia"


def test_mapa_sin_beatmap_no_rompe(tmp_path):
    r = game_rec(1, 10, 100, "2026-01-01T10:10:00Z", [score(7, 700)])
    r["event"]["game"]["beatmap"] = None
    f = write(tmp_path / "a.jsonl", [r])
    [m] = load(f)
    assert m.games[0].title is None
    assert m.games[0].scores[0].score == 700


def test_jugador_desconocido_se_muestra_por_su_id(tmp_path):
    f = write(tmp_path / "a.jsonl", [game_rec(1, 10, 100, "2026-01-01T10:10:00Z", [score(99, 1)])])
    [m] = load(f)
    assert m.username(99) == "99"


def test_una_ruta_que_no_existe_da_error(tmp_path):
    with pytest.raises(FileNotFoundError):
        load(tmp_path / "no-existe.jsonl")


# --- correcciones a mano (manual_score) ---------------------------------------


def manual_rec(mid, game_id, uid, pts, acc=0.99, passed=True, team="blue"):
    return rec(mid, "manual_score", game_id=game_id,
               score={"user_id": uid, "score": pts, "accuracy": acc, "rank": "A",
                      "passed": passed, "team": team})


def test_manual_score_se_suma_al_mapa_sin_tocar_el_original(tmp_path):
    f = write(tmp_path / "datos" / "a.jsonl", [
        match_rec(), player_rec(1, 7, "ana"), player_rec(1, 8, "beto"),
        game_rec(1, 10, 100, "2026-01-01T10:10:00Z", [score(7, 900)]),
    ])
    antes = f.read_text(encoding="utf-8")
    fix = write(tmp_path / "datos" / "correcciones.jsonl", [manual_rec(1, 100, 8, 750)])
    [m] = load(tmp_path / "datos")
    g = m.games[0]
    assert [s.user_id for s in g.scores] == [7, 8]
    nuevo = g.scores[1]
    assert nuevo.manual and nuevo.score == 750 and nuevo.max_combo is None
    assert not g.scores[0].manual
    assert str(fix) in m.sources
    assert f.read_text(encoding="utf-8") == antes  # el archivo de la API queda intacto


def test_manual_score_no_depende_del_orden_de_los_archivos(tmp_path):
    # "0_" se lee antes que "a_": la corrección llega antes que el mapa y igual se aplica
    write(tmp_path / "0_correcciones.jsonl", [manual_rec(1, 100, 8, 750)])
    write(tmp_path / "a_datos.jsonl", [
        match_rec(), game_rec(1, 10, 100, "2026-01-01T10:10:00Z", [score(7, 900)])])
    [m] = load(tmp_path)
    assert sorted(s.user_id for s in m.games[0].scores) == [7, 8]


def test_manual_score_ignorado_si_el_jugador_ya_tiene_score(tmp_path):
    write(tmp_path / "a.jsonl", [
        match_rec(), game_rec(1, 10, 100, "2026-01-01T10:10:00Z", [score(7, 900)]),
        manual_rec(1, 100, 7, 123)])
    [m] = load(tmp_path)
    assert [s.score for s in m.games[0].scores] == [900]  # manda la API


def test_manual_score_de_partida_o_mapa_inexistente_no_crea_nada(tmp_path):
    write(tmp_path / "a.jsonl", [
        match_rec(), game_rec(1, 10, 100, "2026-01-01T10:10:00Z", [score(7, 900)]),
        manual_rec(1, 999, 8, 750),       # mapa que no existe
        manual_rec(2, 100, 8, 750)])      # partida que no existe: no aparece como partida vacía
    [m] = load(tmp_path)
    assert m.match_id == 1 and len(m.games[0].scores) == 1


def test_manual_score_roto_se_ignora(tmp_path):
    write(tmp_path / "a.jsonl", [
        match_rec(), game_rec(1, 10, 100, "2026-01-01T10:10:00Z", [score(7, 900)]),
        rec(1, "manual_score", game_id=100, score={"user_id": 8})])  # faltan score y accuracy
    [m] = load(tmp_path)
    assert len(m.games[0].scores) == 1
