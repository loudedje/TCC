# -*- coding: utf-8 -*-
"""
Camada de dados do sistema web.

Lê os arquivos gerados pelos notebooks (pasta ColetarDados/Resultados), o extrato
do ComexStat (DadosBrutos) e o catálogo da Apti (Catalogo), e monta as estruturas
que as páginas usam. Nada aqui recalcula o ranking: o sistema mostra exatamente o
que os notebooks produziram.
"""

from datetime import datetime
from io import BytesIO
from pathlib import Path

import numpy as np
import pandas as pd


RAIZ = Path(__file__).resolve().parent.parent
PASTA_RESULTADOS = RAIZ / "ColetarDados" / "Resultados"
ARQ_EXPORTACAO = RAIZ / "DadosBrutos" / "V_EXPORTACAO_.csv"
ARQ_CATALOGO = RAIZ / "Catalogo" / "catalogo_linha_grupo_ncm.csv"

# período analisado (o mesmo do notebook Dados_Comex)
ANO_INICIAL = 2015
ANO_FINAL = 2025

PAISES = {
    'AGO': 'Angola',
    'CPV': 'Cabo Verde',
    'GNB': 'Guiné-Bissau',
    'MOZ': 'Moçambique',
    'STP': 'São Tomé e Príncipe',
}
CODIGO_DO_PAIS = {nome: codigo for codigo, nome in PAISES.items()}

CORES_PAISES = {
    'Angola':              '#2f5d8a',
    'Cabo Verde':          '#d08a2e',
    'Guiné-Bissau':        '#4f8a45',
    'Moçambique':          '#b04a3f',
    'São Tomé e Príncipe': '#7a5e98',
}

# na ordem do peso; 'rotulo' é o nome que o cliente vê nas páginas
CASOS = {
    'continuidade':    {'peso': 35, 'cor': '#2E7D32', 'rotulo': 'Compra todo ano',
                        'definicao': 'comprou do Brasil em todos os anos do período',
                        'ordem': 'valor total'},
    'surgimento':      {'peso': 30, 'cor': '#1565C0', 'rotulo': 'Mercado em crescimento',
                        'definicao': 'começou a comprar e não parou mais',
                        'ordem': 'anos ativos, depois valor'},
    'intermitente':    {'peso': 20, 'cor': '#EF6C00', 'rotulo': 'Compra ocasional',
                        'definicao': 'compra em alguns anos e para em outros',
                        'ordem': 'menor sequência parada, depois valor'},
    'descontinuidade': {'peso': 15, 'cor': '#C62828', 'rotulo': 'Parou de comprar',
                        'definicao': 'comprava e deixou de comprar',
                        'ordem': 'anos ativos, depois valor'},
    'nunca exportou':  {'peso': 0,  'cor': '#757575', 'rotulo': 'Sem compras',
                        'definicao': 'nunca comprou do Brasil',
                        'ordem': '—'},
}

INDICADORES = {
    'Populacao':          {'nome': 'População',               'formato': 'inteiro'},
    'PIB_per_capita_usd': {'nome': 'PIB per capita (US$)',    'formato': 'moeda'},
    'Urbanizacao_pct':    {'nome': 'Urbanização (%)',          'formato': 'pct'},
    'Inflacao_pct':       {'nome': 'Inflação (%)',             'formato': 'pct'},
    'Estab_politica':     {'nome': 'Estabilidade política',    'formato': 'indice'},
    'Qualidade_regulat':  {'nome': 'Qualidade regulatória',    'formato': 'indice'},
    'IDH':                {'nome': 'IDH',                      'formato': 'idh'},
}

# as mesmas do caracteristicas_paises_palop.ipynb (inflação fica fora)
VARIAVEIS_SIMILARIDADE = ['Populacao', 'PIB_per_capita_usd', 'Urbanizacao_pct',
                          'Estab_politica', 'Qualidade_regulat', 'IDH']


