"""Parser/agregador do perfil do eleitorado 2026 (Dados Abertos TSE).

Fonte: `data/raw/dadosabertos/.../perfil_eleitorado_2026.zip`, membro
`perfil_eleitorado_2026_BRASIL.csv` — já agregado por
**município×zona×combinação demográfica** (não é 1 linha por eleitor; é a
contagem `QT_ELEITORES` de cada combinação). Ver docs/DADOS.md → "2.
Eleitorado 2026".

Processar o arquivo inteiro (~2,2GB, ~9M linhas) de uma vez estouraria
memória confortavelmente em qualquer notebook — por isso a agregação é feita
em `chunks` (`agregar_chunk`), reduzindo cada pedaço a 4 tabelas pequenas
(total / por sexo / por faixa etária / por grau de instrução) ANTES de
acumular; só o acumulado final (uma linha por município × categoria) fica
em memória inteiro. `consolidar` faz a soma final entre os pedaços.
"""

from __future__ import annotations

import pandas as pd

COLUNAS_USADAS = [
    "SG_UF",
    "CD_MUNICIPIO",
    "NM_MUNICIPIO",
    "DS_GENERO",
    "DS_FAIXA_ETARIA",
    "DS_GRAU_ESCOLARIDADE",
    "QT_ELEITORES",
]

_COLS_MUNICIPIO = ["uf", "cd_mun_tse", "nm_mun_tse"]


def _normalizar_chaves(chunk: pd.DataFrame) -> pd.DataFrame:
    chunk = chunk.copy()
    chunk["uf"] = chunk["SG_UF"].str.lower()
    chunk["cd_mun_tse"] = chunk["CD_MUNICIPIO"].astype(str).str.zfill(5)
    chunk["nm_mun_tse"] = chunk["NM_MUNICIPIO"]
    return chunk


