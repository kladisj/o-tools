import json

from osuctools.reader import Game, Match, Score
from osuctools.salidas.consola import format_clean, format_hardest, main
from osuctools.stats import clean_players, hardest_maps


def sc(uid, acc=0.98, passed=True, miss=0, c100=0, c50=0, pts=1000):
    return Score(
        user_id=uid, score=pts, accuracy=acc, max_combo=500, passed=passed, team="red",
        statistics={"count_miss": miss, "count_100": c100, "count_50": c50},
    )


def game(gid, scores, title="Mapa"):
    return Game(id=gid, scores=scores, title=title, version="Insane", stars=5.5,
                start_time=f"2026-01-01T10:{gid:02d}:00Z")


def match(mid, games, players=None, name="Partida"):
    m = Match(match_id=mid, name=name, players=players or {})
    for g in games:
        m._games[g.id] = g
    return m


# --- jugadores más limpios ---------------------------------------------------


def test_ordena_por_misses_por_mapa():
    m = match(1, [
        game(1, [sc(1, miss=0), sc(2, miss=3)]),
        game(2, [sc(1, miss=0), sc(2, miss=1)]),
    ], players={1: "ana", 2: "beto"})
    ranking = clean_players(m)
    assert [p.username for p in ranking] == ["ana", "beto"]
    assert ranking[0].misses_per_map == 0
    assert ranking[1].misses_per_map == 2.0


def test_los_mapas_fallados_no_cuentan_pero_se_anotan():
    m = match(1, [
        game(1, [sc(1, miss=0), sc(2, miss=0)]),
        game(2, [sc(1, miss=0), sc(2, miss=50, passed=False)]),
    ])
    beto = next(p for p in clean_players(m) if p.user_id == 2)
    assert beto.maps == 1
    assert beto.failed_maps == 1
    assert beto.misses == 0


def test_empate_en_misses_decide_por_100_y_50_y_luego_por_mapas():
    m = match(1, [
        game(1, [sc(1, c100=4), sc(2, c100=1), sc(3, c100=1)]),
        game(2, [sc(3, c100=1)]),
    ])
    # 1: 4 golpes menores por mapa; 2: 1 por mapa (1 mapa); 3: 1 por mapa (2 mapas)
    assert [p.user_id for p in clean_players(m)] == [3, 2, 1]


def test_minimo_de_mapas():
    m = match(1, [game(1, [sc(1), sc(2)]), game(2, [sc(1)])])
    assert [p.user_id for p in clean_players(m, min_maps=2)] == [1]


def test_mapas_sin_ningun_miss():
    m = match(1, [
        game(1, [sc(1, miss=0)]), game(2, [sc(1, miss=2)]),
        game(3, [sc(1, miss=0)]), game(4, [sc(1, miss=1)]),
    ])
    p = clean_players(m)[0]
    assert (p.clean_maps, p.maps) == (2, 4)
    assert p.clean_pct == 0.5


def test_combina_varias_partidas_por_jugador():
    a = match(1, [game(1, [sc(1, miss=2)])], players={1: "ana"})
    b = match(2, [game(1, [sc(1, miss=0)])], players={1: "ana"})
    [p] = clean_players([a, b])
    assert (p.maps, p.misses, p.username) == (2, 2, "ana")


def test_jugador_sin_nombre_se_muestra_por_su_id():
    [p] = clean_players(match(1, [game(1, [sc(99)])]))
    assert p.username == "99"


# --- mapas más duros -----------------------------------------------------------


def test_los_mapas_con_mas_fallos_van_primero():
    m = match(1, [
        game(1, [sc(1), sc(2), sc(3), sc(4)], title="Facil"),
        game(2, [sc(1), sc(2, passed=False), sc(3, passed=False), sc(4)], title="Duro"),
        game(3, [sc(1), sc(2, passed=False), sc(3), sc(4)], title="Medio"),
    ])
    assert [d.title for d in hardest_maps(m)] == ["Duro", "Medio", "Facil"]
    assert hardest_maps(m)[0].fail_rate == 0.5