def moeda(valor):
    """Formata no padrão brasileiro: 1.253.681.500"""
    return f"{valor:,.0f}".replace(",", ".")


def anos_texto(n):
    return f"{n} ano" if n == 1 else f"{n} anos"


def registros(tabela):
    """DataFrame -> lista de dicts, com NaN virando None (para o Jinja e o JSON)."""
    tabela = tabela.astype(object)
    return tabela.where(tabela.notna(), None).to_dict('records')


def _ler_resultado(nome, **opcoes):
    caminho = PASTA_RESULTADOS / nome
    if not caminho.exists():
        return None
    return pd.read_csv(caminho, encoding='utf-8-sig', **opcoes)


def explicar(linha):
    """Frase curta com o motivo da posição do país no ranking do produto."""
    caso = linha['caso_final']

    if linha['herdado'] == 1:
        origem = linha.get('parecidos_que_compram') or [linha['herdado_de']]
        verbo = 'já compram' if len(origem) > 1 else 'já compra'
        return (f"Ainda não compra este NCM do Brasil, mas tem perfil parecido com {' e '.join(origem)}, "
                f"que {verbo}. É uma oportunidade de mercado novo.")

    if caso == 'nunca exportou':
        return "Não compra este NCM do Brasil e não tem perfil parecido com quem compra."

    anos = int(linha['anos_ativos'])
    if caso == 'continuidade':
        return f"Comprou em todos os {anos_texto(anos)}; US$ {moeda(linha['valor_total'])} no total."
    if caso == 'surgimento':
        return f"Começou a comprar há {anos_texto(anos)} e não parou mais."
    if caso == 'descontinuidade':
        return f"Comprou durante {anos_texto(anos)} e depois parou."
    if caso == 'intermitente':
        return (f"Comprou em {anos_texto(anos)}, com intervalos; ficou até "
                f"{anos_texto(int(linha['maior_parada']))} seguidos sem comprar.")
    return "Sem compras deste NCM."


