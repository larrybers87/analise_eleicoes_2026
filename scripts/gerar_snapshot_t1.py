"""Gera `data/processed/snapshot_t1_2026.json`: snapshot congelado do T1 2026 (Presidente).

Lê o JSON BR cru (cabeçalho: geração, `and`, `tf`, `md`) e o parquet
`presidente_t1_br*` (totais e votos por candidato). Pequeno e versionável;
é a referência de "qual versão do TSE" a projeção do 2º turno usa.

Uso: python scripts/gerar_snapshot_t1.py
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from eleicao import config  # noqa: E402


def main() -> int:
    caminho = config.caminho_local(
        config.caminho_resultado(config.ELEICAO_FEDERAL_T1, config.CARGO_PRESIDENTE, "br")
    )
    raw = json.loads(Path(caminho).read_text(encoding="utf-8"))
    cand = pd.read_parquet(config.DATA_PROCESSED / "presidente_t1_br.parquet")
    tot = pd.read_parquet(config.DATA_PROCESSED / "presidente_t1_br_totais.parquet").iloc[0]
    validos = int(tot["validos"])
    cand = cand.sort_values("votos", ascending=False)
    cand["pct_validos_calc"] = 100.0 * cand["votos"] / validos
    outros = cand[cand["pct_validos_calc"] < 1.0]
    snapshot = {
        "eleicao": config.ELEICAO_FEDERAL_T1,
        "cargo": "Presidente",
        "turno": 1,
        "tse": {
            "idg": raw["idg"],
            "dg": raw["dg"],
            "hg": raw["hg"],
            "dt_totalizacao": raw["dt"],
            "ht_totalizacao": raw["ht"],
            "and": raw["and"],
            "tf": raw["tf"],
            "md": raw.get("md"),
            "dv": raw.get("dv"),
        },
        "coleta_em": datetime.fromtimestamp(Path(caminho).stat().st_mtime).isoformat(
            timespec="seconds"
        ),
        "totais_br": {
            "eleitorado": int(tot["eleitorado"]),
            "comparecimento": int(tot["comparecimento"]),
            "abstencao": int(tot["abstencao"]),
            "validos": validos,
            "brancos": int(tot["brancos"]),
            "nulos_tvn": int(tot["nulos_tvn"]),
            "secoes_total": int(tot["secoes_total"]),
            "secoes_nao_instaladas": int(tot["extra_s_sni"]),
        },
        "candidatos": [
            {
                "nr": int(r.nr_candidato),
                "nm_urna": r.nm_urna,
                "partido": r.partido,
                "votos": int(r.votos),
                "pct_validos": round(float(r.pct_validos_calc), 6),
                "situacao": r.situacao,
            }
            for r in cand.itertuples()
        ],
        "outros_menos_1pct": {
            "candidatos": [int(n) for n in outros["nr_candidato"]],
            "votos": int(outros["votos"].sum()),
            "pct_validos": round(float(outros["pct_validos_calc"].sum()), 6),
        },
    }
    saida = config.DATA_PROCESSED / "snapshot_t1_2026.json"
    saida.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"escrito {saida}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
