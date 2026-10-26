"""Fluxo T1 -> T2 2026: estimativa ecológica blindada.

Funções puras sobre arrays (parcelas sobre aptos): `x` [n, K] (origem no T1, incluindo
BN e abstenção), `y` [n, J] (destino no T2: PL, PT, BN, ABST), `w` [n] (aptos).

Três camadas, da mais forte à mais fraca em premissas:
  1. limites de Duncan-Davis (determinísticos, sem modelo);
  2. Goodman restrito (B >= 0, linhas somam 1), o estimador do projeto;
  3. intervalos por bootstrap em três esquemas (município, município dentro da UF e
     UF inteira como unidade), do mais otimista ao mais conservador.
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np
import pandas as pd

from eleicao import inferencia_ecologica as ie


def limites_duncan_davis(
    x: np.ndarray, y: np.ndarray, w: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """Limites inferior e superior [K, J] de B, sem qualquer modelo.

    Em cada unidade, a parcela da origem k que foi para j está em
    [max(0, (y_j - (1 - x_k)) / x_k), min(1, y_j / x_k)]. O limite nacional é a média
    desses limites ponderada pelos aptos da origem (w * x_k). Unidades com x_k = 0 não
    informam sobre a origem k.
    """
    n, k = x.shape
    j = y.shape[1]
    lo = np.zeros((k, j))
    hi = np.zeros((k, j))
    for a in range(k):
        xa = x[:, a]
        ok = xa > 0
        peso = (w * xa)[ok]
        for b in range(j):
            yb = y[ok, b]
            lo_u = np.clip((yb - (1 - xa[ok])) / xa[ok], 0.0, 1.0)
            hi_u = np.clip(yb / xa[ok], 0.0, 1.0)
            lo[a, b] = np.average(lo_u, weights=peso)
            hi[a, b] = np.average(hi_u, weights=peso)
    return lo, hi


def estimar_b(x: np.ndarray, y: np.ndarray, w: np.ndarray) -> np.ndarray:
    return ie.goodman_restrito(x, y, w)


def indices_municipio(n: int, rng: np.random.Generator) -> np.ndarray:
    return rng.integers(0, n, size=n)


def indices_cluster_uf(uf: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """Reamostra UFs inteiras com reposição (captura a correlação espacial dentro da UF)."""
    ufs = np.unique(uf)
    sorteadas = rng.choice(ufs, size=len(ufs), replace=True)
    return np.concatenate([np.flatnonzero(uf == u) for u in sorteadas])


def bootstrap(
    sorteio: Callable[[np.random.Generator], np.ndarray],
    x: np.ndarray,
    y: np.ndarray,
    w: np.ndarray,
    n_boot: int,
    semente: int = 0,
) -> np.ndarray:
    """[n_boot, K, J] de B reestimada em reamostras definidas por `sorteio`."""
    rng = np.random.default_rng(semente)
    out = []
    for _ in range(n_boot):
        i = sorteio(rng)
        out.append(estimar_b(x[i], y[i], w[i]))
    return np.stack(out)


def tabela_fluxo(
    origens: list[str],
    b: np.ndarray,
    ic: dict[str, tuple[np.ndarray, np.ndarray]],
    dd: tuple[np.ndarray, np.ndarray],
) -> pd.DataFrame:
    """Formato longo: estimativa, ICs de cada esquema e limites de Duncan-Davis."""
    linhas = []
    for a, o in enumerate(origens):
        for j, d in enumerate(ie.COLS_T2):
            linha = {"origem": o, "destino": d, "b": b[a, j]}
            for nome, (lo, hi) in ic.items():
                linha[f"{nome}_lo"] = lo[a, j]
                linha[f"{nome}_hi"] = hi[a, j]
            linha["dd_lo"] = dd[0][a, j]
            linha["dd_hi"] = dd[1][a, j]
            linhas.append(linha)
    return pd.DataFrame(linhas)


def condicionamento(x: np.ndarray, w: np.ndarray) -> dict[str, float]:
    """Número de condição de X'WX com uma coluna removida (as parcelas somam 1).

    Valores muito altos indicam categorias quase colineares (o mesmo risco que a
    regressão enfrenta). Também devolve a maior correlação ponderada entre pares.
    """
    xr = x[:, :-1]
    wn = w / w.sum()
    media = wn @ xr
    xc = xr - media
    cov = (xc * wn[:, None]).T @ xc
    dp = np.sqrt(np.diag(cov))
    corr = cov / np.outer(dp, dp)
    np.fill_diagonal(corr, 0.0)
    autov = np.linalg.eigvalsh(cov)
    return {
        "numero_condicao": float(autov.max() / autov.min()),
        "maior_correlacao_abs": float(np.abs(corr).max()),
    }


def ganhos_minimos_pt(
    x: np.ndarray, y: np.ndarray, aptos: np.ndarray, col_lula: int, col_pt: int = 1
) -> dict[str, float]:
    """Votos que o PT precisa ter ganhado de quem NÃO votou em Lula no T1 (sem modelo).

    Por unidade: max(0, y_PT - x_Lula) * aptos é o ganho líquido mínimo vindo de fora do
    eleitorado de Lula; (1 - x_Lula) * aptos é o teto (todos os outros). Soma nacional.
    """
    ganho = np.clip(y[:, col_pt] - x[:, col_lula], 0.0, None) * aptos
    teto = (1 - x[:, col_lula]) * aptos
    return {
        "ganho_minimo_votos": float(ganho.sum()),
        "teto_votos": float(teto.sum()),
        "unidades_com_ganho": float((ganho > 0).sum()),
        "unidades": float(len(ganho)),
    }
