"""Bloco "Previsto × real" (`eleicao.comparacao_web`): consistência com os parquet reais."""

from __future__ import annotations

import json
import re

import pandas as pd
import pytest

from eleicao import config
from eleicao.comparacao_web import montar

PROC = config.DATA_PROCESSED
FLUXO = config.RAIZ / "data" / "interim" / "fluxo_t1_t2"
ARQUIVOS = [
    PROC / "projecao_t2_2026_br.parquet",
    PROC / "projecao_t2_2026_uf.parquet",
    PROC / "presidente_t2_br.parquet",
    PROC / "presidente_t2_br_totais.parquet",
    PROC / "presidente_t2_uf.parquet",
    FLUXO / "decomposicao_erro.csv",
    FLUXO / "ganhos_minimos.json",
]
pytestmark = pytest.mark.skipif(
    not all(a.exists() for a in ARQUIVOS), reason="faltam T2 apurado ou data/interim/fluxo_t1_t2"
)


@pytest.fixture(scope="module")
def cmp() -> dict:
    br, uf, cb, tb, cu, dec, gan = ARQUIVOS
    return montar(
        pd.read_parquet(br),
        pd.read_parquet(uf),
        pd.read_parquet(cb),
        pd.read_parquet(tb),
        pd.read_parquet(cu),
        pd.read_csv(dec),
        json.loads(gan.read_text(encoding="utf-8")),
    )


def test_placar_bate_com_o_resultado_oficial(cmp: dict) -> None:
    cand = pd.read_parquet(ARQUIVOS[2])
    pl = cand.loc[cand["nr_candidato"].astype(int) == 22, "votos"].sum()
    pt = cand.loc[cand["nr_candidato"].astype(int) == 13, "votos"].sum()
    assert cmp["placar"]["real_pct_pl"] == pytest.approx(100 * pl / (pl + pt), abs=1e-3)
    assert cmp["placar"]["erro_pp"] == pytest.approx(
        cmp["placar"]["prev_pct_pl"] - cmp["placar"]["real_pct_pl"], abs=1e-3
    )


def test_mapa_tem_27_ufs_sem_exterior(cmp: dict) -> None:
    assert len(cmp["ufs"]) == 27
    assert "zz" not in cmp["ufs"]


def test_decomposicao_soma_perto_do_erro_em_votos(cmp: dict) -> None:
    """A soma das origens é o erro em votos de vantagem; confere com o erro em p.p. (~20%)."""
    soma = sum(d["milhoes"] for d in cmp["decomposicao"]) * 1e6
    validos = 124_082_273
    erro_votos = cmp["placar"]["erro_pp"] / 100 * validos * 2
    assert soma == pytest.approx(erro_votos, rel=0.2)


def test_toda_chave_data_c_do_html_tem_texto(cmp: dict) -> None:
    html = (config.RAIZ / "web" / "projecao.html").read_text(encoding="utf-8")
    chaves = set(re.findall(r'data-c="([^"]+)"', html))
    assert chaves, "nenhum data-c no HTML"
    assert chaves <= set(cmp["textos"]), chaves - set(cmp["textos"])
