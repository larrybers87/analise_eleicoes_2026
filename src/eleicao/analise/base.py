"""Base municipal e agregações ponderadas (funções puras, sem I/O).

Convenções (ver docs/DECISOES.md D-027):
- Agregado regional/UF = soma de votos ÷ soma de válidos (ponderado). Nunca média
  simples de percentuais municipais, a não ser onde a função diz explicitamente
  `media_simples` no nome.
- Exterior (`zz`) fica em `regiao == "Exterior"` e é removido de todos os agregados
  "Brasil" por `apenas_brasil`.
- Todo percentual tem o denominador no nome da coluna: `*_sobre_validos`,
  `*_sobre_comparecimento`, `*_sobre_eleitorado`.
"""

from __future__ import annotations

import pandas as pd

from .regioes import UF_EXTERIOR, faixa_eleitorado, regiao_da_uf


def base_municipal(totais: pd.DataFrame, capitais: pd.DataFrame) -> pd.DataFrame:
    """Acrescenta à tabela de totais: `regiao`, `eh_capital`, `faixa` (eleitorado).

    `faixa` fica nula no exterior: o recorte de porte é só para municípios brasileiros.
    `totais` precisa ter `uf` (minúsculo), `cd_mun_tse` (str 5 dígitos) e `eleitorado`.
    """
    df = totais.copy()
    df["uf"] = df["uf"].str.lower()
    df["regiao"] = df["uf"].map(regiao_da_uf)
    chaves_capitais = set(zip(capitais["uf"], capitais["cd_mun_tse"], strict=True))
    df["eh_capital"] = [
        (u, c) in chaves_capitais for u, c in zip(df["uf"], df["cd_mun_tse"], strict=True)
    ]
    faixa = faixa_eleitorado(df["eleitorado"])
    df["faixa"] = faixa.where(df["uf"] != UF_EXTERIOR)
    return df


def apenas_brasil(df: pd.DataFrame) -> pd.DataFrame:
    """Remove o exterior (`uf == 'zz'`). Use em todo agregado que se diz "Brasil"."""
    return df.loc[df["uf"] != UF_EXTERIOR].copy()


def pct(numerador: float, denominador: float) -> float:
    """Percentual em 0–100. Denominador zero levanta erro (nunca vira NaN silencioso)."""
    if denominador == 0:
        raise ZeroDivisionError("denominador zero em pct()")
    return 100.0 * numerador / denominador


def somar_por(df: pd.DataFrame, por: list[str], colunas: list[str]) -> pd.DataFrame:
    """Soma `colunas` por `por` (agregado ponderado: soma de contagens absolutas)."""
    return df.groupby(por, observed=True, as_index=False)[colunas].sum()


def participacao_agregada(df: pd.DataFrame, por: list[str]) -> pd.DataFrame:
    """Abstenção, brancos e nulos agregados, com denominador explícito.

    - `pct_abstencao_sobre_eleitorado` = abstenção ÷ eleitorado
    - `pct_comparecimento_sobre_eleitorado` = comparecimento ÷ eleitorado
    - `pct_brancos_sobre_comparecimento` = brancos ÷ comparecimento
    - `pct_nulos_tvn_sobre_comparecimento` = nulos_tvn ÷ comparecimento (nulos comuns + técnicos)
    - `pct_nulos_vn_sobre_comparecimento` = nulos_vn ÷ comparecimento (só nulos comuns)
    """
    g = somar_por(
        df,
        por,
        [
            "eleitorado",
            "comparecimento",
            "abstencao",
            "brancos",
            "nulos_tvn",
            "nulos_vn",
            "validos",
        ],
    )
    g["pct_abstencao_sobre_eleitorado"] = 100 * g["abstencao"] / g["eleitorado"]
    g["pct_comparecimento_sobre_eleitorado"] = 100 * g["comparecimento"] / g["eleitorado"]
    g["pct_brancos_sobre_comparecimento"] = 100 * g["brancos"] / g["comparecimento"]
    g["pct_nulos_tvn_sobre_comparecimento"] = 100 * g["nulos_tvn"] / g["comparecimento"]
    g["pct_nulos_vn_sobre_comparecimento"] = 100 * g["nulos_vn"] / g["comparecimento"]
    return g


