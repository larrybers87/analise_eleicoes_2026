"""Cor do mapa de resultados — mistura ponderada em OKLab (docs/DECISOES.md D-004, D-013, D-014).

Dois modos de colorir uma região (município/UF/zona) a partir dos votos
válidos dos candidatos nela:

- `mistura_oklab`: média ponderada pelos votos, em OKLab (espaço
  perceptualmente uniforme — mistura em RGB puro gera tons barrentos/
  acinzentados de forma não intuitiva). Com 3+ candidatos fortes tende a
  cinza (ver ressalva em D-004); é por isso que existe o segundo modo.
- `vencedor_margem`: cor do candidato vencedor, interpolada em OKLab entre
  um tom neutro claro (margem apertada) e a cor plena do vencedor (margem
  folgada), com teto em `MARGEM_SATURACAO` (fórmula exata no docstring da
  função). Mantém a região legível mesmo quando a mistura ponderada
  colapsaria para cinza.

A paleta fixa por candidato (`{nr_candidato: cor_hex}`) vem de
`config/candidatos.yaml` (`carregar_paleta`). Brancos, nulos e abstenção
NÃO entram em nenhuma das duas funções — são métricas separadas (ver
`presidente_t1_*_totais.parquet`); quem monta o dict `votos_por_candidato`
deve passar só votos válidos por candidato.

Também expõe `simular_daltonismo`/`distancia_oklab`, usados no preview
(`notebooks/01_paleta.ipynb`) para verificar a distinguibilidade de PT/PL e
dos 3º/4º/5º colocados sob deuteranopia/protanopia, e `agrupar_outros`/
`COR_OUTROS`, usados para a categoria agregada "Outros" em gráficos/
legendas (NÃO no mapa — ver docstring de `agrupar_outros`).
"""

from __future__ import annotations

from pathlib import Path

import yaml
from coloraide import Color

from . import config as _config

CAMINHO_PALETA = _config.RAIZ / "config" / "candidatos.yaml"

FAIXA_RESERVADA_PT_PL = (260.0, 30.0)
"""Faixa de matiz (graus, OKLCH) reservada para a mistura PT×PL — nenhum
outro candidato pode ter `h` dentro dela (D-014). A faixa cruza o ponto
0°/360°: vai de `FAIXA_RESERVADA_PT_PL[0]` (260°) até 360°, depois de 0°
até `FAIXA_RESERVADA_PT_PL[1]` (30°).

Calculada varrendo `mistura_oklab` entre PL (`#306adb`) e PT (`#d01f17`) de
0% a 100% em passos finos e convertendo cada ponto para OKLCH: o matiz
percorrido vai de H=261,92° (PL puro) a H=29,04° (PT puro),
monotonicamente, passando por roxo/magenta/rosa — nunca por verde/amarelo
(ver `config/candidatos.yaml`). Os limites acima (260°/30°) arredondam esse
intervalo medido (261,92°–29,04°) para fora por ~2° de margem de segurança,
para não colar exatamente na borda medida e sobrar folga para
arredondamento de ponto flutuante/ajuste de gamute."""


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


MARGEM_SATURACAO = 0.40
"""Margem (fração dos votos do vencedor sobre o 2º colocado, 0 a ~1) a
partir da qual `vencedor_margem` já devolve a cor plena do vencedor.

Escolha de design (D-014): 40 pontos percentuais foi escolhido para que
vitórias "confortáveis" (ainda bem longe de unanimidade) já leiam como cor
plena no mapa — o regime de atenuação (tom claro → cor plena) fica
reservado para as disputas de fato apertadas (margem < 40pp), que são o
caso mais informativo de diferenciar visualmente região a região. Acima de
40pp, diferenças adicionais de margem (ex. 60pp vs 95pp) já não mudam a cor
— achamos que a granularidade de cor não precisa escalar até unanimidade
para ser útil, e um teto evita que a maior parte do mapa fique "desbotada"
numa eleição polarizada como a de 2026 (PT×PL, margens nacionais na casa de
poucos pontos percentuais — ver `presidente_t1_br.parquet`)."""

NEUTRO_EMPATE_OKLAB = (0.92, 0.0, 0.0)
"""Tom usado por `vencedor_margem` quando margem=0 (empate exato): OKLab
`L=0.92` (claro, próximo do branco mas não puro — ainda se distingue do
fundo branco de uma página/mapa), `a=b=0` (perfeitamente acromático, C=0).
Por ser acromático, esse tom não carrega nenhum traço do matiz do
"vencedor" do empate — ver docstring de `vencedor_margem`."""

NEUTRO_EMPATE_HEX = _hex_de_oklab(*NEUTRO_EMPATE_OKLAB)

