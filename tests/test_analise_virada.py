"""Swing T1→T2 (`eleicao.analise.virada`): margem entre finalistas e resumo por grupo."""

from __future__ import annotations

import pandas as pd
import pytest

from eleicao.analise import virada


def _turno(pt: list[int], pl: list[int], terceiros: list[int]) -> pd.DataFrame:
    n = len(pt)
    cand = []
    for i in range(n):
        for nr, v in ((13, pt[i]), (22, pl[i]), (12, terceiros[i])):
            cand.append({"uf": "mg", "cd_mun_tse": f"{i:05d}", "nr_candidato": nr, "votos": v})
    tot = pd.DataFrame(
        {
            "uf": "mg",
            "cd_mun_tse": [f"{i:05d}" for i in range(n)],
            "nm_mun": "x",
            "cd_mun_ibge": 3100000,
            "eleitorado": [pt[i] + pl[i] + terceiros[i] + 10 for i in range(n)],
            "validos": [pt[i] + pl[i] + terceiros[i] for i in range(n)],
            "abstencao": 10,
        }
    )
    return virada.base_turno(pd.DataFrame(cand), tot)


def test_margem_e_entre_finalistas_sem_os_terceiros() -> None:
    t = _turno([60], [30], [10])
    assert t["margem"].iloc[0] == pytest.approx(100 * 30 / 90)


def test_swing_nao_e_inflado_por_terceiros() -> None:
    """T2 = T1 sem terceiros e mesma proporção entre finalistas: swing zero."""
    t1 = _turno([600, 100], [300, 800], [100, 100])
    t2 = _turno([600, 100], [300, 800], [0, 0])
    d = virada.virada_municipal(t1, t2)
    assert d["swing"].abs().max() == pytest.approx(0.0)


def test_troca_de_lado_e_resumo() -> None:
    t1 = _turno([40, 70], [60, 30], [0, 0])
    t2 = _turno([55, 70], [45, 30], [0, 0])
    d = virada.virada_municipal(t1, t2)
    assert d["virou_pt"].tolist() == [True, False]
    r = virada.resumo_grupo(d.assign(g="a"), "g").iloc[0]
    assert r["virou_pt"] == 1
    assert r["swing"] == pytest.approx(r["margem_t2"] - r["margem_t1"])
    assert r["ganho_margem_votos"] == pytest.approx(30)


def test_faixa_porte_limites() -> None:
    f = virada.faixa_porte(pd.Series([3_000.0, 5_000.0, 5_001.0, 600_000.0]))
    assert f.tolist() == ["até 5 mil", "até 5 mil", "5–10 mil", "mais de 500 mil"]