class Dados:

    def __init__(self):
        self.carregar()

    # ------------------------------------------------------------------
    # Carga
    # ------------------------------------------------------------------

    @staticmethod
    def assinatura():
        """Nome, data e tamanho dos arquivos lidos — muda quando um notebook regrava algum."""
        arquivos = list(PASTA_RESULTADOS.glob('*.csv')) + [ARQ_EXPORTACAO, ARQ_CATALOGO]
        estado = []
        for caminho in sorted(arquivos):
            if caminho.exists():
                info = caminho.stat()
                estado.append((caminho.name, info.st_mtime, info.st_size))
        return tuple(estado)

    def atualizar_se_mudou(self):
        """Relê tudo se algum CSV mudou desde a última carga. Devolve True se releu."""
        if self.assinatura() == self.assinatura_carregada:
            return False
        try:
            self.carregar()
        except Exception:
            # um notebook pode estar gravando os arquivos agora; tenta de novo na próxima página
            return False
        return True

    def carregar(self):
        assinatura = self.assinatura()
        ranking = _ler_resultado('ranking_final.csv', dtype={'Código NCM': str})
        self.arquivo_ranking = 'ranking_final.csv'
        if ranking is None:
            ranking = _ler_resultado('ranking.csv', dtype={'Código NCM': str})
            self.arquivo_ranking = 'ranking.csv'
        if ranking is None:
            raise FileNotFoundError(
                f"Não encontrei ranking_final.csv nem ranking.csv em {PASTA_RESULTADOS}. "
                "Rode os notebooks Dados_Comex e Recomendar primeiro.")

        # o ranking.csv ainda não passou pelo cold start: cria as colunas finais
        if 'caso_final' not in ranking.columns:
            ranking['caso_final'] = ranking['caso']
            ranking['peso_final'] = ranking['peso']
            ranking['posicao_final'] = ranking['posicao']
            ranking['herdado'] = 0
            ranking['herdado_de'] = None
            ranking['grau_vizinho'] = 0

        # o CSV perde o zero à esquerda do NCM; 'ncm' é a versão com 8 dígitos
        ranking['ncm'] = ranking['Código NCM'].str.zfill(8)
        ranking['iso'] = ranking['Países'].map(CODIGO_DO_PAIS)
        self.ranking = ranking.sort_values(['ncm', 'posicao_final']).reset_index(drop=True)

        unicos = self.ranking.drop_duplicates('ncm').set_index('ncm')
        self.descricao = unicos['Descrição NCM'].to_dict()
        self.ncms = sorted(self.descricao)

        exportacoes = pd.read_csv(ARQ_EXPORTACAO, sep=';', encoding='utf-8-sig')
        for coluna in ['Países', 'Descrição NCM']:
            exportacoes[coluna] = (exportacoes[coluna]
                                   .str.replace(r'[\r\n]+', ' ', regex=True).str.strip())
        exportacoes['ncm'] = exportacoes['Código NCM'].astype(str).str.zfill(8)
        no_periodo = (exportacoes['Ano'] >= ANO_INICIAL) & (exportacoes['Ano'] <= ANO_FINAL)
        self.exportacoes = exportacoes[exportacoes['Países'].isin(PAISES.values()) & no_periodo]
        self.anos = list(range(ANO_INICIAL, ANO_FINAL + 1))

        if ARQ_CATALOGO.exists():
            catalogo = pd.read_csv(ARQ_CATALOGO, dtype=str, encoding='utf-8-sig')
            # no catálogo alguns NCMs vêm com pontos (ex.: 2106.90.21)
            catalogo['ncm'] = catalogo['NCM'].str.replace(r'\D', '', regex=True).str.zfill(8)
            self.total_produtos_catalogo = len(catalogo)
            self.catalogo = catalogo.drop_duplicates(['Linha', 'Grupo', 'ncm']).reset_index(drop=True)
        else:
            self.total_produtos_catalogo = 0
            self.catalogo = pd.DataFrame(columns=['Linha', 'Grupo', 'NCM', 'ncm'])

        self.caracteristicas = _ler_resultado('caracteristicas_paises.csv', index_col=0)
        self.distancias = _ler_resultado('matriz_distancias.csv', index_col=0)
        self.recomendacoes = _ler_resultado('recomendacoes.csv', dtype={'Código NCM': str})
        self.sem_recomendacao = _ler_resultado('sem_recomendacao.csv', dtype={'Código NCM': str})
        self.ranking['parecidos_que_compram'] = self._parecidos_que_compram()

        self.carregado_em = datetime.now()
        self.assinatura_carregada = assinatura

    # ------------------------------------------------------------------
    # Auxiliares
    # ------------------------------------------------------------------

    def _por_ano(self, tabela, valor='Valor US$ FOB', linhas='Países'):
        """Tabela linhas x anos, com zero onde não houve exportação."""
        if tabela.empty:
            return pd.DataFrame(0, index=[], columns=self.anos)
        pivo = tabela.pivot_table(index=linhas, columns='Ano', values=valor,
                                  aggfunc='sum', fill_value=0)
        return pivo.reindex(columns=self.anos, fill_value=0)

    def _serie_por_pais(self, pivo):
        series = {}
        for pais in PAISES.values():
            if pais in pivo.index:
                series[pais] = [int(v) for v in pivo.loc[pais]]
            else:
                series[pais] = [0] * len(self.anos)
        return series

    def linhas_do_catalogo(self, ncm):
        return sorted(set(self.catalogo.loc[self.catalogo['ncm'] == ncm, 'Linha']))

    @property
    def periodo(self):
        return f"{self.anos[0]}–{self.anos[-1]}"

    # ------------------------------------------------------------------
    # Painel
    # ------------------------------------------------------------------

    def resumo(self):
        r = self.ranking
        com = int((r['caso_final'] != 'nunca exportou').sum())
        ncms_catalogo = set(self.catalogo['ncm'])
        return {
            'ncms': len(self.ncms),
            'produtos_catalogo': self.total_produtos_catalogo,
            'paises': r['Países'].nunique(),
            'pares': len(r),
            'com_recomendacao': com,
            'pct_recomendacao': com / len(r) * 100,
            'herdados': int(r['herdado'].sum()),
            'valor_total': int(self.exportacoes['Valor US$ FOB'].sum()),
            'ncms_catalogo': len(ncms_catalogo),
            'ncms_catalogo_cobertos': len(ncms_catalogo & set(self.ncms)),
        }

    def exportacao_por_ano(self):
        return {'anos': self.anos,
                'series': self._serie_por_pais(self._por_ano(self.exportacoes))}

    def contagem_casos(self):
        contagem = self.ranking['caso_final'].value_counts()
        return {caso: int(contagem.get(caso, 0)) for caso in CASOS}

    def top_produtos(self, quantos=10):
        soma = (self.exportacoes.groupby('ncm')['Valor US$ FOB'].sum()
                .sort_values(ascending=False).head(quantos))
        return [{'ncm': ncm, 'descricao': self.descricao.get(ncm, ncm), 'valor': int(valor)}
                for ncm, valor in soma.items()]

    def paises_resumo(self):
        r = self.ranking
        valor = self.exportacoes.groupby('Países')['Valor US$ FOB'].sum()
        itens = []
        for iso, nome in PAISES.items():
            bloco = r[r['Países'] == nome]
            item = {
                'iso': iso,
                'nome': nome,
                'cor': CORES_PAISES[nome],
                'valor_total': int(valor.get(nome, 0)),
                'com_historico': int((bloco['caso'] != 'nunca exportou').sum()),
                'primeiros': int((bloco['posicao_final'] == 1).sum()),
                'herdados': int(bloco['herdado'].sum()),
                'casos': {caso: int((bloco['caso_final'] == caso).sum()) for caso in CASOS},
            }
            if self.caracteristicas is not None and nome in self.caracteristicas.index:
                item['indicadores'] = self.caracteristicas.loc[nome].to_dict()
            itens.append(item)
        return itens

    # ------------------------------------------------------------------
    # Produtos
    # ------------------------------------------------------------------

    def produtos_lista(self):
        valor = self.exportacoes.groupby('ncm')['Valor US$ FOB'].sum()
        itens = []
        for ncm, bloco in self.ranking.groupby('ncm', sort=True):
            bloco = bloco.sort_values('posicao_final')
            primeiro = bloco.iloc[0]
            segundo = bloco.iloc[1]
            itens.append({
                'ncm': ncm,
                'descricao': self.descricao[ncm],
                'primeiro': primeiro['Países'],
                'caso_primeiro': primeiro['caso_final'],
                'segundo': segundo['Países'],
                'caso_segundo': segundo['caso_final'],
                'herdados': int(bloco['herdado'].sum()),
                'com_historico': int((bloco['caso'] != 'nunca exportou').sum()),
                'linhas': self.linhas_do_catalogo(ncm),
                'valor': int(valor.get(ncm, 0)),
            })
        return itens

    def produto(self, ncm):
        bloco = self.ranking[self.ranking['ncm'] == ncm].sort_values('posicao_final')
        if bloco.empty:
            return None

        linhas = registros(bloco)
        for linha in linhas:
            linha['motivo'] = explicar(linha)

        exportado = self.exportacoes[self.exportacoes['ncm'] == ncm]
        valor = self._por_ano(exportado)
        quilos = self._por_ano(exportado, valor='Quilograma Líquido')
        series_valor = self._serie_por_pais(valor)
        series_kg = self._serie_por_pais(quilos)

        por_pais_tabela = []
        for pais in PAISES.values():
            total = sum(series_valor[pais])
            kg = sum(series_kg[pais])
            anos_com = [ano for ano, v in zip(self.anos, series_valor[pais]) if v > 0]
            por_pais_tabela.append({
                'pais': pais,
                'valor': total,
                'kg': kg,
                'anos_com': len(anos_com),
                'ultimo_ano': anos_com[-1] if anos_com else None,
            })

        posicao = self.ncms.index(ncm)
        catalogo = self.catalogo[self.catalogo['ncm'] == ncm][['Linha', 'Grupo']]

        return {
            'ncm': ncm,
            'descricao': self.descricao[ncm],
            'ranking': linhas,
            'anos': self.anos,
            'series_valor': series_valor,
            'series_kg': series_kg,
            'por_pais': por_pais_tabela,
            'valor_total': sum(item['valor'] for item in por_pais_tabela),
            'catalogo': registros(catalogo),
            'anterior': self.ncms[posicao - 1] if posicao > 0 else None,
            'proximo': self.ncms[posicao + 1] if posicao + 1 < len(self.ncms) else None,
        }

    # ------------------------------------------------------------------
    # Países
    # ------------------------------------------------------------------

    def padronizado(self):
        """Mesma padronização do notebook: log nas variáveis de escala e z-score."""
        if self.caracteristicas is None:
            return None
        dados = self.caracteristicas[VARIAVEIS_SIMILARIDADE].copy()
        dados['Populacao'] = np.log10(dados['Populacao'])
        dados['PIB_per_capita_usd'] = np.log10(dados['PIB_per_capita_usd'])
        return (dados - dados.mean()) / dados.std(ddof=0)

    def pais(self, iso):
        nome = PAISES.get(iso)
        if nome is None:
            return None

        bloco = self.ranking[self.ranking['Países'] == nome].sort_values(
            ['posicao_final', 'valor_total'], ascending=[True, False])

        produtos = []
        for linha in registros(bloco):
            produtos.append({
                'ncm': linha['ncm'],
                'descricao': linha['Descrição NCM'],
                'posicao': int(linha['posicao_final']),
                'caso': linha['caso_final'],
                'herdado': int(linha['herdado']),
                'herdado_de': linha['herdado_de'],
                'parecidos_que_compram': linha['parecidos_que_compram'],
                'valor': int(linha['valor_total']),
                'anos_ativos': int(linha['anos_ativos']),
            })

        parecidos = []
        if self.distancias is not None:
            for outro, distancia in self.distancias.loc[nome].drop(nome).sort_values().items():
                parecidos.append({'nome': outro, 'iso': CODIGO_DO_PAIS[outro],
                                  'distancia': float(distancia)})

        z = self.padronizado()
        exportado = self.exportacoes[self.exportacoes['Países'] == nome]
        por_ano = self._por_ano(exportado)
        serie = [int(v) for v in por_ano.loc[nome]] if nome in por_ano.index else [0] * len(self.anos)

        return {
            'iso': iso,
            'nome': nome,
            'cor': CORES_PAISES[nome],
            'indicadores': (self.caracteristicas.loc[nome].to_dict()
                            if self.caracteristicas is not None else {}),
            'z': ({v: float(z.loc[nome, v]) for v in VARIAVEIS_SIMILARIDADE}
                  if z is not None else None),
            'parecidos': parecidos,
            'produtos': produtos,
            'casos': {caso: int((bloco['caso_final'] == caso).sum()) for caso in CASOS},
            'primeiros': int((bloco['posicao_final'] == 1).sum()),
            'herdados': int(bloco['herdado'].sum()),
            'com_historico': int((bloco['caso'] != 'nunca exportou').sum()),
            'valor_total': int(exportado['Valor US$ FOB'].sum()),
            'serie': serie,
            'anos': self.anos,
        }

    # ------------------------------------------------------------------
    # Matriz, catálogo e similaridade
    # ------------------------------------------------------------------

    def matriz(self):
        """Ranking só pelos critérios do histórico próprio (antes das oportunidades por perfil parecido)."""
        linhas = []
        for ncm, bloco in self.ranking.groupby('ncm', sort=True):
            celulas = {}
            for _, linha in bloco.iterrows():
                celulas[linha['Países']] = {
                    'posicao': int(linha['posicao']),
                    'caso': linha['caso'],
                }
            linhas.append({'ncm': ncm, 'descricao': self.descricao[ncm], 'celulas': celulas,
                           'linhas': self.linhas_do_catalogo(ncm)})
        return linhas

    def catalogo_agrupado(self):
        primeiros = {}
        for item in self.produtos_lista():
            primeiros[item['ncm']] = item

        linhas = []
        for linha_nome, bloco_linha in self.catalogo.groupby('Linha', sort=False):
            grupos = []
            for grupo_nome, bloco_grupo in bloco_linha.groupby('Grupo', sort=False):
                ncms = []
                for ncm in bloco_grupo['ncm'].unique():
                    ncms.append({'ncm': ncm, 'na_base': ncm in primeiros,
                                 'produto': primeiros.get(ncm)})
                grupos.append({'nome': grupo_nome, 'ncms': ncms})
            cobertos = sum(1 for g in grupos for n in g['ncms'] if n['na_base'])
            total = sum(len(g['ncms']) for g in grupos)
            linhas.append({'nome': linha_nome, 'grupos': grupos,
                           'cobertos': cobertos, 'total': total})
        return linhas

    def similaridade(self):
        z = self.padronizado()
        return {
            'caracteristicas': self.caracteristicas,
            'distancias': self.distancias,
            'z': ({pais: [float(z.loc[pais, v]) for v in VARIAVEIS_SIMILARIDADE]
                   for pais in z.index} if z is not None else None),
            'recomendacoes': (registros(self.recomendacoes)
                              if self.recomendacoes is not None else []),
            'sem_recomendacao': (registros(self.sem_recomendacao)
                                 if self.sem_recomendacao is not None else []),
        }

    def perfil_parecido(self):
        """Página do cliente: quem é parecido com quem e as oportunidades que isso gera."""
        vizinhos = self.vizinhos_de()
        herdados = self.ranking[self.ranking['herdado'] == 1]
        # conta cada país parecido que já compra, não só o mais parecido
        passa = herdados['parecidos_que_compram'].explode().value_counts()
        recebe = herdados['Países'].value_counts()

        mercados = []
        for nome in PAISES.values():
            mercados.append({
                'nome': nome,
                'parecidos': vizinhos.get(nome, []),
                'gera': int(passa.get(nome, 0)),
                'recebe': int(recebe.get(nome, 0)),
            })

        oportunidades = []
        ordenados = herdados.sort_values(['peso_final', 'grau_vizinho', 'ncm'],
                                         ascending=[False, True, True])
        for linha in registros(ordenados):
            oportunidades.append({
                'ncm': linha['ncm'],
                'descricao': linha['Descrição NCM'],
                'pais': linha['Países'],
                'parecido_com': linha['parecidos_que_compram'],
                'caso': linha['caso_final'],
                'posicao': int(linha['posicao_final']),
            })

        z = self.padronizado()
        return {
            'mercados': mercados,
            'oportunidades': oportunidades,
            'z': ({pais: [float(z.loc[pais, v]) for v in VARIAVEIS_SIMILARIDADE]
                   for pais in z.index} if z is not None else None),
        }

    def _parecidos_que_compram(self):
        """
        Para cada oportunidade, todos os países parecidos que já compram o produto,
        do mais parecido para o menos. O ranking herda só do primeiro (herdado_de);
        aqui é só para mostrar ao cliente. Fica em lista, e não em texto com " e ",
        porque "São Tomé e Príncipe" já tem um " e " no nome.
        """
        vizinhos = self.vizinhos_de()
        caso = dict(zip(zip(self.ranking['ncm'], self.ranking['Países']), self.ranking['caso']))

        textos = []
        for _, linha in self.ranking.iterrows():
            if linha['herdado'] != 1:
                textos.append(None)
                continue
            ncm, pais = linha['ncm'], linha['Países']
            compram = [outro for outro, lista in vizinhos.items()
                       if pais in lista and caso.get((ncm, outro), 'nunca exportou') != 'nunca exportou']
            compram.sort(key=lambda outro: self.distancias.loc[pais, outro])
            if not compram:
                compram = [linha['herdado_de']]
            textos.append(compram)
        return textos

    def vizinhos_de(self):
        """Os dois países mais parecidos com cada país (mesmo k = 2 do notebook)."""
        if self.distancias is None:
            return {}
        return {pais: list(self.distancias.loc[pais].drop(pais).sort_values().index[:2])
                for pais in self.distancias.index}

    def recomendados_por_vizinho(self):
        """
        Mesma regra do Recomendar.ipynb: o país A comprou o produto e os vizinhos de A
        que nunca compraram recebem a recomendação. Uma linha por (produto, país A),
        só quando pelo menos um vizinho de A nunca comprou.
        """
        vizinhos = self.vizinhos_de()
        casos = self.ranking.set_index(['ncm', 'Países'])
        anos_compra = (self.exportacoes[self.exportacoes['Valor US$ FOB'] > 0]
                       .groupby(['ncm', 'Países'])['Ano'].nunique().to_dict())

        itens = []
        for linha in registros(self.ranking.sort_values(['ncm', 'Países'])):
            if linha['caso'] == 'nunca exportou':
                continue
            ncm, pais_a = linha['ncm'], linha['Países']
            lista = []
            for grau, nome in enumerate(vizinhos.get(pais_a, []), start=1):
                lista.append({
                    'nome': nome,
                    'grau': grau,
                    'comprou': casos.loc[(ncm, nome), 'caso'] != 'nunca exportou',
                })
            if all(v['comprou'] for v in lista):
                continue
            itens.append({
                'ncm': ncm,
                'descricao': linha['Descrição NCM'],
                'pais': pais_a,
                'caso': linha['caso'],
                'anos_compra': int(anos_compra.get((ncm, pais_a), 0)),
                'vizinhos': lista,
                'recebem': [v['nome'] for v in lista if not v['comprou']],
            })
        return itens

    def sem_recomendacao_por_vizinho(self):
        """Pares que nunca compraram e não são vizinhos de nenhum país que comprou."""
        bloco = self.ranking[(self.ranking['caso_final'] == 'nunca exportou')]
        return registros(bloco.sort_values(['Países', 'ncm'])[['ncm', 'Descrição NCM', 'Países']])

    # ------------------------------------------------------------------
    # Arquivos
    # ------------------------------------------------------------------

    def arquivos_resultado(self):
        itens = []
        for caminho in sorted(PASTA_RESULTADOS.glob('*')):
            if caminho.is_file():
                info = caminho.stat()
                itens.append({
                    'nome': caminho.name,
                    'tipo': caminho.suffix.lstrip('.').upper(),
                    'tamanho_kb': info.st_size / 1024,
                    'modificado': datetime.fromtimestamp(info.st_mtime),
                })
        return itens

    def excel_completo(self):
        abas = {
            'ranking': self.ranking.drop(columns=['iso']),
            'recomendacoes': self.recomendacoes,
            'sem_recomendacao': self.sem_recomendacao,
            'caracteristicas_paises': self.caracteristicas,
            'matriz_distancias': self.distancias,
            'catalogo_apti': self.catalogo,
            'exportacoes_comexstat': self.exportacoes,
        }
        saida = BytesIO()
        with pd.ExcelWriter(saida, engine='openpyxl') as planilha:
            for nome, tabela in abas.items():
                if tabela is None:
                    continue
                manter_indice = nome in ('caracteristicas_paises', 'matriz_distancias')
                tabela.to_excel(planilha, sheet_name=nome, index=manter_indice)
        saida.seek(0)
        return saida