COR_OUTROS_OKLAB = (0.6, 0.0, 0.0)
"""Cinza médio (OKLab `L=0.6`, acromático) usado para a categoria agregada
"Outros" em gráficos/legendas (`agrupar_outros`). Deliberadamente diferente
de `NEUTRO_EMPATE_OKLAB`: aquele é um tom claro "lavado" que sinaliza
"empate/sem distinção" num mapa; este é um cinza de leitura normal para uma
barra/fatia de legenda comum, não deve parecer "apagado"."""

COR_OUTROS = _hex_de_oklab(*COR_OUTROS_OKLAB)


def vencedor_margem(votos_por_candidato: dict[int, int], paleta: dict[int, str]) -> str:
    """Cor do vencedor (quem tem mais votos no dict), interpolada pela margem.

    `votos_por_candidato`: `{nr_candidato: votos}`, só votos válidos (mesma
    regra de `mistura_oklab`).

    Fórmula (determinística, interpolação linear em OKLab entre o tom
    neutro `NEUTRO_EMPATE_OKLAB` e a cor do vencedor na paleta):

        margem = (votos_1º - votos_2º) / total_votos        # 0 (empate) .. ~1 (quase unânime)
        r      = clamp(margem / MARGEM_SATURACAO, 0, 1)      # MARGEM_SATURACAO = 0.40
        L'     = L_neutro + r * (L_vencedor - L_neutro)
        a'     = a_neutro + r * (a_vencedor - a_neutro)       # a_neutro = 0
        b'     = b_neutro + r * (b_vencedor - b_neutro)       # b_neutro = 0

    Essa única interpolação já cobre os dois regimes: em `r=0` (margem=0,
    empate exato), o resultado é exatamente `NEUTRO_EMPATE_HEX` — e a cor do
    vencedor *nem entra na conta* nesse ponto (o termo `r * (a_vencedor -
    a_neutro)` zera quando `r=0`, não importa o valor de `a_vencedor`), por
    isso dois empates exatos entre candidatos diferentes sempre dão a MESMA
    cor neutra, sem viés de matiz para nenhum lado (ver
    `tests/test_cores.py::test_vencedor_margem_empate_e_igual_para_qualquer_par`).
    Em `r=1` (margem >= `MARGEM_SATURACAO`), o resultado é exatamente
    `paleta[vencedor]` — não precisa de um `if` separado para "cor plena",
    o clamp de `r` a 1 já produz isso.

    "Claro = margem apertada, escuro = margem folgada": como
    `NEUTRO_EMPATE_OKLAB` tem `L=0.92`, mais claro que qualquer cor da
    paleta (as cores de `config/candidatos.yaml` têm `L` entre ~0.35 e
    ~0.68), a interpolação sempre vai de claro (`r=0`) para mais escuro
    (`r=1`, a cor plena do vencedor) — nunca o contrário.
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
    r = max(0.0, min(1.0, margem / MARGEM_SATURACAO))

    l_v, a_v, b_v = _oklab(paleta[nr_vencedor])
    l_n, a_n, b_n = NEUTRO_EMPATE_OKLAB

    l_final = l_n + r * (l_v - l_n)
    a_final = a_n + r * (a_v - a_n)
    b_final = b_n + r * (b_v - b_n)

    return _hex_de_oklab(l_final, a_final, b_final)


def agrupar_outros(
    votos_por_candidato: dict[int, int], limiar: float = 0.01
) -> dict[int | str, int]:
    """Agrupa candidatos com menos de `limiar` (fração do total do dict) em `"outros"`.

    Uso: gráficos/legendas — NÃO o mapa. `mistura_oklab`/`vencedor_margem`
    continuam recebendo os votos de TODOS os candidatos individualmente;
    agrupar antes mudaria o resultado da mistura ponderada (perderia peso
    de voto real, mesmo que pequeno). `agrupar_outros` serve só para reduzir
    o número de fatias/barras numa legenda ou gráfico de barras.

    `limiar` é relativo ao total do próprio dict recebido (não a um total
    nacional fixo), então a função funciona em qualquer recorte — Brasil,
    UF, município, ou qualquer agregação que o chamador já tenha montado.

    Retorna um novo dict: candidatos com `votos / total >= limiar` mantêm a
    própria chave (`nr_candidato`); os demais são somados sob a chave string
    `"outros"` (ausente do dict de saída se nenhum candidato ficar abaixo de
    `limiar`). A soma de todos os valores do dict retornado é sempre igual à
    soma de `votos_por_candidato` — nenhum voto é descartado, só reagrupado.
    Use `COR_OUTROS` como cor da fatia/barra `"outros"`.
    """
    total = sum(votos_por_candidato.values())
    if total <= 0:
        raise ValueError("soma de votos_por_candidato deve ser positiva")

    agrupado: dict[int | str, int] = {}
    outros = 0
    for nr, votos in votos_por_candidato.items():
        if votos < 0:
            raise ValueError(f"votos negativos para o candidato {nr}")
        if votos / total < limiar:
            outros += votos
        else:
            agrupado[nr] = votos
    if outros > 0:
        agrupado["outros"] = outros
    return agrupado


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
