"""Autocorrelação espacial: Moran global e LISA com correção FDR (Benjamini-Hochberg).

Vizinhança queen (ver geometria.pesos_queen), padronização de linha (`transform="R"`).
Ilhas (municípios sem vizinho) saem da estatística e são listadas pelo chamador:
sem vizinho não há estatística espacial definida, e tratá-las como zero distorceria.

Correção para múltiplos testes: LISA faz 1 teste por município (~5.500 por variável).
Usamos Benjamini-Hochberg com α=0,05 (controla a taxa de falsas descobertas; Bonferroni
seria conservador demais para um mapa com milhares de testes). Ver docs/DECISOES.md D-024.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from esda.moran import Moran, Moran_Local
from libpysal.weights import W
from statsmodels.stats.multitest import multipletests

QUADRANTES = {1: "alto-alto", 2: "baixo-alto", 3: "baixo-baixo", 4: "alto-baixo"}


def sem_ilhas(w: W) -> tuple[W, np.ndarray]:
    """Devolve (W sem ilhas reindexado, máscara booleana das observações mantidas).

    Ilhas não têm vizinhos, então remover as linhas não altera a vizinhança das demais.
    """
    ilhas = {int(i) for i in w.islands}
    manter = np.array([i not in ilhas for i in range(w.n)])
    if not ilhas:
        return w, manter
    novo_indice = {antigo: novo for novo, antigo in enumerate(np.flatnonzero(manter))}
    vizinhos = {novo_indice[k]: [novo_indice[j] for j in w.neighbors[k]] for k in novo_indice}
    w_novo = W(vizinhos, silence_warnings=True)
    w_novo.transform = "R"
    return w_novo, manter


def moran_global(
    y: np.ndarray, w: W, permutacoes: int = 999, seed: int = 12345
) -> dict[str, float]:
    """Moran's I global (sem ilhas: use `sem_ilhas` antes) com pseudo-p por permutação."""
    if len(w.islands) > 0:
        raise ValueError("w contém ilhas: use sem_ilhas(w) antes do cálculo global")
    np.random.seed(seed)
    m = Moran(np.asarray(y, dtype=float), w, permutations=permutacoes, two_tailed=True)
    return {
        "I": float(m.I),
        "E_I": float(m.EI),
        "p_sim": float(m.p_sim),
        "z_sim": float(m.z_sim),
        "n": int(len(y)),
    }


def lisa_com_fdr(
    y: np.ndarray,
    w: W,
    ids: np.ndarray,
    alpha: float = 0.05,
    permutacoes: int = 999,
    seed: int = 12345,
) -> pd.DataFrame:
    """LISA por município (sem ilhas) com p por permutação e ajuste Benjamini-Hochberg.

    Colunas: id, I_local, quadrante, p_perm, p_fdr, significativo_fdr, quadrante_sig
    (`quadrante_sig` = rótulo só se significativo após FDR, senão "não significativo").
    """
    y = np.asarray(y, dtype=float)
    ids = np.asarray(ids)
    if len(ids) != len(y) or len(y) != w.n:
        raise ValueError("y, ids e w precisam ter o mesmo número de observações")
    w_use, manter = sem_ilhas(w)
    np.random.seed(seed)
    # two-sided: p bicaudal (mais conservador). Ver docs/DECISOES.md D-024.
    lisa = Moran_Local(
        y[manter], w_use, permutations=permutacoes, seed=seed, alternative="two-sided"
    )
    p = np.asarray(lisa.p_sim, dtype=float)
    _, p_fdr, _, _ = multipletests(p, alpha=alpha, method="fdr_bh")
    out = pd.DataFrame(
        {
            "id": ids[manter],
            "I_local": np.asarray(lisa.Is, dtype=float),
            "quadrante": [QUADRANTES[int(q)] for q in lisa.q],
            "p_perm": p,
            "p_fdr": p_fdr,
        }
    )
    out["significativo_fdr"] = out["p_fdr"] < alpha
    out["quadrante_sig"] = np.where(out["significativo_fdr"], out["quadrante"], "não significativo")
    return out
