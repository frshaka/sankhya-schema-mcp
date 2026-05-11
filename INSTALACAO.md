# Manual de Instalação — Sankhya Schema MCP

Este guia cobre a instalação completa do servidor MCP que conecta o Claude Code ao banco Oracle do Sankhya, permitindo explorar tabelas, campos, índices e executar queries SQL diretamente durante uma conversa.

---

## Índice

1. [Pré-requisitos](#pré-requisitos)
2. [Instalação no Windows](#instalação-no-windows)
3. [Instalação no Linux](#instalação-no-linux)
4. [Configuração das credenciais](#configuração-das-credenciais)
5. [Registro manual do MCP](#registro-manual-do-mcp)
6. [Verificação da instalação](#verificação-da-instalação)
7. [Atualização](#atualização)
8. [Desinstalação](#desinstalação)
9. [Solução de problemas](#solução-de-problemas)

---

## Pré-requisitos

### Obrigatórios (todos os sistemas)

| Requisito | Versão | Como instalar | Como verificar |
|-----------|--------|---------------|----------------|
| **Python** | 3.10 ou superior | [python.org/downloads](https://www.python.org/downloads/) | `python --version` |
| **Git** | qualquer | [git-scm.com](https://git-scm.com/) | `git --version` |
| **Claude Code** | qualquer | [claude.ai/code](https://claude.ai/code) | `claude --version` |
| **Banco Oracle** | 11.2 ou superior | Docker ou instalação local | Acessível via host:porta |

### Windows — requisitos adicionais

| Requisito | Como instalar | Como verificar |
|-----------|---------------|----------------|
| **PowerShell 7+** (pwsh) | [aka.ms/powershell](https://aka.ms/powershell) | `pwsh --version` |

> O PowerShell 5.x que vem com o Windows **não é suficiente**. É necessário o PowerShell 7+ (pwsh).

### Linux — requisitos adicionais

| Requisito | Como instalar | Como verificar |
|-----------|---------------|----------------|
| **curl** | `sudo apt-get install -y curl` | `curl --version` |
| **unzip** | `sudo apt-get install -y unzip` | `unzip -v` |
| **libaio** | Ver tabela abaixo | `ldconfig -p \| grep libaio` |
| **python3-venv** | `sudo apt-get install -y python3-venv` | `python3 -m venv --help` |

**Instalação do libaio por distribuição:**

| Distribuição | Comando |
|--------------|---------|
| Ubuntu 24.04+ | `sudo apt-get install -y libaio1t64` |
| Ubuntu 20.04 / 22.04 | `sudo apt-get install -y libaio1` |
| Debian 12+ | `sudo apt-get install -y libaio1t64` |
| RHEL / CentOS / Fedora | `sudo yum install -y libaio` |
| Arch Linux | `sudo pacman -S libaio` |

---

## Instalação no Windows

### Passo 1 — Clonar o repositório

Abra o PowerShell 7 (pwsh) e execute:

```powershell
git clone https://github.com/frshaka/sankhya-schema-mcp.git
cd sankhya-schema-mcp
```

> Você pode clonar em qualquer pasta. Exemplo: `C:\projetos\sankhya-schema-mcp`

### Passo 2 — Executar o setup automático

```powershell
pwsh -File setup.ps1
```

O script executa as seguintes etapas automaticamente:

| Etapa | O que faz | Condição para pular |
|-------|-----------|---------------------|
| 1 | Baixa o Oracle Instant Client 21c do GitHub Releases | Pasta `instantclient/` já existe |
| 2 | Cria ambiente virtual Python em `.venv/` | Arquivo `.venv\Scripts\python.exe` já existe |
| 3 | Instala dependências via pip | Sempre executa |
| 4 | Registra o MCP no arquivo `~/.claude/.claude.json` | Entrada `sankhya-schema` já existe |

**Saída esperada (instalação limpa):**

```
=== Setup Sankhya Schema MCP ===

[OK] Projeto encontrado em: C:\projetos\sankhya-schema-mcp
[1/3] Baixando Oracle Instant Client...
[OK] instantclient/ extraido com sucesso.
[2/3] Criando ambiente virtual Python...
[OK] Ambiente virtual criado.
[3/3] Instalando dependencias Python...
[OK] Dependencias instaladas.
[4/4] Registrando MCP no Claude Code...
  [OK] MCP registrado com sucesso.

=== Instalacao concluida! ===
```

### Passo 3 — Configurar credenciais do banco

Copie o arquivo de exemplo:

```powershell
Copy-Item .env.example .env
```

Edite o arquivo `.env` com as credenciais do seu ambiente:

```ini
SANKHYA_DB_HOST=localhost
SANKHYA_DB_PORT=1521
SANKHYA_DB_SERVICE=XE
SANKHYA_DB_USER=SANKHYA
SANKHYA_DB_PASSWORD=developer
```

> Veja a seção [Configuração das credenciais](#configuração-das-credenciais) para detalhes de cada variável.

### Passo 4 — Reiniciar o Claude Code

Feche e abra o Claude Code novamente. O MCP será carregado automaticamente na próxima sessão.

---

## Instalação no Linux

### Passo 1 — Instalar dependências do sistema

```bash
# Ubuntu/Debian
sudo apt-get update
sudo apt-get install -y curl unzip python3-venv

# libaio (necessário para Oracle Instant Client)
# Ubuntu 24+:
sudo apt-get install -y libaio1t64
# Ubuntu 20/22:
sudo apt-get install -y libaio1
# RHEL/CentOS:
sudo yum install -y libaio
```

### Passo 2 — Clonar o repositório

```bash
git clone https://github.com/frshaka/sankhya-schema-mcp.git
cd sankhya-schema-mcp
```

### Passo 3 — Executar o setup automático

```bash
bash setup.sh
```

O script executa as seguintes etapas automaticamente:

| Etapa | O que faz | Condição para pular |
|-------|-----------|---------------------|
| 1 | Baixa o Oracle Instant Client 21c (Linux x64) do GitHub Releases | `instantclient/libclntsh.so*` já existe |
| 2 | Verifica libaio e cria symlink se necessário (Ubuntu 24+) | `libaio.so.1` já acessível |
| 3 | Cria ambiente virtual Python em `.venv/` | `.venv/bin/python` já existe |
| 4 | Instala dependências via pip | Sempre executa |
| 5 | Torna `start.sh` executável | Sempre executa |
| 6 | Registra o MCP no arquivo `~/.claude.json` | Entrada `sankhya-schema` já existe |

**Saída esperada (instalação limpa):**

```
=== Setup Sankhya Schema MCP ===

[OK] Projeto encontrado em: /home/usuario/sankhya-schema-mcp
[1/3] Baixando Oracle Instant Client para Linux...
[OK] instantclient/ extraído com sucesso.
[2/3] Criando ambiente virtual Python...
[OK] Ambiente virtual criado.
[3/3] Instalando dependências Python...
[OK] Dependências instaladas.
[4/4] Registrando MCP no Claude Code...
  [OK] MCP registrado com sucesso.

=== Instalação concluída! ===
```

### Passo 4 — Configurar credenciais do banco

```bash
cp .env.example .env
nano .env   # ou vim, code, etc.
```

Edite com as credenciais do seu ambiente:

```ini
SANKHYA_DB_HOST=localhost
SANKHYA_DB_PORT=1521
SANKHYA_DB_SERVICE=XE
SANKHYA_DB_USER=SANKHYA
SANKHYA_DB_PASSWORD=developer
```

### Passo 5 — Reiniciar o Claude Code

Feche e abra o Claude Code novamente.

---

## Configuração das credenciais

As credenciais ficam no arquivo `.env` na raiz do projeto. Este arquivo **não é versionado** (está no `.gitignore`).

### Variáveis disponíveis

| Variável | Descrição | Valor padrão |
|----------|-----------|--------------|
| `SANKHYA_DB_HOST` | IP ou hostname do servidor Oracle | `localhost` |
| `SANKHYA_DB_PORT` | Porta do listener Oracle | `1521` |
| `SANKHYA_DB_SERVICE` | SID ou Service Name do banco | `XE` |
| `SANKHYA_DB_USER` | Usuário do banco (schema Sankhya) | `SANKHYA` |
| `SANKHYA_DB_PASSWORD` | Senha do usuário | `developer` |

### Exemplos por ambiente

**Desenvolvimento local (Docker):**
```ini
SANKHYA_DB_HOST=localhost
SANKHYA_DB_PORT=1521
SANKHYA_DB_SERVICE=XE
SANKHYA_DB_USER=SANKHYA
SANKHYA_DB_PASSWORD=developer
```

**Servidor de homologação:**
```ini
SANKHYA_DB_HOST=192.168.1.50
SANKHYA_DB_PORT=1521
SANKHYA_DB_SERVICE=SANKHYA
SANKHYA_DB_USER=SANKHYA
SANKHYA_DB_PASSWORD=senha_homolog
```

**Servidor de produção:**
```ini
SANKHYA_DB_HOST=10.0.0.100
SANKHYA_DB_PORT=1521
SANKHYA_DB_SERVICE=SANKHYA_PROD
SANKHYA_DB_USER=SANKHYA
SANKHYA_DB_PASSWORD=consultar_dba
```

> **Atenção:** O MCP permite apenas SELECT. Não há risco de alteração de dados, mas em produção consulte o DBA para obter um usuário com permissões restritas de leitura.

---

## Registro manual do MCP

Se o setup automático não conseguiu registrar o MCP (arquivo `.claude.json` não encontrado), faça o registro manual.

### Windows

Edite o arquivo `C:\Users\<seu-usuario>\.claude\.claude.json` e adicione a entrada `sankhya-schema` dentro de `mcpServers`:

```json
{
  "mcpServers": {
    "sankhya-schema": {
      "type": "stdio",
      "command": "pwsh",
      "args": [
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        "C:\\CAMINHO_COMPLETO\\sankhya-schema-mcp\\start.ps1"
      ],
      "env": {}
    }
  }
}
```

> Substitua `C:\\CAMINHO_COMPLETO\\` pelo caminho real onde você clonou o projeto. Use barras duplas (`\\`).

### Linux

Edite o arquivo `~/.claude.json` e adicione:

```json
{
  "mcpServers": {
    "sankhya-schema": {
      "type": "stdio",
      "command": "bash",
      "args": [
        "/CAMINHO_COMPLETO/sankhya-schema-mcp/start.sh"
      ],
      "env": {}
    }
  }
}
```

> Substitua `/CAMINHO_COMPLETO/` pelo caminho real onde você clonou o projeto.

### Observações sobre o registro

- Se o arquivo `.claude.json` já existir e tiver outras entradas em `mcpServers`, adicione apenas a entrada `sankhya-schema` sem remover as existentes
- O campo `"env": {}` é obrigatório mesmo vazio — as variáveis de ambiente são carregadas pelo script `start.ps1` / `start.sh` a partir do `.env`
- Após editar, reinicie o Claude Code

---

## Verificação da instalação

### 1. Verificar registro do MCP

No Claude Code, execute:

```
/mcp
```

Deve aparecer `sankhya-schema` com status **connected** e as seguintes tools:

- `describe_table`
- `search_tables`
- `search_columns`
- `get_foreign_keys`
- `get_indexes`
- `run_query`
- `validate_query`
- `table_sample`
- `list_modules`
- `search_entities`

### 2. Teste rápido de conexão

Digite no chat do Claude Code:

```
Liste os módulos do schema Sankhya
```

Se a conexão estiver funcionando, o Claude retornará uma lista de módulos baseada nos prefixos das tabelas.

### 3. Teste de exploração de tabela

```
Descreva a tabela TGFCAB
```

Deve retornar as colunas, tipos e comentários da tabela de cabeçalho de notas.

---

## Atualização

Para atualizar o projeto com a versão mais recente:

```bash
cd sankhya-schema-mcp
git pull origin main
```

Se houver mudanças nas dependências, reinstale:

**Windows:**
```powershell
.\.venv\Scripts\pip install -r requirements.txt
```

**Linux:**
```bash
.venv/bin/pip install -r requirements.txt
```

Reinicie o Claude Code após a atualização.

---

## Desinstalação

### 1. Remover registro do MCP

Edite o arquivo de configuração do Claude Code e remova a entrada `sankhya-schema` de `mcpServers`:

- **Windows:** `C:\Users\<usuario>\.claude\.claude.json`
- **Linux:** `~/.claude.json`

### 2. Remover arquivos do projeto

**Windows:**
```powershell
Remove-Item -Recurse -Force C:\caminho\sankhya-schema-mcp
```

**Linux:**
```bash
rm -rf ~/caminho/sankhya-schema-mcp
```

---

## Solução de problemas

### Problemas comuns — Windows

#### "python não é reconhecido como comando"

O Python não está no PATH do sistema.

**Solução:** Reinstale o Python marcando a opção **"Add Python to PATH"** durante a instalação, ou adicione manualmente:
1. Abra "Variáveis de Ambiente" no Windows
2. Em `Path` do usuário, adicione o caminho do Python (ex: `C:\Users\<usuario>\AppData\Local\Programs\Python\Python312\`)
3. Reinicie o terminal

#### "pwsh não é reconhecido como comando"

O PowerShell 7+ não está instalado.

**Solução:** Instale via [aka.ms/powershell](https://aka.ms/powershell) ou:
```powershell
winget install Microsoft.PowerShell
```

#### "DPI-1047: Cannot locate a 64-bit Oracle Client library"

O Oracle Instant Client não foi encontrado ou está corrompido.

**Solução:**
```powershell
Remove-Item instantclient -Recurse -Force
pwsh -File setup.ps1
```

Se persistir, verifique se o Python é 64-bit:
```powershell
python -c "import struct; print(struct.calcsize('P') * 8)"
# Deve retornar: 64
```

#### MCP aparece como "disconnected" ou "error"

1. Verifique se o banco Oracle está rodando e acessível:
   ```powershell
   Test-NetConnection -ComputerName localhost -Port 1521
   ```

2. Confirme as credenciais no `.env`

3. Teste a conexão Python manualmente:
   ```powershell
   .\.venv\Scripts\python.exe -c "import oracledb; print('oracledb OK')"
   ```

4. Teste a conexão completa:
   ```powershell
   .\.venv\Scripts\python.exe -c "
   import os; from dotenv import load_dotenv; import oracledb
   load_dotenv()
   oracledb.init_oracle_client(lib_dir='instantclient')
   dsn = oracledb.makedsn(os.getenv('SANKHYA_DB_HOST','localhost'), int(os.getenv('SANKHYA_DB_PORT','1521')), sid=os.getenv('SANKHYA_DB_SERVICE','XE'))
   conn = oracledb.connect(user=os.getenv('SANKHYA_DB_USER'), password=os.getenv('SANKHYA_DB_PASSWORD'), dsn=dsn)
   print('Conectado:', conn.version)
   conn.close()
   "
   ```

#### Erro "Execution Policy" ao rodar setup.ps1

```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

Ou execute diretamente com bypass:
```powershell
pwsh -ExecutionPolicy Bypass -File setup.ps1
```

---

### Problemas comuns — Linux

#### "DPI-1047: Cannot locate a 64-bit Oracle Client library"

O Oracle Instant Client não foi encontrado ou o `libaio` está ausente.

**Solução 1 — Reinstalar o Instant Client:**
```bash
rm -rf instantclient/
bash setup.sh
```

**Solução 2 — Instalar libaio:**
```bash
# Ubuntu 24+
sudo apt-get install -y libaio1t64

# Ubuntu 20/22
sudo apt-get install -y libaio1

# RHEL/CentOS
sudo yum install -y libaio
```

**Solução 3 — Verificar symlink (Ubuntu 24+):**

O Ubuntu 24+ renomeou `libaio.so.1` para `libaio.so.1t64`. O setup cria o symlink automaticamente, mas se falhou:
```bash
LIBAIO=$(ldconfig -p | grep libaio | awk '{print $NF}' | head -1)
ln -sf "$LIBAIO" instantclient/libaio.so.1
```

#### MCP aparece como "disconnected" ou "error"

1. Confirme as credenciais no `.env`

2. Verifique se o banco está acessível:
   ```bash
   nc -zv localhost 1521
   ```

3. Teste a importação do oracledb:
   ```bash
   .venv/bin/python -c "import oracledb; print('oracledb OK')"
   ```

4. Teste a conexão completa:
   ```bash
   .venv/bin/python -c "
   import os; from dotenv import load_dotenv; import oracledb
   load_dotenv()
   oracledb.init_oracle_client(lib_dir='instantclient')
   dsn = oracledb.makedsn(os.getenv('SANKHYA_DB_HOST','localhost'), int(os.getenv('SANKHYA_DB_PORT','1521')), sid=os.getenv('SANKHYA_DB_SERVICE','XE'))
   conn = oracledb.connect(user=os.getenv('SANKHYA_DB_USER'), password=os.getenv('SANKHYA_DB_PASSWORD'), dsn=dsn)
   print('Conectado:', conn.version)
   conn.close()
   "
   ```

5. Verifique se `LD_LIBRARY_PATH` está correto no `start.sh`:
   ```bash
   cat start.sh | grep LD_LIBRARY_PATH
   # Deve conter: export LD_LIBRARY_PATH="$DIR/instantclient:$LD_LIBRARY_PATH"
   ```

#### Erro "permission denied" ao executar start.sh

```bash
chmod +x start.sh
```

#### Download do Instant Client falhou

Se o download automático falhar (rede corporativa, proxy, etc.), instale manualmente:

1. Baixe o **Instant Client Basic** para Linux x64 em:
   https://www.oracle.com/database/technologies/instant-client/linux-x86-64-downloads.html

2. Extraia para a pasta `instantclient/` dentro do projeto:
   ```bash
   unzip instantclient-basic-linux.x64-*.zip -d .
   mv instantclient_*/ instantclient/
   ```

3. Execute o setup novamente (ele pulará o download):
   ```bash
   bash setup.sh
   ```

---

### Problemas gerais (Windows e Linux)

#### ORA-00942: table or view does not exist

O usuário configurado no `.env` não tem permissão de leitura nas tabelas do schema Sankhya.

**Solução:** Verifique com o DBA se o usuário tem `SELECT` nas tabelas, ou use diretamente o owner do schema (geralmente `SANKHYA`).

#### Queries demoram muito para responder

O banco pode estar sobrecarregado ou a rede lenta. Teste a latência:

**Linux:**
```bash
time .venv/bin/python -c "
import os; from dotenv import load_dotenv; import oracledb
load_dotenv()
oracledb.init_oracle_client(lib_dir='instantclient')
dsn = oracledb.makedsn(os.getenv('SANKHYA_DB_HOST'), int(os.getenv('SANKHYA_DB_PORT','1521')), sid=os.getenv('SANKHYA_DB_SERVICE'))
conn = oracledb.connect(user=os.getenv('SANKHYA_DB_USER'), password=os.getenv('SANKHYA_DB_PASSWORD'), dsn=dsn)
cur = conn.cursor(); cur.execute('SELECT 1 FROM DUAL'); print(cur.fetchone()); conn.close()
"
```

Se demorar mais de 5 segundos, o problema é de rede/banco, não do MCP.

#### ORA-12541: TNS:no listener

O listener Oracle não está rodando ou a porta está errada.

**Verificações:**
- O banco Oracle está iniciado?
- A porta no `.env` está correta? (padrão: 1521)
- Há firewall bloqueando a porta?

#### ORA-12514: TNS:listener does not currently know of service requested

O SID/Service Name no `.env` está incorreto.

**Solução:** Verifique o nome correto do serviço no banco:
```sql
-- Execute no SQL*Plus ou SQL Developer:
SELECT VALUE FROM V$PARAMETER WHERE NAME = 'instance_name';
```

---

## Referência rápida de comandos

| Ação | Windows | Linux |
|------|---------|-------|
| Instalar | `pwsh -File setup.ps1` | `bash setup.sh` |
| Reinstalar Instant Client | `Remove-Item instantclient -Recurse -Force; pwsh -File setup.ps1` | `rm -rf instantclient/ && bash setup.sh` |
| Reinstalar dependências | `.\.venv\Scripts\pip install -r requirements.txt` | `.venv/bin/pip install -r requirements.txt` |
| Testar importação | `.\.venv\Scripts\python -c "import oracledb; print('OK')"` | `.venv/bin/python -c "import oracledb; print('OK')"` |
| Atualizar projeto | `git pull origin main` | `git pull origin main` |
| Ver logs do MCP | Reiniciar Claude Code com `--mcp-debug` | Reiniciar Claude Code com `--mcp-debug` |
