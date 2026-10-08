"""Projeção do 2º turno presidencial 2026 (F5a): orquestra `inferencia_ecologica` com o yaml.

Modelo de referência (D-034, D-035): matriz NACIONAL (sem B por UF); linhas de Flávio e Lula
por Goodman 2022; terceiros (Cury, Renan, Caiado e outros) por regressão ecológica de
composição 2022-T2 -> 2026-T1 com identidade (Lula22->PT, Bolsonaro22->PL, BN22->BN,
Abst22->ABST); linhas de BN e ABST da B nacional 2022 (cenário alternativo: 2018). O exterior
(ZZ) usa a matriz nacional; a própria de 2022 é o cenário `zz_propria`. Agregação SEMPRE somando
votos absolutos. O total com ZZ nunca é rotulado "Brasil".

Funções puras, exceto `carregar_insumos`, `carregar_config_projecao` e `salvar_saidas`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from eleicao import inferencia_ecologica as ie

TERCEIROS = ["cury", "renan", "caiado", "outros_2026"]
CAT_BN, CAT_ABST = "bn_2026", "abst_2026"
RECORTES_BR = {
    "brasil_sem_zz": "Brasil (sem exterior)",
    "zz_exterior": "Exterior (ZZ)",
    "total_oficial_com_zz": "Total oficial (com exterior)",
}
ESCOPOS = ("br", "zz")


# ---------------------------------------------------------------------------
# I/O
# ---------------------------------------------------------------------------
def carregar_insumos(proc: Path) -> dict[str, Any]:
    """Parquet de 2026 T1, 2022 T1/T2 e 2018 T1/T2 (candidatos, totais) + snapshot do T1."""

    def par(prefixo: str) -> tuple[pd.DataFrame, pd.DataFrame]:
        return (
            pd.read_parquet(proc / f"{prefixo}_municipio.parquet"),
            pd.read_parquet(proc / f"{prefixo}_municipio_totais.parquet"),
        )

    snap = json.loads((proc / "snapshot_t1_2026.json").read_text(encoding="utf-8"))
    return {
        "t1_2026": par("presidente_t1"),
        "t1_2022": par("presidente_2022_t1"),
        "t2_2022": par("presidente_2022_t2"),
        "t1_2018": par("presidente_2018_t1"),
        "t2_2018": par("presidente_2018_t2"),
        "snapshot": snap,
    }


def carregar_config_projecao(caminho: Path) -> dict[str, Any]:
    return ie.carregar_config(caminho)


def metadados_snapshot(snap: dict[str, Any]) -> dict[str, str]:
    """idg / and / tf / geração do T1 2026 para gravar nas saídas."""
    t = snap["tse"]
    return {
        "t1_idg": str(t["idg"]),
        "t1_and": str(t["and"]),
        "t1_tf": str(t["tf"]),
        "t1_geracao": f"{t['dg']} {t['hg']}",
    }


# ---------------------------------------------------------------------------
# Grupos
# ---------------------------------------------------------------------------
def grupos_2022(cfg: dict[str, Any]) -> dict[str, list[int]]:
    return {k: list(v["nr"]) for k, v in cfg["categorias_2022_t1"].items() if "nr" in v}


def grupos_2018(cfg: dict[str, Any]) -> dict[str, list[int]]:
    blocos = cfg["backtest_2018_2022"]["blocos"]
    return {k: list(b["c2018"]["nr"]) for k, b in blocos.items() if isinstance(b["c2018"], dict)}


def contagens_2026(ins: dict[str, Any], grupos: dict[str, list[int]]) -> pd.DataFrame:
    """Contagens do T1 2026 por município; bn/abst renomeados para os ids do yaml."""
    c, t = ins["t1_2026"]
    df = ie.montar_contagens(c, t, grupos).rename(columns={"bn": CAT_BN, "abst": CAT_ABST})
    return df.sort_values(ie.CHAVE).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Dados de estimação (arrays) por escopo
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Dados:
    """Arrays de estimação de um escopo ('br' = sem ZZ; 'zz' = exterior)."""

    ids22: list[str]
    ids18: list[str]
    ids26: list[str]
    x22: np.ndarray
    y22: np.ndarray
    w22: np.ndarray
    uf22: np.ndarray
    xprev: np.ndarray
    y26: np.ndarray
    w26: np.ndarray
    ufp: np.ndarray
    x18: np.ndarray
    y18: np.ndarray
    w18: np.ndarray
    uf18: np.ndarray


def _escopo_mask(df: pd.DataFrame, escopo: str) -> pd.Series:
    return df["uf"] == "zz" if escopo == "zz" else df["uf"] != "zz"


def _com_aptos(df: pd.DataFrame, cats: list[str]) -> pd.DataFrame:
    return df[[*ie.CHAVE]].assign(aptos=df[cats].sum(axis=1).to_numpy())


def montar_dados(
    ins: dict[str, Any], cfg: dict[str, Any], escopo: str
) -> tuple[Dados, pd.DataFrame]:
    """Arrays de estimação do escopo e a lista `sem_par` da regressão de composição.

    `sem_par` (2022 T2 x 2026 T1): chaves só em um dos anos ou com aptos 0 em algum. Nada é
    descartado da PROJEÇÃO por estar aqui; só fica fora do ajuste da regressão.
    """
    if escopo not in ESCOPOS:
        raise ValueError(escopo)
    g22, g18 = grupos_2022(cfg), grupos_2018(cfg)
    g26 = ie.grupos_t1_2026(cfg, "base")
    cats22, cats18 = [*g22, "bn", "abst"], [*g18, "bn", "abst"]
    ids22 = [*g22, "bn_2022", "abst_2022"]
    ids18 = cats18
    ids26 = [*g26, CAT_BN, CAT_ABST]

    def prep(
        t1: tuple[pd.DataFrame, pd.DataFrame],
        t2: tuple[pd.DataFrame, pd.DataFrame],
        grupos: dict[str, list[int]],
        pl: int,
        cats: list[str],
    ):
        c1 = ie.montar_contagens(*t1, grupos).sort_values(ie.CHAVE).reset_index(drop=True)
        c2 = ie.contagens_t2(*t2, pl=pl, pt=13).sort_values(ie.CHAVE).reset_index(drop=True)
        par, sem = ie.parear_chaves(c1, c2, "t1", "t2")
        if not sem.empty:
            raise ValueError(f"T1 e T2 do mesmo ano sem par: {len(sem)} chaves")
        m = _escopo_mask(c1, escopo) & (c1[cats].sum(axis=1) > 0)
        return c1[m].reset_index(drop=True), c2[m].reset_index(drop=True)

    c22t1, c22t2 = prep(ins["t1_2022"], ins["t2_2022"], g22, 22, cats22)
    c18t1, c18t2 = prep(ins["t1_2018"], ins["t2_2018"], g18, 17, cats18)
    x22, w22 = ie.parcelas(c22t1, cats22)
    y22, _ = ie.parcelas(c22t2, ie.COLS_T2)
    x18, w18 = ie.parcelas(c18t1, cats18)
    y18, _ = ie.parcelas(c18t2, ie.COLS_T2)

    # pares 2022-T2 x 2026-T1 (aptos > 0 nos dois lados)
    c26 = contagens_2026(ins, g26)
    c22t2_all = ie.contagens_t2(*ins["t2_2022"], pl=22, pt=13).sort_values(ie.CHAVE)
    a = _com_aptos(c22t2_all.reset_index(drop=True), ie.COLS_T2)
    b = _com_aptos(c26, ids26)
    a, b = a[_escopo_mask(a, escopo)], b[_escopo_mask(b, escopo)]
    par, sem_par = ie.parear_chaves(a, b, "2022", "2026", col_aptos="aptos")
    c22p = c22t2_all.merge(par, on=ie.CHAVE).sort_values(ie.CHAVE).reset_index(drop=True)
    c26p = c26.merge(par, on=ie.CHAVE).sort_values(ie.CHAVE).reset_index(drop=True)
    assert c22p[ie.CHAVE].equals(c26p[ie.CHAVE])
    xprev, _ = ie.parcelas(c22p, ["PT", "PL", "BN", "ABST"])  # lula, bolsonaro, bn, abst
    y26, w26 = ie.parcelas(c26p, ids26)
    d = Dados(
        ids22, ids18, ids26,
        x22, y22, w22, c22t1["uf"].to_numpy(),
        xprev, y26, w26, c26p["uf"].to_numpy(),
        x18, y18, w18, c18t1["uf"].to_numpy(),
    )  # fmt: skip
    return d, sem_par.assign(escopo=escopo)


# ---------------------------------------------------------------------------
# Estimação
# ---------------------------------------------------------------------------
@dataclass
class Parametros:
    b22: pd.DataFrame  # índice = ids do yaml (lula_13, ..., bn_2022, abst_2022)
    b18: pd.DataFrame  # índice = blocos 2018 (pl, pt, ciro, centro, outros, bn, abst)
    linhas: dict[str, np.ndarray]  # TERCEIROS -> linha [PL, PT, BN, ABST] por composição
    comp: np.ndarray  # composição [4 grupos 2022-T2, J categorias 2026]
    beta: np.ndarray
    r: float  # taxa de abstenção T1->T2 dos votantes (B 2022 in-sample), D-035
    linhas_sr: dict[str, np.ndarray]  # TERCEIROS -> linha 'identidade sem retorno à abstenção'


def estimar(
    d: Dados,
    i22: np.ndarray | None = None,
    ip: np.ndarray | None = None,
    i18: np.ndarray | None = None,
) -> Parametros:
    """Goodman restrito 2022 e 2018 (nacionais) e composição 2022-T2 -> 2026-T1."""

    def sel(idx: np.ndarray | None, n: int) -> np.ndarray:
        return np.arange(n) if idx is None else idx

    a = sel(i22, len(d.w22))
    p = sel(ip, len(d.w26))
    c = sel(i18, len(d.w18))
    b22 = ie.goodman_restrito(d.x22[a], d.y22[a], d.w22[a])
    b18 = ie.goodman_restrito(d.x18[c], d.y18[c], d.w18[c])
    beta, comp = ie.regressao_composicao(d.xprev[p], d.y26[p], d.w26[p])
    linhas = {}
    for cid in TERCEIROS:
        col = comp[:, d.ids26.index(cid)]
        if np.isnan(col).any():
            raise ValueError(f"categoria '{cid}' sem massa na regressão de composição")
        linhas[cid] = ie.linha_t2_por_composicao(col)
    n_vot = len(d.ids22) - 2  # categorias de candidatos (sem bn/abst)
    votos = (d.x22[a][:, :n_vot] * d.w22[a][:, None]).sum(axis=0)
    r = ie.taxa_abstencao_votantes(b22, votos, range(n_vot))
    linhas_sr = {
        cid: ie.linha_sem_retorno_abst(comp[:, d.ids26.index(cid)], r) for cid in TERCEIROS
    }
    return Parametros(
        pd.DataFrame(b22, index=d.ids22, columns=ie.COLS_T2),
        pd.DataFrame(b18, index=d.ids18, columns=ie.COLS_T2),
        linhas,
        comp,
        beta,
        r,
        linhas_sr,
    )


def _linhas_do_cenario(cfg: dict[str, Any], cenario: str, par: Parametros) -> dict[str, np.ndarray]:
    sem_retorno = cfg["cenarios"][cenario].get("identidade") == "sem_retorno_abst"
    return par.linhas_sr if sem_retorno else par.linhas


def matrizes_cenario(
    cfg: dict[str, Any], cenario: str, par_br: Parametros, par_zz: Parametros
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(matriz Brasil, matriz ZZ) do cenário. D-035: o exterior usa a matriz NACIONAL (base);
    só o cenário com `zz_usa: propria` usa a matriz estimada com os postos de 2022."""
    fontes = {"b_2022": par_br.b22, "b_2018": par_br.b18}
    m_br = ie.matriz_t2(cfg, cenario, fontes, _linhas_do_cenario(cfg, cenario, par_br))
    if cfg["cenarios"][cenario].get("zz_usa") != "propria":
        return m_br, m_br
    fontes_zz = {"b_2022": par_zz.b22, "b_2018": par_zz.b18}
    m_zz = ie.matriz_t2(cfg, cenario, fontes_zz, _linhas_do_cenario(cfg, cenario, par_zz))
    return m_br, m_zz


