"""Perfil do eleitorado x voto: regressão ecológica ponderada (WLS) e diagnóstico de colinearidade.

ECOLÓGICO: unidade = município. Os coeficientes descrevem associação entre médias
municipais, NÃO comportamento de eleitor individual (falácia ecológica).

Variáveis (todas em % do eleitorado do município, denominador = `total` do perfil de 2026,
exceto onde indicado):
- Idade (grupos DISJUNTOS que somam 100% com `pct_faixa_invalida` e a referência):
  - `pct_16_17`  = `pct_faixa_facultativa_16_17` (derivada, facultativo)
  - `pct_18_59`  = referência (omitida na regressão): soma de 18–20 + 21_24…55_59
  - `pct_60_69`  = soma de 60_64 + 65_69 (nativas)
  - `pct_70_mais` = `pct_faixa_facultativa_70_mais` (derivada)
  - `pct_invalida` fica de fora (residual).
- Sexo: `pct_sexo_feminino` (referência = masculino; `nao_informado` fica de fora).
- Escolaridade: `pct_grau_superior_completo` e `pct_grau_analfabeto`.
- Renda: log10 do PIB per capita 2023 (IBGE). Ano defasado em relação ao eleitorado de 2026.
- Porte: log10 da população do Censo 2022. Defasada em relação ao eleitorado de 2026.

Peso WLS = eleitorado de 2026 do município (municípios grandes pesam mais).
Desfecho: % de válidos do candidato no 1º turno 2026 (denominador = válidos do município).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import statsmodels.api as sm
from statsmodels.stats.outliers_influence import variance_inflation_factor

IDADE_18_59_NATIVAS = [
    "pct_faixa_18", "pct_faixa_19", "pct_faixa_20", "pct_faixa_21_24", "pct_faixa_25_29",
    "pct_faixa_30_34", "pct_faixa_35_39", "pct_faixa_40_44", "pct_faixa_45_49",
    "pct_faixa_50_54", "pct_faixa_55_59",
]  # fmt: skip
IDADE_60_69_NATIVAS = ["pct_faixa_60_64", "pct_faixa_65_69"]

VARIAVEIS_MODELO_BASICO = [
    "pct_16_17", "pct_60_69", "pct_70_mais",
    "pct_sexo_feminino", "pct_grau_superior_completo", "pct_grau_analfabeto",
]  # fmt: skip
VARIAVEIS_MODELO_COMPLETO = [*VARIAVEIS_MODELO_BASICO, "log_pib_pc_2023", "log_populacao_2022"]


def preparar_variaveis(df: pd.DataFrame) -> pd.DataFrame:
    """Monta as variáveis de perfil a partir do Parquet de perfil + IBGE já unidos.

    Espera: colunas `pct_faixa_*` (nativas e derivadas), `pct_sexo_feminino`,
    `pct_grau_superior_completo`, `pct_grau_analfabeto`, `pib_per_capita_reais`,
    `populacao_censo_2022`. Não altera o DataFrame de entrada.
    """
    out = pd.DataFrame(index=df.index)
    out["pct_16_17"] = df["pct_faixa_facultativa_16_17"]
    out["pct_70_mais"] = df["pct_faixa_facultativa_70_mais"]
    out["pct_60_69"] = df[IDADE_60_69_NATIVAS].sum(axis=1)
    out["pct_18_59"] = df[IDADE_18_59_NATIVAS].sum(axis=1)
    out["pct_sexo_feminino"] = df["pct_sexo_feminino"]
    out["pct_grau_superior_completo"] = df["pct_grau_superior_completo"]
    out["pct_grau_analfabeto"] = df["pct_grau_analfabeto"]
    out["log_pib_pc_2023"] = np.log10(df["pib_per_capita_reais"])
    out["log_populacao_2022"] = np.log10(df["populacao_censo_2022"])
    return out


def checar_soma_idade(df: pd.DataFrame, tol_pp: float = 0.001) -> None:
    """Confere que 16_17 + 18_59 + 60_69 + 70_mais + invalida = 100 (partição sem dupla contagem).

    Tolerância 0,001 p.p.: o Parquet guarda os % com 4 casas decimais (desvio observado
    máximo 0,0004 p.p. em 5.757 municípios). Somar as derivadas AOS nativos daria ~36 p.p.
    de excesso, por isso o teste existe.
    """
    soma = (
        df["pct_faixa_facultativa_16_17"]
        + df[IDADE_18_59_NATIVAS].sum(axis=1)
        + df[IDADE_60_69_NATIVAS].sum(axis=1)
        + df["pct_faixa_facultativa_70_mais"]
        + df["pct_faixa_invalida"]
    )
    desvio = (soma - 100).abs().max()
    if desvio > tol_pp:
        raise ValueError(f"partição de idade não fecha em 100% (desvio máx {desvio:.6f} p.p.)")


def ajustar_wls(
    dados: pd.DataFrame, y: str, x: list[str], peso: str = "eleitorado"
) -> tuple[pd.DataFrame, float, int]:
    """WLS com constante. Devolve (tabela de coeficientes, R², n).

    Tabela: termo, coef, erro_padrao, ic95_inf, ic95_sup, p_valor. Coeficientes na escala
    das variáveis (p.p. por p.p. de % ou por unidade de log10).
    """
    d = dados[[y, *x, peso]].dropna()
    X = sm.add_constant(d[x], has_constant="add")
    modelo = sm.WLS(d[y], X, weights=d[peso]).fit()
    ic = modelo.conf_int(alpha=0.05)
    tabela = pd.DataFrame(
        {
            "termo": modelo.params.index,
            "coef": modelo.params.to_numpy(),
            "erro_padrao": modelo.bse.to_numpy(),
            "ic95_inf": ic[0].to_numpy(),
            "ic95_sup": ic[1].to_numpy(),
            "p_valor": modelo.pvalues.to_numpy(),
        }
    )
    return tabela, float(modelo.rsquared), int(modelo.nobs)


def vif(dados: pd.DataFrame, x: list[str]) -> pd.DataFrame:
    """Variance Inflation Factor de cada preditor (com constante no cálculo, convenção padrão).

    VIF > 5 sinaliza colinearidade relevante; > 10, forte. Ver docs/ANALISES.md.
    """
    d = dados[x].dropna()
    X = sm.add_constant(d, has_constant="add").to_numpy(dtype=float)
    saida = [
        {"variavel": v, "vif": float(variance_inflation_factor(X, i + 1))} for i, v in enumerate(x)
    ]
    return pd.DataFrame(saida)
