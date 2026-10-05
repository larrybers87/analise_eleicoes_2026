"""Confere, campo a campo, que `web/data/` reflete exatamente `data/processed/`.

Compara os JSON exportados por `scripts/exportar_web.py` contra os Parquet de
origem para BR, uma amostra de UFs e uma amostra de municípios (configurável),
incluindo os municípios da divergência conhecida de BA (`data/known_issues.csv`)
— o painel precisa mostrar fielmente o que está no Parquet mesmo nesse
caso-limite, sem "consertar" nada.

Confere:
  - todos os campos de `presidente_t1_*_totais.parquet` que o export publica;
  - votos por candidato (depois de aplicar o mesmo `agrupar_outros` do export);
  - soma dos votos do JSON == `validos` do Parquet;
  - cores dos 2 modos == recálculo direto por `src/eleicao/cores.py`;
  - margem em p.p. == recálculo a partir dos votos do Parquet;
  - contagem de municípios por UF e do índice nacional.

Uso:
    python scripts/verificar_export_web.py
    python scripts/verificar_export_web.py --municipios ba:33693 mg:41556 pr:75353
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from eleicao import config  # noqa: E402
from eleicao.cores import (  # noqa: E402
    agrupar_outros,
    carregar_paleta,
    mistura_oklab,
    vencedor_margem,
)

WEB_DATA = config.RAIZ / "web" / "data"

CAMPOS = [
    "eleitorado",
    "comparecimento",
    "abstencao",
    "validos",
    "brancos",
    "nulos_vn",
    "nulos_tvn",
    "secoes_totalizadas",
    "secoes_total",
    "status_totalizacao",
    "tf_judicial",
    "matematicamente_definido",
    "data_hora_totalizacao",
]

PADRAO_MUNICIPIOS = ["ba:33693", "mg:41556", "sp:71072"]
PADRAO_UFS = ["ba", "sp"]


class Falhas:
    def __init__(self) -> None:
        self.itens: list[str] = []
        self.ok = 0

    def checar(self, cond: bool, desc: str, esperado: Any = None, obtido: Any = None) -> None:
        if cond:
            self.ok += 1
        else:
            self.itens.append(f"{desc}: parquet={esperado!r} json={obtido!r}")


def conferir(f: Falhas, rotulo: str, reg: dict, linha: pd.Series, votos: dict[int, int], paleta):
    for campo in CAMPOS:
        esperado = linha[campo]
        esperado = None if pd.isna(esperado) else esperado
        if hasattr(esperado, "item"):
            esperado = esperado.item()
        f.checar(
            reg["totais"].get(campo) == esperado,
            f"{rotulo}.{campo}",
            esperado,
            reg["totais"].get(campo),
        )

    for campo in ("anulados", "anulados_sub_judice"):
        esperado = int(linha[campo])
        obtido = reg["totais"].get(campo, 0)
        f.checar(obtido == esperado, f"{rotulo}.{campo}", esperado, obtido)

    # votos por candidato, com o mesmo agrupamento "Outros" do export
    esperado_votos = {
        ("outros" if k == "outros" else int(k)): int(v) for k, v in agrupar_outros(votos).items()
    }
    obtido_votos = {(v[0] if v[0] == "outros" else int(v[0])): int(v[1]) for v in reg["votos"]}
    f.checar(obtido_votos == esperado_votos, f"{rotulo}.votos", esperado_votos, obtido_votos)
    f.checar(
        sum(obtido_votos.values()) == int(linha["validos"]),
        f"{rotulo}.soma_votos==validos",
        int(linha["validos"]),
        sum(obtido_votos.values()),
    )

    # cores e margem, recalculadas direto de src/eleicao/cores.py
    f.checar(
        reg["cor_mistura"] == mistura_oklab(votos, paleta),
        f"{rotulo}.cor_mistura",
        mistura_oklab(votos, paleta),
        reg["cor_mistura"],
    )
    f.checar(
        reg["cor_margem"] == vencedor_margem(votos, paleta),
        f"{rotulo}.cor_margem",
        vencedor_margem(votos, paleta),
        reg["cor_margem"],
    )
    ordenado = sorted(votos.items(), key=lambda it: it[1], reverse=True)
    total = sum(votos.values())
    margem = round((ordenado[0][1] - ordenado[1][1]) / total * 100, 3)
    f.checar(
        reg["vencedor"] == int(ordenado[0][0]),
        f"{rotulo}.vencedor",
        ordenado[0][0],
        reg["vencedor"],
    )
    f.checar(reg["margem_pp"] == margem, f"{rotulo}.margem_pp", margem, reg["margem_pp"])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--municipios", nargs="*", default=PADRAO_MUNICIPIOS, help="uf:cd_mun_tse")
    ap.add_argument("--ufs", nargs="*", default=PADRAO_UFS)
    args = ap.parse_args()

    proc = config.DATA_PROCESSED
    paleta = carregar_paleta()
    br_tot = pd.read_parquet(proc / "presidente_t1_br_totais.parquet").iloc[0]
    br_cand = pd.read_parquet(proc / "presidente_t1_br.parquet")
    uf_tot = pd.read_parquet(proc / "presidente_t1_uf_totais.parquet").set_index("uf")
    uf_cand = pd.read_parquet(proc / "presidente_t1_uf.parquet")
    mun_tot = pd.read_parquet(proc / "presidente_t1_municipio_totais.parquet")
    mun_cand = pd.read_parquet(proc / "presidente_t1_municipio.parquet")

    f = Falhas()
    br_json = json.loads((WEB_DATA / "resultados" / "br.json").read_text(encoding="utf-8"))

    print("BR")
    votos_br = dict(
        zip(br_cand["nr_candidato"].astype(int), br_cand["votos"].astype(int), strict=True)
    )
    conferir(f, "br", br_json["br"], br_tot, votos_br, paleta)

    for sigla in args.ufs:
        print(f"UF {sigla}")
        obj = json.loads((WEB_DATA / "resultados" / "uf" / f"uf_{sigla}.json").read_text("utf-8"))
        sub = uf_cand[uf_cand["uf"] == sigla]
        votos = dict(zip(sub["nr_candidato"].astype(int), sub["votos"].astype(int), strict=True))
        conferir(f, f"uf:{sigla}", obj["uf"], uf_tot.loc[sigla], votos, paleta)
        esperado_n = int((mun_tot["uf"] == sigla).sum())
        f.checar(
            len(obj["municipios"]) == esperado_n,
            f"uf:{sigla}.n_municipios",
            esperado_n,
            len(obj["municipios"]),
        )

    for item in args.municipios:
        sigla, cd = item.split(":")
        print(f"município {sigla}:{cd}")
        obj = json.loads((WEB_DATA / "resultados" / "uf" / f"uf_{sigla}.json").read_text("utf-8"))
        reg = next((m for m in obj["municipios"] if m["cd_mun_tse"] == cd), None)
        if reg is None:
            f.itens.append(f"mun:{sigla}:{cd} ausente de uf_{sigla}.json")
            continue
        linha = mun_tot[(mun_tot["uf"] == sigla) & (mun_tot["cd_mun_tse"] == cd)].iloc[0]
        sub = mun_cand[(mun_cand["uf"] == sigla) & (mun_cand["cd_mun_tse"] == cd)]
        votos = dict(zip(sub["nr_candidato"].astype(int), sub["votos"].astype(int), strict=True))
        conferir(f, f"mun:{sigla}:{cd}", reg, linha, votos, paleta)
        f.checar(
            reg["nome"] == linha["nm_mun"], f"mun:{sigla}:{cd}.nome", linha["nm_mun"], reg["nome"]
        )
        f.checar(
            reg["cd_mun_ibge"] == linha["cd_mun_ibge"],
            f"mun:{sigla}:{cd}.cd_mun_ibge",
            linha["cd_mun_ibge"],
            reg["cd_mun_ibge"],
        )

    # índice nacional: contagem e coerência com os arquivos por UF
    indice = json.loads((WEB_DATA / "resultados" / "municipios_br.json").read_text("utf-8"))
    esperado_br = int((~mun_tot["eh_exterior"]).sum())
    f.checar(
        len(indice["municipios"]) == esperado_br, "indice.n", esperado_br, len(indice["municipios"])
    )
    campos = indice["formato"]
    for item in args.municipios:
        sigla, cd = item.split(":")
        linha = mun_tot[(mun_tot["uf"] == sigla) & (mun_tot["cd_mun_tse"] == cd)].iloc[0]
        arr = indice["municipios"].get(linha["cd_mun_ibge"])
        if arr is None:
            f.itens.append(f"indice sem {linha['cd_mun_ibge']}")
            continue
        d = dict(zip(campos, arr, strict=True))
        obj = json.loads((WEB_DATA / "resultados" / "uf" / f"uf_{sigla}.json").read_text("utf-8"))
        reg = next(m for m in obj["municipios"] if m["cd_mun_tse"] == cd)
        for campo in ("cor_mistura", "cor_margem", "vencedor", "margem_pp", "nome"):
            f.checar(d[campo] == reg[campo], f"indice.{cd}.{campo}", reg[campo], d[campo])

    # exterior
    ext = json.loads((WEB_DATA / "exterior.json").read_text("utf-8"))
    esperado_ext = int(mun_tot["eh_exterior"].sum())
    f.checar(len(ext["locais"]) == esperado_ext, "exterior.n", esperado_ext, len(ext["locais"]))
    soma_ext = sum(m["totais"]["validos"] for m in ext["locais"])
    f.checar(
        soma_ext == int(uf_tot.loc[config.UF_EXTERIOR, "validos"]),
        "exterior.soma_validos",
        int(uf_tot.loc[config.UF_EXTERIOR, "validos"]),
        soma_ext,
    )

    print(f"\n{f.ok} verificações OK, {len(f.itens)} falhas")
    for item in f.itens:
        print("  FALHA", item)
    return 1 if f.itens else 0


if __name__ == "__main__":
    raise SystemExit(main())
