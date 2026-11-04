"""
Servidor web do sistema (Flask).

Como o Flask funciona, em resumo:
  1. O navegador pede um endereço, ex.: http://localhost:5000/paises
  2. O Flask procura a função "ligada" a esse endereço (as que têm @app.route)
  3. A função busca os dados e chama render_template('arquivo.html', ...)
  4. render_template pega o HTML da pasta templates/, preenche com os dados
     e devolve a página pronta para o navegador.

Para rodar:  python app.py   e abrir http://localhost:5000
Em produção quem chama o aplicativo é o uWSGI, pelo arquivo wsgi.py (ver DEPLOY.md).
"""
import math
import os
import secrets
from datetime import datetime

import numpy as np
import pandas as pd
from flask import Flask, abort, render_template, request, send_file
from flask.json.provider import DefaultJSONProvider

import distribuidores as dist
from dados import (CASOS, CORES_PAISES, INDICADORES, PAISES,
                   VARIAVEIS_SIMILARIDADE, CODIGO_DO_PAIS, Dados)


# ======================================================================
# 1. CRIAÇÃO DO APLICATIVO
# ======================================================================

class JSONComNumpy(DefaultJSONProvider):
    """Ensina o Flask a transformar números do numpy/pandas em JSON.

    Os gráficos das páginas recebem os dados em JSON. O Flask sozinho não
    sabe converter tipos como np.int64 ou pd.Timestamp, então esta classe
    converte cada um para um tipo comum do Python (int, float, texto).
    """

    @staticmethod
    def default(objeto):
        if isinstance(objeto, np.integer):
            return int(objeto)
        if isinstance(objeto, np.floating):
            return None if math.isnan(objeto) else float(objeto)  # NaN vira null
        if isinstance(objeto, (pd.Timestamp, datetime)):
            return objeto.isoformat()  # data vira texto "2024-01-31T00:00:00"
        return DefaultJSONProvider.default(objeto)


PRODUCAO = os.environ.get('PRODUCAO') == '1'  # o wsgi.py liga isto no servidor

app = Flask(__name__)                    # o aplicativo; tudo abaixo se pendura nele
app.json = JSONComNumpy(app)             # usa o conversor de JSON acima
# chave interna exigida pelo Flask; sem a variável, gera uma nova a cada início
app.secret_key = os.environ.get('FLASK_SECRET_KEY') or secrets.token_hex(16)

dados = Dados()  # carrega os CSVs uma vez só; todas as páginas usam este objeto


# ======================================================================
# 2. O QUE RODA ANTES DE CADA PÁGINA
# ======================================================================
# Um "@algo" em cima de uma função é um DECORADOR: ele registra a função
# no Flask para ser chamada num momento específico. A função em si é
# Python normal.

def conferir_arquivos():
    """Se algum notebook regravou os CSVs, relê antes de montar a página."""
    if request.endpoint != 'static':  # 'static' = arquivos CSS/JS/imagens, não precisa
        dados.atualizar_se_mudou()


# No servidor os notebooks não rodam: os dados só mudam com um Reload do web app.
if not PRODUCAO:
    app.before_request(conferir_arquivos)  # roda antes de toda requisição


# ======================================================================
# 3. MENU LATERAL
# ======================================================================
# Cada item: (nome_da_função_da_página, texto_que_aparece, ícone)
# O nome da função é o que o template usa em url_for() para montar o link.

MENU = [
    ('Mercados', [
        ('painel', 'Visão geral', 'painel'),
        ('produtos', 'Produtos por NCM', 'caixa'),
        ('ranking', 'Ranking por NCM', 'grade'),
        ('paises', 'Países', 'globo'),
        ('perfil_parecido', 'Perfil parecido entre mercados', 'rede'),
    ]),
    ('Comercial', [
        ('distribuidores', 'Distribuidores', 'alvo'),
        ('catalogo', 'Catálogo Apti', 'livro'),
    ]),
]

# Páginas que não estão no menu, mas devem destacar um item dele.
# Ex.: ao abrir um produto específico (/produto/...), o item "Produtos" fica aceso.
MENU_PAI = {'produto': 'produtos', 'pais': 'paises'}


# ======================================================================
# 4. VARIÁVEIS DISPONÍVEIS EM TODOS OS TEMPLATES
# ======================================================================
# Normalmente cada página só enxerga o que foi passado no render_template.
# O @app.context_processor devolve um dicionário cujas chaves ficam
# disponíveis em TODOS os arquivos .html, sem precisar repassar em cada rota.

