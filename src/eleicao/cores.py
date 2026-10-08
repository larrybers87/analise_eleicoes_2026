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

Para o modo "candidato selecionado" do mapa (D-018) expõe ainda
`escala_forca`/`escala_forca_neutra`/`rampa_oklab`: os STOPS hex de uma rampa
sequencial (claro → cor do candidato) interpolada em OKLab, que o front-end
só posiciona — nunca recalcula. Ver `N_STOPS_ESCALA` para o motivo de serem
vários stops e não só as duas pontas.

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


N_STOPS_ESCALA = 7
"""Número de stops (cores intermediárias) de uma rampa sequencial exportada.

Motivo de exportar vários stops em vez de só as duas pontas: o `interpolate`
do MapLibre (e o `linear-gradient` do CSS) interpolam em **sRGB**, não em
OKLab. Com 2 pontos a rampa sai "suja" (passa por tons barrentos e com
luminosidade irregular); com 7 pontos pré-calculados em OKLab o erro de cada
segmento fica pequeno o bastante para não se notar. Mesma lógica já aplicada
em `ESCALA_MARGEM_PP`/`escala_margem` (`scripts/exportar_web.py`, D-016 item
4) — aqui ela vale para a escala de "força" (D-018)."""

FRACOES_ESCALA = [i / (N_STOPS_ESCALA - 1) for i in range(N_STOPS_ESCALA)]
"""Posições dos stops como fração do valor máximo da escala (0 .. 1).

O valor máximo em si é dado (percentil 98 do candidato, ver
`eleicao.forca.escala_maxima`); quem desenha a legenda/o mapa multiplica
estas frações pelo máximo para saber em que % cada stop fica."""

ESCALA_NEUTRA_FIM_OKLAB = (0.28, 0.0, 0.0)
"""Ponta escura da ESCALA SEQUENCIAL NEUTRA ÚNICA, compartilhada pelos 7
candidatos de cor acromática (grupo `menor` de `config/candidatos.yaml`,
<1% dos válidos — D-014 item 3).

Por que uma escala só para os 7, e não uma rampa `claro → cinza-dele` por
candidato: a cor desses candidatos é cinza com `L` entre 0,35 e 0,77 e croma
ZERO. Uma rampa de `NEUTRO_EMPATE_OKLAB` (L=0,92) até, por exemplo, `#b4b4b4`
(L=0,77) varre 0,15 de luminosidade e nenhum matiz — é praticamente invisível
num mapa, e as rampas dos 7 seriam versões truncadas umas das outras (a de
L=0,35 contendo a de L=0,42 e assim por diante), o que torna impossível ler a
legenda de um sem confundir com a do outro. Com uma escala única de L=0,92 a
L=0,28 (faixa de 0,64, mais ampla que a de qualquer candidato colorido), a
intensidade fica legível para todos os 7; a identidade do candidato vem do
seletor/legenda, não do matiz. Acromática também por coerência com D-014:
escala de cinza é CVD-safe por definição."""

ESCALA_NEUTRA_FIM_HEX = _hex_de_oklab(*ESCALA_NEUTRA_FIM_OKLAB)


def eh_acromatico(cor_hex: str, tolerancia: float = 2e-3) -> bool:
    """`True` se a cor tem croma ~0 em OKLCH (cinza puro) — ver `escala_forca`."""
    return Color(cor_hex).convert("oklch")[1] < tolerancia


def rampa_oklab(
    inicio_oklab: tuple[float, float, float],
    fim_oklab: tuple[float, float, float],
    n: int = N_STOPS_ESCALA,
) -> list[str]:
    """`n` stops hex interpolados LINEARMENTE EM OKLab entre duas pontas.

    `rampa_oklab(a, b, n)[0]` é exatamente `a` convertido para hex e
    `[-1]` exatamente `b` — as pontas nunca são aproximadas (os coeficientes
    de interpolação são 0 e 1 exatos), o que é o que permite exigir, no teste,
    que o último stop seja idêntico ao hex de `config/candidatos.yaml`.
    """
    if n < 2:
        raise ValueError("uma rampa precisa de pelo menos 2 stops")
    stops = []
    for i in range(n):
        t = i / (n - 1)
        componentes = [
            ini + t * (fim - ini) for ini, fim in zip(inicio_oklab, fim_oklab, strict=True)
        ]
        stops.append(_hex_de_oklab(*componentes))
    return stops


def escala_forca(nr: int, paleta: dict[int, str], n: int = N_STOPS_ESCALA) -> list[str]:
    """Stops da escala sequencial de "força" (% dos válidos) do candidato `nr`.

    Vai de `NEUTRO_EMPATE_OKLAB` (0% dos válidos — mesma âncora clara do modo
    "vencedor + margem", para os dois modos lerem como a mesma família de
    rampa) até a cor plena do candidato na paleta (valor máximo da escala, ver
    `eleicao.forca.escala_maxima`; acima disso satura).

    Exceção dos 7 candidatos acromáticos (`eh_acromatico`): devolvem a ESCALA
    NEUTRA ÚNICA compartilhada (`escala_forca_neutra`) em vez de uma rampa
    própria — motivo em `ESCALA_NEUTRA_FIM_OKLAB`.
    """
    if nr not in paleta:
        raise KeyError(f"candidato {nr} não está na paleta recebida")
    cor = paleta[nr]
    fim = ESCALA_NEUTRA_FIM_OKLAB if eh_acromatico(cor) else _oklab(cor)
    return rampa_oklab(NEUTRO_EMPATE_OKLAB, fim, n)


