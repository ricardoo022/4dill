---
tags: [database]
---

# Database Setup Guide

Este guia explica como configurar a base de dados PostgreSQL para o projeto lusitai-aipentest.

## 📋 Pré-requisitos

### PostgreSQL
- **Linux (Ubuntu/Debian)**:
  ```bash
  sudo apt-get update
  sudo apt-get install postgresql postgresql-contrib
  sudo systemctl start postgresql
  ```

- **macOS (Homebrew)**:
  ```bash
  brew install postgresql@15
  brew services start postgresql@15
  ```

- **Windows**:
  - Descarregar installer de: https://www.postgresql.org/download/windows/
  - Executar o instalador e guardar a password do user `postgres`

### Python Dependencies
```bash
pip install -e ".[dev]"
```

---

## 🚀 Setup Rápido (Recomendado)

### 1️⃣ Executar Script de Setup

```bash
chmod +x setup_test_db.sh
./setup_test_db.sh
```

Este script irá:
- ✅ Verificar se PostgreSQL está a correr
- ✅ Criar utilizador `pentest_user`
- ✅ Criar bases de dados `pentagidb` (produção) e `pentagidb_test` (testes)
- ✅ Configurar permissões necessárias
- ✅ Criar ficheiro `.env`

### 2️⃣ Testar Conexão

```bash
python test_connection.py
```

Deve ver:
```
✅ Database connection initialized
✅ Query successful: SELECT 1 returned 1
✅ PostgreSQL version: PostgreSQL 15.x on x86_64...
✅ Database connection closed successfully
```

### 3️⃣ Executar Testes

```bash
# Unit tests (sem BD)
pytest tests/unit/database/ -v

# Integration tests (com BD)
pytest tests/integration/database/test_models.py -v

# Ou usar o script helper
./run_tests.sh all
```

---

## 🔧 Setup Manual (Se o script falhar)

### 1️⃣ Criar Utilizador e Bases de Dados

```bash
# Conectar a PostgreSQL
sudo -u postgres psql
```

Ou no Windows:
```bash
psql -U postgres
```

Dentro do `psql`, executar:
```sql
-- Criar utilizador
CREATE USER pentest_user WITH PASSWORD 'pentest_password_secure_123';

-- Criar BD de produção
CREATE DATABASE pentagidb OWNER pentest_user;

-- Criar BD de testes
CREATE DATABASE pentagidb_test OWNER pentest_user;

-- Configurar permissões na BD de produção
GRANT ALL PRIVILEGES ON DATABASE pentagidb TO pentest_user;
\c pentagidb
GRANT ALL PRIVILEGES ON SCHEMA public TO pentest_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO pentest_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO pentest_user;

-- Configurar permissões na BD de testes
\c pentagidb_test
GRANT ALL PRIVILEGES ON SCHEMA public TO pentest_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO pentest_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO pentest_user;

-- Sair
\q
```

### 2️⃣ Criar Ficheiro `.env`

Copiar o conteúdo abaixo para `.env` na raiz do projeto:

```env
# Database Configuration
DATABASE_URL=postgresql+asyncpg://pentest_user:pentest_password_secure_123@localhost:5432/pentagidb
TEST_DATABASE_URL=postgresql+asyncpg://pentest_user:pentest_password_secure_123@localhost:5432/pentagidb_test

# Logging
LOG_LEVEL=DEBUG

# SQL Echo (para debug)
ECHO_SQL=false
```

---

## ✅ Verificar Estado

### Ver Estrutura da BD

```bash
psql -U pentest_user -d pentagidb -c "\dt"
```

### Ver Índices

```bash
psql -U pentest_user -d pentagidb -c "\di"
```

### Ver ENUMs Criados

```bash
psql -U pentest_user -d pentagidb -c "\dT"
```

### Ver Utilizadores

```bash
psql -U postgres -c "\du"
```

---

## 🧪 Executar Testes

### Todos os Testes

```bash
./run_tests.sh all
```

### Unit Tests (sem BD necessária)

```bash
pytest tests/unit/database/ -v
```