def test_a_igual_cantidad_de_fallos_decide_la_accuracy():
    m = match(1, [
        game(1, [sc(1, acc=0.99), sc(2, acc=0.99)], title="Alta"),
        game(2, [sc(1, acc=0.95), sc(2, acc=0.95)], title="Baja"),
    ])
    assert [d.title for d in hardest_maps(m)] == ["Baja", "Alta"]


def test_los_promedios_usan_solo_a_quienes_pasaron():
    m = match(1, [game(1, [sc(1, acc=0.98, miss=2), sc(2, acc=0.50, miss=40, passed=False)])])
    d = hardest_maps(m)[0]
    assert d.avg_accuracy == 0.98
    assert d.avg_misses == 2.0
    assert (d.fails, d.players) == (1, 2)


def test_mapa_que_todos_fallaron_es_el_mas_duro_y_no_rompe():
    m = match(1, [
        game(1, [sc(1), sc(2)], title="Normal"),
        game(2, [sc(1, passed=False), sc(2, passed=False)], title="Imposible"),
    ])
    ranking = hardest_maps(m)
    assert ranking[0].title == "Imposible"
    assert ranking[0].avg_accuracy is None


def test_mapas_sin_scores_se_ignoran_y_top_limita():
    m = match(1, [game(1, []), game(2, [sc(1)]), game(3, [sc(1)])])
    assert len(hardest_maps(m)) == 2
    assert len(hardest_maps(m, top=1)) == 1


# --- salidas.consola -----------------------------------------------------------


def test_tabla_de_limpios():
    m = match(1, [game(1, [sc(1, miss=0), sc(2, miss=3)])], players={1: "ana", 2: "beto"})
    text = "\n".join(format_clean(clean_players(m)))
    assert "ana" in text and "beto" in text
    assert text.index("ana") < text.index("beto")
    assert "1/1 (100%)" in text


def test_tabla_de_duros_muestra_fallos_y_la_partida_si_hay_varias():
    a = match(1, [game(1, [sc(1), sc(2, passed=False)], title="Uno")], name="Partida A")
    b = match(2, [game(1, [sc(1), sc(2)], title="Dos")], name="Partida B")
    solo = "\n".join(format_hardest(hardest_maps(a)))
    assert "1/2" in solo and "Partida A" not in solo
    varias = "\n".join(format_hardest(hardest_maps([a, b])))
    assert "Partida A" in varias and "Partida B" in varias


def test_tablas_vacias():
    assert format_clean([]) == ["No hay jugadores con mapas pasados."]
    assert format_hardest([]) == ["No hay mapas jugados."]


def test_comando_limpios_de_punta_a_punta(tmp_path, capsys):
    def rec(kind, **payload):
        return {"schema_version": 1, "match_id": 1, "kind": kind, **payload}

    score = {"user_id": 7, "score": 900, "accuracy": 0.98, "max_combo": 500,
             "passed": True, "rank": "A", "mods": [], "team": "red", "slot": 0,
             "statistics": {"count_miss": 0, "count_100": 1, "count_50": 0}}
    game = {"id": 100, "match_id": 1, "beatmap": {"id": 9, "title": "Mapa"},
            "start_time": "2026-01-01T10:10:00Z", "end_time": "2026-01-01T10:13:00Z",
            "mode": "osu", "scoring_type": "scorev2", "team_type": "team-vs",
            "mods": [], "scores": [score]}
    lines = [
        rec("match", match={"name": "Final", "start_time": None, "end_time": None}),
        rec("player", player={"id": 7, "username": "ana", "country_code": "AR"}),
        rec("event", event={"id": 10, "type": "game", "timestamp": "t", "user_id": None,
                            "text": None, "game": game}),
    ]
    f = tmp_path / "a.jsonl"
    f.write_text("\n".join(json.dumps(x) for x in lines) + "\n", encoding="utf-8")

    assert main(["limpios", str(f)]) == 0
    out = capsys.readouterr().out
    assert "Final" in out and "ana" in out

    assert main(["limpios", str(tmp_path / "no-existe.jsonl")]) == 1
