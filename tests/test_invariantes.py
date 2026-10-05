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


CAMINHO_KNOWN_ISSUES = config.RAIZ / "data" / "known_issues.csv"


@pytest.fixture(scope="module")
def known_issues() -> pd.DataFrame:
    """Catálogo de divergências reais do TSE já investigadas e sem explicação/conserto.

    Ver `docs/DADOS.md` (Armadilhas) e `scripts/diagnostico_ba_mg.py`. Qualquer
    divergência NÃO catalogada aqui ainda deve falhar o teste — só as
    exatamente listadas são toleradas.
    """
    if not CAMINHO_KNOWN_ISSUES.exists():
        return pd.DataFrame(columns=["uf", "cd_mun_tse", "campo", "diferenca"])
    return pd.read_csv(CAMINHO_KNOWN_ISSUES, dtype={"cd_mun_tse": "string"}, keep_default_na=False)


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


def test_soma_municipios_por_uf_fecha_com_arquivo_oficial_da_uf(
    mun_totais, uf_totais, known_issues
):
    """Soma dos municípios de cada UF == arquivo oficial da UF, exceto divergências catalogadas.

    Tolera SOMENTE as divergências listadas em `data/known_issues.csv`
    (investigadas, sem explicação/conserto no lado do TSE — ver
    `docs/DADOS.md`). Qualquer divergência nova, ou qualquer divergência
    catalogada que tenha desaparecido (TSE corrigiu), falha o teste — nos
    dois casos o catálogo precisa ser revisado manualmente, não é
    atualizado automaticamente.
    """
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

    observadas: set[tuple[str, str, int]] = set()
    for campo in ("eleitorado", "comparecimento", "abstencao", "validos", "brancos", "nulos_tvn"):
        dif = comparacao[f"{campo}_soma_mun"] - comparacao[f"{campo}_oficial_uf"]
        for uf, valor in zip(comparacao["uf"], dif, strict=True):
            if valor != 0:
                observadas.add((uf, campo, int(valor)))

    campos_totais = {
        "eleitorado",
        "comparecimento",
        "abstencao",
        "validos",
        "brancos",
        "nulos_tvn",
    }
    catalogadas = {
        (row.uf, row.campo, int(row.diferenca))
        for row in known_issues.itertuples()
        if row.campo in campos_totais
    }

    novas = observadas - catalogadas
    resolvidas = catalogadas - observadas
    assert not novas and not resolvidas, (
        f"catálogo data/known_issues.csv desatualizado — "
        f"{len(novas)} divergência(s) NOVA(s) não catalogada(s): {sorted(novas)[:20]}; "
        f"{len(resolvidas)} divergência(s) catalogada(s) que NÃO se repetiu/repetiram "
        f"(TSE pode ter corrigido — revisar o CSV): {sorted(resolvidas)[:20]}"
    )


