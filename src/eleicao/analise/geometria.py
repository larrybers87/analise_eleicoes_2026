"""Geometria: área em CRS equivalente e vizinhança queen (sem I/O; a malha vem de carga.py).

CRS de área (ver docs/DECISOES.md D-022): `EPSG:5880` (SIRGAS 2000 / Brazil Polyconic)
NÃO é de área equivalente (é conforme/policônica), então o briefing não serve para % de
área. Usamos Albers Equal-Area com os paralelos padrão para o Brasil (-2, -22) e
origem (-12, -54), em GRS80. Verificação: a soma das áreas dos municípios tem de
ficar perto da área oficial do Brasil (~8,5 milhões de km²) — ver teste.
"""

from __future__ import annotations

import geopandas as gpd
import libpysal
import numpy as np

CRS_AREA_EQUIVALENTE = (
    "+proj=aea +lat_1=-2 +lat_2=-22 +lat_0=-12 +lon_0=-54 +x_0=0 +y_0=0 "
    "+ellps=GRS80 +units=m +no_defs"
)
AREA_OFICIAL_BR_KM2 = 8_510_345.0  # IBGE, "Áreas Territoriais 2022" (referência para checagem)


def areas_km2(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Acrescenta `area_km2` calculada no CRS equivalente (o gdf é reprojetado uma cópia)."""
    g = gdf.to_crs(CRS_AREA_EQUIVALENTE).copy()
    g["area_km2"] = g.geometry.area / 1e6
    return g


def pesos_queen(gdf: gpd.GeoDataFrame) -> libpysal.weights.W:
    """Matriz de vizinhança queen (contiguidade por aresta OU vértice), sem transformação.

    Ilhas/municípios sem vizinho ficam como isolados (pesos zero) e são listados
    pelo chamador (`ilhas`); `libpysal` avisa, não falha.
    """
    w = libpysal.weights.Queen.from_dataframe(gdf, use_index=False, silence_warnings=True)
    return w


def ilhas(w: libpysal.weights.W) -> list[int]:
    """Índices (posição no gdf) de municípios sem nenhum vizinho."""
    return [int(i) for i in w.islands]


def area_vencida_fracao(gdf_areas: gpd.GeoDataFrame, mascara: np.ndarray) -> float:
    """Fração (0..1) da área total coberta pelas linhas com `mascara == True`."""
    total = float(gdf_areas["area_km2"].sum())
    if total <= 0:
        raise ValueError("área total não positiva")
    return float(gdf_areas.loc[mascara, "area_km2"].sum()) / total
