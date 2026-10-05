import pytest
from coloraide import Color

from eleicao.cores import carregar_paleta, mistura_oklab, vencedor_margem

PALETA = carregar_paleta()


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


def test_vencedor_margem_empate_reduz_croma_mas_nao_zera():
    empate = vencedor_margem({13: 500, 22: 500}, PALETA)
    c_empate = Color(empate).convert("oklch")[1]
    c_pt = Color(PALETA[13]).convert("oklch")[1]
    # Empate (margem=0): croma cai para 15% do original, pela fórmula
    # documentada (tolerância pela quantização do hex intermediário).
    assert abs(c_empate - c_pt * 0.15) < 2e-3
    assert c_empate > 0  # nunca zera


def test_vencedor_margem_cresce_monotonicamente_com_a_margem():
    cores = [vencedor_margem({13: 500 + m, 22: 500 - m}, PALETA) for m in (0, 100, 300, 499)]
    cromas = [Color(c).convert("oklch")[1] for c in cores]
    assert cromas == sorted(cromas)
