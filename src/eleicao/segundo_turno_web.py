"""Dados da página "2º turno: resultado" (`web/segundo-turno.html`).

Monta `web/data/segundo_turno.json` a partir do T2 apurado (`presidente_t2_*`), do T1 oficial e
das saídas de `scripts/virada_t2.py`. Funções puras; nenhum número é digitado no HTML (D-030):
todo texto sai formatado daqui.

Regras de leitura (D-039): o swing usa a margem entre os dois finalistas nos dois turnos e é
descritivo; os números da extensão do horário são de imprensa e vêm marcados como tal.
"""

from __future__ import annotations

import math
from typing import Any

import pandas as pd

from eleicao.analise.regioes import UF_EXTERIOR
from eleicao.analise.site import formatar
from eleicao.comparacao_web import real_por_recorte
from eleicao.cores import (
    NEUTRO_EMPATE_HEX,
    carregar_paleta,
    cor_divergente_simetrica,
    escala_divergente_assimetrica,
)

NR_PL, NR_PT = 22, 13
PASSO_RESULTADO = 5.0
PASSO_SWING = 1.0

VOTOS_APOS_17H_IMPRENSA = 35_521
"""Levantamento do g1 com os logs das urnas, reproduzido por outros veículos. NÃO verificado
nos dados deste projeto (os arquivos usados aqui não têm horário por voto)."""

FONTES_EXTENSAO = [
    {
        "rotulo": "Poder360: STF prorroga a votação em 2 horas",
        "url": "https://www.poder360.com.br/poder-eleicoes-2026/zanin-prorroga-votacao-do-2o-turno-ate-19h/",
    },
    {
        "rotulo": "Band: STF e TSE autorizam a prorrogação em todo o Brasil",
        "url": "https://www.band.com.br/politica/eleicoes/stf-autoriza-prorrogacao-da-eleicao-de-2o-turno-em-todo-o-brasil",
    },
    {
        "rotulo": "Gazeta do Povo: liminar prorroga a votação até as 19h em todo o Brasil",
        "url": "https://www.gazetadopovo.com.br/eleicoes/2026/stf-concede-liminar-e-prorroga-votacao-ate-as-19h-em-todo-o-brasil/",
    },
    {
        "rotulo": "Câmara dos Deputados: presidente do TSE sobre a prorrogação",
        "url": "https://www.camara.leg.br/noticias/1313728-presidente-do-tse-afirma-que-a-decisao-de-prorrogar-a-votacao-exigiu-medidas-extraordinarias",
    },
    {
        "rotulo": "ICL Notícias: só 35,5 mil votos foram registrados após as 17h",
        "url": "https://iclnoticias.com.br/mais-de-35-mil-votos-foram-registrados-apos/",
    },
    {
        "rotulo": "Tribuna do Norte: Flávio diz que vai pedir a anulação",
        "url": "https://tribunadonorte.com.br/tn-nas-eleicoes-2026/flavio-bolsonaro-diz-que-vai-pedir-anulacao-da-votacao-do-segundo-turno/",
    },
]


def _limite(valores: pd.Series, passo: float) -> float:
    return math.ceil(float(valores.abs().max()) / passo) * passo


def _t1_br(cand_t1: pd.DataFrame) -> dict[str, float]:
    v = cand_t1.assign(nr=cand_t1["nr_candidato"].astype(int)).set_index("nr")["votos"]
    return {"pl": float(v[NR_PL]), "pt": float(v[NR_PT])}