@app.context_processor
def variaveis_globais():
    # request.endpoint = nome da função da página atual (ex.: 'produto')
    pagina_atual = request.endpoint
    return {
        'MENU': MENU,
        'menu_ativo': MENU_PAI.get(pagina_atual, pagina_atual),
        'CASOS': CASOS,
        'PAISES': PAISES,
        'CODIGO_DO_PAIS': CODIGO_DO_PAIS,
        'CORES_PAISES': CORES_PAISES,
        'INDICADORES': INDICADORES,
        'arquivo_ranking': dados.arquivo_ranking,
        'periodo': dados.periodo,
        'carregado_em': dados.carregado_em,
    }


# ======================================================================
# 5. FILTROS DE FORMATAÇÃO (usados dentro do HTML)
# ======================================================================
# @app.template_filter('nome') cria um filtro que o HTML usa com a barra |
# Exemplo no template:   {{ 1500000 | moeda }}   ->   US$ 1.500.000
# O valor à esquerda da barra vira o primeiro parâmetro da função.

@app.template_filter('moeda')
def filtro_moeda(valor):
    """1500000 -> 'US$ 1.500.000'"""
    if valor is None:
        return '—'
    return 'US$ ' + f"{valor:,.0f}".replace(',', '.')


@app.template_filter('compacto')
def filtro_compacto(valor):
    """1402407919 -> '1,4 bi'"""
    if valor is None:
        return '—'
    for limite, sufixo in [(1e9, ' bi'), (1e6, ' mi'), (1e3, ' mil')]:
        if abs(valor) >= limite:
            return f"{valor / limite:.1f}".replace('.', ',') + sufixo
    return f"{valor:.0f}"


@app.template_filter('numero')
def filtro_numero(valor, casas=0):
    """Formato brasileiro.  {{ 1234.5 | numero(2) }} -> '1.234,50'"""
    if valor is None or (isinstance(valor, float) and math.isnan(valor)):
        return '—'
    texto = f"{valor:,.{casas}f}"  # Python formata como 1,234.50 (padrão americano)
    # troca vírgula por ponto e vice-versa (o 'X' é só um marcador temporário)
    return texto.replace(',', 'X').replace('.', ',').replace('X', '.')


@app.template_filter('indicador')
def filtro_indicador(valor, chave):
    """Formata um indicador de país de acordo com o tipo dele (em INDICADORES).

    Uso no HTML:  {{ valor | indicador('pib_per_capita') }}
    """
    formato = INDICADORES.get(chave, {}).get('formato')
    if valor is None:
        return '—'
    if formato == 'inteiro':
        return filtro_compacto(valor)
    if formato == 'moeda':
        return 'US$ ' + filtro_numero(valor)
    if formato == 'pct':
        return filtro_numero(valor, 1) + '%'
    if formato == 'idh':
        return filtro_numero(valor, 3)
    return filtro_numero(valor, 2)


@app.template_filter('curto')
def filtro_curto(texto, tamanho=60):
    """Corta textos longos e põe reticências no fim."""
    texto = texto or ''
    if len(texto) <= tamanho:
        return texto
    return texto[:tamanho].rstrip(' ,;') + '…'


# ======================================================================
# 6. FUNÇÕES DE APOIO (usadas por mais de uma página)
# ======================================================================

def linhas_do_catalogo():
    """Nomes das linhas de produto do catálogo, sem repetir e na ordem original."""
    return list(dict.fromkeys(dados.catalogo['Linha']))


def rotulos_do_radar():
    """Nomes legíveis dos indicadores que aparecem no gráfico de radar."""
    return [INDICADORES[v]['nome'] for v in VARIAVEIS_SIMILARIDADE]


# ======================================================================
# 7. PÁGINAS
# ======================================================================
# Cada bloco abaixo é uma página do sistema:
#   @app.route('/endereco')       -> qual endereço abre esta página
#   def nome():                   -> o nome da função (é o que o MENU usa)
#   return render_template(...)   -> qual HTML mostrar e com quais dados
#
# Em render_template('x.html', produtos=lista), o nome à esquerda do "="
# é como o dado se chama dentro do HTML: lá ele aparece como {{ produtos }}.

