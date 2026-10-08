"""Projeção do 2º turno 2026 a partir do T1 final (snapshot_t1_2026.json).

Uso: python scripts/projetar_t2_2026.py [--n-boot 1000] [--saida data/processed]
Não baixa nada: lê só data/processed/ e config/projecao_t2.yaml.
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

from eleicao import projecao_t2 as pj

RAIZ = Path(__file__).resolve().parents[1]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-boot", type=int, default=1000)
    ap.add_argument("--semente", type=int, default=0)
    ap.add_argument("--saida", type=Path, default=RAIZ / "data" / "processed")
    a = ap.parse_args()
    t0 = time.time()
    saidas = pj.executar(
        RAIZ / "data" / "processed", RAIZ / "config" / "projecao_t2.yaml", a.n_boot, a.semente
    )
    a.saida.mkdir(parents=True, exist_ok=True)
    for p in pj.salvar_saidas(saidas, a.saida):
        print("gravado:", p)
    interim = RAIZ / "data" / "interim" / "projecao_t2"
    interim.mkdir(parents=True, exist_ok=True)
    saidas["parametros_r"].to_csv(interim / "projecao_parametros_r.csv", index=False)
    print("r (abstenção dos votantes, B 2022 in-sample):")
    print(saidas["parametros_r"].to_string(index=False))
    print(f"{time.time() - t0:.0f}s, n_boot={a.n_boot}")


if __name__ == "__main__":
    main()
