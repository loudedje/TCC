# -*- coding: utf-8 -*-
"""
Candidatos a distribuidor nos cinco PALOP.

Só lê o arquivo que o notebook ColetarDados/Distribuidores.ipynb gravou. Nada
aqui chama a API do Google nem guarda chave: a coleta é feita no notebook, igual
ao ranking e às características dos países. Se o CSV não existir, as páginas
mostram o aviso para rodar o notebook.
"""

from datetime import datetime
from io import BytesIO
from pathlib import Path

import pandas as pd


RAIZ = Path(__file__).resolve().parent.parent
ARQ_DISTRIBUIDORES = RAIZ / "ColetarDados" / "Resultados" / "distribuidores.csv"

# Quais linhas do catálogo da Apti cada canal atende. O catálogo todo é alimento
# seco (não precisa de frio), por isso um mesmo perfil de distribuidor serve para
# todos os NCMs: o que muda é o canal de venda, não o produto.
LINHAS_DO_CANAL = {
    'varejo': ['Sobremesas', 'Refrescos', 'Misturas', 'Achocolatados',
               'Chocolates', 'Confeitos', 'Chá', 'Cereais', 'Aptiva'],
    'food service': ['Food Service', 'Salgados', 'Condimentos', 'Temperapti'],
}


def existe():
    return ARQ_DISTRIBUIDORES.exists()


def data_da_coleta():
    if not existe():
        return None
    quando = datetime.fromtimestamp(ARQ_DISTRIBUIDORES.stat().st_mtime)
    return quando.strftime('%d/%m/%Y')


def ler():
    """Lista de candidatos na ordem em que o notebook gravou."""
    if not existe():
        return []
    tabela = pd.read_csv(ARQ_DISTRIBUIDORES, encoding='utf-8-sig').fillna("")
    return tabela.to_dict('records')


# colunas da planilha que o cliente baixa: coluna do CSV -> título na planilha
COLUNAS_PLANILHA = {
    'nome':      'Empresa',
    'pais':      'País',
    'canal':     'Canal',
    'unidades':  'Lojas no mapa',
    'cidades':   'Cidades',
    'endereco':  'Endereço',
    'site':      'Site',
    'link_mapa': 'Ver no mapa',
    'fonte':     'Fonte',
}


def planilha():
    """Excel com os candidatos, na mesma ordem da página."""
    tabela = pd.DataFrame(ler())
    tabela = tabela[[c for c in COLUNAS_PLANILHA if c in tabela.columns]]
    tabela = tabela.rename(columns=COLUNAS_PLANILHA)

    arquivo = BytesIO()
    with pd.ExcelWriter(arquivo, engine='openpyxl') as escritor:
        tabela.to_excel(escritor, index=False, sheet_name='Distribuidores')
        folha = escritor.sheets['Distribuidores']
        for coluna in folha.columns:
            maior = max(len(str(celula.value or '')) for celula in coluna)
            folha.column_dimensions[coluna[0].column_letter].width = min(maior + 2, 60)
        folha.freeze_panes = 'A2'
    arquivo.seek(0)
    return arquivo


def contar_por_pais(candidatos, nomes_dos_paises, forca_do_pais):
    """Quantos candidatos por país, na ordem de força do país no ranking."""
    linhas = []
    for nome in nomes_dos_paises:
        quantos = 0
        for candidato in candidatos:
            if candidato['pais'] == nome:
                quantos = quantos + 1
        linhas.append({
            'pais': nome,
            'quantos': quantos,
            'forca': forca_do_pais.get(nome, 0),
        })
    linhas.sort(key=lambda linha: linha['forca'], reverse=True)
    return linhas