@app.route('/')  # página inicial
def painel():
    return render_template(
        'painel.html',
        resumo=dados.resumo(),
        por_ano=dados.exportacao_por_ano(),
        casos=dados.contagem_casos(),
        top=dados.top_produtos(),
        paises=dados.paises_resumo(),
    )


@app.route('/produtos')
def produtos():
    # request.args lê o que vem depois do "?" na URL.
    # Ex.: /produtos?linha=Shampoo  ->  linha_escolhida = 'Shampoo'
    linha_escolhida = request.args.get('linha', '')
    return render_template(
        'produtos.html',
        resumo=dados.resumo(),
        produtos=dados.produtos_lista(),
        linhas=linhas_do_catalogo(),
        linha_escolhida=linha_escolhida,
    )


# O trecho <ncm> é uma parte variável da URL: em /produto/33051000
# a função recebe ncm = '33051000'.
@app.route('/produto/<ncm>')
def produto(ncm):
    info = dados.produto(ncm.zfill(8))  # zfill completa com zeros à esquerda até 8 dígitos
    if info is None:
        abort(404)  # produto não existe -> mostra a página de erro (seção 8)
    return render_template('produto.html', p=info)


@app.route('/paises')
def paises():
    return render_template(
        'paises.html',
        paises=dados.paises_resumo(),
        caracteristicas=dados.caracteristicas,
        variaveis=VARIAVEIS_SIMILARIDADE,
    )


@app.route('/pais/<iso>')  # ex.: /pais/AGO
def pais(iso):
    info = dados.pais(iso.upper())
    if info is None:
        abort(404)
    return render_template(
        'pais.html',
        p=info,
        rotulos_radar=rotulos_do_radar(),
        variaveis=VARIAVEIS_SIMILARIDADE,
    )


@app.route('/catalogo')
def catalogo():
    return render_template(
        'catalogo.html',
        linhas=dados.catalogo_agrupado(),
        resumo=dados.resumo(),
    )


@app.route('/ranking')
def ranking():
    return render_template(
        'ranking.html',
        produtos=dados.matriz(),
        linhas_catalogo=linhas_do_catalogo(),
    )


@app.route('/perfil-parecido')
def perfil_parecido():
    return render_template(
        'perfil_parecido.html',
        s=dados.perfil_parecido(),
        rotulos_radar=rotulos_do_radar(),
    )


@app.route('/distribuidores')
def distribuidores():
    """Lista que o notebook Distribuidores.ipynb gravou. O sistema só lê."""
    candidatos = dist.ler()

    # "Força" de cada país = quantas vezes ele aparece em 1º ou 2º lugar no ranking
    em_destaque = dados.ranking[dados.ranking['posicao_final'] <= 2]
    contagem = em_destaque['Países'].value_counts()
    forca_do_pais = {}
    for nome in PAISES.values():
        forca_do_pais[nome] = int(contagem.get(nome, 0))

    canais = list(dict.fromkeys(c['canal'] for c in candidatos))  # sem repetir

    return render_template(
        'distribuidores.html',
        candidatos=candidatos,
        por_pais=dist.contar_por_pais(candidatos, PAISES.values(), forca_do_pais),
        data_coleta=dist.data_da_coleta(),
        total_produtos=len(dados.ncms),
        canais=canais,
    )


@app.route('/distribuidores/planilha')
def baixar_distribuidores():
    """Baixa a planilha Excel só com o que o time comercial usa."""
    # send_file envia um arquivo para download em vez de mostrar uma página
    return send_file(
        dist.planilha(),
        as_attachment=True,
        download_name='distribuidores_palop.xlsx',
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )


# ======================================================================
# 8. PÁGINA DE ERRO
# ======================================================================

@app.errorhandler(404)  # chamada quando a página não existe ou quando há abort(404)
def nao_encontrado(_erro):
    return render_template('erro.html'), 404  # o 404 é o código de "não encontrado"


# ======================================================================
# 9. INICIAR O SERVIDOR
# ======================================================================
# Este bloco só roda quando você executa "python app.py" diretamente.
# debug=True recarrega o servidor sozinho quando você salva o código
# e mostra os erros detalhados no navegador. Nunca ligar numa URL pública:
# a página de erro do debug permite executar Python no servidor.

if __name__ == '__main__':
    app.run(debug=not PRODUCAO, port=5000)