### Integration Tests (requer BD)

```bash
pytest tests/integration/database/test_models.py -v -s
```

### Teste Específico

```bash
pytest tests/integration/database/test_models.py::test_flow_defaults -v -s
```

### Com Output Detalhado

```bash
pytest tests/integration/database/ -v -s --tb=long
```

---

## 🐛 Troubleshooting

### ❌ "connection refused"

**Solução:**
```bash
# Linux
sudo systemctl start postgresql
sudo systemctl status postgresql

# macOS
brew services start postgresql@15

# Windows: Iniciar PostgreSQL via Services
```

### ❌ "user/password authentication failed"

**Solução:**
```bash
# Recriar utilizador
sudo -u postgres psql
DROP USER IF EXISTS pentest_user;
CREATE USER pentest_user WITH PASSWORD 'pentest_password_secure_123';
\q
```

### ❌ "database already exists"

**Solução:**
```bash
sudo -u postgres psql
DROP DATABASE IF EXISTS pentagidb;
DROP DATABASE IF EXISTS pentagidb_test;
\q

# Depois correr o setup novamente
./setup_test_db.sh
```

### ❌ "role 'postgres' does not exist"

**Solução** (Ubuntu):
```bash
sudo -u postgres createdb
# Ou reinstalar PostgreSQL
sudo apt-get remove postgresql postgresql-contrib
sudo apt-get install postgresql postgresql-contrib
```

### ❌ Testes Skipped

Se os testes de integração forem skipped é porque a BD não está configurada. Verificar `.env`:

```bash
cat .env
# Deve mostrar DATABASE_URL e TEST_DATABASE_URL

# Ou testar conexão
python test_connection.py
```

### ❌ Import Errors

Se houver erros de import:
```bash
# Reinstalar o projeto em modo de desenvolvimento
pip install -e ".[dev]"

# Limpar cache Python
find . -type d -name __pycache__ -exec rm -rf {} +
```

---

## 📊 Estrutura da BD

```
pentagidb/
├── flows          # Sessões de pentest
├── tasks          # Tarefas dentro de um flow
└── subtasks       # Subtarefas dentro de uma task

flows.id ──┐
           ├── FK ──> tasks.flow_id
                      tasks.id ──┐
                                 ├── FK ──> subtasks.task_id
                                           subtasks.id
```

---

## 📝 Notas Importantes

1. **Credenciais**: Alterar `pentest_password_secure_123` em produção!
2. **Ambientes**: Manter `pentagidb` para dev e `pentagidb_test` para testes
3. **ENUM Types**: Criados automaticamente durante testes
4. **Cascata**: Eliminar um Flow apaga automaticamente Tasks e Subtasks
5. **Timestamps**: `created_at` e `updated_at` são definidos automaticamente

---

## 🔗 Recursos Úteis

- [PostgreSQL Documentation](https://www.postgresql.org/docs/)
- [SQLAlchemy Async](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html)
- [asyncpg](https://magicstack.github.io/asyncpg/)
- [pytest-asyncio](https://pytest-asyncio.readthedocs.io/)

---

## ✨ Quick Commands Cheat Sheet

```bash
# Setup
./setup_test_db.sh

# Testar conexão
python test_connection.py

# Testes
./run_tests.sh unit              # Unit tests
./run_tests.sh models            # Model integration tests
./run_tests.sh all               # Todos os testes

# PostgreSQL CLI
psql -U pentest_user -d pentagidb   # Conectar à BD
\dt                                 # Ver tabelas
\di                                 # Ver índices
\q                                  # Sair

# Limpeza
dropdb -U pentest_user pentagidb
dropdb -U pentest_user pentagidb_test
```

---

Qualquer dúvida, avise! 🚀

---

## Related Notes

- [[DATABASE-SCHEMA]]
- [[PROJECT-STRUCTURE]]
- [[EXECUTION-FLOW]]
- [[Epics/Database/README|Database]]
- [[US-006-SQLALCHEMY-ASYNC-CONNECTION-POOL-EXPLAINED]]
