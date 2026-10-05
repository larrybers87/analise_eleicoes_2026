"""Valida as 3 fontes mínimas da API do TSE (etapa 1 da coleta).

Baixa SOMENTE:
  1. config de municípios (`mun-e006257-cm.json`);
  2. resultado de Presidente Brasil (`br-c0001-e006257-u.json`);
  3. resultado de Presidente de Curitiba — o código TSE do município é obtido
     a partir do JSON de configuração já baixado (nunca hardcoded).

Cada arquivo só é baixado uma vez: se já existe em `data/raw/`, o cache é usado
(use `--force` para refazer). Se qualquer requisição retornar 404, o script
para imediatamente e mostra a URL exata tentada — nunca tenta variações.

Uso:
    python scripts/validar_fontes.py [--force]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from eleicao import config  # noqa: E402
from eleicao.tse_client import (  # noqa: E402
    TseAbortadoPor404Error,
    TseArquivoNaoEncontradoError,
    TseBloqueadoError,
    TseClient,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def _codigo_municipio_capital(config_municipios: dict, uf: str, nome: str) -> str:
    """Busca o código TSE (5 dígitos) de um município pelo JSON de config já baixado.

    Usa o campo `c` (="s" para a capital) e o nome como confirmação — nunca
    chuta/hardcoda o código.
    """
    uf = uf.lower()
    for abrangencia in config_municipios["abr"]:
        if abrangencia["cd"] != uf:
            continue
        for municipio in abrangencia["mu"]:
            if municipio.get("c") == "s" and municipio["nm"] == nome.upper():
                return municipio["cd"]
        raise ValueError(f"capital '{nome}' não encontrada na UF '{uf}' no arquivo de config")
    raise ValueError(f"UF '{uf}' não encontrada no arquivo de config")


async def _baixar_ou_abortar(cliente: TseClient, caminho: str, *, force: bool) -> Path:
    try:
        return await cliente.baixar(caminho, force=force)
    except TseArquivoNaoEncontradoError:
        print(f"ERRO: 404 ao baixar {config.url(caminho)}", file=sys.stderr)
        print("Parando imediatamente — nenhuma variação de URL será tentada.", file=sys.stderr)
        raise
    except TseBloqueadoError as exc:
        print(f"ERRO: {exc}", file=sys.stderr)
        raise
    except TseAbortadoPor404Error as exc:
        print(f"ERRO: {exc}", file=sys.stderr)
        raise


async def main(force: bool) -> int:
    eleicao = config.ELEICAO_FEDERAL_T1

    async with TseClient() as cliente:
        # 1. config de municípios
        caminho_cfg = config.caminho_config_municipios(eleicao)
        logger.info("baixando config de municípios: %s", config.url(caminho_cfg))
        local_cfg = await _baixar_ou_abortar(cliente, caminho_cfg, force=force)
        config_municipios = json.loads(local_cfg.read_text(encoding="utf-8"))

        # 2. resultado Presidente Brasil
        caminho_br = config.caminho_resultado(eleicao, config.CARGO_PRESIDENTE, "br")
        logger.info("baixando resultado Presidente Brasil: %s", config.url(caminho_br))
        local_br = await _baixar_ou_abortar(cliente, caminho_br, force=force)

        # 3. resultado Presidente Curitiba — código obtido do config, não hardcoded
        cd_curitiba = _codigo_municipio_capital(config_municipios, "pr", "CURITIBA")
        logger.info("código TSE de Curitiba (do config): %s", cd_curitiba)
        caminho_cwb = config.caminho_resultado(eleicao, config.CARGO_PRESIDENTE, "pr", cd_curitiba)
        logger.info("baixando resultado Presidente Curitiba: %s", config.url(caminho_cwb))
        local_cwb = await _baixar_ou_abortar(cliente, caminho_cwb, force=force)

    for rotulo, caminho in (
        ("config municípios", local_cfg),
        ("Presidente BR", local_br),
        ("Presidente Curitiba", local_cwb),
    ):
        tamanho = caminho.stat().st_size
        print(f"OK  {rotulo:22s} {caminho}  ({tamanho:,} bytes)")

    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--force", action="store_true", help="rebaixa mesmo se o arquivo já existir em data/raw/"
    )
    args = parser.parse_args()
    try:
        codigo_saida = asyncio.run(main(args.force))
    except (TseArquivoNaoEncontradoError, TseBloqueadoError, TseAbortadoPor404Error):
        sys.exit(1)
    sys.exit(codigo_saida)
