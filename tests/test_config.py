from eleicao import config as c


def test_url_presidente_br():
    assert c.caminho_resultado(c.ELEICAO_FEDERAL_T1, c.CARGO_PRESIDENTE, "br") == (
        "/oficial/ele2026/6257/dados/br/br-c0001-e006257-u.json"
    )


def test_url_municipio_preenche_zeros():
    assert c.caminho_resultado(6257, 1, "AC", "1120") == (
        "/oficial/ele2026/6257/dados/ac/ac01120-c0001-e006257-u.json"
    )


def test_config_municipios():
    assert c.caminho_config_municipios(6257) == "/oficial/ele2026/6257/config/mun-e006257-cm.json"
