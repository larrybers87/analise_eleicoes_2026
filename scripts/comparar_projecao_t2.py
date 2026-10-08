"""Compara a projeção do 2º turno 2026 com o resultado real (eleição 6258) e estima a B real.

PRONTO, MAS NÃO EXECUTAR ANTES DE 25/10/2026 (a eleição 6258 ainda não aconteceu).
NÃO baixa nada e não adivinha URLs: consome o parquet do T2 que o coletor-tse vai gerar,
com o mesmo schema do T1 2026 (`presidente_t1_municipio{,_totais}.parquet`):

    data/processed/presidente_t2_municipio.parquet          (candidatos; nr_candidato, votos, ...)
    data/processed/presidente_t2_municipio_totais.parquet   (eleitorado, comparecimento, ...)

Os caminhos podem ser trocados por --t2-dir / --prefixo. Entradas da projeção:
data/processed/projecao_t2_2026_{municipio,uf,br}.parquet e config/projecao_t2.yaml.

Saídas (data/interim/projecao_t2/comparacao_*): erros por cenário e recorte, erros por UF com
cobertura da faixa heurística, e a matriz real T1->T2 (Goodman restrito nacional, com IC
bootstrap estratificado por UF) ao lado das linhas projetadas no cenário base.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from eleicao import inferencia_ecologica as ie
from eleicao import projecao_t2 as pj

RAIZ = Path(__file__).resolve().parents[1]


def carregar_t2(t2_dir: Path, prefixo: str) -> pd.DataFrame:
    """Contagens observadas do T2 2026 (PL=22, PT=13, BN, ABST), uma linha por município."""
    cand_p = t2_dir / f"{prefixo}_municipio.parquet"
    tot_p = t2_dir / f"{prefixo}_municipio_totais.parquet"
    faltam = [p for p in (cand_p, tot_p) if not p.exists()]
    if faltam:
        sys.exit(
            "Faltam os parquet do T2 2026 (o coletor-tse ainda não os gerou?):\n  "
            + "\n  ".join(str(p) for p in faltam)
            + "\nEste script não baixa nada."
        )
    cand, tot = pd.read_parquet(cand_p), pd.read_parquet(tot_p)
    estado = tot["status_totalizacao"].value_counts().to_dict()
    tf = tot["tf_judicial"].value_counts().to_dict()
    print(f"T2 2026: totalização {estado}; tf {tf}")
    if set(tot["status_totalizacao"]) != {"f"} or set(tot["tf_judicial"]) != {"s"}:
        print("AVISO: T2 ainda não é final (and!=f ou tf!=s); a comparação é provisória.")
    extras = sorted(set(cand["nr_candidato"].astype(int)) - {13, 22})
    if extras:
        sys.exit(f"T2 com candidatos além de 13 e 22: {extras}")
    obs = ie.contagens_t2(cand, tot, pl=22, pt=13)
    return obs.sort_values(ie.CHAVE).reset_index(drop=True)


def comparar(
    proj_mun: pd.DataFrame, obs: pd.DataFrame, faixas: dict, saida: Path
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Métricas por cenário e recorte; erros por UF com cobertura da faixa heurística."""
    linhas, ufs = [], []
    for cen, p in proj_mun.groupby("cenario"):
        par, sem_par = ie.parear_chaves(p[ie.CHAVE], obs[ie.CHAVE], "projecao", "t2_real")
        if not sem_par.empty:
            print(f"[{cen}] chaves sem par entre projeção e T2 real: {len(sem_par)}")
            sem_par.to_csv(saida / f"comparacao_sem_par_{cen}.csv", index=False)
        pp = p.merge(par, on=ie.CHAVE)[[*ie.CHAVE, *ie.COLS_T2]]
        oo = obs.merge(par, on=ie.CHAVE)
        for rec, mask in (
            ("brasil_sem_zz", pp["uf"] != "zz"),
            ("zz_exterior", pp["uf"] == "zz"),
            ("total_oficial_com_zz", pp["uf"].notna()),
        ):
            m = ie.metricas(pp[mask].reset_index(drop=True), oo[mask].reset_index(drop=True))
            faixa = faixas["br"] if rec != "zz_exterior" else faixas["mz"]
            linhas.append(
                {
                    "cenario": cen,
                    "recorte": rec,
                    "erro_pct_pl_validos_pp": m["erro_br_pp"],
                    "dentro_da_faixa": abs(m["erro_br_pp"]) <= faixa,
                    "faixa_pp": faixa,
                    "mae_municipal_pp": m["mae_municipal_pp"],
                    "acerto_vencedor_uf": m["acerto_vencedor_uf"],
                    "erro_abstencao_pp": m["erro_abst_pp"],
                    "abst_dentro_da_faixa": abs(m["erro_abst_pp"]) <= faixas["abst"],
                }
            )
            if rec == "brasil_sem_zz":
                u = m["por_uf"].reset_index().assign(cenario=cen)
                u["dentro_da_faixa"] = u["erro_pp"].abs() <= faixas["uf"]
                ufs.append(u)
    return pd.DataFrame(linhas), pd.concat(ufs, ignore_index=True)


