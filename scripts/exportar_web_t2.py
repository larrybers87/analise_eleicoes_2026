"""Gera `web/data/resultados/t2.json` (modos "2º turno" e "Virada" do mapa principal).

Pré-requisitos: `scripts/virada_t2.py` (gera `data/interim/virada/virada_municipal.parquet`) e o
`web/data/meta.json` do mapa (`scripts/exportar_web.py`). Não toca em nenhum outro arquivo de
`web/data/`.

Uso: python scripts/exportar_web_t2.py
"""

from __future__ import annotations

import gzip
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from eleicao import config, t2_mapa_web  # noqa: E402

VIRADA = config.RAIZ / "data" / "interim" / "virada" / "virada_municipal.parquet"
META = config.RAIZ / "web" / "data" / "meta.json"
SAIDA = config.RAIZ / "web" / "data" / "resultados" / "t2.json"
PROC = config.DATA_PROCESSED


def main() -> int:
    for a in (VIRADA, META):
        if not a.exists():
            raise SystemExit(f"falta {a} (rode scripts/virada_t2.py e scripts/exportar_web.py)")
    meta = json.loads(META.read_text(encoding="utf-8"))
    cand = pd.read_parquet(PROC / "presidente_t2_br.parquet")
    tot = pd.read_parquet(PROC / "presidente_t2_br_totais.parquet").iloc[0]
    votos = cand.set_index(cand["nr_candidato"].astype(int))["votos"]
    oficial = {
        "pt": float(votos[t2_mapa_web.NR_PT]),
        "pl": float(votos[t2_mapa_web.NR_PL]),
        "aptos": float(tot["eleitorado"]),
    }
    dados = t2_mapa_web.montar(
        pd.read_parquet(VIRADA),
        meta["forca_offsets"],
        meta["n_municipios_br"],
        meta["cor_sem_votos"],
        oficial,
    )
    texto = json.dumps(dados, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    SAIDA.write_bytes(texto)
    kb, gz = len(texto) / 1024, len(gzip.compress(texto, 9)) / 1024
    print(f"{SAIDA.name}: {kb:.1f} KB bruto, {gz:.1f} KB gzip")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
