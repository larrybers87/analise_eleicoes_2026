"""I/O das análises: leitura dos Parquet de data/processed/ e da malha do IBGE.

Única camada com leitura de disco/rede do pacote `analise`. As funções de
cálculo recebem os DataFrames devolvidos aqui e nunca leem nada por conta própria.
"""

from __future__ import annotations

import pandas as pd

from eleicao import config

PROC = config.DATA_PROCESSED


def _ler(nome: str) -> pd.DataFrame:
    return pd.read_parquet(PROC / nome)


def totais_2026() -> pd.DataFrame:
    """1º turno 2026, 1 linha por município (5.571 BR + 186 exterior `zz`)."""
    df = _ler("presidente_t1_municipio_totais.parquet")
    df["cd_mun_tse"] = df["cd_mun_tse"].astype(str)
    return df


def candidatos_2026() -> pd.DataFrame:
    """1º turno 2026, município × candidato (votos nominais)."""
    df = _ler("presidente_t1_municipio.parquet")
    df["cd_mun_tse"] = df["cd_mun_tse"].astype(str)
    return df


def totais_2022(turno: int) -> pd.DataFrame:
    """Totais 2022 por município (turno 1 ou 2); 5.751 linhas incl. exterior."""
    if turno not in (1, 2):
        raise ValueError("turno deve ser 1 ou 2")
    df = _ler(f"presidente_2022_t{turno}_municipio_totais.parquet")
    df["cd_mun_tse"] = df["cd_mun_tse"].astype(str)
    return df


def candidatos_2022(turno: int) -> pd.DataFrame:
    if turno not in (1, 2):
        raise ValueError("turno deve ser 1 ou 2")
    df = _ler(f"presidente_2022_t{turno}_municipio.parquet")
    df["cd_mun_tse"] = df["cd_mun_tse"].astype(str)
    return df


def perfil_eleitorado_2026() -> pd.DataFrame:
    df = _ler("eleitorado_perfil_2026_municipio.parquet")
    df["cd_mun_tse"] = df["cd_mun_tse"].astype(str)
    return df


def ibge() -> pd.DataFrame:
    """Censo 2022 (população) e PIB 2023 (per capita): 5.570 municípios (sem exterior/Noronha)."""
    df = _ler("ibge_municipio.parquet")
    df["cd_mun_ibge"] = df["cd_mun_ibge"].astype(str)
    return df


def capitais() -> pd.DataFrame:
    """27 capitais (1 por UF), gerado por scripts/persistir_capitais.py."""
    df = pd.read_csv(PROC / "capitais.csv", dtype=str, encoding="utf-8")
    return df


def geometria_municipios_2024(crs: str = "EPSG:4674") -> pd.DataFrame:
    """Malha municipal COMPLETA do IBGE (geobr, year=2024, simplified=False).

    Usada para área e vizinhança. Nunca a versão simplificada (ver docs/DADOS.md §5).
    Não há malha em data/processed/: esta leitura é a única fonte externa às
    análises, e vem do pacote `geobr` (documentado em CLAUDE.md/DADOS.md).
    Devolve GeoDataFrame com `cd_mun_ibge` (7 dígitos, str) e `geometry`
    no CRS pedido.
    """
    import geobr  # import tardio: só quando a geometria é necessária

    gdf = geobr.read_municipality(year=2024, simplified=False)
    gdf = gdf.rename(columns={"code_muni": "cd_mun_ibge"})
    gdf["cd_mun_ibge"] = gdf["cd_mun_ibge"].astype("int64").astype(str)
    gdf["geometry"] = gdf.geometry.make_valid()
    return gdf[["cd_mun_ibge", "name_muni", "abbrev_state", "geometry"]].to_crs(crs)
