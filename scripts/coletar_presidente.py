"""Coleta completa do resultado de Presidente (EA20) via API do TSE.

Baixa, usando `TseClient` (rate limit, cache e retry já implementados em
`src/eleicao/tse_client.py`):

  1. config de municípios (`mun-e<eleicao>-cm.json`) — se ainda não estiver em
     `data/raw/`;
  2. resultado unificado do Brasil;
  3. resultado unificado de cada UF (as 27 + `zz`, todas a partir do próprio
     config — nunca hardcoded);
  4. resultado unificado de cada município/"cidade" (inclusive exterior),
     também a partir do config.

Idempotente: arquivos já presentes em `data/raw/` não são rebaixados (a menos
que `--force`). Log de contagens em `data/raw/coleta_<eleicao>.log`.

Uso:
    python scripts/coletar_presidente.py --eleicao 6257 [--force]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from dataclasses import dataclass
from pathlib import Path

from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from eleicao import config  # noqa: E402
from eleicao.tse_client import (  # noqa: E402
    TseAbortadoPor404Error,
    TseArquivoNaoEncontradoError,
    TseBloqueadoError,
    TseClient,
)

NUM_WORKERS = 10  # igual ao MAX_CONCORRENCIA do TseClient; não adianta ter mais

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Item:
    tipo: str  # "br" | "uf" | "mun"
    caminho: str
    uf: str | None = None
    cd_mun: str | None = None


def _configurar_log(eleicao: int) -> Path:
    caminho_log = config.DATA_RAW / f"coleta_{eleicao}.log"
    caminho_log.parent.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    manipulador_arquivo = logging.FileHandler(caminho_log, encoding="utf-8")
    manipulador_arquivo.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logging.getLogger().addHandler(manipulador_arquivo)
    return caminho_log


def _montar_itens(eleicao: int, config_municipios: dict) -> list[Item]:
    """Monta a lista de downloads SOMENTE a partir do config de municípios.

    Nunca gera UF/município fora de `config_municipios["abr"]`.
    """
    itens: list[Item] = [
        Item(tipo="br", caminho=config.caminho_resultado(eleicao, config.CARGO_PRESIDENTE, "br"))
    ]

    for abrangencia in config_municipios["abr"]:
        uf = abrangencia["cd"]  # já em minúsculas no config (ex.: "ac", "zz")
        itens.append(
            Item(
                tipo="uf",
                uf=uf,
                caminho=config.caminho_resultado(eleicao, config.CARGO_PRESIDENTE, uf),
            )
        )
        for municipio in abrangencia["mu"]:
            cd_mun = municipio["cd"]
            itens.append(
                Item(
                    tipo="mun",
                    uf=uf,
                    cd_mun=cd_mun,
                    caminho=config.caminho_resultado(eleicao, config.CARGO_PRESIDENTE, uf, cd_mun),
                )
            )
    return itens


class _Contadores:
    def __init__(self) -> None:
        self.ok = 0
        self.cache = 0
        self.erro_404 = 0
        self.erro_404_zz = 0
        self.erro = 0


async def _processar_item(
    cliente: TseClient,
    item: Item,
    *,
    force: bool,
    contadores: _Contadores,
    evento_abortar: asyncio.Event,
) -> None:
    if evento_abortar.is_set():
        return

    destino = config.caminho_local(item.caminho)
    era_cache = destino.exists() and not force

    try:
        await cliente.baixar(item.caminho, force=force)
    except TseArquivoNaoEncontradoError:
        if item.tipo == "uf" and item.uf == config.UF_EXTERIOR:
            # Caso previsto: pode não existir arquivo agregado de UF para o
            # exterior. Loga e continua — não é erro de construção de URL.
            contadores.erro_404_zz += 1
            logger.warning(
                "404 esperado para UF 'zz' (sem agregado de exterior?): %s",
                config.url(item.caminho),
            )
        else:
            contadores.erro_404 += 1
            logger.error(
                "404 inesperado (item vem do config, não deveria faltar): tipo=%s uf=%s "
                "cd_mun=%s caminho=%s",
                item.tipo,
                item.uf,
                item.cd_mun,
                config.url(item.caminho),
            )
        return
    except (TseBloqueadoError, TseAbortadoPor404Error) as exc:
        evento_abortar.set()
        contadores.erro += 1
        logger.critical("abortando coleta: %s", exc)
        raise
    except Exception:  # noqa: BLE001 — registra e contabiliza, mas não trava os outros workers
        contadores.erro += 1
        logger.exception(
            "erro inesperado em tipo=%s uf=%s cd_mun=%s caminho=%s",
            item.tipo,
            item.uf,
            item.cd_mun,
            item.caminho,
        )
        return

    if era_cache:
        contadores.cache += 1
    else:
        contadores.ok += 1


async def _worker(
    fila: asyncio.Queue[Item],
    cliente: TseClient,
    *,
    force: bool,
    contadores: _Contadores,
    evento_abortar: asyncio.Event,
    pbar: tqdm,
    excecao_fatal: list[BaseException],
) -> None:
    while True:
        try:
            item = fila.get_nowait()
        except asyncio.QueueEmpty:
            return

        if not evento_abortar.is_set():
            try:
                await _processar_item(
                    cliente,
                    item,
                    force=force,
                    contadores=contadores,
                    evento_abortar=evento_abortar,
                )
            except (TseBloqueadoError, TseAbortadoPor404Error) as exc:
                excecao_fatal.append(exc)
        pbar.update(1)
        fila.task_done()


async def main(eleicao: int, force: bool) -> int:
    caminho_log = _configurar_log(eleicao)
    logger.info("=== início da coleta: eleição %d (force=%s) ===", eleicao, force)

    async with TseClient() as cliente:
        caminho_cfg = config.caminho_config_municipios(eleicao)
        logger.info("garantindo config de municípios em cache: %s", config.url(caminho_cfg))
        local_cfg = await cliente.baixar(caminho_cfg)
        config_municipios = json.loads(local_cfg.read_text(encoding="utf-8"))

        itens = _montar_itens(eleicao, config_municipios)
        logger.info("total de itens a processar (BR + UFs + municípios): %d", len(itens))

        fila: asyncio.Queue[Item] = asyncio.Queue()
        for item in itens:
            fila.put_nowait(item)

        contadores = _Contadores()
        evento_abortar = asyncio.Event()
        excecao_fatal: list[BaseException] = []

        with tqdm(total=len(itens), desc="coletando Presidente 1T", unit="arq") as pbar:
            workers = [
                asyncio.create_task(
                    _worker(
                        fila,
                        cliente,
                        force=force,
                        contadores=contadores,
                        evento_abortar=evento_abortar,
                        pbar=pbar,
                        excecao_fatal=excecao_fatal,
                    )
                )
                for _ in range(NUM_WORKERS)
            ]
            await asyncio.gather(*workers)

    total = (
        contadores.ok
        + contadores.cache
        + contadores.erro_404
        + contadores.erro_404_zz
        + contadores.erro
    )
    resumo = (
        f"ok={contadores.ok} cache={contadores.cache} "
        f"404_zz={contadores.erro_404_zz} 404_outros={contadores.erro_404} "
        f"erro={contadores.erro} total_processado={total} total_esperado={len(itens)}"
    )
    logger.info("=== fim da coleta: %s ===", resumo)
    print(resumo)
    print(f"log completo em: {caminho_log}")

    if excecao_fatal:
        print(f"ERRO FATAL: {excecao_fatal[0]}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--eleicao", type=int, default=config.ELEICAO_FEDERAL_T1, help="código da eleição (TSE)"
    )
    parser.add_argument(
        "--force", action="store_true", help="rebaixa mesmo se o arquivo já existir em data/raw/"
    )
    args = parser.parse_args()
    sys.exit(asyncio.run(main(args.eleicao, args.force)))