# ---------------------------------------------------------------------------
# Projeção
# ---------------------------------------------------------------------------
@dataclass
class DadosCenario:
    cols: list[str]
    contagens: np.ndarray  # [n, K], ordenado por CHAVE
    eh_zz: np.ndarray


def preparar_cenarios(
    cfg: dict[str, Any], ins: dict[str, Any], cenarios: list[str]
) -> tuple[pd.DataFrame, dict[str, DadosCenario]]:
    """Contagens do T1 2026 por cenário (os grupos mudam em 'dividido'). Devolve também o
    quadro de municípios (chaves + nome + aptos), único e ordenado."""
    cache: dict[tuple, tuple[list[str], np.ndarray]] = {}
    out: dict[str, DadosCenario] = {}
    base_df = None
    for cen in cenarios:
        g = ie.grupos_t1_2026(cfg, cen)
        chave = tuple((k, tuple(v)) for k, v in g.items())
        if chave not in cache:
            df = contagens_2026(ins, g)
            cols = [c for c in df.columns if c not in ie.CHAVE]
            cache[chave] = (cols, df[cols].to_numpy(dtype=float))
            if base_df is None:
                base_df = df[ie.CHAVE]
            elif not base_df.equals(df[ie.CHAVE]):
                raise AssertionError("ordem dos municípios difere entre cenários")
        cols, arr = cache[chave]
        out[cen] = DadosCenario(cols, arr, (base_df["uf"] == "zz").to_numpy())
    _, t = ins["t1_2026"]
    nomes = t[[*ie.CHAVE, "cd_mun_ibge", "nm_mun"]]
    mun = base_df.merge(nomes, on=ie.CHAVE, how="left", validate="1:1")
    mun["eh_exterior"] = mun["uf"] == "zz"
    return mun, out


