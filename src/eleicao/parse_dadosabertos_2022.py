"""Parsers dos CSVs de Resultados (2018 e 2022; mesmo layout) do Portal de Dados Abertos do TSE.

Fonte: `data/raw/dadosabertos/cdn.tse.jus.br/estatistica/sead/odsele/...`
(ver docs/DADOS.md). Usamos só os membros `*_BR.csv` de dois pacotes —
"votacao_candidato_munzona" (votos por candidato) e "detalhe_votacao_munzona"
(totais: eleitorado/comparecimento/abstenção/brancos/nulos) — porque
Presidente tem abrangência **federal**: todo o resultado nacional já está
nesse único arquivo (não precisa dos outros 27 CSVs por UF do zip, que são
para cargos de abrangência estadual/municipal). Funções puras: recebem o
DataFrame já lido do CSV (``dtype=str``, ``sep=";"``, ``encoding="latin-1"``)
e devolvem o schema normalizado, agregado de zona para município.
"""

from __future__ import annotations

import pandas as pd

CARGO_PRESIDENTE = "Presidente"


def parse_candidatos_2022(df_bruto: pd.DataFrame, *, turno: int) -> pd.DataFrame:
    """Agrega `votacao_candidato_munzona_2022_BR.csv` de zona para município.

    Filtra `DS_CARGO == "Presidente"` e `NR_TURNO == turno`. Colunas de
    saída no schema comparável a `presidente_t1_municipio.parquet`:
    `uf, cd_mun_tse, nr_candidato, nm_urna, partido, votos`. `pct_validos`
    **não** é calculado aqui (precisa do total de válidos do município, que
    vem do arquivo de totais) — ver `scripts/processar_presidente_2022.py`.
    """
    df = df_bruto[
        (df_bruto["DS_CARGO"] == CARGO_PRESIDENTE) & (df_bruto["NR_TURNO"] == str(turno))
    ].copy()

    df["uf"] = df["SG_UF"].str.lower()
    df["cd_mun_tse"] = df["CD_MUNICIPIO"].str.zfill(5)
    df["nr_candidato"] = df["NR_CANDIDATO"].astype(int)
    df["votos"] = df["QT_VOTOS_NOMINAIS"].astype(int)

    # 1 nome de urna / partido por candidato (igual em toda linha do mesmo
    # candidato); zona é o nível mais fino do arquivo, então pegamos o
    # primeiro valor de cada grupo antes de somar.
    agregado = (
        df.groupby(["uf", "cd_mun_tse", "nr_candidato"], as_index=False)
        .agg(
            votos=("votos", "sum"),
            nm_urna=("NM_URNA_CANDIDATO", "first"),
            partido=("SG_PARTIDO", "first"),
        )
        .sort_values(["uf", "cd_mun_tse", "nr_candidato"])
        .reset_index(drop=True)
    )
    return agregado


def parse_totais_2022(df_bruto: pd.DataFrame, *, turno: int) -> pd.DataFrame:
    """Agrega `detalhe_votacao_munzona_2022_BR.csv` de zona para município.

    Filtra `DS_CARGO == "Presidente"` e `NR_TURNO == turno`. Mapeamento de
    campos (nomes reais do CSV — ver docs/DADOS.md para o de-para completo
    com o schema de 2026):
    `QT_APTOS`→`eleitorado`, `QT_COMPARECIMENTO`→`comparecimento`,
    `QT_ABSTENCOES`→`abstencao`, `QT_TOTAL_VOTOS_VALIDOS`→`validos`,
    `QT_VOTOS_BRANCOS`→`brancos`, `QT_TOTAL_VOTOS_NULOS`→`nulos_tvn`,
    `QT_VOTOS_NULOS`→`nulos_vn`, `QT_TOTAL_VOTOS_ANULADOS`→`anulados`,
    `QT_TOTAL_VOTOS_ANUL_SUBJUD`→`anulados_sub_judice`.
    """
    df = df_bruto[
        (df_bruto["DS_CARGO"] == CARGO_PRESIDENTE) & (df_bruto["NR_TURNO"] == str(turno))
    ].copy()

    df["uf"] = df["SG_UF"].str.lower()
    df["cd_mun_tse"] = df["CD_MUNICIPIO"].str.zfill(5)

    campos_soma = {
        "QT_APTOS": "eleitorado",
        "QT_COMPARECIMENTO": "comparecimento",
        "QT_ABSTENCOES": "abstencao",
        "QT_TOTAL_VOTOS_VALIDOS": "validos",
        "QT_VOTOS_BRANCOS": "brancos",
        "QT_TOTAL_VOTOS_NULOS": "nulos_tvn",
        "QT_VOTOS_NULOS": "nulos_vn",
        "QT_TOTAL_VOTOS_ANULADOS": "anulados",
        "QT_TOTAL_VOTOS_ANUL_SUBJUD": "anulados_sub_judice",
    }
    for col_origem in campos_soma:
        df[col_origem] = df[col_origem].astype(int)

    nomes_municipio = df.groupby(["uf", "cd_mun_tse"])["NM_MUNICIPIO"].first()

    agregado = df.groupby(["uf", "cd_mun_tse"], as_index=False)[list(campos_soma)].sum()
    agregado = agregado.rename(columns=campos_soma)
    agregado["nm_mun_tse"] = agregado.set_index(["uf", "cd_mun_tse"]).index.map(nomes_municipio)
    colunas = ["uf", "cd_mun_tse", "nm_mun_tse", *campos_soma.values()]
    return agregado[colunas].sort_values(["uf", "cd_mun_tse"]).reset_index(drop=True)


# Os layouts de `votacao_candidato_munzona` e `detalhe_votacao_munzona` são
# idênticos em 2018 e 2022 (conferido por inspeção do cabeçalho); as funções
# não dependem do ano, então os nomes genéricos abaixo valem para ambos.
parse_candidatos = parse_candidatos_2022
parse_totais = parse_totais_2022
