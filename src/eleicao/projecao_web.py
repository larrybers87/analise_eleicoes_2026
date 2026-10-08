"""Bloco "A projeção de 2026" da aba "2º turno: projeção" (D-037).

Monta `projecao_2026` de `web/data/projecao_backtest.json` a partir dos parquet de saída da
projeção (`projecao_t2_2026_br` e `_uf`, que o exportador lê por nome exato e só com a flag
`--publicar-projecao-2026`) e dos totais do 1º turno de 2026 (brancos e nulos, para a frase
sobre o eixo de mobilização). Funções puras: nenhum caminho de arquivo aqui.

Regras (D-034 item 4 e D-037):
- O placar é o cenário `base` no recorte `total_oficial_com_zz` (com exterior).
- A frase do veredito é calculada pela mesma regra de `projecao_t2.veredito`
  (|%PL − 50| ≤ faixa → "o método não distingue vencedor") e tem o mesmo peso visual do placar.
- O mapa por UF tem 3 categorias discretas (PL, PT, indistinguível), sem gradiente.
- O exterior fica à parte, como texto (D-027).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd

from eleicao.analise.regioes import UF_EXTERIOR
from eleicao.analise.site import formatar
from eleicao.backtest_web import participacao_br
from eleicao.cores import NEUTRO_EMPATE_HEX, carregar_paleta
from eleicao.projecao_t2 import veredito

NR_PL, NR_PT = 22, 13
CANDIDATOS = {
    "PL": {"nr": NR_PL, "nome": "Flávio Bolsonaro", "partido": "PL"},
    "PT": {"nr": NR_PT, "nome": "Lula", "partido": "PT"},
}
"""Os dois finalistas. Nome de exibição (o `nm_urna` do TSE é caixa-alta sem acento)."""

CENARIO_BASE = "base"
CENARIOS_PRINCIPAIS = [
    ("base", "Base: mobilização tipo 2022, terceiros por composição"),
    ("desmob_2018", "Mobilização tipo 2018, terceiros por composição"),
    ("analogos", "Mobilização tipo 2022, terceiros por análogos de 2022"),
    ("analogos_desmob_2018", "Mobilização tipo 2018, terceiros por análogos de 2022"),
]
"""Os 4 cenários do cruzamento eixo A (terceiros) × eixo B (mobilização), D-034."""

RECORTE_TOTAL = "total_oficial_com_zz"
COR_INDISTINGUIVEL = NEUTRO_EMPATE_HEX
REPO = "https://github.com/larrybers87/analise_eleicoes_2026"


def frase_veredito(pct_pl: float, faixa_pp: float) -> tuple[str, str]:
    """(código, frase) do veredito pela regra da D-034: dentro da faixa → não distingue."""
    v = veredito(pct_pl, faixa_pp)
    if v == "indistinguivel":
        return v, "o método não distingue vencedor"
    return v, f"vencedor projetado: {CANDIDATOS[v]['nome']}"


def _pct(v: float, casas: int = 1) -> str:
    return formatar(v, casas, "pct")


def _data_commit(iso: str) -> str:
    d = datetime.fromisoformat(iso)
    off = d.utcoffset()
    horas = int(off.total_seconds() // 3600) if off is not None else 0
    fuso = "UTC" if horas == 0 else f"UTC{'−' if horas < 0 else '+'}{abs(horas)}"
    return f"{d:%d/%m/%Y %H:%M} ({fuso})"


def _t1(br: pd.DataFrame, uf: pd.DataFrame) -> dict[str, str]:
    cols = ["t1_idg", "t1_and", "t1_tf", "t1_geracao"]
    meta = pd.concat([br[cols], uf[cols]]).drop_duplicates()
    if len(meta) != 1:
        raise ValueError(f"parquet da projeção com mais de um snapshot do T1: {meta.values}")
    r = meta.iloc[0]
    return {
        "idg": str(r["t1_idg"]),
        "and": str(r["t1_and"]),
        "tf": str(r["t1_tf"]),
        "geracao": str(r["t1_geracao"]),
    }


def montar_projecao(
    br: pd.DataFrame,
    uf: pd.DataFrame,
    totais_t1_2026: pd.DataFrame,
    bn_t1_por_ano: dict[str, float],
    commit: dict[str, str],
) -> dict[str, Any]:
    """Conteúdo de `projecao_2026` no JSON da aba. `commit` = {"hash", "data_iso"}."""
    paleta = carregar_paleta()
    tot = br[br["recorte"] == RECORTE_TOTAL].set_index("cenario")
    faltam = [c for c, _ in CENARIOS_PRINCIPAIS if c not in tot.index]
    if faltam:
        raise ValueError(f"projecao_t2_2026_br sem os cenários {faltam} no recorte {RECORTE_TOTAL}")

    # ---- placar (base, total oficial com exterior)
    b = tot.loc[CENARIO_BASE]
    pct_pl, pct_pt, faixa = (
        float(b["pct_pl_validos"]),
        float(b["pct_pt_validos"]),
        float(b["faixa_pl_pp"]),
    )
    cod, frase = frase_veredito(pct_pl, faixa)
    faixa_pl = (pct_pl - faixa, pct_pl + faixa)
    faixa_pt = (pct_pt - faixa, pct_pt + faixa)

    # ---- cenários principais e eixo de mobilização
    cenarios = [
        {
            "id": c,
            "rotulo": r,
            "pct_pl": round(float(tot.loc[c, "pct_pl_validos"]), 4),
            "texto": _pct(float(tot.loc[c, "pct_pl_validos"])),
        }
        for c, r in CENARIOS_PRINCIPAIS
    ]
    valores_pl = [c["pct_pl"] for c in cenarios]
    d_base = float(tot.loc["desmob_2018", "pct_pl_validos"] - tot.loc["base", "pct_pl_validos"])
    d_anal = float(
        tot.loc["analogos_desmob_2018", "pct_pl_validos"] - tot.loc["analogos", "pct_pl_validos"]
    )
    bn_2026 = participacao_br(totais_t1_2026)["bn_pct_aptos"]

    # ---- UFs (base), exterior à parte
    ub = uf[uf["cenario"] == CENARIO_BASE]
    ufs, contagem = {}, {"PL": 0, "PT": 0, "indistinguivel": 0}
    cores = {"PL": paleta[NR_PL], "PT": paleta[NR_PT], "indistinguivel": COR_INDISTINGUIVEL}
    rotulo_cat = {"PL": "PL", "PT": "PT", "indistinguivel": "indistinguível"}
    exterior = None
    for r in ub.itertuples():
        v = veredito(float(r.pct_pl_validos), float(r.faixa_pp))
        item = {
            "pct_pl": round(float(r.pct_pl_validos), 4),
            "faixa_pp": float(r.faixa_pp),
            "veredito": v,
            "cor": cores[v],
            "texto": f"{r.uf.upper()}: PL {_pct(float(r.pct_pl_validos))} dos válidos "
            f"({rotulo_cat[v]})",
        }
        if r.uf == UF_EXTERIOR:
            exterior = item
            continue
        ufs[r.uf] = item
        contagem[v] += 1
    if len(ufs) != 27 or exterior is None:
        raise ValueError("projecao_t2_2026_uf (base) precisa ter as 27 UFs e o exterior")
    faixa_uf = float(ub[ub["uf"] != UF_EXTERIOR]["faixa_pp"].iloc[0])
    _, frase_ext = frase_veredito(exterior["pct_pl"], exterior["faixa_pp"])

    pl, pt = CANDIDATOS["PL"], CANDIDATOS["PT"]
    textos = {
        "placar": f"{pl['nome']} {_pct(pct_pl)} × {pt['nome']} {_pct(pct_pt)} dos válidos",
        "veredito": f"faixa heurística ±{formatar(faixa, 0, 'dec')} p.p. (n=1): {frase}",
        "faixas": (
            f"{pl['partido']} {_pct(faixa_pl[0])}–{_pct(faixa_pl[1])}, "
            f"{pt['partido']} {_pct(faixa_pt[0])}–{_pct(faixa_pt[1])}"
        ),
        "cenarios_faixa": f"{_pct(min(valores_pl))} e {_pct(max(valores_pl))}",
        "mob_delta_base": formatar(d_base, 1, "pp"),
        "mob_delta_analogos": formatar(d_anal, 1, "pp"),
        "mob_bn_2026": _pct(bn_2026),
        "mob_bn_2022": _pct(bn_t1_por_ano["2022"]),
        "mob_bn_2018": _pct(bn_t1_por_ano["2018"]),
        "faixa_uf": f"±{formatar(faixa_uf, 1, 'dec')} p.p.",
        "exterior": (
            f"Exterior (fora do mapa e de todo agregado “Brasil”): PL {_pct(exterior['pct_pl'])} "
            f"dos válidos; faixa ±{formatar(exterior['faixa_pp'], 1, 'dec')} p.p.: {frase_ext}."
        ),
        "t1": (
            f"resultado do 1º turno na totalização do TSE de {_t1(br, uf)['geracao']} "
            f"(geração {_t1(br, uf)['idg']}, and={_t1(br, uf)['and']}, tf={_t1(br, uf)['tf']})"
        ),
        "data_projecao": _data_commit(commit["data_iso"]),
        "commit": commit["hash"][:7],
        "n_pl": str(contagem["PL"]),
        "n_pt": str(contagem["PT"]),
        "n_indist": str(contagem["indistinguivel"]),
    }
    return {
        "candidatos": {k: {**v, "cor": paleta[v["nr"]]} for k, v in CANDIDATOS.items()},
        "recorte_placar": RECORTE_TOTAL,
        "placar": {
            "cenario": CENARIO_BASE,
            "pct_pl": round(pct_pl, 4),
            "pct_pt": round(pct_pt, 4),
            "faixa_pp": faixa,
            "faixa_pl": [round(x, 4) for x in faixa_pl],
            "faixa_pt": [round(x, 4) for x in faixa_pt],
            "veredito": cod,
        },
        "cenarios": cenarios,
        "eixo_mobilizacao": {
            "delta_pl_base_pp": round(d_base, 4),
            "delta_pl_analogos_pp": round(d_anal, 4),
            "bn_t1_pct_aptos": {
                "2018": round(bn_t1_por_ano["2018"], 4),
                "2022": round(bn_t1_por_ano["2022"], 4),
                "2026": round(bn_2026, 4),
            },
        },
        "ufs": ufs,
        "contagem_ufs": contagem,
        "exterior": exterior,
        "categorias": [
            {"id": k, "rotulo": rotulo_cat[k], "cor": cores[k]}
            for k in ("PL", "PT", "indistinguivel")
        ],
        "t1": _t1(br, uf),
        "commit": {
            "hash": commit["hash"],
            "data_iso": commit["data_iso"],
            "url": f"{REPO}/commit/{commit['hash']}",
        },
        "textos": textos,
    }