def projetar_arrays(dc: DadosCenario, m_br: pd.DataFrame, m_zz: pd.DataFrame) -> np.ndarray:
    """Votos projetados [n, 4] (PL, PT, BN, ABST): contagens @ matriz do escopo do município."""
    p = np.zeros((len(dc.contagens), 4))
    p[~dc.eh_zz] = dc.contagens[~dc.eh_zz] @ m_br.loc[dc.cols, ie.COLS_T2].to_numpy()
    p[dc.eh_zz] = dc.contagens[dc.eh_zz] @ m_zz.loc[dc.cols, ie.COLS_T2].to_numpy()
    return p


def pct_pl_validos(pl: np.ndarray, pt: np.ndarray) -> np.ndarray:
    s = pl + pt
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(s > 0, 100 * pl / s, np.nan)


def veredito(pct_pl: float, faixa_pp: float, centro: float = 50.0) -> str:
    """'indistinguivel' se |%PL - 50| <= faixa; senão o vencedor projetado ('PL' ou 'PT')."""
    if np.isnan(pct_pl):
        return "sem_votos_validos"
    if abs(pct_pl - centro) <= faixa_pp:
        return "indistinguivel"
    return "PL" if pct_pl > centro else "PT"


# ---------------------------------------------------------------------------
# Bootstrap (variância de estimação)
# ---------------------------------------------------------------------------
def bootstrap_projecao(
    cfg: dict[str, Any],
    d_br: Dados,
    d_zz: Dados,
    dcs: dict[str, DadosCenario],
    uf_mun: np.ndarray,
    ufs: list[str],
    n_boot: int = 1000,
    semente: int = 0,
) -> dict[str, Any]:
    """Bootstrap estratificado por UF das estimativas (B 2022, B 2018, composição) e, a cada
    reamostra, reprojeta todos os cenários. É 'variância de estimação', NÃO erro de previsão:
    não captura erro sistemático (o backtest mostrou erro real 20 a 30 vezes o desvio)."""
    rng = np.random.default_rng(semente)
    cen_list = list(dcs)
    n = len(next(iter(dcs.values())).contagens)
    codes = np.array([ufs.index(u) for u in uf_mun])
    out: dict[str, Any] = {
        c: {
            "soma": np.zeros(n),
            "soma2": np.zeros(n),
            "nvalid": np.zeros(n),
            "uf": np.zeros((n_boot, len(ufs))),
            "br": np.zeros((n_boot, 3)),
            "abst": np.zeros((n_boot, 3)),
        }
        for c in cen_list
    }
    linhas_boot = {e: np.zeros((n_boot, len(TERCEIROS), 4)) for e in ESCOPOS}  # type: ignore[var-annotated]
    for r in range(n_boot):
        pars = {}
        for esc, d in (("br", d_br), ("zz", d_zz)):
            pars[esc] = estimar(
                d,
                ie.reamostrar_estratificado(d.uf22, rng),
                ie.reamostrar_estratificado(d.ufp, rng),
                ie.reamostrar_estratificado(d.uf18, rng),
            )
            linhas_boot[esc][r] = np.stack([pars[esc].linhas[c] for c in TERCEIROS])
        for cen in cen_list:
            m_br, m_zz = matrizes_cenario(cfg, cen, pars["br"], pars["zz"])
            p = projetar_arrays(dcs[cen], m_br, m_zz)
            _acumular(out[cen], r, p, dcs[cen].eh_zz, codes, len(ufs))
    out["linhas"] = linhas_boot
    return out


