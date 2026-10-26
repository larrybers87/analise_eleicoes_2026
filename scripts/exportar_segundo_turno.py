"""Gera `web/data/segundo_turno.json` (página "2º turno: resultado").

Lê o T2 apurado e o T1 oficial de `data/processed/` e as saídas de `scripts/virada_t2.py` em
`data/interim/virada/` (rode-o antes). Tudo por lista fechada de arquivos.

Uso: python scripts/exportar_segundo_turno.py
"""

from __future__ import annotations

import gzip
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from eleicao import config, segundo_turno_web  # noqa: E402

PROC = config.DATA_PROCESSED
VIRADA = config.RAIZ / "data" / "interim" / "virada"
SAIDA = config.RAIZ / "web" / "data" / "segundo_turno.json"


def main() -> int:
    arquivos = {
        "cand_br": PROC / "presidente_t2_br.parquet",
        "tot_br": PROC / "presidente_t2_br_totais.parquet",
        "cand_t1_br": PROC / "presidente_t1_br.parquet",
        "tot_t1_br": PROC / "presidente_t1_br_totais.parquet",
        "t2_uf_cand": PROC / "presidente_t2_uf.parquet",
        "virada_mun": VIRADA / "virada_municipal.parquet",
        "virada_uf": VIRADA / "virada_uf.csv",
        "virada_porte": VIRADA / "virada_porte.csv",
        "virada_mg": VIRADA / "virada_mg_mesorregiao.csv",
    }
    faltam = [str(a) for a in arquivos.values() if not a.exists()]
    if faltam:
        raise SystemExit("faltam arquivos (rode scripts/virada_t2.py):\n  " + "\n  ".join(faltam))
    dados = {
        k: pd.read_csv(a, dtype={"uf": str}) if a.suffix == ".csv" else pd.read_parquet(a)
        for k, a in arquivos.items()
    }
    out = segundo_turno_web.montar(**dados)
    out["fontes"] = [a.relative_to(config.RAIZ).as_posix() for a in arquivos.values()]
    texto = json.dumps(out, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    SAIDA.write_bytes(texto)
    kb, gz = len(texto) / 1024, len(gzip.compress(texto, 9)) / 1024
    print(f"{SAIDA.name}: {kb:.1f} KB bruto, {gz:.1f} KB gzip")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
