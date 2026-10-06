"""Swing 1º turno 2022 → 1º turno 2026 e lente "PL 2026 vs teto de Bolsonaro no 2º turno 2022".

Pareamento: chave (uf, cd_mun_tse). Municípios e postos sem par NÃO entram no swing
nem em nenhum agregado: são devolvidos em `sem_par`, com motivo (docs/DECISOES.md D-023).
Nunca viram zero nem NaN silencioso.

IDENTIDADE (obrigatória em qualquer texto):
- nr 13 = Lula/PT nos dois anos: mesma pessoa.
- nr 22 = Jair Bolsonaro/PL em 2022; FLÁVIO BOLSONARO/PL em 2026. O swing do nr 22
  mede a sigla/numeração (direita PL), não a mesma pessoa.

Lente "teto": `teto_2t_2022_pp` = % de válidos de Bolsonaro (nr 22) no 2º turno 2022,
no próprio município. Comparar 1º turno 2026 com 2º turno 2022 NÃO é comparação direta:
o 2º turno é binário, com outro comparecimento e dinâmica de rejeição.

Todas as % têm denominador explícito: `pct_*` = votos ÷ válidos (do município, ou do
grupo nos agregados ponderados).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

CHAVE = ["uf", "cd_mun_tse"]
NR_LULA = 13
NR_BOLSONARO_2022 = 22
NR_PL_2026 = 22  # Flávio Bolsonaro (PL) — ver ressalva no docstring do módulo


def pct_municipal(candidatos: pd.DataFrame, totais: pd.DataFrame, nr: int) -> pd.DataFrame:
    """Votos e % sobre válidos de `nr` em cada município de `totais`.

    Município sem linha do candidato recebe 0 votos explícito (grade cheia, sem NaN).
    Colunas: uf, cd_mun_tse, votos, validos, pct_validos.
    """
    base = totais[[*CHAVE, "validos"]]
    v = candidatos.loc[candidatos["nr_candidato"] == nr, [*CHAVE, "votos"]]
    m = base.merge(v, on=CHAVE, how="left", validate="1:1")
    m["votos"] = m["votos"].fillna(0).astype("int64")
    m["pct_validos"] = 100 * m["votos"] / m["validos"]
    return m[[*CHAVE, "votos", "validos", "pct_validos"]]


def _motivo_sem_par(uf: str, ano_presente: str) -> str:
    if ano_presente == "2026 apenas":
        if uf == "zz":
            return "posto consular novo em 2026 (sem resultado em 2022)"
        return "município criado após 2022 (sem resultado em 2022)"
    if uf == "zz":
        return "posto consular de 2022 ausente em 2026 (sem resultado em 2026)"
    return "ausente em 2026"


def parear(totais22: pd.DataFrame, totais26: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Pareia 2022 e 2026 por (uf, cd_mun_tse). Devolve (pareados, sem_par).

    `pareados`: uf, cd_mun_tse, nome. `sem_par`: uf, cd_mun_tse, nome, ano_presente, motivo.
    Inclui o exterior (`zz`) no pareamento, mas o swing agregado do Brasil o exclui depois.
    """
    a = totais22[[*CHAVE, "nm_mun_tse"]].rename(columns={"nm_mun_tse": "nome"})
    b = totais26[[*CHAVE, "nm_mun"]].rename(columns={"nm_mun": "nome"})
    # nome do município: o de 2026 (é o atual); o de 2022 só serve para conferência
    pareados = b.merge(a[CHAVE], on=CHAVE, how="inner", validate="1:1")[[*CHAVE, "nome"]]

    so22 = a.merge(b[CHAVE], on=CHAVE, how="left", indicator=True)
    so22 = so22[so22["_merge"] == "left_only"][[*CHAVE, "nome"]].assign(ano_presente="2022 apenas")
    so26 = b.merge(a[CHAVE], on=CHAVE, how="left", indicator=True)
    so26 = so26[so26["_merge"] == "left_only"][[*CHAVE, "nome"]].assign(ano_presente="2026 apenas")
    sem_par = pd.concat([so22, so26], ignore_index=True)
    sem_par["motivo"] = [
        _motivo_sem_par(u, ano)
        for u, ano in zip(sem_par["uf"], sem_par["ano_presente"], strict=True)
    ]

    # Pares com zero votos válidos em UM dos anos (só postos do exterior, 44 casos em 05/10/2026):
    # % do ano com 0 válidos seria 0/0: sai do pareamento e vai para `sem_par`, com motivo próprio.
    zero = pareados.merge(
        totais22[[*CHAVE, "validos"]].rename(columns={"validos": "v22"}), on=CHAVE, validate="1:1"
    ).merge(
        totais26[[*CHAVE, "validos"]].rename(columns={"validos": "v26"}), on=CHAVE, validate="1:1"
    )
    sem_validos_mask = (zero["v22"] == 0) | (zero["v26"] == 0)
    sem_validos = zero.loc[sem_validos_mask, [*CHAVE, "nome"]].assign(
        ano_presente="ambos, sem votos válidos em um ano",
        motivo=lambda d: "zero votos válidos em 2022 ou 2026 (% indefinido)",
    )
    pareados = pareados.loc[~sem_validos_mask.to_numpy()]

    sem_par = pd.concat([sem_par, sem_validos], ignore_index=True)
    sem_par = sem_par.sort_values(["ano_presente", "uf", "cd_mun_tse"]).reset_index(drop=True)
    return pareados.reset_index(drop=True), sem_par