def matriz_real(cfg: dict, ins: dict, obs: pd.DataFrame, n_boot: int, semente: int) -> pd.DataFrame:
    """B real 2026 T1->T2 (Goodman restrito nacional, Brasil sem exterior) com IC bootstrap,
    ao lado das linhas projetadas no cenário base. A B real é inferência ecológica."""
    g26 = ie.grupos_t1_2026(cfg, "base")
    c1 = pj.contagens_2026(ins, g26)
    ids = [*g26, pj.CAT_BN, pj.CAT_ABST]
    m = (c1["uf"] != "zz").to_numpy()
    c1 = c1[m].reset_index(drop=True)
    o = obs[obs["uf"] != "zz"].reset_index(drop=True)
    par, sem = ie.parear_chaves(c1[ie.CHAVE], o[ie.CHAVE], "t1", "t2")
    if not sem.empty:
        print(f"matriz real: {len(sem)} chaves sem par entre T1 e T2 (fora do ajuste)")
    c1 = c1.merge(par, on=ie.CHAVE)
    o = o.merge(par, on=ie.CHAVE)
    x, w = ie.parcelas(c1, ids)
    y, _ = ie.parcelas(o, ie.COLS_T2)
    uf = c1["uf"].to_numpy()
    b = ie.goodman_restrito(x, y, w)
    boot = ie.bootstrap_uf(uf, lambda i: ie.goodman_restrito(x[i], y[i], w[i]), n_boot, semente)
    lo, hi = ie.intervalo_percentil(boot)

    d_br, _ = pj.montar_dados(ins, cfg, "br")
    d_zz, _ = pj.montar_dados(ins, cfg, "zz")
    mat_proj, _ = pj.matrizes_cenario(cfg, "base", pj.estimar(d_br), pj.estimar(d_zz))
    linhas = []
    for k, cid in enumerate(ids):
        for j, col in enumerate(ie.COLS_T2):
            linhas.append(
                {
                    "categoria": cid,
                    "destino": col,
                    "b_real": b[k, j],
                    "b_real_lo": lo[k, j],
                    "b_real_hi": hi[k, j],
                    "b_projetada_base": float(mat_proj.loc[cid, col])
                    if cid in mat_proj.index
                    else np.nan,
                }
            )
    df = pd.DataFrame(linhas)
    df["diferenca_pp"] = 100 * (df["b_projetada_base"] - df["b_real"])
    return df


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--t2-dir", type=Path, default=RAIZ / "data" / "processed")
    ap.add_argument("--prefixo", default="presidente_t2")
    ap.add_argument("--proj-dir", type=Path, default=RAIZ / "data" / "processed")
    ap.add_argument("--saida", type=Path, default=RAIZ / "data" / "interim" / "projecao_t2")
    ap.add_argument("--n-boot", type=int, default=1000)
    ap.add_argument("--semente", type=int, default=0)
    a = ap.parse_args()

    obs = carregar_t2(a.t2_dir, a.prefixo)
    proj = pd.read_parquet(a.proj_dir / "projecao_t2_2026_municipio.parquet")
    cfg = pj.carregar_config_projecao(RAIZ / "config" / "projecao_t2.yaml")
    fh = cfg["faixa_heuristica"]
    faixas = {
        "br": fh["pct_pl_validos_br_pp"],
        "uf": fh["pct_pl_validos_uf_pp"],
        "mz": fh["municipio_e_zz_pp"],
        "abst": fh["abstencao_aptos_pp"],
    }
    a.saida.mkdir(parents=True, exist_ok=True)
    por_cen, por_uf = comparar(proj, obs, faixas, a.saida)
    por_cen.to_csv(a.saida / "comparacao_cenarios.csv", index=False)
    por_uf.to_csv(a.saida / "comparacao_erros_uf.csv", index=False)
    pd.set_option("display.width", 220)
    print("Erros por cenário e recorte (pred - obs; faixa heurística n=1):")
    print(por_cen.round(3).to_string(index=False))
    cob = por_uf.groupby("cenario")["dentro_da_faixa"].agg(["sum", "count"])
    print("UFs dentro da faixa heurística por cenário:\n", cob.to_string())

    ins = pj.carregar_insumos(a.proj_dir)
    real = matriz_real(cfg, ins, obs, a.n_boot, a.semente)
    real.to_csv(a.saida / "comparacao_matriz_real.csv", index=False)
    print("Matriz real T1->T2 2026 (ecológica) contra a projetada no cenário base:")
    print(real.round(3).to_string(index=False))


if __name__ == "__main__":
    main()
