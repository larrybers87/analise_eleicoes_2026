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
  - contagem de municípios por UF e do índice nacional;
  - F2.2 (candidato selecionado): stops de `escala_forca`/`escala_margem` ==
    recálculo por `cores.py`; `forca/cand_<nr>.json` (tamanho, ordem, p98 e os
    percentuais, por posição) == recálculo por `eleicao.forca`; o fatiamento
    por UF via `meta.forca_offsets`; `votos_cand` de UF/Brasil/exterior; e os
    números de `resumo_candidatos.json` (municípios vencidos, top 10, exterior).

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

from eleicao import config, forca  # noqa: E402
from eleicao.cores import (  # noqa: E402
    agrupar_outros,
    carregar_paleta,
    escala_forca,
    escala_forca_neutra,
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


def conferir_f22(
    f: Falhas,
    paleta: dict[int, str],
    mun_tot: pd.DataFrame,
    mun_cand: pd.DataFrame,
    uf_cand: pd.DataFrame,
    br_cand: pd.DataFrame,
    amostra_mun: list[str],
) -> None:
    """Checagens do F2.2 (D-018): escalas, `forca/*.json`, `votos_cand`, resumo."""
    meta = json.loads((WEB_DATA / "meta.json").read_text("utf-8"))
    br_json = json.loads((WEB_DATA / "resultados" / "br.json").read_text("utf-8"))
    resumo = json.loads((WEB_DATA / "resumo_candidatos.json").read_text("utf-8"))
    ext_json = json.loads((WEB_DATA / "exterior.json").read_text("utf-8"))

    pct = forca.pct_por_municipio(mun_cand, mun_tot)
    ordem_ibge = list(pct.index)

    # --- 1. stops das rampas, recalculados por cores.py ----------------------
    for nr in sorted(paleta):
        f.checar(
            meta["escala_forca"][str(nr)] == escala_forca(nr, paleta),
            f"meta.escala_forca[{nr}]",
            escala_forca(nr, paleta),
            meta["escala_forca"][str(nr)],
        )
    f.checar(
        meta["escala_forca_neutra"] == escala_forca_neutra(),
        "meta.escala_forca_neutra",
        escala_forca_neutra(),
        meta["escala_forca_neutra"],
    )

    # --- 2. ordem canônica e votos_cand --------------------------------------
    votos_br = dict(
        zip(br_cand["nr_candidato"].astype(int), br_cand["votos"].astype(int), strict=True)
    )
    ordem = [nr for nr, _ in sorted(votos_br.items(), key=lambda it: it[1], reverse=True)]
    f.checar(
        meta["ordem_candidatos"] == ordem, "meta.ordem_candidatos", ordem, meta["ordem_candidatos"]
    )
    f.checar(
        br_json["br"]["votos_cand"] == [votos_br[nr] for nr in ordem],
        "br.votos_cand",
        [votos_br[nr] for nr in ordem],
        br_json["br"]["votos_cand"],
    )
    for item in br_json["ufs"]:
        sub = uf_cand[uf_cand["uf"] == item["uf"]]
        esperado = dict(zip(sub["nr_candidato"].astype(int), sub["votos"].astype(int), strict=True))
        f.checar(
            item["votos_cand"] == [esperado.get(nr, 0) for nr in ordem],
            f"br.ufs[{item['uf']}].votos_cand",
            [esperado.get(nr, 0) for nr in ordem],
            item["votos_cand"],
        )

    # --- 3. forca/cand_<nr>.json: tamanho, ordem, p98 e valores --------------
    posicoes = {ibge: i for i, ibge in enumerate(ordem_ibge)}
    for nr in sorted(paleta):
        obj = json.loads((WEB_DATA / "resultados" / "forca" / f"cand_{nr}.json").read_text("utf-8"))
        f.checar(obj["n"] == len(ordem_ibge), f"forca[{nr}].n", len(ordem_ibge), obj["n"])
        f.checar(
            len(obj["pct"]) == len(ordem_ibge),
            f"forca[{nr}].len(pct)",
            len(ordem_ibge),
            len(obj["pct"]),
        )
        esperado_p98 = round(forca.escala_maxima(pct[nr]), 4)
        f.checar(obj["p98"] == esperado_p98, f"forca[{nr}].p98", esperado_p98, obj["p98"])
        f.checar(
            meta["forca_p98"][str(nr)] == esperado_p98,
            f"meta.forca_p98[{nr}]",
            esperado_p98,
            meta["forca_p98"][str(nr)],
        )
        for ibge in amostra_mun:
            i = posicoes[ibge]
            esp = round(float(pct.loc[ibge, nr]), 3)
            esp = 0 if esp == 0 else esp
            f.checar(obj["pct"][i] == esp, f"forca[{nr}].pct[{ibge}]", esp, obj["pct"][i])

    f.checar(
        ordem_ibge == sorted(ordem_ibge, key=int),
        "forca.ordem_crescente",
        "cd_mun_ibge crescente",
        "fora de ordem",
    )

    # --- 4. fatiamento por UF (meta.forca_offsets) ---------------------------
    for sigla, base in meta["forca_offsets"].items():
        uf_json = json.loads(
            (WEB_DATA / "resultados" / "uf" / f"uf_{sigla}.json").read_text("utf-8")
        )
        ibges = sorted((str(m["cd_mun_ibge"]) for m in uf_json["municipios"]), key=int)
        fatia = ordem_ibge[base : base + len(ibges)]
        f.checar(fatia == ibges, f"forca_offsets[{sigla}]", ibges[:3], fatia[:3])

    # --- 5. resumo_candidatos.json -------------------------------------------
    mun_br = mun_tot[~mun_tot["eh_exterior"]]
    chave = {
        str(i): (u, c)
        for i, u, c in zip(mun_br["cd_mun_ibge"], mun_br["uf"], mun_br["cd_mun_tse"], strict=True)
    }
    votos_mun: dict[tuple[str, str], dict[int, int]] = {}
    for (u, c), grupo in mun_cand.groupby(["uf", "cd_mun_tse"], sort=False):
        votos_mun[(u, c)] = dict(
            zip(grupo["nr_candidato"].astype(int), grupo["votos"].astype(int), strict=True)
        )
    vencidos: dict[int, int] = dict.fromkeys(paleta, 0)
    for k in chave.values():
        v = votos_mun.get(k, {})
        if v:
            vencidos[max(v.items(), key=lambda it: it[1])[0]] += 1
    for nr in sorted(paleta):
        r = resumo["candidatos"][str(nr)]
        f.checar(
            r["municipios_vencidos"] == vencidos[nr],
            f"resumo[{nr}].municipios_vencidos",
            vencidos[nr],
            r["municipios_vencidos"],
        )
        f.checar(
            sum(r["municipios_vencidos_por_uf"].values()) == vencidos[nr],
            f"resumo[{nr}].soma_por_uf",
            vencidos[nr],
            sum(r["municipios_vencidos_por_uf"].values()),
        )
        # top 10 por %: tem que bater com o recálculo direto do parquet
        esperado_top = [str(ibge) for ibge in pct[nr].sort_values(ascending=False).head(10).index]
        obtido_top = [linha[0] for linha in r["top_pct"]]
        f.checar(obtido_top == esperado_top, f"resumo[{nr}].top_pct", esperado_top, obtido_top)
        # top 10 por votos absolutos
        serie_votos = pd.Series(
            {ibge: votos_mun.get(chave[ibge], {}).get(nr, 0) for ibge in ordem_ibge}
        )
        esperado_votos = list(serie_votos.sort_values(ascending=False).head(10).index)
        obtido_votos = [linha[0] for linha in r["top_votos"]]
        f.checar(
            obtido_votos == esperado_votos,
            f"resumo[{nr}].top_votos",
            esperado_votos,
            obtido_votos,
        )
        # exterior
        sub = uf_cand[(uf_cand["uf"] == config.UF_EXTERIOR) & (uf_cand["nr_candidato"] == nr)]
        esperado_ext = int(sub["votos"].iloc[0]) if len(sub) else 0
        f.checar(
            r["exterior"]["votos"] == esperado_ext,
            f"resumo[{nr}].exterior.votos",
            esperado_ext,
            r["exterior"]["votos"],
        )

    # --- 6. votos_cand do exterior (por local) -------------------------------
    soma_ext = [0] * len(ordem)
    for local in ext_json["locais"]:
        if local["votos_cand"]:
            for i, v in enumerate(local["votos_cand"]):
                soma_ext[i] += v
    esperado_ext_total = [
        int(
            uf_cand[(uf_cand["uf"] == config.UF_EXTERIOR) & (uf_cand["nr_candidato"] == nr)][
                "votos"
            ].sum()
        )
        for nr in ordem
    ]
    f.checar(
        soma_ext == esperado_ext_total,
        "exterior.soma(votos_cand)",
        esperado_ext_total,
        soma_ext,
    )


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

    # F2.2 — candidato selecionado
    print("F2.2 (escalas, força por município, votos_cand, resumo)")
    amostra_ibge = []
    for item in args.municipios:
        sigla, cd = item.split(":")
        linha = mun_tot[(mun_tot["uf"] == sigla) & (mun_tot["cd_mun_tse"] == cd)]
        if len(linha) and not bool(linha["eh_exterior"].iloc[0]):
            amostra_ibge.append(str(linha["cd_mun_ibge"].iloc[0]))
    amostra_ibge += ["3550308", "3157336", "1100015"]  # SP, menor município, 1º da ordem
    conferir_f22(f, paleta, mun_tot, mun_cand, uf_cand, br_cand, sorted(set(amostra_ibge)))

    print(f"\n{f.ok} verificações OK, {len(f.itens)} falhas")
    for item in f.itens:
        print("  FALHA", item)
    return 1 if f.itens else 0


if __name__ == "__main__":
    raise SystemExit(main())
