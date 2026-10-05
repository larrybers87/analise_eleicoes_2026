"""Cor do mapa de resultados — mistura ponderada em OKLab (docs/DECISOES.md D-004).

Dois modos de colorir uma região (município/UF/zona) a partir dos votos
válidos dos candidatos nela:

- `mistura_oklab`: média ponderada pelos votos, em OKLab (espaço
  perceptualmente uniforme — mistura em RGB puro gera tons barrentos/
  acinzentados de forma não intuitiva). Com 3+ candidatos fortes tende a
  cinza (ver ressalva em D-004); é por isso que existe o segundo modo.
- `vencedor_margem`: cor do candidato vencedor, com croma/luminosidade
  escalados pela margem sobre o 2º colocado (fórmula exata no docstring da
  função). Mantém a região legível mesmo quando a mistura ponderada
  colapsaria para cinza.

A paleta fixa por candidato (`{nr_candidato: cor_hex}`) vem de
`config/candidatos.yaml` (`carregar_paleta`). Brancos, nulos e abstenção
NÃO entram em nenhuma das duas funções — são métricas separadas (ver
`presidente_t1_*_totais.parquet`); quem monta o dict `votos_por_candidato`
deve passar só votos válidos por candidato.

Também expõe `simular_daltonismo`/`distancia_oklab`, usados no preview
(`notebooks/01_paleta.ipynb`) para verificar a distinguibilidade de PT/PL
sob deuteranopia/protanopia (regra (b) da tarefa de paleta).
"""

from __future__ import annotations

from pathlib import Path

import yaml
from coloraide import Color

from . import config as _config

CAMINHO_PALETA = _config.RAIZ / "config" / "candidatos.yaml"


def carregar_paleta(caminho: Path | None = None) -> dict[int, str]:
    """Carrega `{nr_candidato: cor_hex}` de `config/candidatos.yaml`.

    Só os candidatos listados em `candidatos:` entram no dict retornado —
    brancos/nulos/abstenção não têm `nr_candidato` e deliberadamente não
    aparecem em `config/candidatos.yaml` (ver `fora_da_mistura` no topo do
    arquivo e a regra (e) da tarefa de paleta).
    """
    caminho = caminho or CAMINHO_PALETA
    dados = yaml.safe_load(caminho.read_text(encoding="utf-8"))
    return {int(item["nr"]): str(item["cor_hex"]) for item in dados["candidatos"]}


def _oklab(cor_hex: str) -> tuple[float, float, float]:
    lum, a, b = Color(cor_hex).convert("oklab")[:3]
    return lum, a, b


def _hex_de_oklab(lum: float, a: float, b: float) -> str:
    cor = Color("oklab", [lum, a, b])
    if not cor.in_gamut("srgb"):
        cor = cor.fit("srgb")
    return cor.convert("srgb").to_string(hex=True)


def mistura_oklab(votos_por_candidato: dict[int, int], paleta: dict[int, str]) -> str:
    """Cor da mistura ponderada pelos votos, calculada em OKLab.

    `votos_por_candidato`: `{nr_candidato: votos}`, só votos válidos (sem
    brancos/nulos/abstenção — ver docstring do módulo). A ponderação de cada
    candidato é a proporção dos votos dele sobre o total do dict recebido
    (não sobre o eleitorado nem sobre os válidos da região inteira, caso o
    dict seja um subconjunto — quem chama decide o que entra na soma).

    Converte cada cor da paleta para OKLab (`L, a, b`), faz a média
    ponderada componente a componente, e converte o resultado de volta para
    sRGB hex (com ajuste de gamute, se necessário — raro, dado que a paleta
    já está dentro do gamute sRGB e a combinação convexa de pontos dentro do
    gamute tende a permanecer dentro dele, mas o gamute sRGB não é convexo
    em OKLab, então o ajuste existe por segurança).

    Caso-limite: 100% dos votos em um único candidato devolve exatamente a
    cor desse candidato na paleta (a média ponderada degenera no próprio
    ponto). O resultado é invariante à escala dos votos — só a *proporção*
    de cada candidato no dict importa, não os valores absolutos.
    """
    total = sum(votos_por_candidato.values())
    if total <= 0:
        raise ValueError("soma de votos_por_candidato deve ser positiva")

    l_acc = a_acc = b_acc = 0.0
    for nr, votos in votos_por_candidato.items():
        if votos < 0:
            raise ValueError(f"votos negativos para o candidato {nr}")
        if nr not in paleta:
            raise KeyError(f"candidato {nr} não está na paleta recebida")
        peso = votos / total
        lum, a, b = _oklab(paleta[nr])
        l_acc += peso * lum
        a_acc += peso * a
        b_acc += peso * b

    return _hex_de_oklab(l_acc, a_acc, b_acc)


