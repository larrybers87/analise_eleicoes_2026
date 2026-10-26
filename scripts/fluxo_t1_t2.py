"""Fluxo T1 -> T2 2026 blindado: B com ICs por três bootstraps, limites de Duncan-Davis e checagens.

Lê só `data/processed/` (T1 e T2 2026). Brasil sem exterior (como a B real de
`comparar_projecao_t2.py`). Saídas em `data/interim/fluxo_t1_t2/`.

Uso: python scripts/fluxo_t1_t2.py [--n-boot 1000] [--semente 0]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))
sys.path.insert(0, str(RAIZ / "scripts"))

from comparar_projecao_t2 import carregar_t2  # noqa: E402

from eleicao import inferencia_ecologica as ie  # noqa: E402
from eleicao import projecao_t2 as pj  # noqa: E402
from eleicao.analise import fluxo  # noqa: E402


def montar(proc: Path):
    """(origens, municípios, x, y, w) via `fluxo.montar_t1_t2` (mesma lógica do notebook 18)."""
    cfg = pj.carregar_config_projecao(RAIZ / "config" / "projecao_t2.yaml")
    ins = pj.carregar_insumos(proc)
    c_t1, t_t1 = ins["t1_2026"]
    obs = carregar_t2(proc, "presidente_t2")  # confere o status final do T2 e candidatos extras
    del obs
    return fluxo.montar_t1_t2(
        c_t1,
        t_t1,
        pd.read_parquet(proc / "presidente_t2_municipio.parquet"),
        pd.read_parquet(proc / "presidente_t2_municipio_totais.parquet"),
        ie.grupos_t1_2026(cfg, "base"),
        pj.CAT_BN,
        pj.CAT_ABST,
    )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--n-boot", type=int, default=1000)
    ap.add_argument("--semente", type=int, default=0)
    a = ap.parse_args()
    proc = RAIZ / "data" / "processed"
    saida = RAIZ / "data" / "interim" / "fluxo_t1_t2"
    saida.mkdir(parents=True, exist_ok=True)
    pd.set_option("display.width", 220)

    origens, c1, x, y, w = montar(proc)
    cfg = pj.carregar_config_projecao(RAIZ / "config" / "projecao_t2.yaml")
    ins = pj.carregar_insumos(proc)
    uf = c1["uf"].to_numpy()
    print(f"{len(w)} municípios, {w.sum():,.0f} aptos; origens: {origens}")

    b = fluxo.estimar_b(x, y, w)
    dd = fluxo.limites_duncan_davis(x, y, w)
    boot_mun = fluxo.bootstrap(
        lambda r: fluxo.indices_municipio(len(w), r), x, y, w, a.n_boot, a.semente
    )
    boot_mun_uf = ie.bootstrap_uf(
        uf, lambda i: fluxo.estimar_b(x[i], y[i], w[i]), a.n_boot, a.semente
    )
    boot_uf = fluxo.bootstrap(
        lambda r: fluxo.indices_cluster_uf(uf, r), x, y, w, a.n_boot, a.semente
    )
    ics = {
        "mun": ie.intervalo_percentil(boot_mun),
        "mun_em_uf": ie.intervalo_percentil(boot_mun_uf),
        "uf": ie.intervalo_percentil(boot_uf),
    }
    tab = fluxo.tabela_fluxo(origens, b, ics, dd)
    tab.to_csv(saida / "fluxo_b.csv", index=False)
    print("\nB (origem -> destino), IC95% por município / município-em-UF / UF-cluster e DD:")
    print(tab.round(3).to_string(index=False))

    print("\nCondicionamento das parcelas de origem:", fluxo.condicionamento(x, w))
    print(
        "Limites determinísticos: largura média do intervalo DD por origem (p.p.):",
        dict(zip(origens, (100 * (dd[1] - dd[0]).mean(axis=1)).round(1), strict=True)),
    )

    aptos_t1 = c1[origens].sum(axis=1).to_numpy()
    gm = fluxo.ganhos_minimos_pt(x, y, aptos_t1, col_lula=origens.index("lula"))
    pt_t2 = (y[:, 1] * w).sum()
    lula_t1 = (x[:, origens.index("lula")] * w).sum()
    print(f"\nPT T2 {pt_t2:,.0f} vs Lula T1 {lula_t1:,.0f} (diferença {pt_t2 - lula_t1:,.0f})")
    print(f"ganhos mínimos de fora do eleitorado de Lula: {gm}")
    gm.update(pt_t2=float(pt_t2), lula_t1=float(lula_t1))
    (saida / "ganhos_minimos.json").write_text(json.dumps(gm, indent=1), encoding="utf-8")

    # Robustez: terceiros agregados (se a separação for artefato, a soma ponderada bate)
    idx3 = [origens.index(k) for k in ("cury", "renan", "caiado", "outros_2026")]
    x3 = np.column_stack([np.delete(x, idx3, axis=1), x[:, idx3].sum(axis=1)])
    b3 = fluxo.estimar_b(x3, y, w)
    peso3 = (x[:, idx3] * w[:, None]).sum(axis=0)
    media_sep = (peso3[:, None] * b[idx3]).sum(axis=0) / peso3.sum()
    print("\nTerceiros agregados (estimado) :", b3[-1].round(3))
    print("Terceiros: média ponderada dos 4 separados:", media_sep.round(3))

    # Resumo do eleitorado que mudou de lado, em votos
    fluxo_votos = pd.DataFrame(
        (x * w[:, None]).sum(axis=0)[:, None] * b, index=origens, columns=ie.COLS_T2
    )
    fluxo_votos.to_csv(saida / "fluxo_votos.csv")

    # Decomposição do erro da projeção base: por origem, votos a mais do PL sobre o PT
    d_br, _ = pj.montar_dados(ins, cfg, "br")
    d_zz, _ = pj.montar_dados(ins, cfg, "zz")
    mat, _ = pj.matrizes_cenario(cfg, "base", pj.estimar(d_br), pj.estimar(d_zz))
    bp = mat.loc[origens, ie.COLS_T2].to_numpy()
    v_orig = (x * w[:, None]).sum(axis=0)
    dif = np.array([1.0, -1.0, 0.0, 0.0])  # PL - PT
    contrib = v_orig * ((bp - b) @ dif)
    contrib_boot = v_orig[None] * ((bp[None] - boot_uf) @ dif)
    lo_c, hi_c = ie.intervalo_percentil(contrib_boot)
    dec = pd.DataFrame(
        {
            "origem": origens,
            "votos_origem": v_orig,
            "bp_menos_bpt_proj": bp @ dif,
            "bp_menos_bpt_real": b @ dif,
            "excesso_pl_menos_pt": contrib,
            "ic_uf_lo": lo_c,
            "ic_uf_hi": hi_c,
        }
    )
    dec.to_csv(saida / "decomposicao_erro.csv", index=False)
    print("\nDecomposição do erro da base (votos a mais de PL menos PT; milhões):")
    print(
        dec.assign(**{c: dec[c] / 1e6 for c in ("excesso_pl_menos_pt", "ic_uf_lo", "ic_uf_hi")})
        .round(3)
        .to_string(index=False)
    )
    print("soma:", contrib.sum() / 1e6)
    print("\nFluxo em votos (milhões):")
    print((fluxo_votos / 1e6).round(2).to_string())


if __name__ == "__main__":
    main()
