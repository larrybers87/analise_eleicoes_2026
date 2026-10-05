"""Testes de invariantes sobre os Parquet gerados por `scripts/processar_presidente.py`.

Regra do projeto: se um invariante falhar, o teste FALHA — não é ajustado
para passar escondendo o problema. Divergências reais encontradas vão para
`docs/DADOS.md` (seção Armadilhas), não para dentro do teste.

Estes testes são de integração (leem `data/processed/*.parquet`, gerados a
partir da coleta real) e são pulados automaticamente se os arquivos ainda não
existirem — ex. antes da primeira coleta completa.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from eleicao import config

pytestmark = pytest.mark.skipif(
    not (config.DATA_PROCESSED / "presidente_t1_municipio_totais.parquet").exists(),
    reason="data/processed/*.parquet não gerado ainda — rode scripts/processar_presidente.py",
)


@pytest.fixture(scope="module")
def mun_totais() -> pd.DataFrame:
    return pd.read_parquet(config.DATA_PROCESSED / "presidente_t1_municipio_totais.parquet")


@pytest.fixture(scope="module")
def mun_candidatos() -> pd.DataFrame:
    return pd.read_parquet(config.DATA_PROCESSED / "presidente_t1_municipio.parquet")


@pytest.fixture(scope="module")
def uf_totais() -> pd.DataFrame:
    return pd.read_parquet(config.DATA_PROCESSED / "presidente_t1_uf_totais.parquet")


@pytest.fixture(scope="module")
def uf_candidatos() -> pd.DataFrame:
    return pd.read_parquet(config.DATA_PROCESSED / "presidente_t1_uf.parquet")


@pytest.fixture(scope="module")
def br_totais() -> pd.DataFrame:
    return pd.read_parquet(config.DATA_PROCESSED / "presidente_t1_br_totais.parquet")


@pytest.fixture(scope="module")
def br_candidatos() -> pd.DataFrame:
    return pd.read_parquet(config.DATA_PROCESSED / "presidente_t1_br.parquet")


@pytest.fixture(scope="module")
def config_municipios() -> dict:
    caminho = config.caminho_local(config.caminho_config_municipios(config.ELEICAO_FEDERAL_T1))
    return json.loads(Path(caminho).read_text(encoding="utf-8"))


def test_nenhum_municipio_do_config_ficou_sem_linha(mun_totais, config_municipios):
    esperados = {
        f"{abrangencia['cd']}{m['cd']}"
        for abrangencia in config_municipios["abr"]
        for m in abrangencia["mu"]
    }
    obtidos = {
        f"{uf}{cd}" for uf, cd in zip(mun_totais["uf"], mun_totais["cd_mun_tse"], strict=True)
    }
    faltando = esperados - obtidos
    assert not faltando, (
        f"{len(faltando)} município(s) do config sem linha em "
        f"presidente_t1_municipio_totais.parquet: {sorted(faltando)[:20]}"
    )
    assert len(mun_totais) == len(esperados) == 5757


def test_contagem_exterior_e_brasil(mun_totais):
    exterior = mun_totais[mun_totais["eh_exterior"]]
    brasil = mun_totais[~mun_totais["eh_exterior"]]
    assert len(exterior) == 186
    assert len(brasil) == 5571


def test_soma_municipios_por_uf_fecha_com_arquivo_oficial_da_uf(mun_totais, uf_totais):
    """Soma dos municípios de cada UF == arquivo oficial da UF (eleitorado/comparecimento/etc.)."""
    agregado = mun_totais.groupby("uf", as_index=False).agg(
        eleitorado=("eleitorado", "sum"),
        comparecimento=("comparecimento", "sum"),
        abstencao=("abstencao", "sum"),
        validos=("validos", "sum"),
        brancos=("brancos", "sum"),
        nulos_tvn=("nulos_tvn", "sum"),
    )
    comparacao = agregado.merge(
        uf_totais[
            ["uf", "eleitorado", "comparecimento", "abstencao", "validos", "brancos", "nulos_tvn"]
        ],
        on="uf",
        suffixes=("_soma_mun", "_oficial_uf"),
    )

    divergencias = []
    for campo in ("eleitorado", "comparecimento", "abstencao", "validos", "brancos", "nulos_tvn"):
        dif = comparacao[f"{campo}_soma_mun"] - comparacao[f"{campo}_oficial_uf"]
        for uf, valor in zip(comparacao["uf"], dif, strict=True):
            if valor != 0:
                divergencias.append((uf, campo, int(valor)))

    assert not divergencias, (
        f"{len(divergencias)} divergência(s) soma-municípios vs UF oficial "
        f"(uf, campo, soma_mun - oficial_uf): {divergencias[:30]}"
    )


def test_soma_municipios_por_uf_fecha_votos_por_candidato(mun_candidatos, uf_candidatos):
    """Soma de votos por candidato nos municípios de cada UF == arquivo oficial da UF."""
    agregado = (
        mun_candidatos.groupby(["uf", "nr_candidato"], as_index=False)["votos"]
        .sum()
        .rename(columns={"votos": "votos_soma_mun"})
    )
    oficial = uf_candidatos[["uf", "nr_candidato", "votos"]].rename(
        columns={"votos": "votos_oficial_uf"}
    )
    comparacao = agregado.merge(oficial, on=["uf", "nr_candidato"], how="outer", indicator=True)

    nao_casados = comparacao[comparacao["_merge"] != "both"]
    assert nao_casados.empty, (
        f"combinações uf/candidato presentes só de um lado: "
        f"{nao_casados[['uf', 'nr_candidato', '_merge']].to_dict('records')[:20]}"
    )

    comparacao["diferenca"] = comparacao["votos_soma_mun"] - comparacao["votos_oficial_uf"]
    divergentes = comparacao[comparacao["diferenca"] != 0]
    assert divergentes.empty, (
        f"{len(divergentes)} divergência(s) de votos por candidato (soma municípios vs UF "
        f"oficial): {divergentes[['uf', 'nr_candidato', 'diferenca']].to_dict('records')[:30]}"
    )


def test_soma_ufs_fecha_com_br_oficial(uf_totais, br_totais):
    """Soma de todas as UFs + zz == arquivo oficial BR."""
    soma = uf_totais[
        ["eleitorado", "comparecimento", "abstencao", "validos", "brancos", "nulos_tvn"]
    ].sum()
    oficial = br_totais.iloc[0]

    campos = ("eleitorado", "comparecimento", "abstencao", "validos", "brancos", "nulos_tvn")
    divergencias = {
        campo: int(soma[campo] - oficial[campo])
        for campo in campos
        if soma[campo] != oficial[campo]
    }
    assert not divergencias, f"soma UF+zz != BR oficial: {divergencias}"


def test_soma_ufs_fecha_votos_por_candidato_br(uf_candidatos, br_candidatos):
    agregado = (
        uf_candidatos.groupby("nr_candidato", as_index=False)["votos"]
        .sum()
        .rename(columns={"votos": "votos_soma_uf"})
    )
    oficial = br_candidatos[["nr_candidato", "votos"]].rename(columns={"votos": "votos_oficial_br"})
    comparacao = agregado.merge(oficial, on="nr_candidato", how="outer", indicator=True)

    nao_casados = comparacao[comparacao["_merge"] != "both"]
    assert nao_casados.empty, f"candidato presente só de um lado: {nao_casados.to_dict('records')}"

    comparacao["diferenca"] = comparacao["votos_soma_uf"] - comparacao["votos_oficial_br"]
    divergentes = comparacao[comparacao["diferenca"] != 0]
    assert divergentes.empty, (
        f"divergência de votos por candidato (soma UF+zz vs BR oficial): "
        f"{divergentes.to_dict('records')}"
    )


def _so_totalizacao_final(df: pd.DataFrame) -> pd.DataFrame:
    return df[df["status_totalizacao"] == "f"]


def test_comparecimento_mais_abstencao_igual_eleitorado_quando_final(
    mun_totais, uf_totais, br_totais
):
    """`comparecimento + abstencao == eleitorado` só é exato com totalização final (`and == 'f'`).

    Ver docs/DADOS.md (Armadilhas) — enquanto `and == 'p'`, a soma correta é
    `comparecimento + abstencao == extra_e_esi` (eleitorado das seções já
    apuradas), não `eleitorado` (= total do colégio eleitoral).
    """
    for nome, df in (("municipio", mun_totais), ("uf", uf_totais), ("br", br_totais)):
        finais = _so_totalizacao_final(df)
        if finais.empty:
            continue
        diferenca = finais["comparecimento"] + finais["abstencao"] - finais["eleitorado"]
        divergentes = finais[diferenca != 0]
        assert divergentes.empty, (
            f"[{nome}] comparecimento+abstencao != eleitorado em abrangência com "
            f"status_totalizacao=='f': {divergentes[['uf', 'cd_mun_tse']].to_dict('records')[:20]}"
        )


def test_validos_mais_brancos_mais_nulos_tvn_igual_comparecimento(mun_totais, uf_totais, br_totais):
    """`validos + brancos + nulos == comparecimento` usando `nulos_tvn` (não `nulos_vn`).

    `v.tvn` (nulos "totais") = `v.vn` (nulos comuns) + `v.vnt` (nulos
    "técnicos"); só `tvn` fecha a conta com `comparecimento` (= `v.tv`).
    Este invariante não depende de totalização final: `vv + vb + tvn == tv`
    vale sempre, pois `tv` é apenas a soma dos votos já contabilizados até o
    momento (igual a `comparecimento`), não o eleitorado total.
    """
    for nome, df in (("municipio", mun_totais), ("uf", uf_totais), ("br", br_totais)):
        diferenca = df["validos"] + df["brancos"] + df["nulos_tvn"] - df["comparecimento"]
        divergentes = df[diferenca != 0]
        assert divergentes.empty, (
            f"[{nome}] validos+brancos+nulos_tvn != comparecimento: "
            f"{divergentes[['uf', 'cd_mun_tse']].to_dict('records')[:20]}"
        )


def test_nulos_vn_isolado_nao_fecha_a_conta_sozinho(mun_totais):
    """Documenta por que usamos `tvn` e não `vn`: `vn` isolado NÃO fecha com comparecimento.

    `tvn = vn + vnt` (nulos comuns + nulos "técnicos"). Se em algum momento
    `vnt` virar sempre 0, essa distinção deixaria de ter efeito prático — mas
    não removemos a documentação/teste por isso.
    """
    diferenca_vn = (
        mun_totais["validos"]
        + mun_totais["brancos"]
        + mun_totais["nulos_vn"]
        - mun_totais["comparecimento"]
    )
    assert (diferenca_vn != 0).any(), (
        "inesperado: nulos_vn isolado fechou a conta em todos os municípios — "
        "revisar se extra_v_vnt (nulos 'técnicos') é sempre 0 nesta eleição"
    )