def votos_por_grupo(candidatos: pd.DataFrame, base: pd.DataFrame, por: list[str]) -> pd.DataFrame:
    """Votos de cada candidato por grupo e % sobre os VÁLIDOS do grupo (ponderado).

    `candidatos`: uf, cd_mun_tse, nr_candidato, votos (1 linha por município×candidato).
    `base`: uf, cd_mun_tse, validos + as colunas de `por`.
    Retorna: grupo(s) + nr_candidato, votos, validos_grupo, pct_sobre_validos_grupo.
    Grade cheia (grupo × candidato) com zero explícito quando não há linha.
    """
    extras = [p for p in por if p not in ("uf", "cd_mun_tse")]
    m = candidatos.merge(
        base[["uf", "cd_mun_tse", *extras]], on=["uf", "cd_mun_tse"], how="left", validate="m:1"
    )
    if m[por].isna().any().any():
        raise ValueError("candidato sem município correspondente na base")
    g = m.groupby([*por, "nr_candidato"], observed=True, as_index=False)["votos"].sum()
    grade = base.groupby(por, observed=True, as_index=False)["validos"].sum()
    grade = grade.rename(columns={"validos": "validos_grupo"})
    nrs = pd.DataFrame({"nr_candidato": sorted(candidatos["nr_candidato"].unique())})
    cheia = grade.merge(nrs, how="cross")
    cheia = cheia.merge(g, on=[*por, "nr_candidato"], how="left", validate="1:1")
    cheia["votos"] = cheia["votos"].fillna(0).astype("int64")
    cheia["pct_sobre_validos_grupo"] = 100 * cheia["votos"] / cheia["validos_grupo"]
    return cheia


def vencedor_municipal(candidatos: pd.DataFrame) -> pd.DataFrame:
    """Por município: nr do 1º colocado, votos dele, votos do 2º e margem (p.p. de válidos).

    Empate exato: o 1º é `None` e a margem é 0 (não há vencedor). Ver teste.
    """
    ordenado = candidatos.sort_values(
        ["uf", "cd_mun_tse", "votos", "nr_candidato"], ascending=[True, True, False, True]
    )
    topo = ordenado.groupby(["uf", "cd_mun_tse"], sort=False).head(2)
    rank = topo.groupby(["uf", "cd_mun_tse"], sort=False).cumcount()
    primeiro = topo[rank == 0].set_index(["uf", "cd_mun_tse"])
    segundo = topo[rank == 1].set_index(["uf", "cd_mun_tse"])
    out = pd.DataFrame(
        {
            "nr_vencedor": primeiro["nr_candidato"],
            "votos_1o": primeiro["votos"],
            "votos_2o": segundo["votos"].reindex(primeiro.index).fillna(0).astype("int64"),
        }
    ).reset_index()
    total = candidatos.groupby(["uf", "cd_mun_tse"], as_index=False)["votos"].sum()
    total = total.rename(columns={"votos": "validos"})
    out = out.merge(total, on=["uf", "cd_mun_tse"], validate="1:1")
    out["margem_pp"] = 100 * (out["votos_1o"] - out["votos_2o"]) / out["validos"]
    empate = out["votos_1o"] == out["votos_2o"]
    out["nr_vencedor"] = out["nr_vencedor"].astype("object").mask(empate, None)
    return out


def enriquecer(base: pd.DataFrame, perfil: pd.DataFrame, ibge: pd.DataFrame) -> pd.DataFrame:
    """Une perfil do eleitorado (2026, por uf+cd_mun_tse) e IBGE (por cd_mun_ibge).

    Munícipios sem IBGE (exterior e Fernando de Noronha) ficam com NaN nas colunas
    do IBGE; quem usa essas colunas deve filtrar explicitamente (ver `perfil.py`).
    Erro se o perfil não cobrir todas as chaves de `base` (join validado 1:1).
    """
    p = perfil.drop(columns=["nm_mun_tse", "total"], errors="ignore")
    out = base.merge(p, on=["uf", "cd_mun_tse"], how="left", validate="1:1")
    if out[[c for c in p.columns if c not in ("uf", "cd_mun_tse")]].isna().all(axis=1).any():
        raise ValueError("município sem perfil do eleitorado")
    i = ibge[["cd_mun_ibge", "populacao_censo_2022", "pib_mil_reais", "pib_per_capita_reais"]]
    out = out.merge(i, on="cd_mun_ibge", how="left", validate="m:1")
    return out
