"""Inferência ecológica para a projeção do 2º turno (F5).

Funções puras (numpy/pandas/cvxpy); o único I/O é `carregar_config` e `carregar_2022`.

Convenções
- Todas as categorias são contagens (ou parcelas) sobre ELEITORES APTOS. Cada município
  soma exatamente `eleitorado`: candidatos + BN (comparecimento - válidos) + ABST
  (eleitorado - comparecimento). A abstenção aqui é, portanto, `eleitorado - comparecimento`
  e inclui os aptos de seções não instaladas (postos do exterior com comparecimento 0).
- Colunas do T2: PL, PT, BN, ABST (lado partidário, não pessoa).
- Goodman restrito: Y = X B + erro, B >= 0, linhas de B somam 1, ponderado por aptos.
- Inferência ecológica: B descreve a associação entre municípios, NÃO o comportamento de
  eleitores individuais (falácia ecológica).
- ZZ (exterior) é recorte à parte: o total com ZZ nunca é rotulado "Brasil".
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

import cvxpy as cp
import numpy as np
import pandas as pd

CHAVE = ["uf", "cd_mun_tse"]
COLS_T2 = ["PL", "PT", "BN", "ABST"]
GRUPOS_2022_T2 = ["lula", "bolsonaro", "bn", "abst"]  # composição do eleitor de 2022-T2
SOLVER = "CLARABEL"


# ---------------------------------------------------------------------------
# Montagem de parcelas sobre aptos
# ---------------------------------------------------------------------------
def montar_contagens(
    candidatos: pd.DataFrame,
    totais: pd.DataFrame,
    grupos: Mapping[str, Sequence[int]],
) -> pd.DataFrame:
    """Contagens por município: grupos de candidatos + `bn` + `abst`; soma = eleitorado.

    `candidatos`: uf, cd_mun_tse, nr_candidato, votos (formato longo).
    `totais`: uf, cd_mun_tse, eleitorado, comparecimento, validos.
    Levanta ValueError se algum candidato não estiver em `grupos` (nada some em silêncio),
    se um candidato aparecer em dois grupos, ou se os invariantes falharem.
    """
    if {"bn", "abst"} & set(grupos):
        raise ValueError("'bn' e 'abst' são nomes reservados")
    todos = [int(n) for ns in grupos.values() for n in ns]
    if len(todos) != len(set(todos)):
        raise ValueError("candidato em mais de um grupo")
    ausentes = sorted(set(candidatos["nr_candidato"].astype(int)) - set(todos))
    if ausentes:
        raise ValueError(f"candidatos fora de qualquer grupo: {ausentes}")
    if totais.duplicated(CHAVE).any():
        raise ValueError("chave duplicada em totais")

    wide = candidatos.assign(nr_candidato=candidatos["nr_candidato"].astype(int)).pivot_table(
        index=CHAVE, columns="nr_candidato", values="votos", aggfunc="sum", fill_value=0
    )
    base = totais[[*CHAVE, "eleitorado", "comparecimento", "validos"]].set_index(CHAVE)
    wide = wide.reindex(base.index, fill_value=0)
    out = pd.DataFrame(index=base.index)
    for g, ns in grupos.items():
        cols = [n for n in ns if n in wide.columns]
        out[g] = wide[cols].sum(axis=1) if cols else 0
    soma_cand = out[list(grupos)].sum(axis=1)
    if (soma_cand != base["validos"]).any():
        raise ValueError("soma dos candidatos != válidos em algum município")
    out["bn"] = base["comparecimento"] - base["validos"]
    out["abst"] = base["eleitorado"] - base["comparecimento"]
    if (out[["bn", "abst"]] < 0).any().any():
        raise ValueError("BN ou abstenção negativos (comparecimento > eleitorado?)")
    out = out.astype("int64").reset_index()
    cats = [*grupos, "bn", "abst"]
    if (out[cats].sum(axis=1) != base["eleitorado"].to_numpy()).any():
        raise ValueError("categorias não somam o eleitorado")
    return out


def contagens_t2(candidatos: pd.DataFrame, totais: pd.DataFrame, pl: int, pt: int) -> pd.DataFrame:
    """Contagens observadas do T2 com colunas PL, PT, BN, ABST (soma = eleitorado)."""
    c = montar_contagens(candidatos, totais, {"PL": [pl], "PT": [pt]})
    return c.rename(columns={"bn": "BN", "abst": "ABST"})[[*CHAVE, *COLS_T2]]


def parcelas(contagens: pd.DataFrame, cats: Sequence[str]) -> tuple[np.ndarray, np.ndarray]:
    """(parcelas sobre aptos [n, K], aptos [n]). Exclui nada: município com aptos 0 levanta erro."""
    c = contagens[list(cats)].to_numpy(dtype=float)
    aptos = c.sum(axis=1)
    if (aptos <= 0).any():
        raise ValueError("município com aptos <= 0; trate antes com parear_chaves")
    return c / aptos[:, None], aptos


# ---------------------------------------------------------------------------
# Pareamento (nunca descarta em silêncio)
# ---------------------------------------------------------------------------
def parear_chaves(
    a: pd.DataFrame,
    b: pd.DataFrame,
    nome_a: str = "a",
    nome_b: str = "b",
    col_aptos: str | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Pareia por (uf, cd_mun_tse). Devolve (pareados, sem_par).

    Toda chave de `a` ou `b` termina em exatamente um dos dois: `pareados` ou `sem_par`
    (colunas: uf, cd_mun_tse, presente_em, motivo). Se `col_aptos` for dado, chaves com
    aptos 0 em qualquer lado vão para `sem_par`.
    """
    for nome, d in ((nome_a, a), (nome_b, b)):
        if d.duplicated(CHAVE).any():
            raise ValueError(f"chave duplicada em {nome}")
    ka = a[CHAVE].drop_duplicates()
    kb = b[CHAVE].drop_duplicates()
    m = ka.merge(kb, on=CHAVE, how="outer", indicator=True)
    so_a = m[m["_merge"] == "left_only"][CHAVE].assign(presente_em=nome_a, motivo=f"só em {nome_a}")
    so_b = m[m["_merge"] == "right_only"][CHAVE].assign(
        presente_em=nome_b, motivo=f"só em {nome_b}"
    )
    par = m[m["_merge"] == "both"][CHAVE]
    sem = [so_a, so_b]
    if col_aptos is not None:
        z = par.merge(a[[*CHAVE, col_aptos]], on=CHAVE).merge(
            b[[*CHAVE, col_aptos]], on=CHAVE, suffixes=("_a", "_b")
        )
        zero = (z[f"{col_aptos}_a"] <= 0) | (z[f"{col_aptos}_b"] <= 0)
        sem.append(z.loc[zero, CHAVE].assign(presente_em="ambos", motivo="aptos 0 em um dos lados"))
        par = z.loc[~zero, CHAVE]
    sem_par = pd.concat(sem, ignore_index=True)
    return par.reset_index(drop=True), sem_par.reset_index(drop=True)


