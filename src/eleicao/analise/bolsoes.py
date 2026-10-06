"""Redutos e bolsões: onde um candidato supera 3× a própria média nacional.

Definições (docs/DECISOES.md D-025):
- Média nacional = % sobre VÁLIDOS nacionais (votos do candidato no Brasil ÷ válidos
  do Brasil), NÃO a média simples dos municípios.
- Município qualificado = % sobre válidos do município > 3 × média nacional.
- Bolsão = componente conexa (vizinhança queen) de municípios qualificados.
  Um município isolado qualificado também é um bolsão (de tamanho 1).
- Tamanho do bolsão = nº de municípios. Bolsão pequeno e isolado tende a ser ruído de
  município pequeno: o ranking de "maiores" é por nº de municípios, e a % do
  eleitorado do bolsão é reportada junto.

Ressalva: bolsão é uma propriedade de municípios (ecológica), não de eleitores.
"""

from __future__ import annotations

from collections import deque

import numpy as np
import pandas as pd

from .base import pct


def media_nacional_pct(votos_br: float, validos_br: float) -> float:
    """% nacional sobre válidos (votos do candidato ÷ válidos do Brasil, sem exterior)."""
    return pct(votos_br, validos_br)


def componentes_conexas(mascara: np.ndarray, vizinhos: dict[int, list[int]]) -> list[list[int]]:
    """Componentes conexas (BFS) dos índices com `mascara` True, usando a lista de vizinhos.

    Índices de `vizinhos` são posições (0..n-1). Vizinhos fora da máscara são ignorados.
    Devolve listas de índices, ordenadas por tamanho decrescente.
    """
    marcados = set(np.flatnonzero(mascara).tolist())
    visitados: set[int] = set()
    componentes: list[list[int]] = []
    for ini in sorted(marcados):
        if ini in visitados:
            continue
        comp = []
        fila = deque([ini])
        visitados.add(ini)
        while fila:
            atual = fila.popleft()
            comp.append(atual)
            for viz in vizinhos.get(atual, []):
                if viz in marcados and viz not in visitados:
                    visitados.add(viz)
                    fila.append(viz)
        componentes.append(sorted(comp))
    componentes.sort(key=len, reverse=True)
    return componentes


def bolsoes(
    municipios: pd.DataFrame,
    pct_col: str,
    media_nac_pct: float,
    vizinhos: dict[int, list[int]],
    limiar_x: float = 3.0,
) -> pd.DataFrame:
    """Lista de bolsões (um por linha) para um candidato.

    `municipios` deve estar na MESMA ordem das posições de `vizinhos` e ter `pct_col`,
    `uf`, `cd_mun_tse`, `nome` e `eleitorado`. Devolve: id_bolsao, n_municipios,
    eleitorado, membros (lista de (uf, cd)), e o município com maior %.
    """
    mascara = municipios[pct_col].to_numpy(dtype=float) > limiar_x * media_nac_pct
    comps = componentes_conexas(mascara, vizinhos)
    linhas = []
    for i, comp in enumerate(comps, start=1):
        sub = municipios.iloc[comp]
        topo = sub.loc[sub[pct_col].idxmax()]
        linhas.append(
            {
                "id_bolsao": i,
                "n_municipios": len(comp),
                "eleitorado": int(sub["eleitorado"].sum()),
                "municipio_maior_pct": topo["nome"],
                "uf_maior_pct": topo["uf"],
                "pct_maximo": float(topo[pct_col]),
                "membros": list(zip(sub["uf"], sub["cd_mun_tse"], strict=True)),
            }
        )
    colunas = [
        "id_bolsao", "n_municipios", "eleitorado", "municipio_maior_pct",
        "uf_maior_pct", "pct_maximo", "membros",
    ]  # fmt: skip
    return pd.DataFrame(linhas, columns=colunas)


def resumo_reduto(
    municipios: pd.DataFrame, pct_col: str, uf: str, media_nac_pct: float
) -> dict[str, float]:
    """Desempenho num reduto (UF): % do candidato na UF (sobre válidos da UF) vs média nacional.

    Razão = % na UF ÷ % nacional. Os votos e válidos da UF são somados (agregado ponderado).
    """
    sub = municipios[municipios["uf"] == uf]
    if sub.empty:
        raise ValueError(f"UF sem municípios: {uf}")
    votos = float(sub["votos"].sum())
    validos = float(sub["validos"].sum())
    pct_uf = pct(votos, validos)
    return {
        "uf": uf,
        "pct_uf_sobre_validos": pct_uf,
        "pct_nacional_sobre_validos": media_nac_pct,
        "razao_vs_nacional": pct_uf / media_nac_pct,
        "n_municipios_uf": int(len(sub)),
        "n_municipios_acima_3x": int((sub[pct_col] > 3 * media_nac_pct).sum()),
    }
