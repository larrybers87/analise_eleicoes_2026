"""Mapeamento fixo UF -> região do Brasil (IBGE) e recortes de porte/capital.

Versionado de propósito (CLAUDE.md, F3): não usa lookup externo que possa mudar.
Ver docs/DADOS.md (seção "Recortes de análise") e docs/DECISOES.md (D-027).

Atenção: a sigla `SE` aqui é SUDESTE (região), não Sergipe (que é NE).
O exterior (UF `zz`) não pertence a nenhuma região do Brasil: é um recorte à parte.
"""

from __future__ import annotations

import pandas as pd

UF_EXTERIOR = "zz"
REGIAO_EXTERIOR = "Exterior"

UF_REGIAO: dict[str, str] = {
    "ac": "N", "ap": "N", "am": "N", "pa": "N", "ro": "N", "rr": "N", "to": "N",
    "al": "NE", "ba": "NE", "ce": "NE", "ma": "NE", "pb": "NE", "pe": "NE",
    "pi": "NE", "rn": "NE", "se": "NE",
    "df": "CO", "go": "CO", "mt": "CO", "ms": "CO",
    "es": "SE", "mg": "SE", "rj": "SE", "sp": "SE",
    "pr": "S", "rs": "S", "sc": "S",
}  # fmt: skip

REGIOES_BR: tuple[str, ...] = ("N", "NE", "CO", "SE", "S")

NOME_REGIAO: dict[str, str] = {
    "N": "Norte",
    "NE": "Nordeste",
    "CO": "Centro-Oeste",
    "SE": "Sudeste",
    "S": "Sul",
    "Exterior": "Exterior (recorte à parte)",
}

# Faixas de eleitorado do município (eleitorado de 2026, 1º turno).
# Limite inferior inclusivo, superior exclusivo. Ver docs/DECISOES.md (D-027).
FAIXAS_ELEITORADO: tuple[tuple[str, float, float], ...] = (
    ("<10k", 0, 10_000),
    ("10k–50k", 10_000, 50_000),
    ("50k–200k", 50_000, 200_000),
    ("200k–1M", 200_000, 1_000_000),
    (">1M", 1_000_000, float("inf")),
)
ORDEM_FAIXAS: tuple[str, ...] = tuple(f[0] for f in FAIXAS_ELEITORADO)


def regiao_da_uf(uf: str) -> str:
    """Região ('N','NE','CO','SE','S') da UF; 'Exterior' para `zz`. KeyError se UF desconhecida."""
    uf = uf.lower()
    if uf == UF_EXTERIOR:
        return REGIAO_EXTERIOR
    return UF_REGIAO[uf]


def faixa_eleitorado(eleitorado: pd.Series) -> pd.Series:
    """Rotula cada município pela faixa do eleitorado (ver FAIXAS_ELEITORADO).

    Devolve categoria ordenada (ORDEM_FAIXAS). Valores fora de qualquer faixa
    (ex.: NaN) ficam nulos.
    """
    rotulos = pd.Series(None, index=eleitorado.index, dtype="object")
    for rotulo, lo, hi in FAIXAS_ELEITORADO:
        mascara = (eleitorado >= lo) & (eleitorado < hi)
        rotulos = rotulos.mask(mascara, rotulo)
    return pd.Series(
        pd.Categorical(rotulos, categories=list(ORDEM_FAIXAS), ordered=True),
        index=eleitorado.index,
    )