def swing_municipal(
    pareados: pd.DataFrame,
    cand22: pd.DataFrame,
    tot22: pd.DataFrame,
    cand26: pd.DataFrame,
    tot26: pd.DataFrame,
    nr22: int = NR_BOLSONARO_2022,
    nr26: int = NR_PL_2026,
) -> pd.DataFrame:
    """Por município pareado: votos e % (sobre válidos de cada ano) e `swing_pp`.

    `swing_pp = pct_2026 - pct_2022` (p.p. de válidos). Só municípios em `pareados`.
    Para o PT use nr22=nr26=13 (`NR_LULA`).
    """
    p22 = pct_municipal(cand22, tot22, nr22).rename(
        columns={"votos": "votos_2022", "validos": "validos_2022", "pct_validos": "pct_2022"}
    )
    p26 = pct_municipal(cand26, tot26, nr26).rename(
        columns={"votos": "votos_2026", "validos": "validos_2026", "pct_validos": "pct_2026"}
    )
    out = pareados.merge(p22, on=CHAVE, how="inner", validate="1:1")
    out = out.merge(p26, on=CHAVE, how="inner", validate="1:1")
    if len(out) != len(pareados):
        raise ValueError("pareado sem votação em algum dos anos")
    out["swing_pp"] = out["pct_2026"] - out["pct_2022"]
    return out


def agregado_ponderado(swing: pd.DataFrame, grupo: str) -> pd.DataFrame:
    """Swing AGREGADO por grupo: soma de votos ÷ soma de válidos, nos dois anos, mesma base.

    `swing_agregado_pp = pct_2026_agregado - pct_2022_agregado`. Não é média de swing
    municipal (ver `media_simples_swing` para essa comparação).
    """
    g = swing.groupby(grupo, as_index=False)[
        ["votos_2022", "validos_2022", "votos_2026", "validos_2026"]
    ].sum()
    g["pct_2022_agregado"] = 100 * g["votos_2022"] / g["validos_2022"]
    g["pct_2026_agregado"] = 100 * g["votos_2026"] / g["validos_2026"]
    g["swing_agregado_pp"] = g["pct_2026_agregado"] - g["pct_2022_agregado"]
    return g


def media_simples_swing(swing: pd.DataFrame, grupo: str) -> pd.DataFrame:
    """MÉDIA SIMPLES do swing municipal por grupo (cada município pesa 1). Só para comparação."""
    return (
        swing.groupby(grupo, as_index=False)["swing_pp"]
        .mean()
        .rename(columns={"swing_pp": "media_simples_swing_pp"})
    )


def teste_uniformidade(
    swing: pd.DataFrame, grupo: str, valor: str = "swing_pp"
) -> dict[str, float]:
    """Swing difere entre grupos (ex.: regiões) mais do que dentro deles?

    - Kruskal-Wallis (sem suposição de normalidade) e ANOVA de 1 via.
    - eta² = SQ_entre ÷ SQ_total: fração da variância municipal do swing explicada pelo grupo.
    - Unidade = município (n ~5.500). Com n grande, diferença pequena vira "significativa":
      o tamanho do efeito (eta², epsilon²) é o que importa para a interpretação.
    """
    d = swing[[grupo, valor]].dropna()
    grupos = [g[valor].to_numpy() for _, g in d.groupby(grupo, observed=True)]
    if len(grupos) < 2:
        raise ValueError("precisa de pelo menos 2 grupos")
    h, p_kw = stats.kruskal(*grupos)
    y = d[valor].to_numpy(dtype=float)
    grand = y.mean()
    ss_total = float(((y - grand) ** 2).sum())
    ss_entre = float(sum(len(g) * (g.mean() - grand) ** 2 for g in grupos))
    k, n = len(grupos), len(y)
    f, p_anova = stats.f_oneway(*grupos)
    return {
        "kruskal_H": float(h),
        "kruskal_p": float(p_kw),
        "anova_F": float(f),
        "anova_p": float(p_anova),
        "eta2": ss_entre / ss_total if ss_total > 0 else float("nan"),
        "epsilon2_kruskal": float((h - k + 1) / (n - k)),
        "n": int(n),
        "k_grupos": int(k),
    }


