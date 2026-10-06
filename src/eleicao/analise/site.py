"""Conteúdo da página `web/analises.html` (F3 fase B, D-030).

Monta `web/data/analises.json` e `web/data/analises_dispersao.json` só encadeando funções já
testadas de `eleicao.analise` (via `composicao`, `swing`, `base`, `participacao`). Nada de
estatística nova aqui.

Regra de ouro da página: **nenhum número digitado no HTML**. Cada número que aparece no
texto é uma chave de `CHAVES`, com:
- o achado de `docs/ANALISES.md` de onde ele vem (0 = parágrafo de escopo do topo);
- as casas decimais e o tipo de formatação.
O export grava o valor bruto (`valores`) e o texto já formatado em pt-BR (`textos`), e a
página só insere `textos[chave]`. `tests/test_exportar_analises.py` confere que cada texto
aparece, como número, na seção do achado correspondente do ANALISES.md: se o TSE mudar o
dado ou alguém mudar o .md, o teste aponta a chave que divergiu.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from eleicao import config
from eleicao.cores import COR_OUTROS, carregar_paleta

from . import base, carga, composicao, participacao
from . import swing as sw
from .regioes import NOME_REGIAO, ORDEM_FAIXAS, REGIOES_BR

NR_PT, NR_PL, NR_CAIADO, NR_ZEMA = 13, 22, 55, 30
CANDIDATOS_GINI = (14, 13, 22, 70, 55)  # Renan, Lula, Flávio, Cury, Caiado (achado 4)

CORES_REGIOES = {
    "N": "#009e73",
    "NE": "#e69f00",
    "CO": "#8c6d31",
    "SE": "#cc79a7",
    "S": "#56b4e9",
}
"""Cores categóricas das 5 regiões (só na dispersão da seção de renda). Escolhidas na
paleta Okabe-Ito (segura para daltonismo), evitando o vermelho e o azul saturados que
identificam PT e PL no resto do site. Definidas aqui (Python), lidas prontas pelo JS."""

ROTULO_FAIXA = {
    "<10k": "até 10 mil",
    "10k–50k": "10 a 50 mil",
    "50k–200k": "50 a 200 mil",
    "200k–1M": "200 mil a 1 milhão",
    ">1M": "mais de 1 milhão",
}

MEDIDAS_MAPA = [
    ("pct_municipios_vencidos", "municípios"),
    ("pct_area_sobre_area_br", "área"),
    ("pct_eleitorado_sobre_eleitorado_br", "eleitorado"),
    ("pct_votos_do_candidato_nos_vencidos", "votos do próprio candidato"),
]


@dataclass(frozen=True)
class Chave:
    chave: str
    achado: int
    casas: int
    tipo: str  # pct | pp (com sinal) | int | dec | x | pct100 | data


def _ch(chave: str, achado: int, casas: int, tipo: str) -> Chave:
    return Chave(chave, achado, casas, tipo)


CHAVES: list[Chave] = [
    _ch("snapshot.data", 0, 0, "data"),
    _ch("geral.n_municipios", 3, 0, "int"),
    _ch("geral.empates", 0, 0, "int"),
    # seção 1 — achado 3
    *[
        _ch(f"s1.{p}.{m}", 3, 1, "pct")
        for p in ("pl", "pt")
        for m in ("pct_municipios", "pct_area", "pct_eleitorado", "pct_votos_nos_vencidos")
    ],
    _ch("s1.pl.n_municipios", 3, 0, "int"),
    _ch("s1.pt.n_municipios", 3, 0, "int"),
    # seção 2 — achados 2 e 8
    _ch("s2.br.pt", 2, 1, "pp"),
    _ch("s2.br.pl", 2, 1, "pp"),
    _ch("s2.br.pt_2022", 2, 1, "pct"),
    _ch("s2.br.pt_2026", 2, 1, "pct"),
    _ch("s2.br.pl_2022", 2, 1, "pct"),
    _ch("s2.br.pl_2026", 2, 1, "pct"),
    _ch("s2.br.delta_margem", 2, 1, "pp"),
    _ch("s2.mediana.pt", 2, 1, "pp"),
    _ch("s2.mediana.pl", 2, 1, "pp"),
    _ch("s2.nota.co_pt_media_simples", 2, 1, "pp"),
    _ch("s2.nota.co_pt_ponderado", 2, 1, "pp"),
    *[_ch(f"s2.regiao.{r}.{p}", 8, 1, "pp") for r in REGIOES_BR for p in ("pt", "pl")],
    _ch("s2.eta2.pt", 8, 0, "pct100"),
    _ch("s2.eta2.pl", 8, 0, "pct100"),
    # seção 3 — achado 9
    _ch("s3.capitais.pt", 9, 1, "pct"),
    _ch("s3.capitais.pl", 9, 1, "pct"),
    _ch("s3.capitais.n", 9, 0, "int"),
    _ch("s3.interior.pt", 9, 1, "pct"),
    _ch("s3.interior.pl", 9, 1, "pct"),
    _ch("s3.interior.n", 9, 0, "int"),
    *[_ch(f"s3.faixa.{i}.{p}", 9, 1, "pct") for i in range(5) for p in ("pt", "pl")],
    _ch("s3.faixa.4.n", 9, 0, "int"),
    # seção 4 — achado 5 (ρ e n só na nota "detalhes")
    _ch("s4.rho_pt", 5, 2, "dec"),
    _ch("s4.n", 5, 0, "int"),
    # seção 5 — achados 1 e 4
    _ch("s5.caiado.pct_uf", 1, 2, "pct"),
    _ch("s5.caiado.pct_nacional", 1, 2, "pct"),
    _ch("s5.caiado.razao", 1, 1, "x"),
    _ch("s5.caiado.acima_3x", 1, 0, "int"),
    _ch("s5.caiado.n_uf", 1, 0, "int"),
    _ch("s5.zema.pct_uf", 1, 2, "pct"),
    _ch("s5.zema.pct_nacional", 1, 2, "pct"),
    _ch("s5.zema.razao", 1, 1, "x"),
    _ch("s5.zema.acima_3x", 1, 0, "int"),
    _ch("s5.zema.n_uf", 1, 0, "int"),
    *[_ch(f"s5.gini_pct.{nr}", 4, 2, "dec") for nr in CANDIDATOS_GINI],
    # seção 6 — achado 11
    _ch("s6.br_2026", 11, 1, "pct"),
    _ch("s6.br_2022", 11, 1, "pct"),
    *[
        _ch(f"s6.regiao.{r}.{m}", 11, 1, "pct")
        for r in REGIOES_BR
        for m in ("abstencao", "nulos", "brancos")
    ],
]

MENOS = "−"  # sinal de menos tipográfico, o mesmo do ANALISES.md


def _num(valor: float, casas: int) -> str:
    """Número em pt-BR: milhar com ponto, decimal com vírgula, sinal de menos tipográfico."""
    s = f"{abs(valor):,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return (MENOS + s) if valor < 0 and float(s.replace(".", "").replace(",", ".")) != 0 else s


def formatar(valor: Any, casas: int, tipo: str) -> str:
    """Texto exibido na página para um valor (pt-BR). Ver `Chave.tipo`."""
    if tipo == "data":
        return str(valor)
    v = float(valor)
    if tipo == "int":
        return _num(round(v), 0)
    if tipo == "pct":
        return _num(v, casas) + "%"
    if tipo == "pct100":
        return _num(100 * v, casas) + "%"
    if tipo == "pp":
        corpo = _num(v, casas)
        return ("+" + corpo if v > 0 and not corpo.startswith(MENOS) else corpo) + " p.p."
    if tipo == "x":
        return _num(v, casas) + "×"
    if tipo == "dec":
        return _num(v, casas)
    raise ValueError(f"tipo desconhecido: {tipo}")


def nucleo(texto: str, tipo: str) -> str:
    """Parte numérica do texto formatado (o que o teste procura no ANALISES.md)."""
    for sufixo in ("%", " p.p.", "×"):
        texto = texto.removesuffix(sufixo)
    return texto


# ================================ montagem ===================================


def _snapshot() -> dict[str, Any]:
    snap = json.loads((config.DATA_PROCESSED / "snapshot_6257.json").read_text(encoding="utf-8"))
    br = snap["br"]
    return {
        "dg": br["dg"],
        "hg": br["hg"],
        "idg": br["idg"],
        "status_totalizacao": br["and"],
        "tf_judicial": br["tf"],
        "provisorio": br["tf"] != "s",
    }


def _pct_grupo(cand: pd.DataFrame, bb: pd.DataFrame, por: str) -> pd.DataFrame:
    g = base.votos_por_grupo(cand, bb, [por])
    return g[g["nr_candidato"].isin([NR_PT, NR_PL])].pivot_table(
        index=por, columns="nr_candidato", values="pct_sobre_validos_grupo", observed=True
    )


def montar() -> tuple[dict[str, Any], dict[str, Any]]:
    """Devolve `(analises, dispersao)`: o conteúdo dos dois JSON da página.

    Lento (~1–2 min): calcula a área dos municípios (malha completa do IBGE) para o achado 3.
    """
    paleta = carregar_paleta()
    b = composicao.base_2026()
    bb = base.apenas_brasil(b)
    cand = composicao.candidatos_2026_br()
    v: dict[str, float | int | str] = {}
    snap = _snapshot()
    v["snapshot.data"] = f"{snap['dg']} {snap['hg'][:5]}"
    v["geral.n_municipios"] = len(bb)

    # ---------- seção 1: o mapa engana (achado 3) ----------
    res = composicao.resumo_mapa_mente(b).set_index("nr_candidato")
    v["geral.empates"] = len(bb) - int(res["n_municipios_vencidos"].sum())
    graf1 = []
    for nome, nr in (("pl", NR_PL), ("pt", NR_PT)):
        r = res.loc[nr]
        v[f"s1.{nome}.n_municipios"] = int(r["n_municipios_vencidos"])
        v[f"s1.{nome}.pct_municipios"] = float(r["pct_municipios_vencidos"])
        v[f"s1.{nome}.pct_area"] = float(r["pct_area_sobre_area_br"])
        v[f"s1.{nome}.pct_eleitorado"] = float(r["pct_eleitorado_sobre_eleitorado_br"])
        v[f"s1.{nome}.pct_votos_nos_vencidos"] = float(r["pct_votos_do_candidato_nos_vencidos"])
        for col, rot in MEDIDAS_MAPA:
            graf1.append({"medida": rot, "nr": nr, "valor": float(r[col])})

    # ---------- seção 2: onde mudou (achados 2 e 8) ----------
    dados = composicao.swing_pt_pl()
    pt = dados["pt"][dados["pt"]["uf"] != "zz"]
    pl = dados["pl"][dados["pl"]["uf"] != "zz"]
    ag = sw.delta_margem_agregado(pt, pl).iloc[0]
    v["s2.br.pt"] = float(ag["swing_pt_pp"])
    v["s2.br.pl"] = float(ag["swing_pl_pp"])
    v["s2.br.pt_2022"] = float(ag["pt_2022"])
    v["s2.br.pt_2026"] = float(ag["pt_2026"])
    v["s2.br.pl_2022"] = float(ag["pl_2022"])
    v["s2.br.pl_2026"] = float(ag["pl_2026"])
    v["s2.br.delta_margem"] = float(ag["delta_margem_pp"])
    v["s2.mediana.pt"] = float(pt["swing_pp"].median())
    v["s2.mediana.pl"] = float(pl["swing_pp"].median())
    reg_pt = sw.agregado_ponderado(pt, "regiao").set_index("regiao")
    reg_pl = sw.agregado_ponderado(pl, "regiao").set_index("regiao")
    media_pt = sw.media_simples_swing(pt, "regiao").set_index("regiao")
    v["s2.nota.co_pt_media_simples"] = float(media_pt.loc["CO", "media_simples_swing_pp"])
    v["s2.nota.co_pt_ponderado"] = float(reg_pt.loc["CO", "swing_agregado_pp"])
    graf2 = []
    for r in REGIOES_BR:
        v[f"s2.regiao.{r}.pt"] = float(reg_pt.loc[r, "swing_agregado_pp"])
        v[f"s2.regiao.{r}.pl"] = float(reg_pl.loc[r, "swing_agregado_pp"])
        graf2 += [
            {"regiao": NOME_REGIAO[r], "nr": NR_PT, "valor": v[f"s2.regiao.{r}.pt"]},
            {"regiao": NOME_REGIAO[r], "nr": NR_PL, "valor": v[f"s2.regiao.{r}.pl"]},
        ]
    v["s2.eta2.pt"] = float(sw.teste_uniformidade(pt, "regiao")["eta2"])
    v["s2.eta2.pl"] = float(sw.teste_uniformidade(pl, "regiao")["eta2"])

    # ---------- seção 3: tamanho da cidade (achado 9) ----------
    cap = _pct_grupo(cand, bb, "eh_capital")
    v["s3.capitais.pt"] = float(cap.loc[True, NR_PT])
    v["s3.capitais.pl"] = float(cap.loc[True, NR_PL])
    v["s3.interior.pt"] = float(cap.loc[False, NR_PT])
    v["s3.interior.pl"] = float(cap.loc[False, NR_PL])
    v["s3.capitais.n"] = int(bb["eh_capital"].sum())
    v["s3.interior.n"] = int((~bb["eh_capital"]).sum())
    bbf = bb.dropna(subset=["faixa"]).assign(faixa=lambda d: d["faixa"].astype(str))
    fx = _pct_grupo(cand, bbf, "faixa")
    n_fx = bbf.groupby("faixa").size()
    graf3 = []
    for i, f in enumerate(ORDEM_FAIXAS):
        v[f"s3.faixa.{i}.pt"] = float(fx.loc[f, NR_PT])
        v[f"s3.faixa.{i}.pl"] = float(fx.loc[f, NR_PL])
        graf3 += [
            {"faixa": ROTULO_FAIXA[f], "nr": nr, "valor": float(fx.loc[f, nr]), "n": int(n_fx[f])}
            for nr in (NR_PT, NR_PL)
        ]
    v["s3.faixa.4.n"] = int(n_fx[ORDEM_FAIXAS[4]])

    # ---------- seção 4: renda e voto (achado 5) ----------
    m = bb.dropna(subset=["pib_per_capita_reais"]).copy()
    for nome, nr in (("pt", NR_PT), ("pl", NR_PL)):
        p = sw.pct_municipal(cand, m, nr)[["uf", "cd_mun_tse", "pct_validos"]]
        m = m.merge(p.rename(columns={"pct_validos": f"pct_{nome}"}), on=["uf", "cd_mun_tse"])
    m["log_pib"] = np.log10(m["pib_per_capita_reais"])
    rho = participacao.correlacao_ecologica(m, "log_pib", "pct_pt", "spearman")
    v["s4.rho_pt"] = rho["r"]
    v["s4.n"] = rho["n"]
    regioes_idx = {r: i for i, r in enumerate(REGIOES_BR)}
    dispersao = {
        "formato": ["log10_pib_pc_2023", "pct_pt", "pct_pl", "i_regiao", "eleitorado"],
        "regioes": [
            {"sigla": r, "nome": NOME_REGIAO[r], "cor": CORES_REGIOES[r]} for r in REGIOES_BR
        ],
        "pontos": [
            [round(x, 3), round(a, 1), round(c, 1), regioes_idx[g], int(e)]
            for x, a, c, g, e in zip(
                m["log_pib"], m["pct_pt"], m["pct_pl"], m["regiao"], m["eleitorado"], strict=True
            )
        ],
    }

    # ---------- seção 5: redutos (achados 1 e 4) ----------
    graf5 = []
    for nome, uf, nr in (("caiado", "go", NR_CAIADO), ("zema", "mg", NR_ZEMA)):
        r = composicao.tabela_reduto(uf, nr)
        v[f"s5.{nome}.pct_uf"] = float(r["pct_uf_sobre_validos"])
        v[f"s5.{nome}.pct_nacional"] = float(r["pct_nacional_sobre_validos"])
        v[f"s5.{nome}.razao"] = float(r["razao_vs_nacional"])
        v[f"s5.{nome}.acima_3x"] = int(r["n_municipios_acima_3x"])
        v[f"s5.{nome}.n_uf"] = int(r["n_municipios_uf"])
        graf5 += [
            {
                "candidato": nome,
                "nr": nr,
                "recorte": "Brasil",
                "valor": v[f"s5.{nome}.pct_nacional"],
            },
            {"candidato": nome, "nr": nr, "recorte": uf.upper(), "valor": v[f"s5.{nome}.pct_uf"]},
        ]
    gini = composicao.tabela_concentracao(b, list(CANDIDATOS_GINI)).set_index("nr_candidato")
    for nr in CANDIDATOS_GINI:
        v[f"s5.gini_pct.{nr}"] = float(gini.loc[nr, "gini_pct_validos"])

    # ---------- seção 6: participação (achado 11) ----------
    part = base.participacao_agregada(bb, ["regiao"]).set_index("regiao")
    br26 = base.participacao_agregada(bb.assign(_br="BR"), ["_br"]).iloc[0]
    t22 = carga.totais_2022(1)
    br22 = base.participacao_agregada(t22[t22["uf"] != "zz"].assign(_br="BR"), ["_br"]).iloc[0]
    v["s6.br_2026"] = float(br26["pct_abstencao_sobre_eleitorado"])
    v["s6.br_2022"] = float(br22["pct_abstencao_sobre_eleitorado"])
    tabela6 = []
    for r in REGIOES_BR:
        v[f"s6.regiao.{r}.abstencao"] = float(part.loc[r, "pct_abstencao_sobre_eleitorado"])
        v[f"s6.regiao.{r}.nulos"] = float(part.loc[r, "pct_nulos_tvn_sobre_comparecimento"])
        v[f"s6.regiao.{r}.brancos"] = float(part.loc[r, "pct_brancos_sobre_comparecimento"])
        tabela6.append({"regiao": NOME_REGIAO[r], "sigla": r})

    faltando = {c.chave for c in CHAVES} - set(v)
    sobrando = set(v) - {c.chave for c in CHAVES}
    if faltando or sobrando:
        raise ValueError(f"chaves sem valor {sorted(faltando)} / sem spec {sorted(sobrando)}")
    for k, x in v.items():
        if isinstance(x, float) and not math.isfinite(x):
            raise ValueError(f"valor não finito em {k}")

    textos = {c.chave: formatar(v[c.chave], c.casas, c.tipo) for c in CHAVES}
    analises = {
        "snapshot": snap,
        "fonte_numeros": "docs/ANALISES.md (cada chave declara o achado de origem)",
        "achado_de": {c.chave: c.achado for c in CHAVES},
        "valores": v,
        "textos": textos,
        "candidatos": {
            str(nr): {"nome": nome, "cor": paleta[nr]}
            for nr, nome in (
                (NR_PT, "Lula (PT)"),
                (NR_PL, "Flávio Bolsonaro (PL)"),
                (NR_CAIADO, "Ronaldo Caiado (PSD)"),
                (NR_ZEMA, "Zema (Novo)"),
            )
        },
        "cor_outros": COR_OUTROS,
        "secoes": {
            "s1": {"grafico": graf1},
            "s2": {"grafico": graf2},
            "s3": {"grafico": graf3},
            "s4": {"arquivo": "data/analises_dispersao.json"},
            "s5": {"grafico": graf5},
            "s6": {"tabela": tabela6},
        },
    }
    return analises, dispersao
