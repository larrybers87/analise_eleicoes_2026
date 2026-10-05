"""Testes de `eleicao.forca` — % por município e percentil 98 da escala (D-018).

Os testes do percentil são de integração (leem `data/processed/*.parquet`) e
pulam sozinhos se a coleta ainda não tiver sido feita, igual a
`tests/test_invariantes.py`. O ponto crítico que eles guardam: o **exterior**
(`uf == "zz"`, 186 locais) não pode entrar nem na matriz de percentuais nem no
cálculo do percentil — é fácil de errar em silêncio, porque o resultado
continua "parecendo certo".
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from eleicao import config
from eleicao.forca import PERCENTIL_FORCA, escala_maxima, pct_por_municipio

pytestmark = pytest.mark.skipif(
    not (config.DATA_PROCESSED / "presidente_t1_municipio_totais.parquet").exists(),
    reason="data/processed/*.parquet não gerado ainda — rode scripts/processar_presidente.py",
)


@pytest.fixture(scope="module")
def totais() -> pd.DataFrame:
    return pd.read_parquet(config.DATA_PROCESSED / "presidente_t1_municipio_totais.parquet")


@pytest.fixture(scope="module")
def candidatos() -> pd.DataFrame:
    return pd.read_parquet(config.DATA_PROCESSED / "presidente_t1_municipio.parquet")


@pytest.fixture(scope="module")
def pct(candidatos, totais) -> pd.DataFrame:
    return pct_por_municipio(candidatos, totais)


def test_so_entram_municipios_do_brasil(pct, totais):
    esperado = int((~totais["eh_exterior"]).sum())
    assert len(pct) == esperado == 5571


def test_nenhum_local_do_exterior_entra_no_indice(pct, totais):
    # o exterior não tem cd_mun_ibge; a checagem direta é por cd_mun_tse,
    # garantindo que nenhuma linha `zz` virou município do Brasil no caminho.
    ext = totais[totais["eh_exterior"]]
    assert len(ext) == 186
    assert set(pct.index).isdisjoint(set(ext["cd_mun_tse"].astype(str)))
    assert set(pct.index) == set(totais[~totais["eh_exterior"]]["cd_mun_ibge"].astype(str))


def test_indice_em_ordem_numerica_crescente(pct):
    # é essa ordem que os arrays posicionais de forca/cand_<nr>.json seguem
    assert list(pct.index) == sorted(pct.index, key=int)


def test_percentuais_somam_100_por_municipio(pct):
    soma = pct.sum(axis=1)
    assert np.allclose(soma, 100.0, atol=1e-6)


def test_zeros_do_candidato_entram_na_conta(pct):
    # Rui Costa Pimenta (29) tem 0 voto na maioria dos municípios; esses zeros
    # PRECISAM estar na matriz, senão o percentil seria calculado só onde ele
    # pontuou e a escala de cor sairia várias vezes maior.
    assert (pct[29] == 0).sum() > 1000


def test_p98_ignora_o_exterior(pct, candidatos, totais):
    """p98 com e sem exterior tem que divergir — e o oficial é o SEM.

    Construímos de propósito a versão "errada" (exterior incluído) e exigimos
    que `escala_maxima` NÃO devolva esse valor para pelo menos um candidato.
    Sem esse teste, incluir o exterior passaria despercebido: são 186 linhas
    contra 5.571, um deslocamento pequeno no percentil.
    """
    validos = totais.set_index(totais["cd_mun_tse"].astype(str) + totais["uf"])["validos"]
    cand = candidatos.copy()
    cand["chave"] = cand["cd_mun_tse"].astype(str) + cand["uf"]
    com_ext = (
        cand.pivot_table(index="chave", columns="nr_candidato", values="votos", fill_value=0)
        .div(validos.replace(0, np.nan), axis=0)
        .fillna(0.0)
        * 100
    )
    assert len(com_ext) == len(pct) + 186

    divergiram = 0
    for nr in pct.columns:
        certo = escala_maxima(pct[nr])
        errado = float(np.percentile(com_ext[nr].to_numpy(), PERCENTIL_FORCA))
        if abs(certo - errado) > 1e-9:
            divergiram += 1
    assert divergiram > 0, "incluir o exterior não mudou nenhum p98 — teste não está vigiando nada"


def test_p98_fica_entre_a_mediana_e_o_maximo(pct):
    for nr in pct.columns:
        teto = escala_maxima(pct[nr])
        assert teto > 0
        assert pct[nr].median() <= teto <= pct[nr].max()


def test_p98_bate_com_numpy_percentile_direto(pct):
    for nr in pct.columns:
        assert escala_maxima(pct[nr]) == pytest.approx(
            float(np.percentile(pct[nr].to_numpy(), PERCENTIL_FORCA))
        )


def test_p98_deixa_cerca_de_2_porcento_dos_municipios_acima(pct):
    for nr in pct.columns:
        acima = int((pct[nr] > escala_maxima(pct[nr])).sum())
        assert acima <= len(pct) * 0.02 + 1


def test_escala_maxima_rejeita_serie_vazia():
    with pytest.raises(ValueError):
        escala_maxima(pd.Series([], dtype=float))


def test_escala_maxima_cai_para_o_maximo_quando_o_percentil_da_zero():
    # candidato hipotético com votos em 1 município só: p98 = 0, mas a escala
    # não pode degenerar (divisão por zero no front-end).
    serie = pd.Series([0.0] * 199 + [7.5])
    assert escala_maxima(serie) == pytest.approx(7.5)