def escala_forca_neutra(n: int = N_STOPS_ESCALA) -> list[str]:
    """A escala sequencial neutra única dos candidatos acromáticos (D-018)."""
    return rampa_oklab(NEUTRO_EMPATE_OKLAB, ESCALA_NEUTRA_FIM_OKLAB, n)


N_STOPS_LADO_DIVERGENTE = 5
"""Stops de CADA lado da escala divergente (o neutro do centro é compartilhado: 2×5−1 = 9)."""


def escala_divergente_assimetrica(
    limite_negativo: float,
    limite_positivo: float,
    cor_negativo: str,
    cor_positivo: str,
    n_lado: int = N_STOPS_LADO_DIVERGENTE,
) -> list[tuple[float, str]]:
    """Escala divergente com centro em 0 e limites DIFERENTES em cada lado (D-030).

    Devolve `[(valor, hex), ...]` em ordem crescente de valor, com `2*n_lado - 1` stops:
    - lado negativo: `n_lado` stops de `cor_negativo` (em `limite_negativo`) até
      `NEUTRO_EMPATE_HEX` (em 0), interpolados linearmente em OKLab, com os valores
      igualmente espaçados entre `limite_negativo` e 0;
    - lado positivo: de `NEUTRO_EMPATE_HEX` (em 0) até `cor_positivo` (em `limite_positivo`).

    Valor 0 é EXATAMENTE o neutro ("sem mudança"). Os limites não são espelhados: cada lado
    satura no seu próprio extremo (ex.: p1 e p99 do dado), porque a distribuição do swing
    2022→2026 é muito assimétrica. Quem desenha a legenda precisa mostrar os dois limites.
    """
    if not limite_negativo < 0 < limite_positivo:
        raise ValueError("precisa de limite_negativo < 0 < limite_positivo")
    if n_lado < 2:
        raise ValueError("cada lado precisa de pelo menos 2 stops")
    neg = rampa_oklab(_oklab(cor_negativo), NEUTRO_EMPATE_OKLAB, n_lado)
    pos = rampa_oklab(NEUTRO_EMPATE_OKLAB, _oklab(cor_positivo), n_lado)
    passos = [i / (n_lado - 1) for i in range(n_lado)]
    valores_neg = [limite_negativo * (1 - t) for t in passos]  # limite_negativo .. 0
    valores_pos = [limite_positivo * t for t in passos]  # 0 .. limite_positivo
    valores_neg[-1] = 0.0
    valores_pos[0] = 0.0
    return list(zip(valores_neg, neg, strict=True)) + list(
        zip(valores_pos[1:], pos[1:], strict=True)
    )


COR_ERRO_NEGATIVO_OKLCH = (0.50, 0.09, 195.0)
COR_ERRO_POSITIVO_OKLCH = (0.52, 0.11, 60.0)
"""Pontas da escala divergente de ERRO (previsto − real) da página de projeção (D-036).

Petróleo (h=195°) para erro negativo e marrom (h=60°) para positivo, à moda da BrBG
do ColorBrewer. Ficam fora da faixa de matiz da mistura PT×PL (260°→30°, roxos e
magentas: `FAIXA_RESERVADA_PT_PL`) e longe do azul do PL e do vermelho do PT, para que
"erro" não seja lido como "partido". Croma moderado (0,09–0,11) e luminosidade parecida
nas duas pontas: o sinal se lê pelo matiz e a intensidade, pela distância ao neutro.
Distinguíveis em deutan, protan e tritan (`tests/test_cores.py`)."""

COR_ERRO_NEGATIVO = (
    Color("oklch", list(COR_ERRO_NEGATIVO_OKLCH)).convert("srgb").fit("srgb").to_string(hex=True)
)
COR_ERRO_POSITIVO = (
    Color("oklch", list(COR_ERRO_POSITIVO_OKLCH)).convert("srgb").fit("srgb").to_string(hex=True)
)


def cor_divergente_simetrica(
    valor: float, limite: float, cor_negativo: str, cor_positivo: str
) -> str:
    """Cor de `valor` numa escala divergente simétrica `[-limite, +limite]` com centro neutro.

    Interpola LINEARMENTE EM OKLab entre `NEUTRO_EMPATE_OKLAB` (valor 0) e a ponta do
    lado do sinal (valor ±limite); acima do limite, satura na ponta. Os stops de legenda
    da mesma escala saem de `escala_divergente_assimetrica(-limite, limite, ...)`, que usa
    a mesma interpolação, então mapa e legenda coincidem.
    """
    if limite <= 0:
        raise ValueError("limite precisa ser positivo")
    t = min(abs(valor) / limite, 1.0)
    fim = _oklab(cor_negativo if valor < 0 else cor_positivo)
    return _hex_de_oklab(*(n + t * (f - n) for n, f in zip(NEUTRO_EMPATE_OKLAB, fim, strict=True)))


def luminosidade_oklab(cor_hex: str) -> float:
    """`L` de OKLab de uma cor hex (0 = preto, 1 = branco). Usado nos testes de rampa."""
    return _oklab(cor_hex)[0]


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
