import pytest
from coloraide import Color

from eleicao.cores import (
    COR_OUTROS,
    ESCALA_NEUTRA_FIM_HEX,
    FRACOES_ESCALA,
    MARGEM_SATURACAO,
    N_STOPS_ESCALA,
    NEUTRO_EMPATE_HEX,
    agrupar_outros,
    carregar_paleta,
    eh_acromatico,
    escala_forca,
    escala_forca_neutra,
    luminosidade_oklab,
    mistura_oklab,
    rampa_oklab,
    vencedor_margem,
)

PALETA = carregar_paleta()

ACROMATICOS = sorted(nr for nr, cor in PALETA.items() if eh_acromatico(cor))
COLORIDOS = sorted(nr for nr, cor in PALETA.items() if not eh_acromatico(cor))


def test_paleta_tem_12_candidatos():
    assert len(PALETA) == 12
    assert 13 in PALETA  # PT
    assert 22 in PALETA  # PL


def test_mistura_100_porcento_devolve_cor_exata_do_candidato():
    for nr, cor_hex in PALETA.items():
        resultado = mistura_oklab({nr: 1000}, PALETA)
        assert resultado == cor_hex


def test_mistura_50_50_pt_pl_bate_com_ponto_medio_calculado_independentemente():
    # Ponto médio em OKLab calculado aqui, sem chamar mistura_oklab, para não
    # testar a função contra ela mesma.
    l_pt, a_pt, b_pt = Color(PALETA[13]).convert("oklab")[:3]
    l_pl, a_pl, b_pl = Color(PALETA[22]).convert("oklab")[:3]
    esperado = Color("oklab", [(l_pt + l_pl) / 2, (a_pt + a_pl) / 2, (b_pt + b_pl) / 2]).convert(
        "srgb"
    )
    if not esperado.in_gamut():
        esperado = esperado.fit("srgb")
    esperado_hex = esperado.to_string(hex=True)

    resultado = mistura_oklab({13: 100, 22: 100}, PALETA)

    assert resultado == esperado_hex


def test_mistura_invariante_a_escala():
    a = mistura_oklab({13: 100, 22: 100}, PALETA)
    b = mistura_oklab({13: 1_000_000, 22: 1_000_000}, PALETA)
    assert a == b


def test_mistura_invariante_a_escala_com_proporcao_nao_trivial():
    a = mistura_oklab({13: 3, 22: 7, 70: 1}, PALETA)
    b = mistura_oklab({13: 300, 22: 700, 70: 100}, PALETA)
    assert a == b


def test_mistura_rejeita_candidato_fora_da_paleta():
    with pytest.raises(KeyError):
        mistura_oklab({999: 100}, PALETA)


def test_mistura_rejeita_soma_zero():
    with pytest.raises(ValueError):
        mistura_oklab({13: 0, 22: 0}, PALETA)


def test_vencedor_margem_um_candidato_devolve_cor_exata():
    assert vencedor_margem({13: 1000}, PALETA) == PALETA[13]


def test_vencedor_margem_margem_total_devolve_cor_exata():
    # 2º colocado com 0 votos -> margem = 1 (mesmo caso de "vitória total").
    assert vencedor_margem({13: 1000, 22: 0}, PALETA) == PALETA[13]


def test_vencedor_margem_escolhe_quem_tem_mais_votos():
    resultado = vencedor_margem({13: 100, 22: 900}, PALETA)
    # PL (22) venceu; a cor resultante deve ter (quase) o mesmo matiz (H) do
    # PL, não do PT. Tolerância folgada porque o resultado passa por hex
    # (quantização de 8 bits por canal) antes de voltar para OKLCH.
    h_pl = Color(PALETA[22]).convert("oklch")[2]
    h_resultado = Color(resultado).convert("oklch")[2]
    assert abs(h_pl - h_resultado) < 1.0


def test_vencedor_margem_empate_e_neutro():
    # Margem exatamente 0 -> tom neutro exato (NEUTRO_EMPATE_HEX), croma 0.
    empate = vencedor_margem({13: 500, 22: 500}, PALETA)
    assert empate == NEUTRO_EMPATE_HEX
    assert Color(empate).convert("oklch")[1] < 1e-6  # croma ~0


