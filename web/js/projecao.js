/* Aba "2º turno: projeção" (F5a): método e backtest 2018→2022. Vanilla JS + d3 via CDN.
 *
 * REGRAS:
 * - Nenhum número vem digitado do HTML: todo <span data-v="chave"> recebe
 *   `P.textos[chave]`, o texto JÁ FORMATADO em Python (scripts/exportar_projecao_web.py).
 * - Nenhuma cor é calculada aqui: a cor de cada UF e os stops da legenda vêm prontos do JSON
 *   (eleicao.cores.cor_divergente_simetrica / escala_divergente_assimetrica, D-036).
 * - Esta página não tem NENHUM número da projeção 2026: o JSON só traz o backtest.
 */
'use strict';

(function () {
  const $ = (s) => document.querySelector(s);
  const fmt = (v, casas) =>
    v.toLocaleString('pt-BR', { minimumFractionDigits: casas, maximumFractionDigits: casas });
  const sinal = (v, casas) => (v > 0 ? '+' : v < 0 ? '−' : '') + fmt(Math.abs(v), casas);

  let P = null; // projecao_backtest.json
  let ufs = null; // GeoJSON das UFs
  let modelo = null;

  async function obter(caminho) {
    const r = await fetch(caminho, { cache: 'no-cache' });
    if (!r.ok) throw new Error(`falha ao carregar ${caminho}: HTTP ${r.status}`);
    return r.json();
  }

  function preencherTextos() {
    document.querySelectorAll('[data-v]').forEach((el) => {
      const t = P.textos[el.dataset.v];
      el.textContent = t === undefined ? '?' : t;
      if (t === undefined) console.error('chave sem texto:', el.dataset.v);
    });
  }

  // ------------------------------------------------------------ tabela
  function tabela() {
    const corpo = $('#t-backtest tbody');
    corpo.innerHTML = '';
    P.tabela.forEach((m) => {
      const tr = document.createElement('tr');
      if (m.referencia) tr.className = 'referencia';
      const celulas = [
        m.rotulo,
        m.textos.erro_br_pp,
        m.textos.uf_media_abs_pp,
        m.textos.pior_uf,
        m.textos.mae_municipal_pp,
        m.textos.vencedor_uf,
        m.textos.erro_abst_br_pp,
      ];
      celulas.forEach((texto, i) => {
        const td = document.createElement(i === 0 ? 'th' : 'td');
        if (i === 0) {
          td.scope = 'row';
          const nome = document.createElement('span');
          nome.className = 'modelo-nome';
          nome.textContent = texto;
          const desc = document.createElement('span');
          desc.className = 'modelo-desc';
          desc.textContent = m.descricao;
          td.append(nome, desc);
        } else {
          td.textContent = texto;
        }
        tr.appendChild(td);
      });
      corpo.appendChild(tr);
    });
  }

  // ------------------------------------------------------------ mapa
  function seletor() {
    const caixa = $('#seletor-modelo');
    P.modelos_mapa.forEach((m) => {
      const b = document.createElement('button');
      b.type = 'button';
      b.dataset.modelo = m.id;
      b.textContent = m.rotulo;
      b.setAttribute('aria-pressed', String(m.id === modelo));
      if (m.id === modelo) b.classList.add('ativo');
      b.addEventListener('click', () => {
        modelo = m.id;
        caixa.querySelectorAll('button').forEach((o) => {
          o.classList.toggle('ativo', o === b);
          o.setAttribute('aria-pressed', String(o === b));
        });
        pintar();
      });
      caixa.appendChild(b);
    });
  }

  function desenharMapa() {
    const alvo = $('#g-mapa');
    alvo.innerHTML = '';
    const w = Math.max(280, Math.min(alvo.clientWidth || 600, 600));
    const h = Math.round(w * 0.95);
    const proj = d3.geoMercator().fitSize([w, h], ufs);
    const caminho = d3.geoPath(proj);
    const svg = d3
      .select(alvo)
      .append('svg')
      .attr('viewBox', `0 0 ${w} ${h}`)
      .attr('width', w)
      .attr('height', h)
      .attr('role', 'img')
      .attr('aria-label', alvo.getAttribute('aria-label'));
    svg
      .append('g')
      .selectAll('path')
      .data(ufs.features)
      .join('path')
      .attr('d', caminho)
      .attr('data-uf', (f) => f.properties.uf)
      .attr('stroke', '#ffffff')
      .attr('stroke-width', 0.8)
      .append('title');
    svg
      .append('g')
      .attr('class', 'rotulos-uf')
      .selectAll('text')
      .data(ufs.features)
      .join('text')
      .attr('transform', (f) => `translate(${caminho.centroid(f)})`)
      .attr('text-anchor', 'middle')
      .attr('dy', '0.35em')
      .text((f) => f.properties.uf.toUpperCase());
    pintar();
  }

  function pintar() {
    const dados = P.mapa[modelo];
    d3.selectAll('#g-mapa path').each(function () {
      const uf = this.dataset.uf;
      const d = dados[uf];
      this.setAttribute('fill', d.cor);
      this.querySelector('title').textContent = `${uf.toUpperCase()}: ${d.texto}`;
    });
  }

  function legenda() {
    const e = P.escala;
    const stops = e.stops
      .map(([v, c]) => `${c} ${(((v + e.limite_pp) / (2 * e.limite_pp)) * 100).toFixed(1)}%`)
      .join(', ');
    $('#legenda-erro').innerHTML =
      `<div class="barra" style="background: linear-gradient(to right, ${stops})"></div>` +
      `<div class="marcas"><span>${sinal(-e.limite_pp, 1)} p.p.</span><span>${fmt(0, 0)}</span>` +
      `<span>${sinal(e.limite_pp, 1)} p.p.</span></div>` +
      `<div class="marcas"><span>${e.rotulo_negativo}</span><span>${e.rotulo_positivo}</span></div>`;
  }

  // ------------------------------------------------------------ início
  async function iniciar() {
    let topo;
    try {
      [P, topo] = await Promise.all([
        obter('data/projecao_backtest.json'),
        obter('data/geo/brasil_uf.topojson'),
      ]);
    } catch (err) {
      $('.intro').textContent = `Não foi possível carregar os dados: ${err.message}`;
      return;
    }
    ufs = topojson.feature(topo, topo.objects.data);
    modelo = P.modelo_referencia;
    preencherTextos();
    tabela();
    seletor();
    legenda();
    desenharMapa();

    let espera = null;
    let larguraAnterior = window.innerWidth;
    window.addEventListener('resize', () => {
      if (window.innerWidth === larguraAnterior) return;
      larguraAnterior = window.innerWidth;
      clearTimeout(espera);
      espera = setTimeout(desenharMapa, 200);
    });
  }

  iniciar();
})();