def _acumular(acc: dict, r: int, p: np.ndarray, eh_zz: np.ndarray, codes: np.ndarray, k: int):
    pl, pt, bn, ab = p.T
    pct = pct_pl_validos(pl, pt)
    ok = ~np.isnan(pct)
    acc["soma"][ok] += pct[ok]
    acc["soma2"][ok] += pct[ok] ** 2
    acc["nvalid"][ok] += 1
    uf_pl = np.bincount(codes, weights=pl, minlength=k)
    uf_pt = np.bincount(codes, weights=pt, minlength=k)
    acc["uf"][r] = pct_pl_validos(uf_pl, uf_pt)
    aptos = p.sum(axis=1)
    masks = (~eh_zz, eh_zz, np.ones_like(eh_zz))
    for j, m in enumerate(masks):
        acc["br"][r, j] = pct_pl_validos(pl[m].sum(), pt[m].sum())
        acc["abst"][r, j] = 100 * ab[m].sum() / aptos[m].sum()


def variancia_municipal(acc: dict) -> np.ndarray:
    """Variância amostral (pp^2) do % PL entre reamostras, por município (NaN se < 2 reamostras)."""
    n = acc["nvalid"]
    with np.errstate(invalid="ignore", divide="ignore"):
        media = acc["soma"] / n
        return np.where(n > 1, (acc["soma2"] - n * media**2) / (n - 1), np.nan)