def test_vencedor_margem_empate_e_igual_para_qualquer_par():
    # Empate exato entre PT/PL e empate exato entre Cury/Renan devem dar a
    # MESMA cor neutra — a identidade do "vencedor" não pode vazar para o
    # resultado quando margem=0 (a fórmula nem usa a cor do vencedor nesse
    # ponto). Testa também as duas ordens de inserção do dict (o "vencedor"
    # detectado por sorted() pode mudar conforme a ordem em caso de empate).
    empate_pt_pl_a = vencedor_margem({13: 500, 22: 500}, PALETA)
    empate_pt_pl_b = vencedor_margem({22: 500, 13: 500}, PALETA)
    empate_outro_par = vencedor_margem({70: 500, 14: 500}, PALETA)

    assert empate_pt_pl_a == empate_pt_pl_b == empate_outro_par == NEUTRO_EMPATE_HEX


def test_vencedor_margem_teto_saturacao():
    # margem == MARGEM_SATURACAO (exatamente) -> já é a cor plena do vencedor.
    total = 1000
    diferenca = int(MARGEM_SATURACAO * total)
    votos_1 = (total + diferenca) // 2
    votos_2 = total - votos_1
    assert (votos_1 - votos_2) / total == pytest.approx(MARGEM_SATURACAO)

    resultado = vencedor_margem({13: votos_1, 22: votos_2}, PALETA)
    assert resultado == PALETA[13]


def test_vencedor_margem_cresce_monotonicamente_com_a_margem():
    cores = [vencedor_margem({13: 500 + m, 22: 500 - m}, PALETA) for m in (0, 100, 300, 499)]
    cromas = [Color(c).convert("oklch")[1] for c in cores]
    assert cromas == sorted(cromas)
    assert cromas[0] < 1e-6  # primeiro ponto (margem=0) é o tom neutro, croma ~0


def test_agrupar_outros_soma_bate_e_individualiza_maiores():
    # total=1000; candidatos 1 e 2 ficam >=1% (limiar padrão); 3,4,5 somam <1% cada.
    votos = {1: 500, 2: 480, 3: 9, 4: 7, 5: 4}
    agrupado = agrupar_outros(votos)

    assert sum(agrupado.values()) == sum(votos.values())
    assert agrupado[1] == 500
    assert agrupado[2] == 480
    assert agrupado["outros"] == 9 + 7 + 4
    assert 3 not in agrupado and 4 not in agrupado and 5 not in agrupado


def test_agrupar_outros_sem_ninguem_abaixo_do_limiar():
    votos = {1: 600, 2: 400}
    agrupado = agrupar_outros(votos)
    assert agrupado == votos
    assert "outros" not in agrupado


def test_agrupar_outros_rejeita_soma_zero():
    with pytest.raises(ValueError):
        agrupar_outros({1: 0, 2: 0})


def test_cor_outros_e_acromatica():
    assert Color(COR_OUTROS).convert("oklch")[1] < 1e-6


# ============ escala sequencial de "força" do candidato (D-018) ==============


def test_grupos_da_paleta_batem_com_o_esperado():
    # 5 candidatos com cor (PT, PL e os 3 "secundario") + 7 cinzas (<1%).
    assert len(COLORIDOS) == 5
    assert len(ACROMATICOS) == 7
    assert set(COLORIDOS) == {13, 22, 70, 14, 55}


@pytest.mark.parametrize("nr", sorted(PALETA))
def test_escala_forca_tem_luminosidade_estritamente_monotonica(nr):
    # Claro -> escuro, do primeiro ao último stop, SEM "voltar" em nenhum
    # segmento (não precisa ser linear, mas precisa ser monotônica — é o que
    # garante que um % maior nunca pareça "mais claro" no mapa).
    stops = escala_forca(nr, PALETA)
    assert len(stops) == N_STOPS_ESCALA
    lums = [luminosidade_oklab(c) for c in stops]
    assert all(a > b for a, b in zip(lums, lums[1:], strict=False)), lums


@pytest.mark.parametrize("nr", sorted(PALETA))
def test_escala_forca_comeca_na_ancora_clara_neutra(nr):
    assert escala_forca(nr, PALETA)[0] == NEUTRO_EMPATE_HEX


@pytest.mark.parametrize("nr", COLORIDOS)
def test_escala_forca_termina_na_cor_cheia_do_candidato(nr):
    # hex IDÊNTICO ao de config/candidatos.yaml — nada de "aproximadamente".
    assert escala_forca(nr, PALETA)[-1] == PALETA[nr]


@pytest.mark.parametrize("nr", ACROMATICOS)
def test_candidatos_cinza_compartilham_a_mesma_escala_neutra(nr):
    # Os 7 <1% não ganham rampa própria (uma rampa clara -> cinza-dele seria
    # invisível e as 7 seriam versões truncadas umas das outras): todos usam a
    # ESCALA NEUTRA ÚNICA, que termina mais escuro que qualquer um deles.
    assert escala_forca(nr, PALETA) == escala_forca_neutra()
    assert escala_forca(nr, PALETA)[-1] != PALETA[nr]


