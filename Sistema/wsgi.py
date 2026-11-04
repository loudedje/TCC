"""
Ponto de entrada para o servidor de produção.

    navegador -> nginx -> uWSGI -> este arquivo -> rotas do app.py

O uWSGI não executa `python app.py`: ele importa daqui um objeto chamado
`application` e o chama a cada requisição. Por isso o `app.run()` do final
do app.py nunca roda em produção.

No PythonAnywhere, o arquivo WSGI da aba Web importa `application` daqui
(ver DEPLOY.md).
"""

import os
import sys

# A pasta Sistema precisa estar no path para o `from app import app` funcionar.
PASTA = os.path.dirname(os.path.abspath(__file__))
if PASTA not in sys.path:
    sys.path.insert(0, PASTA)

# Liga o modo produção antes de importar o app, porque o app.py lê estas
# variáveis no momento da importação.
os.environ.setdefault('PRODUCAO', '1')

from app import app as application   # noqa: E402
