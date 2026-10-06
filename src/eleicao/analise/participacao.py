"""Participação: ranking de abstenção/comparecimento com corte de eleitorado e correlação ecológica.

Sinalização obrigatória (CLAUDE.md, rigor): correlação entre variáveis de município é
ECOLÓGICA. Não autoriza conclusão sobre eleitor individual.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import stats

COL_ABSTENCAO = "pct_abstencao_sobre_eleitorado"
COL_COMPARECIMENTO = "pct_comparecimento_sobre_eleitorado"


def adicionar_abstencao(df: pd.DataFrame) -> pd.DataFrame:
    """Acrescenta `COL_ABSTENCAO` = abstenção ÷ eleitorado (×100). Denominador: eleitorado."""
    out = df.copy()
    out[COL_ABSTENCAO] = 100 * out["abstencao"] / out["eleitorado"]
    return out


def ranking_participacao(
    municipios: pd.DataFrame, corte_eleitorado: int, n: int = 20
) -> dict[str, pd.DataFrame]:
    """Top/bottom `n` por abstenção (sobre eleitorado), só com `eleitorado >= corte_eleitorado`.

    `municipios` deve ser a base municipal SEM exterior (`apenas_brasil`) passada por
    `adicionar_abstencao` (ou com `COL_ABSTENCAO` já calculada).
    Devolve {"maior_abstencao": ..., "menor_abstencao": ...} com `n` linhas cada.
    """
    if corte_eleitorado < 0:
        raise ValueError("corte_eleitorado não pode ser negativo")
    elegiveis = municipios.loc[municipios["eleitorado"] >= corte_eleitorado]
    ordenado = elegiveis.sort_values([COL_ABSTENCAO, "cd_mun_tse"], ascending=[False, True])
    colunas = ["uf", "cd_mun_tse", "nm_mun", "eleitorado", COL_ABSTENCAO]
    return {
        "maior_abstencao": ordenado.head(n)[colunas].reset_index(drop=True),
        "menor_abstencao": ordenado.tail(n).iloc[::-1][colunas].reset_index(drop=True),
    }


@dataclass(frozen=True)
class EstabilidadeCorte:
    corte: int
    n_municipios: int
    top_n: frozenset
    bottom_n: frozenset
    fracao_menores_50k_no_top: float


def estabilidade_cortes(
    municipios: pd.DataFrame, cortes: list[int], n: int = 20
) -> list[EstabilidadeCorte]:
    """Para cada corte, o conjunto de municípios do top/bottom `n` e quanto ele muda.

    Serve para justificar o corte: se o top `n` muda muito entre cortes vizinhos,
    o ranking está dominado por ruído de município pequeno.
    Identidade de município = (uf, cd_mun_tse).
    """
    saidas = []
    for corte in cortes:
        r = ranking_participacao(municipios, corte, n)
        topo = frozenset(
            zip(r["maior_abstencao"]["uf"], r["maior_abstencao"]["cd_mun_tse"], strict=True)
        )
        fundo = frozenset(
            zip(r["menor_abstencao"]["uf"], r["menor_abstencao"]["cd_mun_tse"], strict=True)
        )
        elegiveis = municipios.loc[municipios["eleitorado"] >= corte]
        pequenos = r["maior_abstencao"]["eleitorado"] < 50_000
        saidas.append(
            EstabilidadeCorte(
                corte=corte,
                n_municipios=len(elegiveis),
                top_n=topo,
                bottom_n=fundo,
                fracao_menores_50k_no_top=float(pequenos.mean()),
            )
        )
    return saidas


def jaccard(a: frozenset, b: frozenset) -> float:
    """Índice de Jaccard (0..1) entre dois conjuntos; 1 = idênticos. Vazio vs vazio = 1."""
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b)


def correlacao_ecologica(
    municipios: pd.DataFrame, x: str, y: str, metodo: str = "spearman"
) -> dict[str, float]:
    """Correlação entre duas colunas de município, sem NaN nas duas.

    ATENÇÃO: correlação ecológica (nível município). Não se aplica a eleitor individual.
    `metodo`: 'pearson' ou 'spearman' (Spearman é o padrão: robusto a distribuição assimétrica).
    """
    d = municipios[[x, y]].dropna()
    if metodo == "pearson":
        r, p = _pearson(d[x], d[y])
    elif metodo == "spearman":
        r, p = stats.spearmanr(d[x], d[y])
    else:
        raise ValueError("metodo deve ser 'pearson' ou 'spearman'")
    return {"r": float(r), "p_valor": float(p), "n": int(len(d)), "metodo": metodo}


def _pearson(a: pd.Series, b: pd.Series) -> tuple[float, float]:
    r, p = stats.pearsonr(np.asarray(a, dtype=float), np.asarray(b, dtype=float))
    return float(r), float(p)
