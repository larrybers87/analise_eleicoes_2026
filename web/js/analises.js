/* Página de análises (F3 fase B, D-030). Vanilla JS + Observable Plot via CDN.
 *
 * REGRAS:
 * - Nenhum número vem digitado do HTML: todo <span data-v="chave"> recebe
 *   `analises.textos[chave]`, o texto JÁ FORMATADO em Python (scripts/exportar_analises.py).
 *   É esse texto que tests/test_exportar_analises.py confere contra docs/ANALISES.md.
 * - Nenhuma cor é calculada aqui: cores de candidato e de região vêm prontas do JSON.
 * - Os rótulos dos gráficos são números do próprio JSON, só formatados para exibição.
 */
'use strict';

(function () {
  const $ = (s) => document.querySelector(s);
  const fmt = (v, casas) =>
    v.toLocaleString('pt-BR', { minimumFractionDigits: casas, maximumFractionDigits: casas });
  const sinal = (v, casas) => (v > 0 ? '+' : v < 0 ? '−' : '') + fmt(Math.abs(v), casas);
  const celular = () => window.matchMedia('(max-width: 820px)').matches;

  let A = null; // analises.json
  let D = null; // analises_dispersao.json (sob demanda)
  let candDispersao = 'pt';

  async function obter(caminho) {
    const r = await fetch(caminho, { cache: 'no-cache' });
    if (!r.ok) throw new Error(`falha ao carregar ${caminho}: HTTP ${r.status}`);
    return r.json();
  }

  function largura(el) {
    return Math.max(280, Math.min(el.clientWidth || 640, 760));
  }

  function nomeCand(nr) {
    return A.candidatos[String(nr)].nome;
  }
  function corCand(nr) {
    return A.candidatos[String(nr)].cor;
  }

  // ------------------------------------------------------------ textos
  function preencherTextos() {
    document.querySelectorAll('[data-v]').forEach((el) => {
      const t = A.textos[el.dataset.v];
      el.textContent = t === undefined ? '?' : t;
      if (t === undefined) console.error('chave sem texto:', el.dataset.v);
    });
    const s = A.snapshot;
    const selo = $('#status-totalizacao');
    if (s.provisorio) {
      selo.textContent = 'Resultado provisório';
      selo.classList.add('parcial');
    } else {
      selo.textContent = 'Totalização final';
      selo.classList.remove('parcial');
      $('#nota-status').hidden = true;
    }
  }

  // ------------------------------------------------------------ gráficos
  function legendaCands(nrs) {
    return {
      legend: true,
      domain: nrs.map(nomeCand),
      range: nrs.map(corCand),
    };
  }

  function barrasAgrupadas(alvo, dados, grupo, opcoes) {
    const el = $(alvo);
    const w = largura(el);
    const nrs = [...new Set(dados.map((d) => d.nr))];
    const linhas = dados.map((d) => ({ ...d, nome: nomeCand(d.nr) }));
    const casas = opcoes.casas ?? 1;
    const rot = opcoes.sinal ? (d) => sinal(d.valor, casas) : (d) => fmt(d.valor, casas);
    el.replaceChildren(
      Plot.plot({
        width: w,
        height: opcoes.altura || 300,
        marginBottom: 46,
        marginLeft: 44,
        style: { fontFamily: 'inherit', fontSize: '12px' },
        fx: {
          label: null,
          padding: 0.18,
          domain: [...new Set(dados.map((d) => d[grupo]))], // ordem do JSON, não alfabética
          tickRotate: celular() && opcoes.girar ? -25 : 0,
        },
        x: { axis: null, domain: nrs.map(nomeCand), padding: 0.08 },
        y: { label: opcoes.rotuloY, grid: true, domain: opcoes.dominioY },
        color: legendaCands(nrs),
        marks: [
          Plot.ruleY([0], { stroke: '#555' }),
          Plot.barY(linhas, {
            fx: grupo,
            x: 'nome',
            y: 'valor',
            fill: 'nome',
            tip: { format: { fx: true, x: true, y: (v) => rot({ valor: v }), fill: false } },
          }),
          // rótulo acima da barra positiva e abaixo da negativa (dy é constante no Plot)
          ...[
            [(d) => d.valor >= 0, -6],
            [(d) => d.valor < 0, 10],
          ].map(([filtro, dy]) =>
            Plot.text(linhas, {
              filter: filtro,
              fx: grupo,
              x: 'nome',
              y: 'valor',
              text: rot,
              dy,
              fontSize: celular() ? 9 : 11,
              fill: '#1d2126',
            })
          ),
        ],
      })
    );
  }

  function graficoS1() {
    barrasAgrupadas('#g-s1', A.secoes.s1.grafico, 'medida', {
      rotuloY: '% do total do Brasil',
      dominioY: [0, 100],
      girar: true,
    });
  }

  function graficoS2() {
    barrasAgrupadas('#g-s2', A.secoes.s2.grafico, 'regiao', {
      rotuloY: 'p.p. dos válidos (2026 − 2022)',
      sinal: true,
      girar: true,
    });
  }

  function graficoS3() {
    barrasAgrupadas('#g-s3', A.secoes.s3.grafico, 'faixa', {
      rotuloY: '% dos válidos do grupo',
      dominioY: [0, 60],
      girar: true,
    });
  }

  function graficoS5() {
    const el = $('#g-s5');
    const dados = A.secoes.s5.grafico.map((d) => ({
      ...d,
      nome: nomeCand(d.nr),
      rotulo: `${nomeCand(d.nr)} · ${d.recorte}`,
    }));
    el.replaceChildren(
      Plot.plot({
        width: largura(el),
        height: 210,
        marginLeft: celular() ? 150 : 190,
        marginRight: 56,
        style: { fontFamily: 'inherit', fontSize: '12px' },
        y: { label: null, domain: dados.map((d) => d.rotulo) },
        x: { label: '% dos válidos', grid: true },
        marks: [
          Plot.barX(dados, {
            y: 'rotulo',
            x: 'valor',
            fill: (d) => corCand(d.nr),
            fillOpacity: (d) => (d.recorte === 'Brasil' ? 0.45 : 1),
          }),
          Plot.text(dados, {
            y: 'rotulo',
            x: 'valor',
            text: (d) => `${fmt(d.valor, 2)}%`,
            dx: 6,
            textAnchor: 'start',
            fill: '#1d2126',
          }),
          Plot.ruleX([0]),
        ],
      })
    );
  }

  function tabelaS6() {
    const t = A.textos;
    $('#t-s6 tbody').innerHTML = A.secoes.s6.tabela
      .map(
        (r) =>
          `<tr><td>${r.regiao}</td><td>${t[`s6.regiao.${r.sigla}.abstencao`]}</td>` +
          `<td>${t[`s6.regiao.${r.sigla}.brancos`]}</td><td>${t[`s6.regiao.${r.sigla}.nulos`]}</td></tr>`
      )
      .join('');
  }

  // dispersão: 5.570 pontos, desenhada só quando a seção entra na tela
  function graficoS4() {
    if (!D) return;
    const el = $('#g-s4');
    const iy = { pt: 1, pl: 2 };
    const nr = { pt: 13, pl: 22 };
    const regioes = D.regioes;
    const um = (qual, w) => {
      const pts = D.pontos.map((p) => ({
        x: p[0],
        y: p[iy[qual]],
        regiao: regioes[p[3]].nome,
        eleitorado: p[4],
      }));
      return Plot.plot({
        width: w,
        height: celular() ? 300 : 340,
        marginLeft: 44,
        style: { fontFamily: 'inherit', fontSize: '12px' },
        title: `Voto em ${nomeCand(nr[qual])}`,
        x: {
          label: 'PIB per capita do município (R$, escala log)',
          ticks: [1e4, 3e4, 1e5, 3e5].map(Math.log10),
          tickFormat: (v) => `${Math.round(10 ** v / 1000)} mil`,
        },
        y: { label: '% dos válidos', domain: [0, 100], grid: true },
        r: { range: [0.6, celular() ? 9 : 14] },
        color: {
          legend: true,
          domain: regioes.map((r) => r.nome),
          range: regioes.map((r) => r.cor),
        },
        marks: [
          Plot.dot(pts, {
            x: 'x',
            y: 'y',
            r: 'eleitorado',
            fill: 'regiao',
            fillOpacity: 0.5,
            stroke: null,
            sort: { channel: '-r' },
          }),
        ],
      });
    };
    if (celular()) {
      el.replaceChildren(um(candDispersao, largura(el)));
    } else {
      const w = Math.floor((el.clientWidth - 24) / 2);
      const caixa = document.createElement('div');
      caixa.className = 'dispersao-duas';
      caixa.append(um('pt', w), um('pl', w));
      el.replaceChildren(caixa);
    }
  }

  async function carregarDispersao() {
    if (D) return;
    D = await obter(A.secoes.s4.arquivo);
    graficoS4();
  }

  function desenharTudo() {
    graficoS1();
    graficoS2();
    graficoS3();
    graficoS5();
    graficoS4();
  }

  // ------------------------------------------------------------ início
  async function iniciar() {
    try {
      A = await obter('data/analises.json');
    } catch (err) {
      $('.intro').textContent = `Não foi possível carregar os dados: ${err.message}`;
      return;
    }
    preencherTextos();
    tabelaS6();
    desenharTudo();

    const alvo = $('#renda');
    if ('IntersectionObserver' in window) {
      const io = new IntersectionObserver((ents) => {
        if (ents.some((e) => e.isIntersecting)) {
          io.disconnect();
          carregarDispersao();
        }
      }, { rootMargin: '400px' });
      io.observe(alvo);
    } else {
      carregarDispersao();
    }

    document.querySelectorAll('[data-cand]').forEach((b) =>
      b.addEventListener('click', () => {
        document.querySelectorAll('[data-cand]').forEach((o) => o.classList.remove('ativo'));
        b.classList.add('ativo');
        candDispersao = b.dataset.cand;
        graficoS4();
      })
    );

    let espera = null;
    let larguraAnterior = window.innerWidth;
    window.addEventListener('resize', () => {
      if (window.innerWidth === larguraAnterior) return;
      larguraAnterior = window.innerWidth;
      clearTimeout(espera);
      espera = setTimeout(desenharTudo, 200);
    });
  }

  iniciar();
})();