def montar(
    cand_br: pd.DataFrame,
    tot_br: pd.DataFrame,
    cand_t1_br: pd.DataFrame,
    tot_t1_br: pd.DataFrame,
    virada_mun: pd.DataFrame,
    virada_uf: pd.DataFrame,
    virada_porte: pd.DataFrame,
    virada_mg: pd.DataFrame,
    t2_uf_cand: pd.DataFrame,
) -> dict[str, Any]:
    paleta = carregar_paleta()
    cor_pl, cor_pt = paleta[NR_PL], paleta[NR_PT]
    real = real_por_recorte(cand_br, tot_br)
    t = tot_br.iloc[0]
    margem_votos = int(real["pt"] - real["pl"])

    # ---- 1º turno nacional, para a frase da virada (válidos, como o TSE divulga)
    t1 = _t1_br(cand_t1_br)
    validos_t1 = float(tot_t1_br.iloc[0]["validos"])
    pct_pl_t1, pct_pt_t1 = 100 * t1["pl"] / validos_t1, 100 * t1["pt"] / validos_t1

    # ---- UFs: resultado do T2 (arquivo oficial da UF) e swing
    v = t2_uf_cand.assign(nr=t2_uf_cand["nr_candidato"].astype(int)).pivot_table(
        index="uf", columns="nr", values="votos", aggfunc="sum"
    )
    m_t2 = 100 * (v[NR_PT] - v[NR_PL]) / (v[NR_PT] + v[NR_PL])
    vu = virada_uf.set_index("uf")
    ufs27 = [u for u in vu.index if u != UF_EXTERIOR]
    lim_res = _limite(m_t2[ufs27], PASSO_RESULTADO)
    lim_sw = _limite(vu.loc[ufs27, "swing"], PASSO_SWING)
    ufs = {}
    for u in ufs27:
        m2, sw = float(m_t2[u]), float(vu.loc[u, "swing"])
        lado = "Lula" if m2 > 0 else "Flávio Bolsonaro"
        ufs[u] = {
            "margem_t1": round(float(vu.loc[u, "margem_t1"]), 4),
            "margem_t2": round(m2, 4),
            "swing": round(sw, 4),
            "dabst": round(float(vu.loc[u, "dabst_pp"]), 4),
            "venceu": "PT" if m2 > 0 else "PL",
            "cor_resultado": cor_divergente_simetrica(m2, lim_res, cor_pl, cor_pt),
            "cor_swing": cor_divergente_simetrica(sw, lim_sw, cor_pl, cor_pt),
            "texto_resultado": f"{u.upper()}: {lado} por "
            f"{formatar(abs(m2), 1, 'dec')} p.p. entre os finalistas",
            "texto_swing": f"{u.upper()}: {formatar(sw, 1, 'pp')} para o PT "
            f"(margem de {formatar(vu.loc[u, 'margem_t1'], 1, 'dec')} para "
            f"{formatar(m2, 1, 'dec')})",
        }
    n_pt = sum(d["venceu"] == "PT" for d in ufs.values())
    tabela_ufs = [
        {
            "uf": u.upper(),
            "margem_t1": formatar(ufs[u]["margem_t1"], 1, "dec"),
            "margem_t2": formatar(ufs[u]["margem_t2"], 1, "dec"),
            "swing": formatar(ufs[u]["swing"], 1, "pp"),
            "dabst": formatar(ufs[u]["dabst"], 1, "pp"),
            "viraram": int(vu.loc[u, "virou_pt"] + vu.loc[u, "virou_pl"]),
        }
        for u in sorted(ufs27, key=lambda x: -float(vu.loc[x, "swing"]))
    ]

    def escala(lim: float, rneg: str, rpos: str) -> dict[str, Any]:
        e = escala_divergente_assimetrica(-lim, lim, cor_pl, cor_pt)
        return {
            "limite_pp": lim,
            "stops": [[round(x, 4), c] for x, c in e],
            "rotulo_negativo": rneg,
            "rotulo_positivo": rpos,
        }

    # ---- municípios e porte
    n_mun = len(virada_mun)
    para_pt, para_pl = int(virada_mun["virou_pt"].sum()), int(virada_mun["virou_pl"].sum())
    pt_t1_n = int((virada_mun["margem_t1"] > 0).sum())
    pt_t2_n = int((virada_mun["margem_t2"] > 0).sum())
    porte = [
        {
            "rotulo": r.porte,
            "municipios": formatar(r.municipios, 0, "int"),
            "swing": formatar(r.swing, 1, "pp"),
            "dabst": formatar(r.dabst_pp, 1, "pp"),
            "viraram": formatar(r.virou_pt + r.virou_pl, 0, "int"),
        }
        for r in virada_porte.itertuples()
    ]
    mg = virada_mg.sort_values("swing")
    mg_tab = [
        {
            "rotulo": r.mesorregiao,
            "swing": formatar(r.swing, 1, "pp"),
            "margem": f"{formatar(r.margem_t1, 1, 'dec')} → {formatar(r.margem_t2, 1, 'dec')}",
            "ganho": formatar(r.parte_ganho_pct, 1, "pct"),
            "eleitorado": formatar(r.parte_eleitorado_pct, 1, "pct"),
        }
        for r in mg.itertuples()
    ]
    mg_total_m1 = vu.loc["mg", "margem_t1"]
    mg_total_m2 = vu.loc["mg", "margem_t2"]
    mg_viraram = int(vu.loc["mg", "virou_pt"])

    # ---- exterior (à parte, D-027)
    ext = v.loc[UF_EXTERIOR] if UF_EXTERIOR in v.index else None
    texto_ext = ""
    if ext is not None:
        pct_pt_ext = 100 * ext[NR_PT] / (ext[NR_PT] + ext[NR_PL])
        texto_ext = (
            f"Exterior (fora dos mapas e do swing, D-027): Lula {formatar(pct_pt_ext, 1, 'pct')} "
            f"dos válidos."
        )

    apos = VOTOS_APOS_17H_IMPRENSA
    textos = {
        "lula_pct": formatar(real["pct_pt"], 2, "pct"),
        "flavio_pct": formatar(real["pct_pl"], 2, "pct"),
        "lula_votos": formatar(real["pt"], 0, "int"),
        "flavio_votos": formatar(real["pl"], 0, "int"),
        "margem_votos": formatar(margem_votos, 0, "int"),
        "margem_pp": formatar(real["pct_pt"] - real["pct_pl"], 2, "dec"),
        "abst": formatar(real["abst_pct"], 2, "pct"),
        "t1_flavio_a_frente": formatar(pct_pl_t1 - pct_pt_t1, 2, "dec"),
        "mun_total": formatar(n_mun, 0, "int"),
        "mun_para_pt": formatar(para_pt, 0, "int"),
        "mun_para_pl": formatar(para_pl, 0, "int"),
        "mun_pt_t1": formatar(pt_t1_n, 0, "int"),
        "mun_pt_t2": formatar(pt_t2_n, 0, "int"),
        "swing_mediana": formatar(virada_mun["swing"].median(), 1, "pp"),
        "swing_uf_min": formatar(vu.loc[ufs27, "swing"].min(), 1, "pp"),
        "swing_uf_max": formatar(vu.loc[ufs27, "swing"].max(), 1, "pp"),
        "ufs_pt": formatar(n_pt, 0, "int"),
        "ufs_pl": formatar(len(ufs) - n_pt, 0, "int"),
        "limite_resultado": formatar(lim_res, 0, "dec"),
        "limite_swing": formatar(lim_sw, 0, "dec"),
        "mg_t1": formatar(mg_total_m1, 1, "dec"),
        "mg_t2": formatar(mg_total_m2, 1, "dec"),
        "mg_viraram": formatar(mg_viraram, 0, "int"),
        "exterior": texto_ext,
        "ext_corte": "17h",
        "ext_fim": "19h",
        "ext_votos_17h": formatar(apos, 0, "int"),
        "ext_razao": formatar(margem_votos / apos, 0, "int"),
        "ext_margem_sem_17h": formatar(margem_votos - apos, 0, "int"),
        "ext_pct_margem": formatar(100 * apos / margem_votos, 1, "pct"),
        "ext_nao_instaladas": formatar(t["extra_s_sni"], 0, "int"),
        "ext_aptos_nao_instaladas": formatar(t["extra_e_esni"], 0, "int"),
    }
    return {
        "candidatos": {
            "PL": {"nome": "Flávio Bolsonaro", "cor": cor_pl},
            "PT": {"nome": "Lula", "cor": cor_pt},
        },
        "neutro": NEUTRO_EMPATE_HEX,
        "ufs": ufs,
        "escala_resultado": escala(lim_res, "mais Flávio", "mais Lula"),
        "escala_swing": escala(lim_sw, "para o PL", "para o PT"),
        "tabela_ufs": tabela_ufs,
        "porte": porte,
        "mg": mg_tab,
        "fontes_extensao": FONTES_EXTENSAO,
        "totalizacao": {
            "and": str(t["status_totalizacao"]),
            "tf": str(t["tf_judicial"]),
            "data_hora": str(t["data_hora_totalizacao"]),
        },
        "textos": textos,
    }
