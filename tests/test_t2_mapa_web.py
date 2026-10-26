"""`resultados/t2.json` (modos "2º turno" e "Virada"): alinhamento, escalas e totais."""

from __future__ import annotations

import json

import pandas as pd
import pytest

from eleicao import config, t2_mapa_web

VIRADA = config.RAIZ / "data" / "interim" / "virada" / "virada_municipal.parquet"
META = config.RAIZ / "web" / "data" / "meta.json"
T2 = config.RAIZ / "web" / "data" / "resultados" / "t2.json"

sem_dados = pytest.mark.skipif(
    not (VIRADA.exists() and META.exists()), reason="rode scripts/virada_t2.py e exportar_web.py"
)


def _mini() -> pd.DataFrame:
    """Três municípios em duas UFs, fora de ordem de cd_mun_ibge."""
    linhas = [
        ("mg", "00003", 3100003, 40, 60, 55, 45),
        ("ac", "00001", 1200001, 70, 30, 75, 25),
        ("ac", "00002", 1200002, 45, 55, 52, 48),
    ]
    d = pd.DataFrame(
        linhas, columns=["uf", "cd_mun_tse", "cd_mun_ibge_t1", "pt_t1", "pl_t1", "pt_t2", "pl_t2"]
    )
    d["nm_mun_t1"] = "X"
    d["eleitorado_t2"] = 1000
    d["margem_t1"] = 100 * (d["pt_t1"] - d["pl_t1"]) / (d["pt_t1"] + d["pl_t1"])
    d["margem_t2"] = 100 * (d["pt_t2"] - d["pl_t2"]) / (d["pt_t2"] + d["pl_t2"])
    d["swing"] = d["margem_t2"] - d["margem_t1"]
    for c in ("abstencao_t1", "abstencao_t2", "validos_t1", "validos_t2", "eleitorado_t1"):
        d[c] = 1000
    d["dmargem_votos"] = (d["pt_t2"] - d["pl_t2"]) - (d["pt_t1"] - d["pl_t1"])
    d["virou_pt"] = (d["margem_t1"] < 0) & (d["margem_t2"] > 0)
    d["virou_pl"] = (d["margem_t1"] > 0) & (d["margem_t2"] < 0)
    return d


def test_ordena_por_ibge_e_marca_quem_virou() -> None:
    out = t2_mapa_web.montar(_mini(), {"ac": 0, "mg": 2}, 3, "#ddd")
    assert out["pt"] == [75, 52, 55]  # cd_mun_ibge 1200001, 1200002, 3100003
    assert out["vr"] == [0, 1, 1]
    assert out["escala_virada"]["virou_pl"] == []
    assert out["br"][out["formato_regiao"].index("virou_pt")] == 2


def test_levanta_se_offsets_ou_n_nao_batem() -> None:
    with pytest.raises(ValueError, match="offsets"):
        t2_mapa_web.montar(_mini(), {"ac": 0, "mg": 1}, 3, "#ddd")
    with pytest.raises(ValueError, match="meta.n_municipios_br"):
        t2_mapa_web.montar(_mini(), {"ac": 0, "mg": 2}, 4, "#ddd")


@sem_dados
def test_arquivo_real_alinha_com_o_meta() -> None:
    meta = json.loads(META.read_text(encoding="utf-8"))
    out = t2_mapa_web.montar(
        pd.read_parquet(VIRADA), meta["forca_offsets"], meta["n_municipios_br"], "#ddd"
    )
    n = meta["n_municipios_br"]
    for k in ("m1", "m2", "sw", "pt", "pl", "aptos", "vr"):
        assert len(out[k]) == n
    assert sum(1 for v in out["vr"] if v == 1) == out["br"][6]
    assert (
        sum(1 for v in out["vr"] if v == -1)
        == out["br"][7]
        == len(out["escala_virada"]["virou_pl"])
    )
    # soma das UFs = Brasil sem exterior
    assert sum(u[3] for u in out["ufs"].values()) == out["br"][3] == sum(out["pt"])


@pytest.mark.skipif(not T2.exists(), reason="rode scripts/exportar_web_t2.py")
def test_json_publicado_tem_escalas_prontas() -> None:
    d = json.loads(T2.read_text(encoding="utf-8"))
    assert d["escala_t2"]["limite_pp"] == 40.0
    assert d["escala_virada"]["limite_pp"] == 10.0
    assert len(d["escala_virada"]["valores"]) == len(d["escala_virada"]["cores"])
    assert d["escala_virada"]["n_alem_escala"] < d["escala_virada"]["n_total"] * 0.05