def test_soma_municipios_por_uf_fecha_votos_por_candidato(
    mun_candidatos, uf_candidatos, known_issues
):
    """Soma de votos/candidato nos municípios de cada UF == arquivo oficial, exceto catalogadas."""
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
    observadas = {
        (row.uf, int(row.nr_candidato), int(row.diferenca))
        for row in comparacao.itertuples()
        if row.diferenca != 0
    }

    catalogadas: set[tuple[str, int, int]] = set()
    for row in known_issues.itertuples():
        if not row.campo.startswith("votos_candidato_"):
            continue
        nr_candidato = int(row.campo.removeprefix("votos_candidato_"))
        catalogadas.add((row.uf, nr_candidato, int(row.diferenca)))

    novas = observadas - catalogadas
    resolvidas = catalogadas - observadas
    assert not novas and not resolvidas, (
        f"catálogo data/known_issues.csv desatualizado — "
        f"{len(novas)} divergência(s) NOVA(s) de candidato não catalogada(s): "
        f"{sorted(novas)[:20]}; {len(resolvidas)} divergência(s) catalogada(s) que NÃO se "
        f"repetiu/repetiram (TSE pode ter corrigido — revisar o CSV): {sorted(resolvidas)[:20]}"
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


def test_comparecimento_mais_abstencao_igual_eleitorado_em_secoes_instaladas(
    mun_totais, uf_totais, br_totais
):
    """`comparecimento + abstencao == extra_e_esi`, SEMPRE — confirmado pela spec EA20.

    Correção pós-conferência com `docs/specs/tse-ea20-arquivo-de-resultado-unificado.pdf`
    (pg.18-19): `c` (comparecimento) e `a` (abstenção) são definidos como "o
    comparecimento/abstenção do eleitorado das **seções instaladas**" — ou
    seja, sempre fecham com `e.esi`, não com `e.te` (eleitorado total). A
    versão anterior deste teste comparava com `eleitorado` e só quando
    `status_totalizacao=="f"`; isso era uma aproximação empírica incorreta
    (falhava nos 40 municípios do exterior com seção nunca instalada, que já
    são `and="f"`). Este invariante vale em TODAS as linhas, sem exceção,
    independente de `status_totalizacao`.
    """
    for nome, df in (("municipio", mun_totais), ("uf", uf_totais), ("br", br_totais)):
        diferenca = df["comparecimento"] + df["abstencao"] - df["extra_e_esi"]
        divergentes = df[diferenca != 0]
        assert divergentes.empty, (
            f"[{nome}] comparecimento+abstencao != extra_e_esi: "
            f"{divergentes[['uf', 'cd_mun_tse']].to_dict('records')[:20]}"
        )


def test_eleitorado_igual_esi_somente_sem_pendencia_de_instalacao_ou_totalizacao(
    mun_totais, uf_totais, br_totais
):
    """`eleitorado == extra_e_esi` só quando `esni==0 e esnt==0` (não quando `and=="f"`).

    Pela spec (pg.9-10 e árvore de `e` na pg.17): `te = est + esnt` e
    `est = esi + esni`, logo `te == esi` só quando `esni==0` (nenhuma seção
    "não instalada") **e** `esnt==0` (nenhuma seção "não totalizada"). Essas
    duas condições são independentes de `and`:
    - os 40 "municípios" do exterior com seção nunca instalada têm
      `and="f"` mas `esni>0` (ver docs/DADOS.md);
    - os 11 municípios (BA: 3, MG: 8) com seções instaladas mas ainda não
      totalizadas têm `and="p"` (coerente — `and` de abrangência municipal
      em eleição federal vira "f" quando `snt==0`) e `esnt>0`.
    Documentamos aqui a condição exata, não aproximamos por `and`.
    """
    for nome, df in (("municipio", mun_totais), ("uf", uf_totais), ("br", br_totais)):
        sem_pendencia = (df["extra_e_esni"] == 0) & (df["extra_e_esnt"] == 0)
        diferenca = df["eleitorado"] - df["extra_e_esi"]
        # equivalência completa: sem pendência <=> eleitorado==esi
        inconsistente = df[sem_pendencia != (diferenca == 0)]
        assert inconsistente.empty, (
            f"[{nome}] (esni==0 e esnt==0) não é equivalente a eleitorado==esi: "
            f"{inconsistente[['uf', 'cd_mun_tse']].to_dict('records')[:20]}"
        )


def test_validos_mais_brancos_mais_nulos_tvn_mais_anulados_igual_comparecimento(
    mun_totais, uf_totais, br_totais
):
    """`tv = vb + vn + vnt + van + vansj + vv`, fórmula exata da spec EA20 (pg.20).

    Correção pós-conferência: a versão anterior deste teste checava apenas
    `validos+brancos+nulos_tvn==comparecimento`, omitindo `anulados` (`van`)
    e `anulados_sub_judice` (`vansj`) — coincidentemente sempre 0 nesta
    eleição (ver `test_anulados_e_sub_judice_sao_zero_nesta_amostra` abaixo),
    então a conta "fechava" por acidente, não por estar completa. A fórmula
    abaixo é a da spec, válida mesmo que `van`/`vansj` deixem de ser 0 (ex.
    se algum candidato tiver a candidatura anulada depois do 1º turno).
    `tvn` (não `vn` isolado) é usado porque `tvn = vn + vnt` por definição
    da spec (pg.21).
    """
    for nome, df in (("municipio", mun_totais), ("uf", uf_totais), ("br", br_totais)):
        diferenca = (
            df["validos"]
            + df["brancos"]
            + df["nulos_tvn"]
            + df["anulados"]
            + df["anulados_sub_judice"]
            - df["comparecimento"]
        )
        divergentes = df[diferenca != 0]
        assert divergentes.empty, (
            f"[{nome}] vv+vb+tvn+van+vansj != comparecimento (tv): "
            f"{divergentes[['uf', 'cd_mun_tse']].to_dict('records')[:20]}"
        )


def test_anulados_e_sub_judice_sao_zero_nesta_amostra(mun_totais, uf_totais, br_totais):
    """Registra explicitamente que `van`/`vansj` são 0 em toda a coleta de 05/10/2026.

    Não é um invariante estrutural da eleição (a spec não garante que sejam
    sempre 0 — ver `test_validos_mais_brancos_mais_nulos_tvn_mais_anulados_igual_comparecimento`,
    que não depende disso). É só uma observação da amostra atual, registrada
    em teste para detectar se isso mudar em coletas futuras.
    """
    for df in (mun_totais, uf_totais, br_totais):
        assert (df["anulados"] == 0).all()
        assert (df["anulados_sub_judice"] == 0).all()


def test_vvc_igual_validos_mais_anulados_mais_sub_judice(mun_totais):
    """`vvc = vv + van + vansj` (Votos a Votáveis Concorrentes), spec EA20 pg.19-20."""
    diferenca = mun_totais["extra_v_vvc"] - (
        mun_totais["validos"] + mun_totais["anulados"] + mun_totais["anulados_sub_judice"]
    )
    assert (diferenca == 0).all()


def test_vnom_igual_validos_para_presidente(mun_totais, uf_totais, br_totais):
    """`vnom == validos` para Presidente: cargo majoritário, sem voto de legenda (`vl`).

    Pela spec, `vv = vnom + vl` e `vl` "deve estar presente somente para
    cargos proporcionais" (pg.20) — Presidente é majoritário, então `vl`
    não deveria existir e `vnom` deveria igualar `vv` em toda a amostra.
    """
    for df in (mun_totais, uf_totais, br_totais):
        assert (df["extra_v_vnom"] == df["validos"]).all()


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