def test_escala_neutra_unica_extremos_e_monotonicidade():
    stops = escala_forca_neutra()
    assert len(stops) == N_STOPS_ESCALA
    assert stops[0] == NEUTRO_EMPATE_HEX
    assert stops[-1] == ESCALA_NEUTRA_FIM_HEX
    lums = [luminosidade_oklab(c) for c in stops]
    assert all(a > b for a, b in zip(lums, lums[1:], strict=False)), lums
    # acromática em toda a extensão (CVD-safe por definição — ver D-014)
    assert all(Color(c).convert("oklch")[1] < 1e-6 for c in stops)


def test_escala_neutra_e_mais_escura_que_qualquer_candidato_cinza():
    fim = luminosidade_oklab(ESCALA_NEUTRA_FIM_HEX)
    assert all(fim < luminosidade_oklab(PALETA[nr]) for nr in ACROMATICOS)


def test_fracoes_da_escala_vao_de_0_a_1_uniformemente():
    assert len(FRACOES_ESCALA) == N_STOPS_ESCALA
    assert FRACOES_ESCALA[0] == 0.0
    assert FRACOES_ESCALA[-1] == 1.0
    passos = [b - a for a, b in zip(FRACOES_ESCALA, FRACOES_ESCALA[1:], strict=False)]
    assert all(p == pytest.approx(passos[0]) for p in passos)


def test_rampa_oklab_respeita_as_pontas_exatas():
    inicio = (0.92, 0.0, 0.0)
    fim = (0.45, 0.1, -0.1)
    stops = rampa_oklab(inicio, fim, 5)
    assert len(stops) == 5
    assert stops[0] == Color("oklab", list(inicio)).convert("srgb").to_string(hex=True)
    esperado_fim = Color("oklab", list(fim))
    if not esperado_fim.in_gamut("srgb"):
        esperado_fim = esperado_fim.fit("srgb")
    assert stops[-1] == esperado_fim.convert("srgb").to_string(hex=True)


def test_rampa_oklab_rejeita_menos_de_2_stops():
    with pytest.raises(ValueError):
        rampa_oklab((0.9, 0, 0), (0.3, 0, 0), 1)


def test_escala_forca_rejeita_candidato_fora_da_paleta():
    with pytest.raises(KeyError):
        escala_forca(999, PALETA)


# ============ escala divergente assimétrica do swing (D-030) =================

from eleicao.cores import N_STOPS_LADO_DIVERGENTE, escala_divergente_assimetrica  # noqa: E402

ESCALA_SW = escala_divergente_assimetrica(-0.8, 27.0, PALETA[13], PALETA[22])


def test_divergente_tem_2n_menos_1_stops_e_valores_crescentes():
    assert len(ESCALA_SW) == 2 * N_STOPS_LADO_DIVERGENTE - 1
    valores = [v for v, _ in ESCALA_SW]
    assert all(a < b for a, b in zip(valores, valores[1:], strict=False))
    assert valores[0] == -0.8 and valores[-1] == 27.0


def test_divergente_zero_e_neutro_exato():
    centro = dict(ESCALA_SW)
    assert centro[0.0] == NEUTRO_EMPATE_HEX
    assert ESCALA_SW[N_STOPS_LADO_DIVERGENTE - 1] == (0.0, NEUTRO_EMPATE_HEX)


def test_divergente_pontas_com_hex_da_paleta():
    assert ESCALA_SW[0][1] == PALETA[13]
    assert ESCALA_SW[-1][1] == PALETA[22]


def test_divergente_luminosidade_monotonica_em_cada_lado():
    n = N_STOPS_LADO_DIVERGENTE
    lums = [luminosidade_oklab(c) for _, c in ESCALA_SW]
    neg, pos = lums[:n], lums[n - 1 :]
    assert all(a < b for a, b in zip(neg, neg[1:], strict=False)), neg  # escuro -> claro
    assert all(a > b for a, b in zip(pos, pos[1:], strict=False)), pos  # claro -> escuro


def test_divergente_limites_nao_sao_espelhados():
    valores = [v for v, _ in ESCALA_SW]
    assert valores[0] != -valores[-1]


def test_divergente_rejeita_limites_invalidos():
    with pytest.raises(ValueError):
        escala_divergente_assimetrica(0.0, 10.0, PALETA[13], PALETA[22])
    with pytest.raises(ValueError):
        escala_divergente_assimetrica(-1.0, 0.0, PALETA[13], PALETA[22])
