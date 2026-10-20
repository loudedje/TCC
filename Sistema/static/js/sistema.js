/* Funções usadas por várias páginas. */

const Sistema = (() => {
  const formatoNumero = new Intl.NumberFormat('pt-BR');
  const formatoCompacto = new Intl.NumberFormat('pt-BR', { notation: 'compact', maximumFractionDigits: 1 });

  const moeda = v => 'US$ ' + formatoNumero.format(Math.round(v));
  const compacto = v => formatoCompacto.format(v);
  const numero = (v, casas = 0) =>
    new Intl.NumberFormat('pt-BR', { minimumFractionDigits: casas, maximumFractionDigits: casas }).format(v);

  if (window.Chart) {
    Chart.defaults.font.family = getComputedStyle(document.body).fontFamily;
    Chart.defaults.font.size = 12;
    Chart.defaults.color = '#5f6b76';
    Chart.defaults.borderColor = '#eceff2';
    Chart.defaults.plugins.legend.labels.boxWidth = 12;
    Chart.defaults.plugins.legend.labels.boxHeight = 12;
    Chart.defaults.animation = false;
    Chart.defaults.maintainAspectRatio = false;
  }

  /** Cor com transparência a partir de um hex (#rrggbb). */
  function transparente(hex, alfa) {
    const n = parseInt(hex.slice(1), 16);
    return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${alfa})`;
  }

  /** Ordena a tabela ao clicar num cabeçalho com a classe .ordenavel */
  function tabelaOrdenavel(tabela) {
    const cabecalhos = tabela.querySelectorAll('th.ordenavel');
    cabecalhos.forEach((th) => {
      th.addEventListener('click', () => {
        const indice = Array.from(th.parentNode.children).indexOf(th);
        const dir = th.dataset.dir === 'asc' ? 'desc' : 'asc';
        cabecalhos.forEach(outro => delete outro.dataset.dir);
        th.dataset.dir = dir;
        const corpo = tabela.tBodies[0];
        const valor = (linha) => {
          const celula = linha.cells[indice];
          const bruto = celula.dataset.valor ?? celula.textContent.trim();
          const n = parseFloat(bruto);
          return isNaN(n) ? bruto.toLowerCase() : n;
        };
        Array.from(corpo.rows)
          .sort((a, b) => {
            const va = valor(a), vb = valor(b);
            const r = va > vb ? 1 : va < vb ? -1 : 0;
            return dir === 'asc' ? r : -r;
          })
          .forEach(l => corpo.appendChild(l));
      });
    });
  }

  /** Linhas com data-href abrem o link ao clicar. */
  function linhasClicaveis() {
    document.querySelectorAll('tr[data-href]').forEach((tr) => {
      tr.classList.add('clicavel');
      tr.addEventListener('click', (e) => {
        if (e.target.closest('a, button, input, select')) return;
        window.location = tr.dataset.href;
      });
    });
  }

  document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('table.tabela').forEach(tabelaOrdenavel);
    linhasClicaveis();
  });

  return { moeda, compacto, numero, transparente };
})();
