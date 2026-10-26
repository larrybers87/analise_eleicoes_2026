/* Página "2º turno: resultado". Vanilla JS + d3 via CDN.
 *
 * REGRAS (D-030): nenhum número vem digitado do HTML: todo <span data-s="chave"> recebe
 * `S.textos[chave]`, já formatado em Python (scripts/exportar_segundo_turno.py). Nenhuma cor é
 * calculada aqui: a cor de cada UF e os stops das legendas vêm prontos do JSON.
 */
'use strict';

(function () {
  const $ = (s) => document.querySelector(s);
  const fmt = (v, casas) =>
    v.toLocaleString('pt-BR', { minimumFractionDigits: casas, maximumFractionDigits: casas });
  const sinal = (v, casas) => (v > 0 ? '+' : v < 0 ? '−' : '') + fmt(Math.abs(v), casas);

  let S = null;
  let ufs = null;

  async function obter(caminho) {
    const r = await fetch(caminho, { cache: 'no-cache' });
    if (!r.ok) throw new Error(`falha ao carregar ${caminho}: HTTP ${r.status}`);
    return r.json();
  }

  function textos() {
    document.querySelectorAll('[data-s]').forEach((el) => {
      const t = S.textos[el.dataset.s];
      el.textContent = t === undefined ? '?' : t;
      if (t === undefined) console.error('chave sem texto:', el.dataset.s);
    });
  }

  function mapa(alvo, campoCor, campoTexto) {
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
      .attr('fill', (f) => S.ufs[f.properties.uf][campoCor])
      .append('title')
      .text((f) => S.ufs[f.properties.uf][campoTexto]);
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
  }

  function legenda(alvo, e) {
    const stops = e.stops
      .map(([v, c]) => `${c} ${(((v + e.limite_pp) / (2 * e.limite_pp)) * 100).toFixed(1)}%`)
      .join(', ');
    $(alvo).innerHTML =
      `<div class="barra" style="background: linear-gradient(to right, ${stops})"></div>` +
      `<div class="marcas"><span>${sinal(-e.limite_pp, 0)} p.p.</span><span>${fmt(0, 0)}</span>` +
      `<span>${sinal(e.limite_pp, 0)} p.p.</span></div>` +
      `<div class="marcas"><span>${e.rotulo_negativo}</span><span>${e.rotulo_positivo}</span></div>`;
  }

  function tabela(seletor, linhas, colunas) {
    const corpo = $(`${seletor} tbody`);
    corpo.innerHTML = '';
    linhas.forEach((l) => {
      const tr = document.createElement('tr');
      colunas.forEach((c, i) => {
        const el = document.createElement(i === 0 ? 'th' : 'td');
        if (i === 0) el.scope = 'row';
        el.textContent = l[c];
        tr.appendChild(el);
      });
      corpo.appendChild(tr);
    });
  }

  function desenhar() {
    mapa($('#g-resultado'), 'cor_resultado', 'texto_resultado');
    mapa($('#g-swing'), 'cor_swing', 'texto_swing');
  }

  async function iniciar() {
    let topo;
    try {
      [S, topo] = await Promise.all([
        obter('data/segundo_turno.json'),
        obter('data/geo/brasil_uf.topojson'),
      ]);
    } catch (err) {
      $('.intro').textContent = `Não foi possível carregar os dados: ${err.message}`;
      return;
    }
    ufs = topojson.feature(topo, topo.objects.data);
    textos();
    legenda('#legenda-resultado', S.escala_resultado);
    legenda('#legenda-swing', S.escala_swing);
    tabela('#t-ufs', S.tabela_ufs, ['uf', 'margem_t1', 'margem_t2', 'swing', 'dabst', 'viraram']);
    tabela('#t-porte', S.porte, ['rotulo', 'municipios', 'swing', 'dabst', 'viraram']);
    tabela('#t-mg', S.mg, ['rotulo', 'swing', 'margem', 'ganho', 'eleitorado']);
    const ul = $('#fontes-extensao');
    S.fontes_extensao.forEach((f) => {
      const li = document.createElement('li');
      const a = document.createElement('a');
      a.href = f.url;
      a.target = '_blank';
      a.rel = 'noopener';
      a.textContent = f.rotulo;
      li.appendChild(a);
      ul.appendChild(li);
    });
    desenhar();

    let espera = null;
    let larguraAnterior = window.innerWidth;
    window.addEventListener('resize', () => {
      if (window.innerWidth === larguraAnterior) return;
      larguraAnterior = window.innerWidth;
      clearTimeout(espera);
      espera = setTimeout(desenhar, 200);
    });
  }

  iniciar();
})();