def lente_pl_vs_teto(
    swing: pd.DataFrame,
    cand_t2_22: pd.DataFrame,
    tot_t2_22: pd.DataFrame,
    nr_bolsonaro_t2: int = NR_BOLSONARO_2022,
) -> pd.DataFrame:
    """PL 2026 (1º turno) vs teto de Bolsonaro no 2º turno 2022, por município pareado.

    `teto_2t_2022_pp` = votos de Bolsonaro no 2T 2022 ÷ válidos do 2T 2022 do município.
    `diferenca_pp` = pct_2026 (PL, 1T, sobre válidos 2026) - teto. Positivo = acima do teto.
    `swing` precisa ter `regiao` e as colunas `votos_2026`/`validos_2026` (de `swing_municipal`).
    Município pareado sem linha no 2T 2022 levanta erro (não há NaN silencioso).
    """
    teto = pct_municipal(cand_t2_22, tot_t2_22, nr_bolsonaro_t2).rename(
        columns={
            "votos": "votos_teto_2t_2022",
            "validos": "validos_2t_2022",
            "pct_validos": "teto_2t_2022_pp",
        }
    )
    out = swing[[*CHAVE, "nome", "regiao", "pct_2026", "votos_2026", "validos_2026"]].merge(
        teto, on=CHAVE, how="left", validate="1:1"
    )
    if out["teto_2t_2022_pp"].isna().any():
        raise ValueError("município pareado sem resultado no 2º turno 2022")
    out["diferenca_pp"] = out["pct_2026"] - out["teto_2t_2022_pp"]
    return out


def lente_regiao(lente: pd.DataFrame, grupo: str = "regiao") -> pd.DataFrame:
    """Agregado ponderado por região: PL 2026 (1T) vs teto 2T 2022, mesma base de municípios."""
    g = lente.groupby(grupo, as_index=False)[
        ["votos_2026", "validos_2026", "votos_teto_2t_2022", "validos_2t_2022"]
    ].sum()
    g["pl_2026_1t_agregado_pp"] = 100 * g["votos_2026"] / g["validos_2026"]
    g["teto_2t_2022_agregado_pp"] = 100 * g["votos_teto_2t_2022"] / g["validos_2t_2022"]
    g["diferenca_agregada_pp"] = g["pl_2026_1t_agregado_pp"] - g["teto_2t_2022_agregado_pp"]
    return g


def contagem_acima_do_teto(lente: pd.DataFrame, grupo: str = "regiao") -> pd.DataFrame:
    """Por grupo: nº de municípios acima do teto e fração sobre o total do grupo."""
    x = lente.assign(acima=lente["diferenca_pp"] > 0)
    g = x.groupby(grupo, as_index=False).agg(
        n_municipios=("acima", "size"), n_acima_do_teto=("acima", "sum")
    )
    g["pct_municipios_acima_do_teto"] = 100 * g["n_acima_do_teto"] / g["n_municipios"]
    return g


