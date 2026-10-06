"""Gera `web/data/analises.json` e `web/data/analises_dispersao.json` (F3 fase B, D-030).

Todos os números da página `web/analises.html` saem daqui, de funções testadas em
`src/eleicao/analise/` (montagem em `eleicao.analise.site`). Quando o TSE finalizar a
totalização ou vier o 2º turno: reprocessar os Parquet, rodar este script e
`pytest tests/test_exportar_analises.py` (que confere os números contra docs/ANALISES.md).

Uso:
    python scripts/exportar_analises.py
"""

from __future__ import annotations

import gzip
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from eleicao import config  # noqa: E402
from eleicao.analise import site  # noqa: E402

WEB_DATA = config.RAIZ / "web" / "data"


def escrever(caminho: Path, obj: object) -> tuple[int, int]:
    texto = json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    caminho.write_bytes(texto)
    return len(texto), len(gzip.compress(texto, 9))


def main() -> int:
    t0 = time.time()
    analises, dispersao = site.montar()
    for nome, obj in (("analises.json", analises), ("analises_dispersao.json", dispersao)):
        bruto, gz = escrever(WEB_DATA / nome, obj)
        print(f"  {nome:26s} {bruto / 1024:7.1f} KB bruto  {gz / 1024:6.1f} KB gzip")
    print(
        f"  {len(analises['valores'])} números, snapshot {analises['snapshot']['dg']} "
        f"(provisório: {analises['snapshot']['provisorio']}) em {time.time() - t0:.0f}s"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
