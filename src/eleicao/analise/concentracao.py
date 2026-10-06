"""Concentração dos votos entre municípios: Lorenz, Gini e nº de municípios para 50%.

Definições (docs/DECISOES.md D-026):
- Unidade: município brasileiro (5.571; exterior fica fora).
- `gini_votos_absolutos`: Gini dos votos ABSOLUTOS do candidato entre os municípios.
  Mede quão concentrado está o voto dele em poucos municípios GRANDES. Por ser
  absoluto, ele reflete tanto a força do candidato quanto o tamanho dos municípios.
- `gini_pct_validos`: Gini do % sobre válidos do município (cada município pesa 1).
  Mede a dispersão do apoio entre municípios, sem o peso do tamanho.
- Os dois Ginis usam fórmula de Lorenz em todos os municípios (zeros entram).

Ressalva: concentração entre municípios é um fato sobre a DISTRIBUIÇÃO geográfica
agregada. Não diz nada sobre quem votou em quem dentro do município.
"""

from __future__ import annotations

import numpy as np


def _limpar(valores: np.ndarray) -> np.ndarray:
    v = np.asarray(valores, dtype=float)
    if v.size == 0:
        raise ValueError("lista vazia")
    if np.any(v < 0):
        raise ValueError("valores negativos")
    if np.isnan(v).any():
        raise ValueError("valores ausentes (NaN): trate antes de chamar")
    return v


def lorenz(valores: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Curva de Lorenz: (fração acumulada de municípios, fração acumulada de votos).

    Ordena do menor para o maior. Começa em (0,0) e termina em (1,1).
    """
    v = np.sort(_limpar(valores))
    total = v.sum()
    if total <= 0:
        raise ValueError("soma dos valores deve ser positiva")
    n = v.size
    x = np.concatenate([[0.0], np.arange(1, n + 1) / n])
    y = np.concatenate([[0.0], np.cumsum(v) / total])
    return x, y


def gini(valores: np.ndarray) -> float:
    """Coeficiente de Gini em [0, 1-1/n]: 0 = distribuição igual, perto de 1 = concentrado."""
    v = np.sort(_limpar(valores))
    n = v.size
    total = v.sum()
    if total <= 0:
        raise ValueError("soma dos valores deve ser positiva")
    indices = np.arange(1, n + 1)
    return float((2 * np.sum(indices * v) / (n * total)) - (n + 1) / n)


def n_municipios_para_fracao(valores: np.ndarray, alvo: float = 0.5) -> int:
    """Menor número de municípios (do maior para o menor) cuja soma alcança `alvo` do total."""
    if not 0 < alvo <= 1:
        raise ValueError("alvo deve estar em (0, 1]")
    v = np.sort(_limpar(valores))[::-1]
    total = v.sum()
    if total <= 0:
        raise ValueError("soma dos valores deve ser positiva")
    acumulado = np.cumsum(v) / total
    return int(np.searchsorted(acumulado, alvo - 1e-12) + 1)
