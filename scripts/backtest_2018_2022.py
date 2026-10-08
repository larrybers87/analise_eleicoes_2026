"""Backtest fora da amostra: B estimada em 2018 (T1->T2) prevê o T2 de 2022 a partir do T1 de 2022.

Não usa dados de 2022 para escolher λ nem para ajustar B (só para a regressão de composição
da variante `regressao_terceiros`, que usa o T1 de 2022 como variável dependente, como fará
a projeção de 2026). Não usa nada de 2026. Saídas: data/interim/projecao_t2/backtest_*.
"""

from __future__ import annotations

import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

from eleicao import inferencia_ecologica as ie

RAIZ = Path(__file__).resolve().parents[1]
PROC = RAIZ / "data" / "processed"
SAIDA = RAIZ / "data" / "interim" / "projecao_t2"
GRADE = [0.0, 0.01, 0.1, 1.0, 10.0, 100.0, 1000.0, np.inf]
N_BOOT = 1000

G18 = {
    "pl": [17],
    "pt": [13],
    "ciro": [12],
    "centro": [45, 15, 19, 18],
    "outros": [30, 51, 50, 54, 16, 27],
}
G22 = {"pl": [22], "pt": [13], "ciro": [12], "centro": [15], "outros": [44, 30, 14, 80, 21, 16, 27]}


def _sem_novo(g: dict[str, list[int]]) -> dict[str, list[int]]:
    """Variante amoedo_separado: nr 30 (NOVO) sai de 'outros' e vira bloco 'novo'."""
    out = {k: [n for n in v if n != 30] if k == "outros" else list(v) for k, v in g.items()}
    out["novo"] = [30]
    return {**{k: out[k] for k in ("pl", "pt", "ciro", "centro", "novo", "outros")}}


