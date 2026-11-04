# Subir o sistema no PythonAnywhere

Objetivo: o sistema rodando numa URL pública, sem depender da sua máquina.
Tempo: cerca de 30 minutos na primeira vez.

---

## 1. Como as camadas se encaixam

```
navegador
   ↓  HTTPS
nginx          ← cuida de HTTPS, arquivos estáticos, fila
   ↓  WSGI
uWSGI          ← mantém o Python vivo e chama o application
   ↓
seu Flask      ← as rotas do app.py
```

No PythonAnywhere, o nginx e o uWSGI já vêm instalados e são administrados por
eles. Você não instala nem escreve configuração para nenhum dos dois: só
preenche a aba **Web**.

| Camada | Onde se configura |
|---|---|
| HTTPS | aba Web → **Force HTTPS** (seção 5) |
| Arquivos estáticos | aba Web → **Static files** (seção 5) |
| uWSGI → `application` | arquivo WSGI da aba Web, que importa `Sistema/wsgi.py` (seção 5) |
| Flask | `Sistema/app.py` |

---

## 2. Criar a conta

1. pythonanywhere.com → **Pricing & signup** → **Create a Beginner account**
2. Não pede cartão. O usuário que você escolher vira a URL:
   `SEUUSUARIO.pythonanywhere.com`

> **Atenção:** desde janeiro de 2026 a conta grátis expira com 1 mês sem uso.
> Crie perto da apresentação e entre nela de vez em quando enquanto a
> empresa estiver testando.

---

## 3. O que subir (e o que não subir)

Suba **só isto**:

```
Sistema/                              (tudo)
ColetarDados/Resultados/              (os CSVs e as figuras)
DadosBrutos/V_EXPORTACAO_.csv
Catalogo/catalogo_linha_grupo_ncm.csv
```

**Não suba:** `.git/`, `Catalogo/catalogo.pdf` (16 MB, o sistema não usa),
os notebooks, a pasta `TCC I/`, `__pycache__/`.

Isso deixa o envio em poucos MB, bem dentro dos 512 MB do plano grátis.

Como subir: aba **Files** → crie a pasta `palop` → envie um .zip e
descompacte pelo console (`unzip palop.zip`). É mais rápido que arquivo
por arquivo.

A estrutura no servidor tem que ficar assim, porque o `dados.py` procura
as pastas um nível acima de `Sistema/`:

```
/home/SEUUSUARIO/palop/
├── Sistema/
├── ColetarDados/Resultados/
├── DadosBrutos/
└── Catalogo/
```

---

## 4. Instalar as bibliotecas

Aba **Consoles** → **Bash**, usando **a mesma versão do Python** que você vai
escolher no web app (seção 5). Troque `3.XX` por ela:

```bash
python3.XX -m pip install --user -r /home/SEUUSUARIO/palop/Sistema/requirements.txt
```

O `requirements.txt` fixa as versões testadas no desenvolvimento. Se o pip
recusar alguma, o Python escolhido é antigo demais para ela: use um mais novo.

---

## 5. Criar o web app

1. Aba **Web** → **Add a new web app**
2. Domínio: aceite o `SEUUSUARIO.pythonanywhere.com`
3. Framework: **Manual configuration** (não escolha "Flask")
4. Python: a versão mais nova oferecida

### Editar o arquivo WSGI

Ainda na aba **Web**, clique no link do arquivo
`/var/www/SEUUSUARIO_pythonanywhere_com_wsgi.py`.

**Apague tudo** e deixe só isto, trocando `SEUUSUARIO` e a chave:

```python
import os
import sys

path = '/home/SEUUSUARIO/palop/Sistema'
if path not in sys.path:
    sys.path.insert(0, path)

os.environ['FLASK_SECRET_KEY'] = 'cole-aqui-a-chave-gerada'

from wsgi import application
```

O `Sistema/wsgi.py` liga o modo produção (`PRODUCAO=1`) e entrega o
`application` para o uWSGI. A chave fica só neste arquivo do servidor: não a
coloque no repositório.

Para gerar a chave, no console Bash:

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

### Arquivos estáticos

Ainda na aba **Web**, em **Static files**, adicione:

| URL | Directory |
|---|---|
| `/static/` | `/home/SEUUSUARIO/palop/Sistema/static` |

Assim o nginx entrega o CSS e o JS direto, sem passar pelo Python.

### HTTPS

Ainda na aba **Web**, em **Security**, ligue **Force HTTPS**. O certificado de
`*.pythonanywhere.com` já vem pronto.

### Recarregar

Botão verde **Reload** no topo da aba Web. Abra a URL.

---

## 6. O que mudou no app.py, e por quê

**`debug` desligado em produção.** Era `app.run(debug=True)`. Com debug
ligado, qualquer erro abre o console do Werkzeug na página, e por ele se
executa Python no servidor. Numa URL pública isso fica aberto para
qualquer pessoa. Agora: `app.run(debug=not PRODUCAO, port=5000)`.

**Chave de sessão vinda do ambiente.** Era sempre `secrets.token_hex(16)`, o
que gera uma chave nova a cada restart e em cada processo. O sistema ainda não
usa sessão nem `flash`, então nada quebrava, mas passaria a quebrar se usasse.
Agora lê de `FLASK_SECRET_KEY`, com o comportamento antigo como reserva no
desenvolvimento.

**`before_request` desligado em produção.** O app conferia a data de todos
os CSVs a cada requisição, para reler se um notebook tivesse regravado.
No servidor os notebooks não rodam e os arquivos nunca mudam, então era
trabalho à toa — e é o único ponto que pesaria com vários acessos
simultâneos, já que o plano grátis tem um worker só.

Nada disso muda o comportamento local: sem as variáveis de ambiente
definidas, o app roda exatamente como antes.

---

## 7. Depois de atualizar os dados

Quando você rodar os notebooks de novo e os CSVs mudarem:

1. Suba os novos arquivos para `ColetarDados/Resultados/`
2. Aba **Web** → **Reload**

Sem o Reload o app continua servindo os dados antigos da memória, porque
em produção ele não confere mais os arquivos sozinho.

---

## 8. Antes da apresentação

- [ ] Abrir a URL do celular, fora do wi-fi da empresa
- [ ] Clicar em todas as telas do menu lateral
- [ ] Conferir se o CSS carregou e se os gráficos aparecem
- [ ] Conferir o cadeado de HTTPS na barra do navegador
- [ ] Baixar a planilha de distribuidores
- [ ] Conferir o NCM da demonstração
- [ ] Deixar a URL escrita no último slide, junto com o link do questionário
