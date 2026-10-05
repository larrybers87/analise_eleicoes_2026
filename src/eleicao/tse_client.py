"""Cliente HTTP assíncrono para a API de divulgação de resultados do TSE.

Implementa as regras anti-bloqueio da skill `tse-dados` (ver docs/DADOS.md):

- no máximo ~10 requisições/s, limite **global** ao cliente (não por worker/task);
- cache em disco em ``data/raw/`` (via :func:`eleicao.config.caminho_local`): se o
  arquivo já existe, não há requisição nova, a menos que ``force=True``;
- retry com backoff exponencial (``tenacity``), até 4 tentativas, **apenas** para
  erros 5xx e timeout;
- 404 nunca é retentado — é contado, e a execução inteira aborta se passar de 5
  no total (nunca "adivinhar" URLs: a lista de municípios vem do arquivo de
  config, então 404s indicam algo errado);
- 403/429 aborta IMEDIATAMENTE (limite de taxa do TSE: bloqueio de IP de ~10 min,
  renovável).

O conteúdo é gravado em disco exatamente como veio do servidor (bytes crus, sem
reformatar/reserializar JSON).
"""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path

import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from eleicao import config

logger = logging.getLogger(__name__)

USER_AGENT = "analise-eleicao-2026/0.1 (contato: uso pessoal/pesquisa)"
MAX_REQ_POR_SEGUNDO = 10.0
MAX_CONCORRENCIA = 10
MAX_404_ANTES_DE_ABORTAR = 5
TIMEOUT_SEGUNDOS = 30.0
MAX_TENTATIVAS = 4


class TseBloqueadoError(RuntimeError):
    """O TSE respondeu 403/429: provável limite de taxa atingido.

    Pare TODAS as requisições e aguarde pelo menos 10 minutos antes de tentar
    de novo (bloqueio de IP renovável — insistir só piora).
    """


class TseArquivoNaoEncontradoError(RuntimeError):
    """404 para um caminho específico. Não é retentado."""


class TseAbortadoPor404Error(RuntimeError):
    """Mais de MAX_404_ANTES_DE_ABORTAR respostas 404 na mesma execução.

    Provável URL errada ou lista de municípios/UFs inválida — nunca "adivinhar"
    URLs; monte a lista a partir do arquivo de config (mun-e006257-cm.json).
    """


def _eh_erro_retentavel(excecao: BaseException) -> bool:
    """Só timeout e 5xx são retentados; 404/403/429 nunca."""
    if isinstance(excecao, httpx.TimeoutException):
        return True
    if isinstance(excecao, httpx.HTTPStatusError):
        return excecao.response.status_code >= 500
    return False


class _LimitadorTaxaGlobal:
    """Garante intervalo mínimo global entre início de requisições.

    O limite é do cliente como um todo (todas as tasks concorrentes
    compartilham o mesmo limitador), não por worker individual.
    """

    def __init__(self, max_por_segundo: float = MAX_REQ_POR_SEGUNDO) -> None:
        self._intervalo_min = 1.0 / max_por_segundo
        self._lock = asyncio.Lock()
        self._proxima_liberacao = 0.0

    async def aguardar(self) -> None:
        async with self._lock:
            agora = time.monotonic()
            espera = self._proxima_liberacao - agora
            if espera > 0:
                await asyncio.sleep(espera)
                agora = time.monotonic()
            self._proxima_liberacao = agora + self._intervalo_min


class TseClient:
    """Cliente assíncrono com rate limit global, cache em disco e retry seletivo."""

    def __init__(self, max_por_segundo: float = MAX_REQ_POR_SEGUNDO) -> None:
        self._limitador = _LimitadorTaxaGlobal(max_por_segundo)
        self._semaforo = asyncio.Semaphore(MAX_CONCORRENCIA)
        self._cliente = httpx.AsyncClient(
            base_url=config.BASE_URL,
            timeout=TIMEOUT_SEGUNDOS,
            headers={"User-Agent": USER_AGENT},
        )
        self.contagem_404 = 0

    async def __aenter__(self) -> TseClient:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.fechar()

    async def fechar(self) -> None:
        await self._cliente.aclose()

    async def baixar(self, caminho: str, *, force: bool = False) -> Path:
        """Baixa ``caminho`` (path remoto, ex. ``config.caminho_resultado(...)``).

        Usa o espelho local em ``data/raw/`` como cache: se o arquivo já existe
        e ``force`` é ``False``, não faz nenhuma requisição HTTP. Retorna o
        ``Path`` do arquivo local (gravado com os bytes exatos da resposta).
        """
        destino = config.caminho_local(caminho)
        if destino.exists() and not force:
            logger.debug("cache hit: %s", destino)
            return destino

        conteudo = await self._requisitar_com_retry(caminho)
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(conteudo)
        logger.info("baixado: %s (%d bytes)", destino, len(conteudo))
        return destino

    @retry(
        retry=retry_if_exception(_eh_erro_retentavel),
        stop=stop_after_attempt(MAX_TENTATIVAS),
        wait=wait_exponential(multiplier=1, min=1, max=20),
        reraise=True,
    )
    async def _requisitar_com_retry(self, caminho: str) -> bytes:
        return await self._requisitar_uma_vez(caminho)

    async def _requisitar_uma_vez(self, caminho: str) -> bytes:
        async with self._semaforo:
            await self._limitador.aguardar()
            resposta = await self._cliente.get(caminho)

        if resposta.status_code in (403, 429):
            raise TseBloqueadoError(
                f"TSE respondeu {resposta.status_code} para {config.url(caminho)}. "
                "Limite de taxa provavelmente atingido: PARE todas as requisições "
                "e aguarde pelo menos 10 minutos antes de tentar de novo."
            )

        if resposta.status_code == 404:
            self.contagem_404 += 1
            logger.warning(
                "404 (%d/%d): %s", self.contagem_404, MAX_404_ANTES_DE_ABORTAR, config.url(caminho)
            )
            if self.contagem_404 > MAX_404_ANTES_DE_ABORTAR:
                raise TseAbortadoPor404Error(
                    f"Mais de {MAX_404_ANTES_DE_ABORTAR} 404s nesta execução "
                    f"(último: {config.url(caminho)}). Abortando para não arriscar "
                    "bloqueio de IP — confira se a lista de municípios/UFs vem do "
                    "arquivo de config, nunca gere URLs por adivinhação."
                )
            raise TseArquivoNaoEncontradoError(f"404: {config.url(caminho)}")

        resposta.raise_for_status()  # 5xx -> cai no retry; outros 4xx inesperados propagam
        return resposta.content