# ---------------------------------------------------------------------------
# Goodman restrito (cvxpy)
# ---------------------------------------------------------------------------
def estatisticas_suficientes(
    x: np.ndarray, y: np.ndarray, w: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """G = X' W X, H = X' W Y (W = diag(w))."""
    xw = x * w[:, None]
    return xw.T @ x, xw.T @ y


def _resolver(
    g: np.ndarray, h: np.ndarray, b0: np.ndarray | None = None, lam: float = 0.0
) -> np.ndarray:
    """min tr(B'GB) - 2 tr(H'B) + lam ||B - B0||^2  s.a. B >= 0, B 1 = 1."""
    k, j = h.shape
    vals, vecs = np.linalg.eigh((g + g.T) / 2)
    f = (vecs * np.sqrt(np.clip(vals, 0.0, None))).T  # F'F = G
    b = cp.Variable((k, j))
    obj = cp.sum_squares(f @ b) - 2 * cp.trace(h.T @ b)
    if lam > 0 and b0 is not None:
        obj = obj + lam * cp.sum_squares(b - b0)
    prob = cp.Problem(cp.Minimize(obj), [b >= 0, cp.sum(b, axis=1) == 1])
    prob.solve(solver=SOLVER)
    if b.value is None or prob.status not in ("optimal", "optimal_inaccurate"):
        raise RuntimeError(f"cvxpy falhou: {prob.status}")
    out = np.clip(np.asarray(b.value), 0.0, None)
    return out / out.sum(axis=1, keepdims=True)


def goodman_restrito(
    x: np.ndarray,
    y: np.ndarray,
    w: np.ndarray,
    b0: np.ndarray | None = None,
    lam: float = 0.0,
) -> np.ndarray:
    """Matriz B [K, J]: Y ~ X B, B >= 0, linhas somam 1, ponderado por w (normalizado)."""
    wn = w / w.mean()
    g, h = estatisticas_suficientes(x, y, wn)
    return _resolver(g, h, b0, lam)


def goodman_por_uf(
    x: np.ndarray,
    y: np.ndarray,
    w: np.ndarray,
    uf: np.ndarray,
    lam: float,
    b_nacional_sem_uf: Mapping[str, np.ndarray] | None = None,
) -> dict[str, np.ndarray]:
    """B por UF com shrinkage em direção ao B nacional (sem a própria UF, se dado).

    lam = np.inf devolve o alvo; lam = 0 é o ajuste puro da UF (pode ser mal posto em
    UF pequena).
    """
    wn = w / w.mean()
    g_t, h_t = estatisticas_suficientes(x, y, wn)
    out: dict[str, np.ndarray] = {}
    for u in sorted(set(uf)):
        m = uf == u
        g_u, h_u = estatisticas_suficientes(x[m], y[m], wn[m])
        if b_nacional_sem_uf is not None and u in b_nacional_sem_uf:
            alvo = b_nacional_sem_uf[u]
        else:
            alvo = _resolver(g_t - g_u, h_t - h_u)
        out[u] = alvo if np.isinf(lam) else _resolver(g_u, h_u, alvo, lam)
    return out


def alvos_leave_one_uf_out(
    x: np.ndarray, y: np.ndarray, w: np.ndarray, uf: np.ndarray
) -> dict[str, np.ndarray]:
    """B nacional estimado SEM cada UF (alvo do shrinkage)."""
    wn = w / w.mean()
    g_t, h_t = estatisticas_suficientes(x, y, wn)
    out = {}
    for u in sorted(set(uf)):
        m = uf == u
        g_u, h_u = estatisticas_suficientes(x[m], y[m], wn[m])
        out[u] = _resolver(g_t - g_u, h_t - h_u)
    return out


def selecionar_lambda(
    x: np.ndarray,
    y: np.ndarray,
    w: np.ndarray,
    uf: np.ndarray,
    grade: Sequence[float],
    n_folds: int = 5,
    semente: int = 0,
) -> tuple[float, pd.DataFrame]:
    """Escolhe λ por validação cruzada com leave-one-UF-out no alvo.

    Para cada UF u: alvo = B nacional SEM u (leave-one-UF-out). Os municípios de u são
    divididos em `n_folds` blocos (ou leave-one-município-out se n < n_folds); em cada
    bloco, ajusta-se B_u nos demais com shrinkage λ em direção ao alvo e mede-se o erro
    quadrático ponderado no bloco retido. Erro total = soma sobre UFs / soma dos pesos.
    UF com 1 município não entra no escore. λ = inf = usar só o alvo.
    """
    rng = np.random.default_rng(semente)
    wn = w / w.mean()
    alvos = alvos_leave_one_uf_out(x, y, w, uf)
    erros = {float(lam): 0.0 for lam in grade}
    peso_total = 0.0
    for u in sorted(set(uf)):
        idx = np.flatnonzero(uf == u)
        if len(idx) < 2:
            continue
        k = min(n_folds, len(idx))
        blocos = np.array_split(rng.permutation(idx), k)
        g_u, h_u = estatisticas_suficientes(x[idx], y[idx], wn[idx])
        for bl in blocos:
            g_f, h_f = estatisticas_suficientes(x[bl], y[bl], wn[bl])
            for lam in grade:
                b = alvos[u] if np.isinf(lam) else _resolver(g_u - g_f, h_u - h_f, alvos[u], lam)
                r = y[bl] - x[bl] @ b
                erros[float(lam)] += float((wn[bl][:, None] * r**2).sum())
            peso_total += float(wn[bl].sum())
    tab = pd.DataFrame({"lambda": list(erros), "erro_cv": [e / peso_total for e in erros.values()]})
    melhor = float(tab.loc[tab["erro_cv"].idxmin(), "lambda"])
    return melhor, tab


# ---------------------------------------------------------------------------
# Regressão ecológica de composição (T2 anterior -> T1 atual)
# ---------------------------------------------------------------------------
def regressao_composicao(
    x_prev: np.ndarray, y_cur: np.ndarray, w: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """beta [G, J] (Goodman restrito) e composição [G, J].

    beta[g, j] = fração do grupo g (T2 anterior) que está na categoria j (T1 atual).
    composição[g, j] = P(grupo anterior = g | categoria atual = j) = beta[g,j] P_g / sum_g'.
    P_g = parcela ponderada do grupo g no T2 anterior. Colunas sem massa viram NaN.
    A composição é associação entre municípios, não trajetória individual.
    """
    beta = goodman_restrito(x_prev, y_cur, w)
    p = (x_prev * w[:, None]).sum(axis=0) / w.sum()
    num = beta * p[:, None]
    den = num.sum(axis=0, keepdims=True)
    with np.errstate(invalid="ignore", divide="ignore"):
        comp = np.where(den > 0, num / den, np.nan)
    return beta, comp


def linha_t2_por_composicao(comp_col: np.ndarray) -> np.ndarray:
    """Composição [lula22, bolsonaro22, bn22, abst22] -> linha T2 [PL, PT, BN, ABST].

    Premissa (D-033): cada componente volta ao comportamento de 2022-T2 (Bolsonaro22->PL,
    Lula22->PT, BN22->BN, Abst22->ABST). Nenhuma matriz de retenção é aplicada.
    """
    lula, bol, bn, ab = comp_col
    return np.array([bol, lula, bn, ab])


def linha_sem_retorno_abst(comp_col: np.ndarray, r: float) -> np.ndarray:
    """Variante 'identidade sem retorno à abstenção' (D-035).

    Zera o componente ABST22 da composição [lula22, bolsonaro22, bn22, abst22], renormaliza
    PL/PT/BN e aplica a taxa r de abstenção T1->T2 dos votantes: linha = (1-r) * linha + r em
    ABST. Se não sobrar massa fora de ABST22, devolve abstenção total.
    """
    if not 0.0 <= r <= 1.0:
        raise ValueError(f"r fora de [0, 1]: {r}")
    lula, bol, bn, _ = comp_col
    base = np.array([bol, lula, bn, 0.0])
    s = base.sum()
    if s <= 0:
        return np.array([0.0, 0.0, 0.0, 1.0])
    return (1 - r) * base / s + r * np.array([0.0, 0.0, 0.0, 1.0])


def taxa_abstencao_votantes(
    b: np.ndarray, votos_t1: np.ndarray, idx_votantes: Sequence[int]
) -> float:
    """r = média da coluna ABST de B nas linhas de votantes, ponderada pelos votos do T1.

    `b`: [K, 4] (colunas PL, PT, BN, ABST); `votos_t1`: votos (ou aptos) do T1 por categoria.
    """
    i = list(idx_votantes)
    w = np.asarray(votos_t1, dtype=float)[i]
    return float((w * b[i, 3]).sum() / w.sum())


# ---------------------------------------------------------------------------
# Bootstrap estratificado por UF
# ---------------------------------------------------------------------------
def reamostrar_estratificado(uf: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """Índices reamostrados com reposição DENTRO de cada UF (tamanho de cada UF preservado)."""
    partes = []
    for u in np.unique(uf):
        idx = np.flatnonzero(uf == u)
        partes.append(rng.choice(idx, size=len(idx), replace=True))
    return np.concatenate(partes)


def bootstrap_uf(
    uf: np.ndarray,
    estimador: Callable[[np.ndarray], np.ndarray],
    n_boot: int,
    semente: int = 0,
) -> np.ndarray:
    """Aplica `estimador(indices)` a n_boot reamostras; empilha em [n_boot, ...]."""
    rng = np.random.default_rng(semente)
    return np.stack([estimador(reamostrar_estratificado(uf, rng)) for _ in range(n_boot)])


def intervalo_percentil(amostras: np.ndarray, nivel: float = 0.95) -> tuple[np.ndarray, np.ndarray]:
    """(inferior, superior) por percentis ao longo do eixo 0, ignorando NaN."""
    a = (1 - nivel) / 2 * 100
    return np.nanpercentile(amostras, a, axis=0), np.nanpercentile(amostras, 100 - a, axis=0)


def ic_largo(linhas_boot: np.ndarray, limite_pp: float, nivel: float = 0.95) -> tuple[bool, float]:
    """Critério PROPOSTO de 'IC largo': largura do IC de (PL - PT) da linha, em p.p.

    `linhas_boot`: [n_boot, 4] (PL, PT, BN, ABST). Devolve (dispara, largura_pp).
    """
    d = (linhas_boot[:, 0] - linhas_boot[:, 1]) * 100
    lo, hi = intervalo_percentil(d, nivel)
    largura = float(hi - lo)
    return largura > limite_pp, largura


def usar_matriz_propria(
    x: np.ndarray,
    y: np.ndarray,
    w: np.ndarray,
    b_nacional: np.ndarray,
    min_municipios: int = 30,
    n_folds: int = 5,
    semente: int = 0,
) -> tuple[bool, dict[str, float]]:
    """Critério PROPOSTO para matriz própria (ex.: ZZ): n mínimo E menor erro de CV.

    Compara, por validação cruzada em blocos de municípios, o ajuste próprio (λ=0) com a
    matriz nacional aplicada. Usa a própria só se n >= min_municipios e o erro de CV
    próprio < erro da nacional. Devolve (decisão, diagnóstico).
    """
    n = len(x)
    wn = w / w.mean()
    if n < min_municipios:
        return False, {"n": n, "erro_proprio": np.nan, "erro_nacional": np.nan}
    rng = np.random.default_rng(semente)
    blocos = np.array_split(rng.permutation(n), min(n_folds, n))
    g, h = estatisticas_suficientes(x, y, wn)
    e_p = e_n = 0.0
    for bl in blocos:
        g_f, h_f = estatisticas_suficientes(x[bl], y[bl], wn[bl])
        b = _resolver(g - g_f, h - h_f)
        e_p += float((wn[bl][:, None] * (y[bl] - x[bl] @ b) ** 2).sum())
        e_n += float((wn[bl][:, None] * (y[bl] - x[bl] @ b_nacional) ** 2).sum())
    return e_p < e_n, {"n": n, "erro_proprio": e_p / wn.sum(), "erro_nacional": e_n / wn.sum()}


# ---------------------------------------------------------------------------
# Configuração (yaml): mapeamento e cenários
# ---------------------------------------------------------------------------
def carregar_config(caminho: Path) -> dict[str, Any]:
    import yaml

    with open(caminho, encoding="utf-8") as f:
        return yaml.safe_load(f)


def mapeamentos_do_cenario(cfg: Mapping[str, Any], cenario: str) -> dict[str, dict[str, Any]]:
    """Mapeamento por categoria 2026 com as sobrescritas do cenário aplicadas."""
    if cenario not in cfg["cenarios"]:
        raise KeyError(f"cenário desconhecido: {cenario}")
    out = {c["id"]: dict(c["mapeamento"]) for c in cfg["categorias_2026_t1"]}
    for cid, novo in (cfg["cenarios"][cenario].get("sobrescreve") or {}).items():
        if cid not in out:
            raise KeyError(f"cenário '{cenario}' sobrescreve categoria inexistente: {cid}")
        out[cid] = dict(novo)
    return out


def grupos_t1_2026(cfg: Mapping[str, Any], cenario: str = "base") -> dict[str, list[int]]:
    """Grupos de candidatos 2026 (id -> nrs) para `montar_contagens`; 'dividido' gera id__pK."""
    maps = mapeamentos_do_cenario(cfg, cenario)
    grupos: dict[str, list[int]] = {}
    for c in cfg["categorias_2026_t1"]:
        if "nr" not in c:
            continue  # bn / abst
        nrs = c["nr"] if isinstance(c["nr"], list) else [c["nr"]]
        m = maps[c["id"]]
        if m["tipo"] == "dividido":
            for k, parte in enumerate(m["partes"]):
                grupos[f"{c['id']}__p{k}"] = list(parte["nr"])
            usados = {n for p in m["partes"] for n in p["nr"]}
            if usados != set(nrs):
                raise ValueError(f"partes de '{c['id']}' não cobrem exatamente seus candidatos")
        else:
            grupos[c["id"]] = [int(n) for n in nrs]
    return grupos


def _linha_analogo(
    fontes: Mapping[str, pd.DataFrame], m: Mapping[str, Any], chave_cat: str = "t1_2022"
) -> np.ndarray:
    """Linha de B de uma fonte (`fonte`, padrão 'b_2022') e categoria (`categoria` ou t1_2022)."""
    fonte = m.get("fonte", "b_2022")
    cat = m.get("categoria", m.get(chave_cat))
    if fonte not in fontes:
        raise KeyError(f"fonte de B desconhecida: {fonte}")
    b = fontes[fonte]
    if cat not in b.index:
        raise KeyError(f"categoria de calibração ausente em {fonte}: {cat}")
    return b.loc[cat, COLS_T2].to_numpy(dtype=float)


def _linha_manual(linha: Mapping[str, float]) -> np.ndarray:
    v = np.array([linha[c] for c in COLS_T2], dtype=float)
    if (v < 0).any() or abs(v.sum() - 1) > 1e-6:
        raise ValueError(f"linha manual inválida (soma {v.sum()}): {dict(linha)}")
    return v


def matriz_t2(
    cfg: Mapping[str, Any],
    cenario: str,
    b_analogos: pd.DataFrame | Mapping[str, pd.DataFrame],
    linhas_regressao: Mapping[str, np.ndarray] | None = None,
    usar_fallback: Sequence[str] = (),
) -> pd.DataFrame:
    """Matriz de transferência 2026 [categorias, PL/PT/BN/ABST] para um cenário.

    `b_analogos`: B de calibração (índice = categorias 2022 do yaml) ou dicionário de fontes
    {'b_2022': ..., 'b_2018': ...}; mapeamentos 'analogo' escolhem a fonte por `fonte`
    (padrão 'b_2022') e a linha por `categoria` ou `t1_2022`. Para tipo
    'regressao_composicao', usa `linhas_regressao[id]`; se o id estiver em `usar_fallback`
    (decisão EXPLÍCITA do chamador, ex.: critério de IC largo) usa o `fallback` do yaml.
    Nada é decidido automaticamente aqui. Cada linha soma 1 (validado).
    """
    fontes = b_analogos if not isinstance(b_analogos, pd.DataFrame) else {"b_2022": b_analogos}
    linhas: dict[str, np.ndarray] = {}
    for cid, m in mapeamentos_do_cenario(cfg, cenario).items():
        tipo = m["tipo"]
        if tipo == "regressao_composicao" and cid not in usar_fallback:
            if linhas_regressao is None or cid not in linhas_regressao:
                raise KeyError(f"falta a linha de regressão de '{cid}' (ou peça o fallback)")
            linhas[cid] = np.asarray(linhas_regressao[cid], dtype=float)
        elif tipo == "regressao_composicao":
            fb = m["fallback"]
            linhas[cid] = _linha_analogo(fontes, fb)
        elif tipo == "analogo":
            linhas[cid] = _linha_analogo(fontes, m)
        elif tipo == "manual":
            linhas[cid] = _linha_manual(m["linha"])
        elif tipo == "dividido":
            for k, parte in enumerate(m["partes"]):
                pm = parte["mapeamento"]
                linhas[f"{cid}__p{k}"] = (
                    _linha_analogo(fontes, pm)
                    if pm["tipo"] == "analogo"
                    else _linha_manual(pm["linha"])
                )
        else:
            raise ValueError(f"tipo de mapeamento desconhecido: {tipo}")
    mat = pd.DataFrame.from_dict(linhas, orient="index", columns=COLS_T2)
    soma = mat.sum(axis=1)
    if (abs(soma - 1) > 1e-6).any():
        raise ValueError(f"linhas não somam 1: {soma[abs(soma - 1) > 1e-6].to_dict()}")
    return mat


# ---------------------------------------------------------------------------
# Projeção e agregação (somando votos absolutos)
# ---------------------------------------------------------------------------
def projetar(contagens_t1: pd.DataFrame, mat: pd.DataFrame) -> pd.DataFrame:
    """T2 projetado por município (contagens, não %): contagens[cats] @ mat.

    Exige que todas as categorias de `mat` existam em `contagens_t1` e que as colunas de
    categoria de `contagens_t1` (exceto chaves) estejam todas em `mat`: nada sobra nem some.
    """
    cats = list(mat.index)
    extras = [c for c in contagens_t1.columns if c not in CHAVE and c not in cats]
    if extras:
        raise ValueError(f"colunas de contagem fora da matriz: {extras}")
    faltam = [c for c in cats if c not in contagens_t1.columns]
    if faltam:
        raise ValueError(f"categorias da matriz ausentes nas contagens: {faltam}")
    v = contagens_t1[cats].to_numpy(dtype=float) @ mat[COLS_T2].to_numpy()
    return pd.concat(
        [contagens_t1[CHAVE].reset_index(drop=True), pd.DataFrame(v, columns=COLS_T2)], axis=1
    )


def agregar(proj: pd.DataFrame, por: Sequence[str] | None) -> pd.DataFrame:
    """Soma votos absolutos por `por` (ex.: ['uf']); por=None soma tudo (1 linha)."""
    cols = [c for c in proj.columns if c not in CHAVE]
    if por:
        return proj.groupby(list(por), as_index=False)[cols].sum()
    return pd.DataFrame([proj[cols].sum()])


def agregados_rotulados(proj: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Brasil sem ZZ, ZZ e total oficial (soma). O total COM ZZ nunca se chama 'Brasil'."""
    zz = proj["uf"] == "zz"
    return {
        "brasil_sem_zz": agregar(proj[~zz], None),
        "zz_exterior": agregar(proj[zz], None),
        "total_oficial_com_zz": agregar(proj, None),
    }


def checar_somas(proj: pd.DataFrame, aptos: pd.Series | np.ndarray, tol: float = 1e-6) -> None:
    """Levanta se a soma das categorias projetadas != aptos em algum município."""
    d = np.abs(proj[COLS_T2].sum(axis=1).to_numpy() - np.asarray(aptos, dtype=float))
    if (d > tol * np.maximum(1.0, np.asarray(aptos, dtype=float))).any():
        raise AssertionError("categorias projetadas não somam os aptos")


# ---------------------------------------------------------------------------
# Baselines e métricas
# ---------------------------------------------------------------------------
def baseline_a(c_t1: pd.DataFrame, col_pl: str, col_pt: str) -> pd.DataFrame:
    """(a) T1 renormalizado entre finalistas: votos dos finalistas mantidos; o resto é
    BN-ou-abstenção só para fechar a soma (BN = T1 BN; ABST = demais não-finalistas)."""
    pl, pt = c_t1[col_pl].astype(float), c_t1[col_pt].astype(float)
    aptos = c_t1.drop(columns=CHAVE).sum(axis=1).astype(float)
    return pd.DataFrame(
        {
            **{k: c_t1[k] for k in CHAVE},
            "PL": pl,
            "PT": pt,
            "BN": c_t1["bn"].astype(float),
            "ABST": aptos - pl - pt - c_t1["bn"],
        }
    )


def baseline_b(c_t1: pd.DataFrame, col_pl: str, col_pt: str) -> pd.DataFrame:
    """(b) Terceiros e BN divididos na proporção dos finalistas por município; ABST constante.
    Município sem votos dos finalistas: divisão 50/50 (listada no docstring, não silenciosa)."""
    pl, pt = c_t1[col_pl].astype(float), c_t1[col_pt].astype(float)
    fin = pl + pt
    sobra = c_t1.drop(columns=[*CHAVE, "abst", col_pl, col_pt]).sum(axis=1).astype(float)
    fr_pl = np.where(fin > 0, pl / fin.where(fin > 0, 1), 0.5)
    return pd.DataFrame(
        {
            **{k: c_t1[k] for k in CHAVE},
            "PL": pl + sobra * fr_pl,
            "PT": pt + sobra * (1 - fr_pl),
            "BN": 0.0,
            "ABST": c_t1["abst"].astype(float),
        }
    )


def metricas(pred: pd.DataFrame, obs: pd.DataFrame) -> dict[str, Any]:
    """Métricas do backtest. Ambos com CHAVE + PL/PT/BN/ABST (contagens) no mesmo conjunto.

    - erro_br_pp: erro do % de PL entre válidos (PL/(PL+PT)) agregado, em p.p.
    - por_uf: erro do mesmo %, por UF, e se o vencedor da UF foi acertado.
    - mae_municipal_pp: erro absoluto médio do % de PL entre válidos, ponderado por aptos.
    - acerto_vencedor_uf: fração de UFs com vencedor correto.
    - erro_abst_pp: erro do % de abstenção sobre aptos (BR).
    Esta função não filtra: a escolha de incluir ou não ZZ é de quem chama.
    """
    m = pred.merge(obs, on=CHAVE, suffixes=("_p", "_o"), validate="1:1")
    if len(m) != len(pred) or len(m) != len(obs):
        raise ValueError("pred e obs não cobrem as mesmas chaves")
    pl_p, pt_p, pl_o, pt_o = m["PL_p"], m["PT_p"], m["PL_o"], m["PT_o"]
    aptos = m[[f"{c}_o" for c in COLS_T2]].sum(axis=1)

    def pct(pl: Any, pt: Any) -> Any:
        s = pl + pt
        return 100 * pl / (s.where(s > 0) if hasattr(s, "where") else (s if s > 0 else np.nan))

    erro_mun = (pct(pl_p, pt_p) - pct(pl_o, pt_o)).abs()
    ok = erro_mun.notna()
    mae = float((erro_mun[ok] * aptos[ok]).sum() / aptos[ok].sum())
    g = m.assign(aptos=aptos).groupby("uf")
    uf = g[["PL_p", "PT_p", "PL_o", "PT_o"]].sum()
    uf["erro_pp"] = pct(uf["PL_p"], uf["PT_p"]) - pct(uf["PL_o"], uf["PT_o"])
    uf["acertou_vencedor"] = (uf["PL_p"] > uf["PT_p"]) == (uf["PL_o"] > uf["PT_o"])
    tot = m[["PL_p", "PT_p", "PL_o", "PT_o"]].sum()
    erro_br = float(pct(tot["PL_p"], tot["PT_p"]) - pct(tot["PL_o"], tot["PT_o"]))
    ab_p = m["ABST_p"].sum() / aptos.sum() * 100
    ab_o = m["ABST_o"].sum() / aptos.sum() * 100
    return {
        "erro_br_pp": erro_br,
        "por_uf": uf[["erro_pp", "acertou_vencedor"]],
        "mae_municipal_pp": mae,
        "acerto_vencedor_uf": float(uf["acertou_vencedor"].mean()),
        "erro_abst_pp": float(ab_p - ab_o),
    }


def residuo_por_uf(pred: pd.DataFrame, obs: pd.DataFrame) -> pd.DataFrame:
    """Resíduo (obs - pred) por UF: votos e p.p. dos aptos em PL, PT, BN, ABST."""
    m = pred.merge(obs, on=CHAVE, suffixes=("_p", "_o"), validate="1:1")
    s = m.groupby("uf")[[f"{c}_{t}" for c in COLS_T2 for t in "po"]].sum()
    aptos = s[[f"{c}_o" for c in COLS_T2]].sum(axis=1)
    out = pd.DataFrame(index=s.index)
    for c in COLS_T2:
        out[f"res_{c}_votos"] = s[f"{c}_o"] - s[f"{c}_p"]
        out[f"res_{c}_pp"] = 100 * (s[f"{c}_o"] - s[f"{c}_p"]) / aptos
    out["aptos"] = aptos
    return out


# ---------------------------------------------------------------------------
# I/O (isolado): dados processados de 2022
# ---------------------------------------------------------------------------
def carregar_2022(dir_processed: Path, turno: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(candidatos, totais) de Presidente 2022 no turno dado, por município."""
    c = pd.read_parquet(dir_processed / f"presidente_2022_t{turno}_municipio.parquet")
    t = pd.read_parquet(dir_processed / f"presidente_2022_t{turno}_municipio_totais.parquet")
    return c, t


# ---------------------------------------------------------------------------
# Previsão por UF, substituição de linhas e resumo de erros (backtest)
# ---------------------------------------------------------------------------
def prever_por_uf(
    contagens: pd.DataFrame, cats: Sequence[str], mats_uf: Mapping[str, np.ndarray]
) -> pd.DataFrame:
    """T2 previsto por município usando a matriz da UF do município (contagens @ B_uf).

    Levanta KeyError se alguma UF das contagens não tiver matriz (nada some em silêncio).
    """
    faltam = sorted(set(contagens["uf"]) - set(mats_uf))
    if faltam:
        raise KeyError(f"UFs sem matriz: {faltam}")
    v = np.zeros((len(contagens), len(COLS_T2)))
    c = contagens[list(cats)].to_numpy(dtype=float)
    ufs = contagens["uf"].to_numpy()
    for u in np.unique(ufs):
        m = ufs == u
        v[m] = c[m] @ mats_uf[u]
    return pd.concat(
        [contagens[CHAVE].reset_index(drop=True), pd.DataFrame(v, columns=COLS_T2)], axis=1
    )


def substituir_linhas(
    b: np.ndarray, cats: Sequence[str], linhas: Mapping[str, np.ndarray]
) -> np.ndarray:
    """Cópia de B [K, J] com as linhas das categorias indicadas trocadas (cada linha soma 1)."""
    out = b.copy()
    for cat, lin in linhas.items():
        lin = np.asarray(lin, dtype=float)
        if abs(lin.sum() - 1) > 1e-6:
            raise ValueError(f"linha '{cat}' não soma 1")
        out[list(cats).index(cat)] = lin
    return out


def resumo_erros_uf(erro_pp: pd.Series) -> dict[str, float]:
    """Resumo da distribuição do erro por UF (p.p., com sinal): média, |.| mediana, p90, máx."""
    a = erro_pp.abs()
    return {
        "media_com_sinal": float(erro_pp.mean()),
        "media_abs": float(a.mean()),
        "mediana_abs": float(a.median()),
        "p90_abs": float(a.quantile(0.9)),
        "max_abs": float(a.max()),
    }
