"""Helpers de plot das análises (matplotlib). Só desenham; nenhum cálculo de análise aqui.

Cores: vêm de `config/candidatos.yaml` via `eleicao.cores.carregar_paleta`; candidatos
abaixo de 1% dos válidos nacionais viram "Outros" com `COR_OUTROS` (regra do projeto).
Figuras vão para docs/img/analises/<nome>.png (ver `salvar`).
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from eleicao import config
from eleicao.cores import COR_OUTROS, carregar_paleta

DIR_FIGURAS = config.RAIZ / "docs" / "img" / "analises"
PALETA = carregar_paleta()
NOME_CURTO = {
    13: "Lula (PT)", 22: "Flávio Bolsonaro (PL)", 70: "Cury", 14: "Renan Santos",
    55: "Caiado", 30: "Zema", 80: "Samara", 16: "Hertz", 27: "Clariana",
    21: "Edmilson", 35: "Wilson Grassi", 29: "Rui Costa Pimenta",
}  # fmt: skip


def cor_candidato(nr: int | str) -> str:
    if nr == "outros":
        return COR_OUTROS
    return PALETA.get(int(nr), COR_OUTROS)


def salvar(fig: plt.Figure, nome: str) -> Path:
    """Salva o PNG em docs/img/analises/<nome>.png (cria a pasta se preciso)."""
    DIR_FIGURAS.mkdir(parents=True, exist_ok=True)
    caminho = DIR_FIGURAS / f"{nome}.png"
    fig.savefig(caminho, dpi=130, bbox_inches="tight")
    return caminho


def barras_por_candidato(
    tabela: pd.DataFrame, grupo: str, coluna: str, titulo: str, ylabel: str
) -> plt.Figure:
    """Barras agrupadas: eixo x = `grupo`, uma barra por candidato (cor fixa), valor = `coluna`.

    `tabela`: colunas `grupo`, `nr_candidato`, `coluna`. Candidatos já agrupados pelo chamador.
    """
    grupos = list(dict.fromkeys(tabela[grupo]))
    nrs = list(dict.fromkeys(tabela["nr_candidato"]))
    fig, ax = plt.subplots(figsize=(10, 4.8))
    largura = 0.8 / max(len(nrs), 1)
    x = np.arange(len(grupos))
    for i, nr in enumerate(nrs):
        sub = tabela[tabela["nr_candidato"] == nr].set_index(grupo).reindex(grupos)
        ax.bar(x + i * largura, sub[coluna].to_numpy(), largura, color=cor_candidato(nr),
               label=NOME_CURTO.get(nr, str(nr)) if nr != "outros" else "Outros (<1%)")  # fmt: skip
    ax.set_xticks(x + largura * (len(nrs) - 1) / 2, grupos)
    ax.set_ylabel(ylabel)
    ax.set_title(titulo, loc="left")
    ax.legend(ncol=4, fontsize=8, frameon=False)
    ax.spines[["top", "right"]].set_visible(False)
    return fig


def lorenz_candidatos(curvas: dict[str, tuple[np.ndarray, np.ndarray]], titulo: str) -> plt.Figure:
    """Curvas de Lorenz por candidato (chave = nr ou rótulo) + diagonal de igualdade."""
    fig, ax = plt.subplots(figsize=(6.5, 6))
    ax.plot([0, 1], [0, 1], color="#999999", ls="--", lw=1, label="igualdade")
    for chave, (x, y) in curvas.items():
        nr = chave if isinstance(chave, int) else None
        ax.plot(x, y, color=cor_candidato(nr) if nr is not None else COR_OUTROS,
                lw=2, label=NOME_CURTO.get(nr, str(chave)) if nr is not None else str(chave),
        )  # fmt: skip
    ax.set_xlabel("fração acumulada dos municípios (do menor para o maior)")
    ax.set_ylabel("fração acumulada dos votos do candidato")
    ax.set_title(titulo, loc="left")
    ax.legend(fontsize=8, frameon=False)
    ax.spines[["top", "right"]].set_visible(False)
    return fig


def dispersao_com_reta(
    df: pd.DataFrame, x: str, y: str, titulo: str, xlabel: str, ylabel: str, subtitulo: str = ""
) -> plt.Figure:
    """Dispersão municipal com reta de tendência (OLS só para visualizar; inferência no cálculo)."""
    d = df[[x, y]].dropna()
    fig, ax = plt.subplots(figsize=(7, 5))
    ax.scatter(d[x], d[y], s=5, alpha=0.25, color="#555555", edgecolors="none")
    if len(d) > 1:
        coef = np.polyfit(d[x], d[y], 1)
        xs = np.linspace(d[x].min(), d[x].max(), 50)
        ax.plot(xs, coef[0] * xs + coef[1], color="#c0392b", lw=1.5)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.set_title(titulo, loc="left", fontsize=11)
    if subtitulo:
        ax.text(0.01, 0.98, subtitulo, transform=ax.transAxes, va="top", fontsize=8)
    ax.spines[["top", "right"]].set_visible(False)
    return fig


def mapa_valores(
    gdf, coluna: str, titulo: str, cmap: str = "RdBu_r", centro: float | None = None,
    limites: tuple[float, float] | None = None, rotulo_cbar: str = "",
) -> plt.Figure:  # fmt: skip
    """Coropletos municipais (gdf já no CRS de área). Divergente se `centro` é dado."""
    fig, ax = plt.subplots(figsize=(7, 8))
    if centro is not None:
        vmin, vmax = limites if limites else (gdf[coluna].min(), gdf[coluna].max())
        lim = max(abs(vmin - centro), abs(vmax - centro))
        norm_kw = {"vmin": centro - lim, "vmax": centro + lim}
    else:
        norm_kw = {} if limites is None else {"vmin": limites[0], "vmax": limites[1]}
    gdf.plot(column=coluna, cmap=cmap, linewidth=0, ax=ax, legend=True,
             legend_kwds={"shrink": 0.6, "label": rotulo_cbar}, **norm_kw)  # fmt: skip
    ax.set_axis_off()
    ax.set_title(titulo, loc="left", fontsize=11)
    return fig


def mapa_categorico(gdf, coluna: str, cores: dict[str, str], titulo: str) -> plt.Figure:
    """Mapa de categorias (ex.: clusters LISA): uma cor por categoria; sem categoria = cinza."""
    fig, ax = plt.subplots(figsize=(7, 8))
    base = gdf.assign(_cor=gdf[coluna].map(cores).fillna("#ececec"))
    base.plot(color=base["_cor"], linewidth=0, ax=ax)
    ax.set_axis_off()
    ax.set_title(titulo, loc="left", fontsize=11)
    handles = [plt.Rectangle((0, 0), 1, 1, color=c) for c in cores.values()]
    ax.legend(handles, list(cores.keys()), fontsize=8, frameon=False, loc="lower left")
    return fig


def agrupar_outros_grafico(
    tabela: pd.DataFrame, grupo: str, col_pct: str, nacionais_pct: dict[int, float]
) -> pd.DataFrame:
    """Para gráficos: candidatos com <1% nacional (regra do projeto) viram "outros".

    Usa `eleicao.cores.agrupar_outros` (limiar 1%, sobre o total nacional recebido)
    para decidir QUEM vai para "outros"; a soma de % do grupo é só apresentação.
    Não recalcula % (o `col_pct` já é sobre válidos do grupo).
    """
    from eleicao.cores import agrupar_outros

    votos_nac = {int(k): int(round(v * 1e6)) for k, v in nacionais_pct.items()}
    agr = agrupar_outros(votos_nac, limiar=0.01)
    grandes = {k for k in agr if k != "outros"}
    t = tabela.copy()
    # object (não np.where): preserva o código inteiro dos candidatos grandes para o nome/cor
    t["nr_candidato"] = pd.Series(
        [nr if nr in grandes else "outros" for nr in t["nr_candidato"]], index=t.index, dtype=object
    )
    return t.groupby([grupo, "nr_candidato"], as_index=False)[col_pct].sum()


def forest_coeficientes(tabelas: dict[str, pd.DataFrame], titulo: str) -> plt.Figure:
    """Coeficientes WLS com IC95 (um painel por modelo/desfecho). Sem a constante."""
    n = len(tabelas)
    fig, eixos = plt.subplots(1, n, figsize=(5.2 * n, 4.8), sharey=True)
    eixos = np.atleast_1d(eixos)
    for ax, (nome, tab) in zip(eixos, tabelas.items(), strict=True):
        t = tab[tab["termo"] != "const"].iloc[::-1]
        y = np.arange(len(t))
        ax.errorbar(
            t["coef"], y, xerr=[t["coef"] - t["ic95_inf"], t["ic95_sup"] - t["coef"]],
            fmt="o", color="#333333", ecolor="#999999", capsize=2, ms=4,
        )  # fmt: skip
        ax.axvline(0, color="#c0392b", lw=1, ls="--")
        ax.set_yticks(y, t["termo"], fontsize=8)
        ax.set_title(nome, loc="left", fontsize=10)
        ax.spines[["top", "right"]].set_visible(False)
    fig.suptitle(titulo, x=0.01, ha="left", fontsize=11)
    return fig