def agregar_chunk(chunk_bruto: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Reduz um `chunk` bruto (saída de `pandas.read_csv(..., chunksize=N)`) a 4 somas parciais."""
    chunk = _normalizar_chaves(chunk_bruto)
    chunk["QT_ELEITORES"] = chunk["QT_ELEITORES"].astype("int64")

    total = chunk.groupby(_COLS_MUNICIPIO, as_index=False, observed=True)["QT_ELEITORES"].sum()
    por_sexo = chunk.groupby([*_COLS_MUNICIPIO, "DS_GENERO"], as_index=False, observed=True)[
        "QT_ELEITORES"
    ].sum()
    por_faixa = chunk.groupby([*_COLS_MUNICIPIO, "DS_FAIXA_ETARIA"], as_index=False, observed=True)[
        "QT_ELEITORES"
    ].sum()
    por_grau = chunk.groupby(
        [*_COLS_MUNICIPIO, "DS_GRAU_ESCOLARIDADE"], as_index=False, observed=True
    )["QT_ELEITORES"].sum()
    return {"total": total, "sexo": por_sexo, "faixa": por_faixa, "grau": por_grau}


_DIMENSOES = {
    "total": [],
    "sexo": ["DS_GENERO"],
    "faixa": ["DS_FAIXA_ETARIA"],
    "grau": ["DS_GRAU_ESCOLARIDADE"],
}


def consolidar(parciais: dict[str, list[pd.DataFrame]]) -> dict[str, pd.DataFrame]:
    """Soma final entre os pedaços acumulados por `agregar_chunk` (1 concat + groupby cada)."""
    saida = {}
    for nome, lista_dfs in parciais.items():
        colunas_grupo = [*_COLS_MUNICIPIO, *_DIMENSOES[nome]]
        empilhado = pd.concat(lista_dfs, ignore_index=True)
        saida[nome] = (
            empilhado.groupby(colunas_grupo, as_index=False, observed=True)["QT_ELEITORES"]
            .sum()
            .sort_values(colunas_grupo)
            .reset_index(drop=True)
        )
    return saida


def _slug(texto: str) -> str:
    """`"80 a 84 anos"` -> `"80_84"`; `"Ensino médio completo"` -> `"ensino_medio_completo"`."""
    import re
    import unicodedata

    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    minusculo = sem_acento.lower()
    minusculo = minusculo.replace(" a ", "_").replace(" ou mais", "_mais").replace(" anos", "")
    minusculo = re.sub(r"[^a-z0-9]+", "_", minusculo).strip("_")
    return minusculo


def pivotar_wide(consolidado: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Monta o Parquet final: 1 linha por município, colunas `pct_<categoria>` por dimensão.

    `total` vira a coluna `total`; `sexo`/`faixa`/`grau` viram `pct_sexo_<slug>`,
    `pct_faixa_<slug>`, `pct_grau_<slug>` (percentual sobre o `total` do
    município, 0–100). O TSE usa bins de 1 ano para 16/17/18/19/20, depois
    de 5 em 5 anos até "95 a 99 anos", mais "100 anos ou mais" e uma
    categoria "Inválida" (idade não aferível) — ver docs/DADOS.md para a
    lista completa. `pct_faixa_<slug>` é uma PARTIÇÃO (soma 100% sozinha).

    Como as faixas **16-17 anos** e **70 anos ou mais** (voto facultativo)
    não existem como um único bin do TSE, este parser soma os bins
    correspondentes em duas colunas extras, fora do prefixo `pct_faixa_`
    (para não contar a mesma pessoa duas vezes em quem somar
    `pct_faixa_*` "às cegas" esperando 100%):
    `pct_faixa_facultativa_16_17` (= `pct_faixa_16 + pct_faixa_17`) e
    `pct_faixa_facultativa_70_mais` (soma de `70_74` até `100_mais`).
    """
    base = consolidado["total"].rename(columns={"QT_ELEITORES": "total"})

    def _pivot(nome: str, coluna_categoria: str, prefixo: str) -> pd.DataFrame:
        df = consolidado[nome].copy()
        df["categoria"] = df[coluna_categoria].map(_slug)
        largo = df.pivot_table(
            index=_COLS_MUNICIPIO,
            columns="categoria",
            values="QT_ELEITORES",
            fill_value=0,
            observed=True,
        )
        largo.columns = [f"pct_{prefixo}_{c}" for c in largo.columns]
        return largo.reset_index()

    largo_sexo = _pivot("sexo", "DS_GENERO", "sexo")
    largo_faixa = _pivot("faixa", "DS_FAIXA_ETARIA", "faixa")
    largo_grau = _pivot("grau", "DS_GRAU_ESCOLARIDADE", "grau")

    saida = base.merge(largo_sexo, on=_COLS_MUNICIPIO, how="left")
    saida = saida.merge(largo_faixa, on=_COLS_MUNICIPIO, how="left")
    saida = saida.merge(largo_grau, on=_COLS_MUNICIPIO, how="left")
    saida = saida.fillna(0)

    # Colunas derivadas (somas de contagem, ANTES de converter para %, para
    # não acumular erro de arredondamento): 16-17 anos e 70+ (voto
    # facultativo) não são bins nativos do TSE — ver docstring acima.
    colunas_70_mais = [
        c
        for c in saida.columns
        if c.startswith("pct_faixa_")
        and (c.removeprefix("pct_faixa_").split("_")[0].isdigit())
        and int(c.removeprefix("pct_faixa_").split("_")[0]) >= 70
    ]
    saida["pct_faixa_facultativa_16_17"] = saida["pct_faixa_16"] + saida["pct_faixa_17"]
    saida["pct_faixa_facultativa_70_mais"] = saida[colunas_70_mais].sum(axis=1)

    colunas_pct = [c for c in saida.columns if c.startswith("pct_")]
    for col in colunas_pct:
        saida[col] = (100.0 * saida[col] / saida["total"]).round(4)

    return saida.sort_values(_COLS_MUNICIPIO).reset_index(drop=True)
