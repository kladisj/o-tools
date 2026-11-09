import json
import re
import xml.etree.ElementTree as ET

from osuctools.cli import main
from osuctools.salidas.html import render
from osuctools.stats import MapResult


def result(i, red, blue, cum, red_wins, blue_wins, flipped=False):
    winner = "red" if red > blue else "blue" if blue > red else None
    return MapResult(
        game_id=i, title=f"Mapa {i}", version="Insane", red=red, blue=blue,
        diff=red - blue, winner=winner, cumulative_diff=cum,
        red_wins=red_wins, blue_wins=blue_wins, flipped=flipped,
    )


RESULTS = [
    result(1, 3000, 1000, 2000, 1, 0),
    result(2, 500, 2500, 0, 1, 1),
    result(3, 1500, 1000, 500, 2, 1),
]


def svg_of(page: str) -> str:
    return re.search(r"<svg.*?</svg>", page, re.S).group(0)


def test_la_pagina_muestra_nombre_marcador_y_el_svg_es_valido():
    page = render("OWC2026: (China) VS (France)", RESULTS, red_name="China", blue_name="Francia")
    assert "OWC2026: (China) VS (France)" in page
    assert "China 2" in page and "1 Francia" in page  # marcador de mapas
    ET.fromstring(svg_of(page))  # si el SVG está mal formado, esto falla


def test_los_nombres_se_escapan():
    page = render("<script>x</script>", RESULTS, red_name="<b>R</b>")
    assert "<script>x</script>" not in page
    assert "&lt;script&gt;" in page
    assert "<b>R</b>" not in page


def test_recarga_automatica_solo_si_se_pide():
    assert 'http-equiv="refresh"' not in render("t", RESULTS)
    assert '<meta http-equiv="refresh" content="5">' in render("t", RESULTS, refresh=5)


def test_fondo_transparente():
    assert "background: transparent" in render("t", RESULTS, transparent=True)
    assert "background: #14161a" in render("t", RESULTS)


def test_sin_tabla():
    assert "<table" in render("t", RESULTS)
    assert "<table" not in render("t", RESULTS, table=False)


def test_sin_mapas_muestra_un_aviso_y_sigue_recargando():
    page = render("t", [], refresh=5)
    assert "Todavía no hay mapas" in page
    assert '<meta http-equiv="refresh"' in page


def test_marca_con_asterisco_los_mapas_donde_cambia_el_ganador():
    flipped = [result(1, 1000, 3000, -2000, 0, 1, flipped=True)]
    page = render("t", flipped)
    assert "Si contaran también los jugadores que fallaron" in page
    assert "Si contaran" not in render("t", RESULTS)


def test_un_solo_mapa_y_diferencia_cero_no_rompen():
    solo = [result(1, 500, 500, 0, 0, 0)]
    page = render("t", solo)
    assert "Empate" in page
    ET.fromstring(svg_of(page))


# --- el comando grafico ------------------------------------------------------------


def jsonl_lines(match_ids=(1,)):
    lines = []
    for mid in match_ids:
        def rec(kind, **payload):
            return {"schema_version": 1, "match_id": mid, "kind": kind, **payload}

        def score(uid, pts, team):
            return {"user_id": uid, "score": pts, "accuracy": 0.98, "max_combo": 500,
                    "passed": True, "rank": "A", "mods": [], "team": team, "slot": 0,
                    "statistics": {"count_miss": 0}}

        game = {"id": 100 + mid, "match_id": mid, "beatmap": {"id": 9, "title": "Mapa"},
                "start_time": "2026-01-01T10:10:00Z", "end_time": "2026-01-01T10:13:00Z",
                "mode": "osu", "scoring_type": "scorev2", "team_type": "team-vs", "mods": [],
                "scores": [score(1, 900, "red"), score(2, 800, "blue")]}
        lines += [
            rec("match", match={"name": f"Final {mid}", "start_time": None, "end_time": None}),
            rec("event", event={"id": 10, "type": "game", "timestamp": "t", "user_id": None,
                                "text": None, "game": game}),
        ]
    return lines


def write_jsonl(path, lines):
    path.write_text("\n".join(json.dumps(x) for x in lines) + "\n", encoding="utf-8")
    return path


def test_comando_grafico_escribe_la_pagina(tmp_path):
    f = write_jsonl(tmp_path / "a.jsonl", jsonl_lines())
    out = tmp_path / "salida" / "g.html"  # la carpeta se crea sola
    assert main(["grafico", str(f), "--out", str(out), "--rojo", "China", "--azul", "Francia"]) == 0
    page = out.read_text(encoding="utf-8")
    assert "Final 1" in page and "China 1" in page
    assert not list(out.parent.glob("*.tmp"))  # no queda el archivo temporal


def test_comando_grafico_con_varias_partidas_da_error(tmp_path):
    f = write_jsonl(tmp_path / "a.jsonl", jsonl_lines(match_ids=(1, 2)))
    assert main(["grafico", str(f), "--out", str(tmp_path / "g.html")]) == 1
    assert not (tmp_path / "g.html").exists()


def test_comando_grafico_con_archivo_inexistente_da_error(tmp_path):
    assert main(["grafico", str(tmp_path / "no-existe.jsonl"), "--out", str(tmp_path / "g.html")]) == 1