# ---------------------------------------------------------------------------
# Saídas
# ---------------------------------------------------------------------------
def _pct_cols(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    s = df["PL"] + df["PT"]
    df["pct_pl_validos"] = np.where(s > 0, 100 * df["PL"] / s.where(s > 0, 1), np.nan)
    df["pct_pt_validos"] = np.where(s > 0, 100 * df["PT"] / s.where(s > 0, 1), np.nan)
    df["pct_abst_aptos"] = 100 * df["ABST"] / df["aptos"]
    return df


def montar_saidas(
    cfg: dict[str, Any],
    mun: pd.DataFrame,
    dcs: dict[str, DadosCenario],
    par_br: Parametros,
    par_zz: Parametros,
    boot: dict[str, Any],
    ufs: list[str],
    meta: dict[str, str],
) -> dict[str, pd.DataFrame]:
    """DataFrames 'municipio', 'uf' e 'br' em formato longo (coluna `cenario`)."""
    fh = cfg["faixa_heuristica"]
    f_br, f_uf, f_abs, f_mz = (
        fh["pct_pl_validos_br_pp"],
        fh["pct_pl_validos_uf_pp"],
        fh["abstencao_aptos_pp"],
        fh["municipio_e_zz_pp"],
    )
    mun_l, uf_l, br_l = [], [], []
    for cen, dc in dcs.items():
        m_br, m_zz = matrizes_cenario(cfg, cen, par_br, par_zz)
        p = projetar_arrays(dc, m_br, m_zz)
        aptos = dc.contagens.sum(axis=1)
        if not np.allclose(p.sum(axis=1), aptos):
            raise AssertionError(f"categorias projetadas não somam os aptos ({cen})")
        pm = mun.assign(cenario=cen, aptos=aptos, **dict(zip(ie.COLS_T2, p.T, strict=True)))
        pm = _pct_cols(pm)
        pm["faixa_pp"] = f_mz
        pm["var_boot_pct_pl_pp2"] = variancia_municipal(boot[cen])
        pm["veredito"] = [veredito(x, f_mz) for x in pm["pct_pl_validos"]]
        mun_l.append(pm)

        # UF (soma de votos absolutos dos municípios), ZZ como linha própria
        g = ie.agregar(pm[["uf", "aptos", *ie.COLS_T2]], ["uf"])
        g = _pct_cols(g)
        g["cenario"] = cen
        g["recorte"] = np.where(g["uf"] == "zz", "exterior", "brasil")
        g["faixa_pp"] = f_uf
        idx = [ufs.index(u) for u in g["uf"]]
        g["var_boot_pct_pl_pp2"] = np.nanvar(boot[cen]["uf"], axis=0, ddof=1)[idx]
        g["veredito"] = [veredito(x, f_uf) for x in g["pct_pl_validos"]]
        uf_l.append(g)

        # BR: 3 recortes com rótulos distintos
        zz = pm["uf"] == "zz"
        partes = {
            "brasil_sem_zz": pm[~zz],
            "zz_exterior": pm[zz],
            "total_oficial_com_zz": pm,
        }
        faixas = {"brasil_sem_zz": f_br, "zz_exterior": f_mz, "total_oficial_com_zz": f_br}
        for j, (rec, sub) in enumerate(partes.items()):
            a = _pct_cols(
                ie.agregar(sub[["aptos", *ie.COLS_T2]].assign(uf="x", cd_mun_tse="x"), None)
            )
            a["cenario"] = cen
            a["recorte"] = rec
            a["rotulo"] = RECORTES_BR[rec]
            a["faixa_pl_pp"] = faixas[rec]
            a["faixa_abst_pp"] = f_abs
            a["rotulo_faixa"] = fh["rotulo"]
            a["var_boot_pct_pl_pp2"] = np.var(boot[cen]["br"][:, j], ddof=1)
            a["var_boot_pct_abst_pp2"] = np.var(boot[cen]["abst"][:, j], ddof=1)
            a["veredito"] = veredito(float(a["pct_pl_validos"].iloc[0]), faixas[rec])
            br_l.append(a)
    out = {
        "municipio": pd.concat(mun_l, ignore_index=True),
        "uf": pd.concat(uf_l, ignore_index=True),
        "br": pd.concat(br_l, ignore_index=True),
    }
    for k, df in out.items():
        for c, v in meta.items():
            df[c] = v
        out[k] = df
    return out


def tabela_linhas_compostas(
    par_br: Parametros, par_zz: Parametros, boot: dict[str, Any], nivel: float = 0.95
) -> pd.DataFrame:
    """Linhas compostas (Cury, Renan, Caiado, outros) com IC bootstrap e largura de PL - PT."""
    rows = []
    for esc, par in (("br", par_br), ("zz", par_zz)):
        arr = boot["linhas"][esc]
        lo, hi = ie.intervalo_percentil(arr, nivel)
        for k, cid in enumerate(TERCEIROS):
            dif = (arr[:, k, 0] - arr[:, k, 1]) * 100
            lo_d, hi_d = ie.intervalo_percentil(dif, nivel)
            r = {"escopo": esc, "categoria": cid, "largura_pl_menos_pt_pp": float(hi_d - lo_d)}
            for j, col in enumerate(ie.COLS_T2):
                r[f"{col}"] = par.linhas[cid][j]
                r[f"{col}_lo"] = lo[k, j]
                r[f"{col}_hi"] = hi[k, j]
            rows.append(r)
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Execução completa
# ---------------------------------------------------------------------------
def executar(
    proc: Path, cfg_path: Path, n_boot: int = 1000, semente: int = 0
) -> dict[str, pd.DataFrame]:
    cfg = carregar_config_projecao(cfg_path)
    ins = carregar_insumos(proc)
    meta = metadados_snapshot(ins["snapshot"])
    cenarios = list(cfg["cenarios"])
    d_br, sem_br = montar_dados(ins, cfg, "br")
    d_zz, sem_zz = montar_dados(ins, cfg, "zz")
    par_br, par_zz = estimar(d_br), estimar(d_zz)
    mun, dcs = preparar_cenarios(cfg, ins, cenarios)
    ufs = sorted(mun["uf"].unique())
    boot = bootstrap_projecao(cfg, d_br, d_zz, dcs, mun["uf"].to_numpy(), ufs, n_boot, semente)
    saidas = montar_saidas(cfg, mun, dcs, par_br, par_zz, boot, ufs, meta)
    saidas["linhas_compostas"] = tabela_linhas_compostas(par_br, par_zz, boot)
    saidas["sem_par"] = pd.concat([sem_br, sem_zz], ignore_index=True)
    saidas["b22_br"] = par_br.b22.reset_index(names="categoria")
    saidas["b22_zz"] = par_zz.b22.reset_index(names="categoria")
    saidas["b18_br"] = par_br.b18.reset_index(names="categoria")
    saidas["parametros_r"] = pd.DataFrame(
        {"escopo": ["br", "zz"], "r_abst_votantes_2022": [par_br.r, par_zz.r]}
    )
    return saidas


def salvar_saidas(saidas: dict[str, pd.DataFrame], proc: Path) -> list[Path]:
    """Grava os três parquet de projeção e os CSV pequenos de apoio em data/processed/."""
    caminhos = []
    for nivel in ("municipio", "uf", "br"):
        p = proc / f"projecao_t2_2026_{nivel}.parquet"
        saidas[nivel].to_parquet(p, index=False)
        caminhos.append(p)
    for nome in ("sem_par", "linhas_compostas"):
        p = proc / f"projecao_t2_2026_{nome}.csv"
        saidas[nome].to_csv(p, index=False)
        caminhos.append(p)
    return caminhos


# ---------------------------------------------------------------------------
# Apresentação (usada pelo notebook; não calcula nada novo)
# ---------------------------------------------------------------------------
def carregar_saidas(proc: Path) -> dict[str, pd.DataFrame]:
    """Lê os parquet/CSV de projeção já gravados em data/processed/."""
    return {
        "municipio": pd.read_parquet(proc / "projecao_t2_2026_municipio.parquet"),
        "uf": pd.read_parquet(proc / "projecao_t2_2026_uf.parquet"),
        "br": pd.read_parquet(proc / "projecao_t2_2026_br.parquet"),
        "linhas_compostas": pd.read_csv(proc / "projecao_t2_2026_linhas_compostas.csv"),
        "sem_par": pd.read_csv(proc / "projecao_t2_2026_sem_par.csv", dtype=str),
    }


def frase_vencedor_br(br: pd.DataFrame, cenario: str = "base") -> str:
    """Frase de abertura. 'O método não distingue vencedor' vem ANTES de qualquer número."""
    x = br[(br["cenario"] == cenario) & (br["recorte"] == "brasil_sem_zz")].iloc[0]
    n = (
        f"{x['pct_pl_validos']:.1f}% PL entre válidos, "
        f"faixa heurística (n=1) de ±{x['faixa_pl_pp']:.1f} p.p."
    )
    if x["veredito"] == "indistinguivel":
        return f"O método não distingue vencedor no Brasil (sem exterior): {n}"
    return f"Vencedor projetado no Brasil (sem exterior): {x['veredito']}. {n}"


def tabela_resumo(br: pd.DataFrame) -> pd.DataFrame:
    """Cenários × recortes com % PL, % PT dos válidos, faixa e abstenção (% aptos)."""
    t = br[
        ["cenario", "rotulo", "pct_pl_validos", "pct_pt_validos", "faixa_pl_pp", "pct_abst_aptos"]
        + ["faixa_abst_pp", "veredito"]
    ].copy()
    return t.rename(columns={"rotulo": "recorte"}).round(2)


def tabela_uf(uf: pd.DataFrame, cenario: str = "base") -> pd.DataFrame:
    t = uf[uf["cenario"] == cenario][["uf", "pct_pl_validos", "faixa_pp", "veredito"]]
    return t.round(2).reset_index(drop=True)