def carregar_ano(
    ano: int, grupos: dict[str, list[int]], pl: int
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(T1 em contagens por bloco, T2 em PL/PT/BN/ABST), ordenados por chave, com checagem."""
    r = {}
    for t in (1, 2):
        c = pd.read_parquet(PROC / f"presidente_{ano}_t{t}_municipio.parquet")
        tot = pd.read_parquet(PROC / f"presidente_{ano}_t{t}_municipio_totais.parquet")
        r[t] = (c, tot)
    x1 = ie.montar_contagens(*r[1], grupos)
    y2 = ie.contagens_t2(*r[2], pl=pl, pt=13)
    par, sem = ie.parear_chaves(x1, y2, "t1", "t2")
    assert sem.empty, sem
    return (
        x1.sort_values(ie.CHAVE).reset_index(drop=True),
        y2.sort_values(ie.CHAVE).reset_index(drop=True),
    )


def cats_de(g: dict[str, list[int]]) -> list[str]:
    return [*g, "bn", "abst"]


def ajustar_tudo(x, y, w, uf, lam):
    """(B nacional, {uf: B}) com alvo leave-one-UF-out e shrinkage λ."""
    wn = w / w.mean()
    g_t, h_t = ie.estatisticas_suficientes(x, y, wn)
    b_nat = ie._resolver(g_t, h_t)
    b_uf = {}
    for u in np.unique(uf):
        m = uf == u
        g_u, h_u = ie.estatisticas_suficientes(x[m], y[m], wn[m])
        alvo = ie._resolver(g_t - g_u, h_t - h_u)
        b_uf[u] = alvo if np.isinf(lam) else ie._resolver(g_u, h_u, alvo, lam)
    return b_nat, b_uf


# ---------------------------------------------------------------------------
# bootstrap paralelo (dados em variável global do processo)
# ---------------------------------------------------------------------------
D: dict = {}


def _init(d):
    D.update(d)


def _pct_uf(s_uf: dict, mats: dict, ufs: list[str]) -> np.ndarray:
    """% de PL entre válidos por UF (27) + BR (último), a partir de somas de contagens por UF."""
    pl = np.array([(s_uf[u] @ mats[u])[0] for u in ufs])
    pt = np.array([(s_uf[u] @ mats[u])[1] for u in ufs])
    return np.append(100 * pl / (pl + pt), 100 * pl.sum() / (pl.sum() + pt.sum()))


def _rep(i: int) -> dict:
    rng = np.random.default_rng(10_000 + i)
    idx = ie.reamostrar_estratificado(D["uf"], rng)
    uf = D["uf"][idx]
    ufs = D["ufs"]
    out = {}
    b_nat, b_uf = ajustar_tudo(D["x18"][idx], D["y18"][idx], D["w18"][idx], uf, D["lam_base"])
    out["base_nac"] = _pct_uf(D["s22"], {u: b_nat for u in ufs}, ufs)
    out["base_uf"] = _pct_uf(D["s22"], b_uf, ufs)
    _, comp = ie.regressao_composicao(D["xprev"][idx], D["x22sh"][idx], D["w22"][idx])
    linhas = {c: ie.linha_t2_por_composicao(comp[:, D["cols_terc"][c]]) for c in D["terc"]}
    out["linhas"] = np.stack([linhas[c] for c in D["terc"]])
    cats = D["cats"]
    bn2 = ie.substituir_linhas(b_nat, cats, linhas)
    bu2 = {u: ie.substituir_linhas(b, cats, linhas) for u, b in b_uf.items()}
    out["regter_nac"] = _pct_uf(D["s22"], {u: bn2 for u in ufs}, ufs)
    out["regter_uf"] = _pct_uf(D["s22"], bu2, ufs)
    bna, _ = ajustar_tudo(D["x18a"][idx], D["y18"][idx], D["w18"][idx], uf, np.inf)
    out["amoedo_nac"] = _pct_uf(D["s22a"], {u: bna for u in ufs}, ufs)
    return out


# ---------------------------------------------------------------------------
def tabela_metricas(preds: dict[str, pd.DataFrame], obs: pd.DataFrame):
    linhas, por_uf = [], {}
    for nome, p in preds.items():
        m = ie.metricas(p, obs)
        r = ie.resumo_erros_uf(m["por_uf"]["erro_pp"])
        linhas.append(
            {
                "modelo": nome,
                "erro_br_pp": m["erro_br_pp"],
                "uf_media_com_sinal": r["media_com_sinal"],
                "uf_media_abs": r["media_abs"],
                "uf_mediana_abs": r["mediana_abs"],
                "uf_p90_abs": r["p90_abs"],
                "uf_max_abs": r["max_abs"],
                "mae_municipal_pp": m["mae_municipal_pp"],
                "acerto_vencedor_uf": m["acerto_vencedor_uf"],
                "ufs_erradas": int((~m["por_uf"]["acertou_vencedor"]).sum()),
                "erro_abst_br_pp": m["erro_abst_pp"],
            }
        )
        por_uf[nome] = m["por_uf"]["erro_pp"]
    return pd.DataFrame(linhas).set_index("modelo"), pd.DataFrame(por_uf)


def main() -> None:
    SAIDA.mkdir(parents=True, exist_ok=True)
    G18a, G22a = _sem_novo(G18), _sem_novo(G22)
    x18, y18 = carregar_ano(2018, G18, 17)
    x22, y22 = carregar_ano(2022, G22, 22)
    x18a, _ = carregar_ano(2018, G18a, 17)
    x22a, _ = carregar_ano(2022, G22a, 22)
    cats, cats_a = cats_de(G18), cats_de(G18a)
    assert cats == cats_de(G22) and cats_a == cats_de(G22a)

    # recortes: Brasil (sem ZZ) e ZZ; aptos > 0
    def brasil(d):
        return d["uf"] != "zz"

    k18, k22 = set(map(tuple, x18[ie.CHAVE].to_numpy())), set(map(tuple, x22[ie.CHAVE].to_numpy()))
    par = k18 & k22
    sem_par_br = sorted((k18 ^ k22) - {k for k in (k18 ^ k22) if k[0] == "zz"})
    print("BR 2018:", brasil(x18).sum(), "BR 2022:", brasil(x22).sum(), "| sem par BR:", sem_par_br)
    print(
        "ZZ 2018:",
        (~brasil(x18)).sum(),
        "ZZ 2022:",
        (~brasil(x22)).sum(),
        "ZZ pares:",
        sum(k[0] == "zz" for k in par),
    )

    chave = lambda d: list(map(tuple, d[ie.CHAVE].to_numpy()))  # noqa: E731
    m18 = brasil(x18) & pd.Series([k in par for k in chave(x18)], index=x18.index)
    m22 = brasil(x22) & pd.Series([k in par for k in chave(x22)], index=x22.index)
    assert chave(x18[m18]) == chave(x22[m22])  # mesmas chaves, mesma ordem

    t18, t18y = x18[m18].reset_index(drop=True), y18[m18].reset_index(drop=True)
    t18a = x18a[m18].reset_index(drop=True)
    t22, t22a = x22[m22].reset_index(drop=True), x22a[m22].reset_index(drop=True)
    o22 = y22[m22].reset_index(drop=True)
    xs, w = ie.parcelas(t18, cats)
    xsa, _ = ie.parcelas(t18a, cats_a)
    ys, _ = ie.parcelas(t18y, ie.COLS_T2)
    uf = t18["uf"].to_numpy()
    ufs = sorted(set(uf))

    # λ por CV só com 2018
    lam, tab = ie.selecionar_lambda(xs, ys, w, uf, GRADE, 5, 0)
    lam_a, tab_a = ie.selecionar_lambda(xsa, ys, w, uf, GRADE, 5, 0)
    tab.assign(variante="base").to_csv(SAIDA / "backtest_lambda_base.csv", index=False)
    tab_a.assign(variante="amoedo_separado").to_csv(
        SAIDA / "backtest_lambda_amoedo.csv", index=False
    )
    print("CV λ base:\n", tab.to_string(index=False), "\nλ base:", lam, "| λ amoedo:", lam_a)

    b_nat, b_uf = ajustar_tudo(xs, ys, w, uf, lam)
    b_nat_a, b_uf_a = ajustar_tudo(xsa, ys, w, uf, lam_a)
    bnat_df = pd.DataFrame(b_nat, index=cats, columns=ie.COLS_T2)
    bnat_df.to_csv(SAIDA / "backtest_B_2018_nacional.csv")
    print("B 2018 nacional:\n", bnat_df.round(3))

    # bootstrap da B nacional 2018 (IC)
    boot_b = ie.bootstrap_uf(uf, lambda i: ie.goodman_restrito(xs[i], ys[i], w[i]), N_BOOT, 7)
    lo, hi = ie.intervalo_percentil(boot_b)
    pd.DataFrame(
        {
            f"{c}_{k}": v[:, j]
            for j, c in enumerate(ie.COLS_T2)
            for k, v in (("lo", lo), ("hi", hi))
        },
        index=cats,
    ).to_csv(SAIDA / "backtest_B_2018_nacional_ic95.csv")
    dif = (boot_b[:, :, 0] - boot_b[:, :, 1]) * 100
    larg_b = pd.Series(
        np.percentile(dif, 97.5, axis=0) - np.percentile(dif, 2.5, axis=0), index=cats
    )
    print("largura IC95 PL-PT (B 2018 estimada, p.p.):\n", larg_b.round(1))

    # regressão de composição 2018-T2 -> 2022-T1 (ordem lula,bolsonaro,bn,abst = PT,PL,BN,ABST)
    xprev = t18y[["PT", "PL", "BN", "ABST"]].to_numpy(float)
    xprev = xprev / xprev.sum(axis=1, keepdims=True)
    x22sh, w22 = ie.parcelas(t22, cats)
    terc = ["centro", "ciro", "outros"]
    cols_terc = {c: cats.index(c) for c in terc}
    _, comp = ie.regressao_composicao(xprev, x22sh, w22)
    linhas = {c: ie.linha_t2_por_composicao(comp[:, cols_terc[c]]) for c in terc}
    print(
        "Linhas compostas (PL, PT, BN, ABST):", {c: v.round(3).tolist() for c, v in linhas.items()}
    )
    print(
        "Linhas Goodman 2018 correspondentes:", {c: bnat_df.loc[c].round(3).tolist() for c in terc}
    )

    # previsões pontuais (Brasil sem ZZ)
    def prev(cont, cs, bn, bu):
        return ie.prever_por_uf(cont, cs, {u: bn for u in ufs}), ie.prever_por_uf(cont, cs, bu)

    p = {}
    p["base_nac"], p["base_uf"] = prev(t22, cats, b_nat, b_uf)
    p["amoedo_nac"], p["amoedo_uf"] = prev(t22a, cats_a, b_nat_a, b_uf_a)
    bn2 = ie.substituir_linhas(b_nat, cats, linhas)
    bu2 = {u: ie.substituir_linhas(b, cats, linhas) for u, b in b_uf.items()}
    p["regter_nac"], p["regter_uf"] = prev(t22, cats, bn2, bu2)
    # D-035: identidade sem retorno à abstenção; r vem da B 2018 in-sample (fora da amostra de 2022)
    n_vot = len(G18)
    votos18 = t18[cats[:n_vot]].to_numpy(float).sum(axis=0)
    r18 = ie.taxa_abstencao_votantes(b_nat, votos18, range(n_vot))
    lin_sr = {c: ie.linha_sem_retorno_abst(comp[:, cols_terc[c]], r18) for c in terc}
    bn_sr = ie.substituir_linhas(b_nat, cats, lin_sr)
    p["regter_nac_semretorno"] = ie.prever_por_uf(t22, cats, {u: bn_sr for u in ufs})
    print("r (B 2018 in-sample; linhas de votantes pl, pt, ciro, centro, outros):", round(r18, 5))
    print("   ABST por linha:", {c: round(float(b_nat[cats.index(c), 3]), 4) for c in cats[:n_vot]})
    print(
        "   votos T1 2018 (BR sem ZZ) por bloco:",
        dict(zip(cats[:n_vot], votos18.astype(int), strict=True)),
    )
    pd.DataFrame({"r_abst_votantes_2018": [r18]}).to_csv(SAIDA / "backtest_r_2018.csv", index=False)
    p["baseline_a"] = ie.baseline_a(t22, "pl", "pt")
    p["baseline_b"] = ie.baseline_b(t22, "pl", "pt")
    for pr in p.values():
        ie.checar_somas(pr, t22[cats].sum(axis=1))
    resumo, erros_uf = tabela_metricas(p, o22)
    resumo.to_csv(SAIDA / "backtest_resumo.csv")
    erros_uf.to_csv(SAIDA / "backtest_erros_uf.csv")
    res_uf = {n: ie.residuo_por_uf(pr, o22) for n, pr in p.items()}
    pd.concat(res_uf, axis=1).to_csv(SAIDA / "backtest_residuos_uf.csv")
    pd.set_option("display.width", 250)
    print("RESUMO:\n", resumo.round(3).to_string())
    print("ERROS POR UF (pred - obs, p.p. do % PL entre válidos):\n", erros_uf.round(2).to_string())

    # observado 2022 (referência)
    tot = o22[["PL", "PT"]].sum()
    print("% PL entre válidos observado BR 2022:", round(100 * tot["PL"] / tot.sum(), 3))

    # ZZ: 2018 (treino) -> 2022 (teste)
    z18 = (~brasil(x18)) & (x18[cats].sum(axis=1) > 0)
    z22 = (~brasil(x22)) & (x22[cats].sum(axis=1) > 0)
    print("ZZ treino (aptos>0):", z18.sum(), "de", (~brasil(x18)).sum(), "| teste:", z22.sum())
    xz, wz = ie.parcelas(x18[z18], cats)
    yz, _ = ie.parcelas(y18[z18], ie.COLS_T2)
    b_zz = ie.goodman_restrito(xz, yz, wz)
    b_nat_full = b_nat  # nacional 2018 do Brasil
    tz22 = x22[z22].reset_index(drop=True)
    oz22 = y22[z22].reset_index(drop=True)
    pz = {
        "zz_matriz_propria_2018": ie.prever_por_uf(tz22, cats, {"zz": b_zz}),
        "zz_matriz_nacional_2018": ie.prever_por_uf(tz22, cats, {"zz": b_nat_full}),
        "zz_baseline_a": ie.baseline_a(tz22, "pl", "pt"),
        "zz_baseline_b": ie.baseline_b(tz22, "pl", "pt"),
    }
    zr = []
    for nome, pr in pz.items():
        m = ie.metricas(pr, oz22)
        zr.append(
            {
                "modelo": nome,
                "erro_zz_pp": m["erro_br_pp"],
                "mae_posto_pp": m["mae_municipal_pp"],
                "erro_abst_pp": m["erro_abst_pp"],
            }
        )
    zdf = pd.DataFrame(zr).set_index("modelo")
    zdf.to_csv(SAIDA / "backtest_zz.csv")
    pd.DataFrame(b_zz, index=cats, columns=ie.COLS_T2).to_csv(SAIDA / "backtest_B_zz_2018.csv")
    tz = oz22[["PL", "PT"]].sum()
    print("ZZ observado % PL entre válidos 2022:", round(100 * tz["PL"] / tz.sum(), 3))
    print("ZZ:\n", zdf.round(3).to_string())
    print("B ZZ 2018:\n", pd.DataFrame(b_zz, index=cats, columns=ie.COLS_T2).round(3))

    # bootstrap das previsões (estratificado por UF)
    s22 = {u: t22.loc[t22["uf"] == u, cats].to_numpy(float).sum(axis=0) for u in ufs}
    s22a = {u: t22a.loc[t22a["uf"] == u, cats_a].to_numpy(float).sum(axis=0) for u in ufs}
    dados = dict(
        uf=uf, ufs=ufs, x18=xs, x18a=xsa, y18=ys, w18=w, lam_base=lam, s22=s22, s22a=s22a,
        xprev=xprev, x22sh=x22sh, w22=w22, terc=terc, cols_terc=cols_terc, cats=cats,
    )  # fmt: skip
    nproc = max(1, (os.cpu_count() or 2) - 1)
    t0 = time.time()
    with ProcessPoolExecutor(nproc, initializer=_init, initargs=(dados,)) as ex:
        reps = list(ex.map(_rep, range(N_BOOT), chunksize=10))
    print(f"bootstrap: {N_BOOT} reamostras, {nproc} processos, {time.time() - t0:.0f}s")

    obs_uf = o22.groupby("uf")[["PL", "PT"]].sum()
    obs_pct = np.append(
        100 * obs_uf["PL"] / (obs_uf["PL"] + obs_uf["PT"]), 100 * tot["PL"] / tot.sum()
    )
    cob = []
    uf_cob = {}
    for nome in ["base_nac", "base_uf", "regter_nac", "regter_uf", "amoedo_nac"]:
        arr = np.stack([r[nome] for r in reps])
        lo_, hi_ = ie.intervalo_percentil(arr)
        sd = arr.std(axis=0, ddof=1)
        cobre = (obs_pct >= lo_) & (obs_pct <= hi_)
        cob.append(
            {
                "modelo": nome,
                "br_obs": obs_pct[-1],
                "br_lo": lo_[-1],
                "br_hi": hi_[-1],
                "br_largura_ic": hi_[-1] - lo_[-1],
                "br_cobre": bool(cobre[-1]),
                "br_erro_sobre_sd": float(abs(arr[:, -1].mean() - obs_pct[-1]) / sd[-1]),
                "ufs_cobertas": int(cobre[:-1].sum()),
                "ufs_total": len(ufs),
                "largura_media_ic_uf": float((hi_ - lo_)[:-1].mean()),
            }
        )
        uf_cob[nome] = pd.DataFrame(
            {"obs": obs_pct[:-1], "lo": lo_[:-1], "hi": hi_[:-1], "cobre": cobre[:-1]}, index=ufs
        )
    cdf = pd.DataFrame(cob).set_index("modelo")
    cdf.to_csv(SAIDA / "backtest_bootstrap_cobertura.csv")
    pd.concat(uf_cob, axis=1).to_csv(SAIDA / "backtest_bootstrap_cobertura_uf.csv")
    print("COBERTURA DO BOOTSTRAP:\n", cdf.round(3).to_string())
    print(
        "UFs não cobertas (regter_uf):", [u for u in ufs if not uf_cob["regter_uf"].loc[u, "cobre"]]
    )

    # IC das linhas compostas
    arr = np.stack([r["linhas"] for r in reps])  # [boot, 3, 4]
    lo_l, hi_l = ie.intervalo_percentil(arr)
    rows = []
    for k, c in enumerate(terc):
        d = (arr[:, k, 0] - arr[:, k, 1]) * 100
        row = {
            "categoria": c,
            "largura_PL_menos_PT_pp": np.percentile(d, 97.5) - np.percentile(d, 2.5),
        }
        for j, col in enumerate(ie.COLS_T2):
            row[f"{col}_pt"] = linhas[c][j]
            row[f"{col}_lo"] = lo_l[k, j]
            row[f"{col}_hi"] = hi_l[k, j]
            row[f"{col}_goodman2018"] = bnat_df.loc[c, col]
        rows.append(row)
    ldf = pd.DataFrame(rows).set_index("categoria")
    ldf.to_csv(SAIDA / "backtest_ic_linhas_compostas.csv")
    print("LINHAS COMPOSTAS (IC95% bootstrap):\n", ldf.round(3).T.to_string())


if __name__ == "__main__":
    sys.exit(main())
