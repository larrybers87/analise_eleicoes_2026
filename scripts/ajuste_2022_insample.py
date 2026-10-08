"""Ajuste in-sample 2022 (T1 2022 -> T2 2022): B nacional (IC bootstrap), λ por UF e resíduos.

Usa só data/processed/presidente_2022_*. ZZ fica fora do ajuste do Brasil (recorte à parte).
Saídas em data/interim/projecao_t2/ (não versionado). Não projeta 2026.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from eleicao import inferencia_ecologica as ie

RAIZ = Path(__file__).resolve().parents[1]
SAIDA = RAIZ / "data" / "interim" / "projecao_t2"
GRUPOS = {
    "lula_13": [13],
    "bolsonaro_22": [22],
    "tebet_15": [15],
    "ciro_12": [12],
    "outros_2022": [44, 30, 14, 80, 21, 16, 27],
}
CATS = [*GRUPOS, "bn", "abst"]
GRADE = [0.0, 0.01, 0.1, 1.0, 10.0, 100.0, 1000.0, np.inf]
N_BOOT = 1000


def main() -> None:
    SAIDA.mkdir(parents=True, exist_ok=True)
    c1, t1 = ie.carregar_2022(RAIZ / "data" / "processed", 1)
    c2, t2 = ie.carregar_2022(RAIZ / "data" / "processed", 2)
    x1 = ie.montar_contagens(c1, t1, GRUPOS)
    y2 = ie.contagens_t2(c2, t2, pl=22, pt=13)
    par, sem = ie.parear_chaves(x1, y2, "t1", "t2")
    assert sem.empty, sem
    x1 = x1.merge(par, on=ie.CHAVE).sort_values(ie.CHAVE).reset_index(drop=True)
    y2 = y2.merge(par, on=ie.CHAVE).sort_values(ie.CHAVE).reset_index(drop=True)

    br = x1["uf"] != "zz"
    xb, wb = ie.parcelas(x1[br], CATS)
    yb, _ = ie.parcelas(y2[br], ie.COLS_T2)
    ufb = x1.loc[br, "uf"].to_numpy()
    print(f"municípios Brasil: {br.sum()}, ZZ: {(~br).sum()}")

    # nacional + bootstrap estratificado por UF
    b_nac = ie.goodman_restrito(xb, yb, wb)
    boot = ie.bootstrap_uf(ufb, lambda i: ie.goodman_restrito(xb[i], yb[i], wb[i]), N_BOOT, 1)
    lo, hi = ie.intervalo_percentil(boot)
    nac = pd.DataFrame(b_nac, index=CATS, columns=ie.COLS_T2)
    nac.to_csv(SAIDA / "B_nacional_2022.csv")
    ic = pd.DataFrame(
        {
            f"{c}_{k}": v[:, j]
            for j, c in enumerate(ie.COLS_T2)
            for k, v in (("lo", lo), ("hi", hi))
        },
        index=CATS,
    )
    ic.to_csv(SAIDA / "B_nacional_2022_ic95.csv")
    d = (boot[:, :, 0] - boot[:, :, 1]) * 100
    larg = pd.Series(np.percentile(d, 97.5, axis=0) - np.percentile(d, 2.5, axis=0), index=CATS)
    print("B nacional 2022 (linhas = T1, colunas = T2):\n", nac.round(3))
    print("IC95% bootstrap:\n", ic.round(3))
    print("Largura IC95% de PL-PT por linha (p.p.):\n", larg.round(1))
    larg.to_csv(SAIDA / "largura_ic_pl_pt_2022.csv", header=["largura_pp"])

    # λ
    lam, tab = ie.selecionar_lambda(xb, yb, wb, ufb, GRADE, n_folds=5, semente=0)
    tab.to_csv(SAIDA / "cv_lambda_2022.csv", index=False)
    print("CV λ:\n", tab, "\nλ escolhido:", lam)

    alvos = ie.alvos_leave_one_uf_out(xb, yb, wb, ufb)
    b_uf = ie.goodman_por_uf(xb, yb, wb, ufb, lam, alvos)
    rows = [pd.DataFrame(b, index=CATS, columns=ie.COLS_T2).assign(uf=u) for u, b in b_uf.items()]
    pd.concat(rows).to_csv(SAIDA / "B_por_uf_2022.csv")

    # resíduos: reconstrução do T2 2022 (in-sample)
    def prever(mats: dict[str, np.ndarray]) -> pd.DataFrame:
        v = np.vstack(
            [x1.loc[br].iloc[i][CATS].to_numpy(float) @ mats[ufb[i]] for i in range(br.sum())]
        )
        return pd.concat(
            [x1.loc[br, ie.CHAVE].reset_index(drop=True), pd.DataFrame(v, columns=ie.COLS_T2)],
            axis=1,
        )

    obs = y2.loc[br].reset_index(drop=True)
    p_nac = prever({u: b_nac for u in b_uf})
    p_uf = prever(b_uf)
    ie.checar_somas(p_uf, x1.loc[br, CATS].sum(axis=1))
    r_nac = ie.residuo_por_uf(p_nac, obs)
    r_uf = ie.residuo_por_uf(p_uf, obs)
    m_nac, m_uf = ie.metricas(p_nac, obs), ie.metricas(p_uf, obs)
    tabela = pd.DataFrame(
        {
            "aptos": r_uf["aptos"],
            "res_PL_pp_nac": r_nac["res_PL_pp"],
            "res_PL_pp_uf": r_uf["res_PL_pp"],
            "res_PT_pp_uf": r_uf["res_PT_pp"],
            "res_BN_pp_uf": r_uf["res_BN_pp"],
            "res_ABST_pp_uf": r_uf["res_ABST_pp"],
            "erro_pct_PL_validos_pp_nac": m_nac["por_uf"]["erro_pp"],
            "erro_pct_PL_validos_pp_uf": m_uf["por_uf"]["erro_pp"],
        }
    )
    tabela.to_csv(SAIDA / "residuos_por_uf_2022.csv")
    print("Resíduos por UF (obs - pred, p.p. dos aptos da UF; erro do % PL entre válidos):")
    print(tabela.round(2).to_string())
    for nome, m in (("nacional", m_nac), ("por UF", m_uf)):
        print(
            f"{nome}: erro BR {m['erro_br_pp']:+.3f} p.p.; "
            f"MAE municipal {m['mae_municipal_pp']:.3f} p.p.; "
            f"vencedor UF {m['acerto_vencedor_uf']:.2f}; erro abst {m['erro_abst_pp']:+.3f} p.p."
        )

    # ZZ: critério proposto de matriz própria (apenas diagnóstico)
    z = ~br
    xz, wz = ie.parcelas(x1[z], CATS)
    yz, _ = ie.parcelas(y2[z], ie.COLS_T2)
    usar, diag = ie.usar_matriz_propria(xz, yz, wz, b_nac)
    print("ZZ matriz própria?", usar, diag)
    pz = ie.projetar(
        x1[z].reset_index(drop=True), pd.DataFrame(b_nac, index=CATS, columns=ie.COLS_T2)
    )
    mz = ie.metricas(pz, y2[z].reset_index(drop=True))
    print(f"ZZ com B nacional: erro % PL entre válidos {mz['erro_br_pp']:+.2f} p.p.")


if __name__ == "__main__":
    main()