def delta_margem_municipal(swing_pt: pd.DataFrame, swing_pl: pd.DataFrame) -> pd.DataFrame:
    """Variação da margem do PL sobre o PT, 1T 2022 → 1T 2026, por município pareado.

    Definição (docs/DECISOES.md D-030):
        delta_margem_pp = (pl_2026 - pt_2026) - (pl_2022 - pt_2022)
    em p.p. de válidos de cada ano. É idêntico a `swing_pl - swing_pt`. Positivo = a margem
    andou a favor do PL; negativo = a favor do PT; zero = sem mudança na margem.

    `swing_pt`/`swing_pl`: saídas de `swing_municipal` (nr 13 e nr 22) com a MESMA base de
    pareados. Base diferente levanta erro. Identidade do nr 22: Jair (2022) → Flávio (2026).
    """
    cols = [*CHAVE, "pct_2022", "pct_2026", "swing_pp"]
    a = swing_pt[cols].rename(
        columns={"pct_2022": "pt_2022", "pct_2026": "pt_2026", "swing_pp": "swing_pt_pp"}
    )
    b = swing_pl[cols].rename(
        columns={"pct_2022": "pl_2022", "pct_2026": "pl_2026", "swing_pp": "swing_pl_pp"}
    )
    out = a.merge(b, on=CHAVE, how="outer", validate="1:1", indicator=True)
    if (out["_merge"] != "both").any():
        raise ValueError("swing do PT e do PL com bases de municípios diferentes")
    out = out.drop(columns="_merge")
    out["delta_margem_pp"] = (out["pl_2026"] - out["pt_2026"]) - (out["pl_2022"] - out["pt_2022"])
    return out


def delta_margem_agregado(
    swing_pt: pd.DataFrame, swing_pl: pd.DataFrame, grupo: str | None = None
) -> pd.DataFrame:
    """Δmargem AGREGADA (ponderada): soma de votos ÷ soma de válidos, nos dois anos.

    Mesma base de municípios para PT e PL (as duas tabelas vêm de `swing_municipal` sobre os
    mesmos pareados). `grupo=None` agrega tudo numa linha (`grupo` = "total"). Não é média do
    delta municipal.
    """
    if len(swing_pt) != len(swing_pl):
        raise ValueError("swing do PT e do PL com bases de municípios diferentes")
    chave = grupo or "_grupo"
    pt = swing_pt.assign(_grupo="total") if grupo is None else swing_pt
    pl = swing_pl.assign(_grupo="total") if grupo is None else swing_pl
    a = agregado_ponderado(pt, chave)[[chave, "pct_2022_agregado", "pct_2026_agregado"]]
    b = agregado_ponderado(pl, chave)[[chave, "pct_2022_agregado", "pct_2026_agregado"]]
    m = a.merge(b, on=chave, suffixes=("_pt", "_pl"), validate="1:1")
    out = pd.DataFrame(
        {
            chave: m[chave],
            "pt_2022": m["pct_2022_agregado_pt"],
            "pt_2026": m["pct_2026_agregado_pt"],
            "pl_2022": m["pct_2022_agregado_pl"],
            "pl_2026": m["pct_2026_agregado_pl"],
        }
    )
    out["swing_pt_pp"] = out["pt_2026"] - out["pt_2022"]
    out["swing_pl_pp"] = out["pl_2026"] - out["pl_2022"]
    out["delta_margem_pp"] = (out["pl_2026"] - out["pt_2026"]) - (out["pl_2022"] - out["pt_2022"])
    return out.rename(columns={"_grupo": "grupo"}) if grupo is None else out


PERCENTIL_LADO_NEGATIVO = 95
PERCENTIL_LADO_POSITIVO = 99
"""Percentis que saturam a escala divergente do modo "Swing" do mapa (D-031).

Cada lado usa a distribuição dos PRÓPRIOS valores: o negativo é o p95 de |Δmargem| só entre
os municípios com Δmargem < 0; o positivo é o p99 só entre os com Δmargem > 0. Percentis da
distribuição inteira (D-030 usava p1/p99) misturam os dois sinais: como quase todo município
andou para o PL, o p1 inteiro era −0,05 p.p., e qualquer movimento para o PT saturava no
vermelho pleno (lado negativo ilegível)."""


def limites_escala_delta(delta_pp: pd.Series) -> tuple[float, float]:
    """(limite negativo, limite positivo) da escala do swing, um percentil POR LADO.

    - negativo = −p95(|Δ|) entre os municípios com Δ < 0;
    - positivo = p99(Δ) entre os municípios com Δ > 0.
    Zeros não entram em nenhum lado. Não espelha (os dois lados têm escalas diferentes).
    Sem valores de um dos lados, levanta erro: a escala divergente não faz sentido assim.
    """
    d = delta_pp.dropna().to_numpy(dtype=float)
    negativos = -d[d < 0]
    positivos = d[d > 0]
    if negativos.size == 0 or positivos.size == 0:
        raise ValueError("Δmargem sem valores dos dois lados de zero")
    neg = -float(np.percentile(negativos, PERCENTIL_LADO_NEGATIVO))
    pos = float(np.percentile(positivos, PERCENTIL_LADO_POSITIVO))
    return neg, pos
