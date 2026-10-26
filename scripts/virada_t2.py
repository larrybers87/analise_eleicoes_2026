"""Swing T1→T2 2026 por município, UF, porte e (Minas) mesorregião.

Saídas em `data/interim/virada/`.

Uso: python scripts/virada_t2.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

from eleicao.analise import carga, virada  # noqa: E402


def main() -> None:
    t1 = virada.base_turno(carga.candidatos_2026(), carga.totais_2026())
    t2 = virada.base_turno(carga.candidatos_t2_2026(), carga.totais_t2_2026())
    d = virada.virada_municipal(t1, t2)
    saida = RAIZ / "data" / "interim" / "virada"
    saida.mkdir(parents=True, exist_ok=True)
    d.to_parquet(saida / "virada_municipal.parquet", index=False)

    pd.set_option("display.width", 220)
    print(
        f"{len(d)} municípios; virou PT {int(d['virou_pt'].sum())}, "
        f"virou PL {int(d['virou_pl'].sum())}; PT à frente: T1 {(d['margem_t1'] > 0).sum()}, "
        f"T2 {(d['margem_t2'] > 0).sum()}"
    )
    print("swing municipal (p.p.):", d["swing"].describe().round(2).to_dict())

    por_uf = virada.resumo_grupo(d, "uf")
    por_uf.to_csv(saida / "virada_uf.csv", index=False)
    d["porte"] = virada.faixa_porte(d["eleitorado_t1"])
    por_porte = virada.resumo_grupo(d, "porte")
    por_porte["ordem"] = por_porte["porte"].map(
        {r: i for i, (r, _, _) in enumerate(virada.FAIXAS_PORTE)}
    )
    por_porte = por_porte.sort_values("ordem").drop(columns="ordem")
    por_porte.to_csv(saida / "virada_porte.csv", index=False)
    print("\nPor porte do município:")
    print(por_porte.round(2).to_string(index=False))

    mg = d[d["uf"] == "mg"].copy()
    mp = carga.mesorregiao_por_municipio("MG")
    mg["mesorregiao"] = mg["cd_mun_ibge_t1"].astype(int).map(mp)
    assert mg["mesorregiao"].notna().all()
    mgm = virada.resumo_grupo(mg, "mesorregiao").sort_values("swing")
    mgm["parte_ganho_pct"] = 100 * mgm["ganho_margem_votos"] / mgm["ganho_margem_votos"].sum()
    mgm["parte_eleitorado_pct"] = 100 * mgm["eleitorado"] / mgm["eleitorado"].sum()
    mgm.to_csv(saida / "virada_mg_mesorregiao.csv", index=False)
    print("\nMinas por mesorregião:")
    print(mgm.round(1).to_string(index=False))
    m1 = 100 * (mg["pt_t1"].sum() - mg["pl_t1"].sum()) / (mg["pt_t1"].sum() + mg["pl_t1"].sum())
    m2 = 100 * (mg["pt_t2"].sum() - mg["pl_t2"].sum()) / (mg["pt_t2"].sum() + mg["pl_t2"].sum())
    ganho = mg["dmargem_votos"].sum()
    print(f"\nMG total: margem T1 {m1:.2f}, T2 {m2:.2f}, ganho de margem {ganho:.0f} votos")


if __name__ == "__main__":
    main()