def vencedor_margem(votos_por_candidato: dict[int, int], paleta: dict[int, str]) -> str:
    """Cor do vencedor (quem tem mais votos no dict), com intensidade pela margem.

    `votos_por_candidato`: `{nr_candidato: votos}`, só votos válidos (mesma
    regra de `mistura_oklab`).

    Fórmula (determinística, em OKLCH — luminosidade `L`, croma `C`, matiz
    `H` da cor do vencedor na paleta):

        margem = (votos_1º - votos_2º) / total_votos   # 0 (empate) .. ~1 (quase unânime)
        t      = clamp(margem, 0, 1)
        C'     = C * (0.15 + 0.85 * t)
        L'     = L + (1 - t) * (1 - L) * 0.5
        H'     = H                                      # matiz não muda

    Com `t=1` (só 1 candidato no dict, ou 2º colocado com 0 votos), `C'=C` e
    `L'=L`: devolve exatamente `paleta[vencedor]`. Com `t=0` (empate exato
    com o 2º colocado), o croma cai para 15% do original (nunca zero — um
    piso deliberado para a cor do vencedor continuar reconhecível mesmo numa
    vitória apertadíssima, em vez de colapsar para cinza) e a luminosidade
    sobe até a meio caminho do branco (fator 0,5, também deliberado: clareia
    visivelmente sem lavar a cor por completo). Os dois coeficientes (0.15 e
    0.5) são escolhas de design desta tarefa — não derivados de nenhuma
    norma — e podem ser recalibrados depois de ver o preview em
    `notebooks/01_paleta.ipynb`.
    """
    if not votos_por_candidato:
        raise ValueError("votos_por_candidato não pode ser vazio")
    total = sum(votos_por_candidato.values())
    if total <= 0:
        raise ValueError("soma de votos_por_candidato deve ser positiva")

    ordenado = sorted(votos_por_candidato.items(), key=lambda item: item[1], reverse=True)
    nr_vencedor, votos_1 = ordenado[0]
    votos_2 = ordenado[1][1] if len(ordenado) > 1 else 0
    if nr_vencedor not in paleta:
        raise KeyError(f"candidato {nr_vencedor} não está na paleta recebida")

    margem = (votos_1 - votos_2) / total
    t = max(0.0, min(1.0, margem))

    lum, c, h = Color(paleta[nr_vencedor]).convert("oklch")[:3]
    c_final = c * (0.15 + 0.85 * t)
    l_final = lum + (1 - t) * (1 - lum) * 0.5

    resultado = Color("oklch", [l_final, c_final, h])
    if not resultado.in_gamut("srgb"):
        resultado = resultado.fit("srgb")
    return resultado.convert("srgb").to_string(hex=True)


def simular_daltonismo(cor_hex: str, tipo: str = "deutan", severidade: float = 1.0) -> str:
    """Simula como uma cor apareceria para quem tem a deficiência `tipo`.

    `tipo`: `"deutan"` (deuteranopia/deuteranomalia) ou `"protan"`
    (protanopia/protanomalia) — as duas confusões vermelho-verde relevantes
    para a regra (b) da tarefa de paleta (distinguir PT de PL). `severidade`
    em `[0, 1]`: `1.0` = dicromacia completa (sem percepção do cone
    afetado), valores menores = anomalia (percepção reduzida, não ausente).

    Usa o filtro de deficiência de visão de cor já embutido na biblioteca
    `coloraide` (`coloraide.filters.cvd`), não uma implementação própria —
    a biblioteca já cobre os dois métodos citados nas instruções da tarefa:
    para `severidade=1.0` usa Viénot, Brettel & Mollon 1999 (dicromacia
    completa); para `severidade<1.0`, Machado, Oliveira & Fernandes 2009
    (anomalia, interpolado). Fonte:
    https://github.com/facelessuser/coloraide/blob/main/coloraide/filters/cvd.py
    """
    return (
        Color(cor_hex)
        .filter(tipo, severidade, space="srgb-linear", out_space="srgb")
        .to_string(hex=True)
    )


def distancia_oklab(cor_hex_1: str, cor_hex_2: str) -> float:
    """ΔE perceptual entre duas cores hex, calculado em OKLab (método "ok" do coloraide)."""
    return Color(cor_hex_1).delta_e(cor_hex_2, method="ok")
