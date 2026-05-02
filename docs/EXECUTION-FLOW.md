---
tags: [architecture]
---

# PentestAI — Fluxo de Execução Completo

Baseado no código real do PentAGI. Cada passo está verificado no source code.

---

## Visão Geral

```
FASE 1: Criar Flow
FASE 2: Preparar ambiente
FASE 3: Criar Task
FASE 4: Generator cria plano
FASE 5: Loop de execução (subtask → refiner → subtask → refiner → ...)
FASE 6: Reporter gera resultado
FASE 7: Cleanup
```

---

## FASE 1 — Criar Flow

**Onde no código PentAGI:** `controller/flow.go` → `NewFlowWorker()`

**O que acontece:**
1. User faz request à API com o input (ex: "scan https://app.example.com")
2. O server cria um FlowWorker
3. Flow é guardado na DB com status `created`

**Quem faz:**
- `server/` recebe o request HTTP
- `controller/flow.py` cria o FlowWorker

**Estado da DB após esta fase:**
```
flows: { id: 1, status: "created", title: "untitled" }
```

---

## FASE 2 — Preparar Ambiente

**Onde no código PentAGI:** `NewFlowWorker()` continuação + `NewFlowProvider()`

**O que acontece (nesta ordem exacta):**

1. **Criar FlowProvider** — configura qual LLM usar (Claude, GPT, etc.)

2. **Image Chooser** (chamada LLM) — o LLM decide qual imagem Docker usar com base no input do user.
   - No PentAGI: pode escolher Kali Linux, Python, Debian, etc.
   - No SecureDev: será sempre Kali Linux (ou imagem custom nossa)

3. **Language Chooser** (chamada LLM) — o LLM detecta o idioma do user.
   - "scan https://app.example.com" → English
   - "analisa a segurança de https://app.pt" → Portuguese

4. **Flow Descriptor** (chamada LLM) — o LLM gera um título para o flow.
   - Input: "scan https://app.example.com"
   - Output: "Security scan of app.example.com"

5. **Criar Docker container** — com a imagem escolhida, volume isolado, ports alocados.
   - `executor.Prepare(ctx)` cria o container primário
   - Volume: `/work/flow-{id}/`
   - 2 ports alocados (28000 + offset)

6. **Iniciar worker goroutine** — o FlowWorker começa a esperar input.

7. **Enviar o input do user** — o input original é enviado para o worker via channel.

**Agentes que correm:**
- Nenhum dos 10 agentes. São 3 chamadas LLM simples (Image Chooser, Language Chooser, Flow Descriptor) — simple chains sem tools.

**Estado da DB após esta fase:**
```
flows: { id: 1, status: "running", title: "Security scan of app.example.com", model: "claude-sonnet-4-6", language: "en" }
containers: { id: 1, flow_id: 1, status: "running", image: "kali-linux", docker_id: "abc123" }
```

---

## FASE 3 — Criar Task

**Onde no código PentAGI:** `controller/flow.go` → `processInput()` → `controller/task.go` → `NewTaskWorker()`

**O que acontece:**

1. O FlowWorker recebe o input do channel
2. Verifica se há algum task à espera de input (waiting). Se sim, passa o input a esse task.
3. Se não, cria um novo TaskWorker.
4. **GetTaskTitle** (chamada LLM) — gera título para o task.
   - Input: "scan https://app.example.com"
   - Output: "Full security assessment of app.example.com"
5. Task guardado na DB com status `created`.
6. O input do user é guardado como message log (tipo `input`).

**Agentes que correm:**
- Nenhum dos 10. Só uma chamada LLM simples para gerar o título.

**Estado da DB após esta fase:**
```
tasks: { id: 1, flow_id: 1, status: "created", title: "Full security assessment", input: "scan https://app.example.com" }
msg_logs: { type: "input", task_id: 1, content: "scan https://app.example.com" }
```

---

## FASE 4 — Generator Cria Plano

**Onde no código PentAGI:** `NewTaskWorker()` chama `stc.GenerateSubtasks(ctx)` → `providers/provider.go` → `GenerateSubtasks()`

**O que acontece:**

1. O GenerateSubtasks() cria um executor com tools limitadas:
   - `subtask_list` (barrier) — para entregar a lista de subtasks
   - `memorist` (delegação) — para consultar memória de scans anteriores
   - `searcher` (delegação) — para pesquisar info sobre o target

2. Renderiza o prompt do Generator com:
   - O input do user
   - O execution context (vazio neste ponto, é o primeiro task)
   - O conhecimento de como decompor tarefas

3. Corre `performAgentChain()` com o Generator agent (max 20 iterações).

4. O Generator (LLM) analisa o target e cria uma lista de ≤15 subtasks.

5. Cada subtask é guardada na DB com status `created`.

**Agente que corre:** `Generator` (max 20 iterações)
**Pode delegar para:** `Memorist` (consultar scans passados), `Searcher` (pesquisar o target)

**O Generator pode:**
- Chamar `memorist("já scannei apps com Supabase antes?")` para saber técnicas que funcionaram
- Chamar `searcher("que framework usa app.example.com?")` para reconhecimento inicial
- Chamar `subtask_list([...])` para entregar o plano (barrier — para o loop)

**Exemplo de output:**
```
subtask_list([
  { title: "Extract Supabase config", description: "Find Supabase URL and anon key in JS bundle" },
  { title: "Schema discovery", description: "Enumerate tables via REST and GraphQL introspection" },
  { title: "RLS testing", description: "Test Row Level Security on discovered tables" },
  { title: "Auth testing", description: "Test rate limiting, password policy, enumeration" },
  { title: "Security headers", description: "Analyze HTTP security headers" },
  { title: "JWT analysis", description: "Decode and test JWT tokens" },
])
```

**Estado da DB após esta fase:**
```
tasks: { id: 1, status: "created" }
subtasks: [
  { id: 1, task_id: 1, status: "created", title: "Extract Supabase config" },
  { id: 2, task_id: 1, status: "created", title: "Schema discovery" },
  { id: 3, task_id: 1, status: "created", title: "RLS testing" },
  { id: 4, task_id: 1, status: "created", title: "Auth testing" },
  { id: 5, task_id: 1, status: "created", title: "Security headers" },
  { id: 6, task_id: 1, status: "created", title: "JWT analysis" },
]
msg_chains: { type: "generator", task_id: 1, chain: [...mensagens do Generator...] }
```

---

## FASE 5 — Loop de Execução

**Onde no código PentAGI:** `controller/task.go` → `Run()`

**Este é o loop principal. Repete para cada subtask:**

```
for cada subtask na queue:
    1. PopSubtask()                    ← tira a próxima da queue
    2. SubtaskWorker.Run()             ← executa
    3. Se task ficou waiting → para    ← (user precisa dar input)
    4. RefineSubtasks()                ← Refiner ajusta plano
```

**Limite:** max `TasksNumberLimit + 3` = 18 subtasks no total (PentAGI hardcoded).

### FASE 5.1 — PopSubtask

**Onde:** `controller/subtasks.go` → `PopSubtask()`

Tira a próxima subtask com status `created` da queue. Se não há mais, o loop termina.

### FASE 5.2 — Executar Subtask

**Onde:** `controller/subtask.go` → `SubtaskWorker.Run()` → `providers/provider.go` → `PerformAgentChain()`

**O que acontece:**

1. Subtask muda para status `running`.

2. `PrepareAgentChain()` é chamado:
   - Renderiza o system prompt do **Orchestrator** (Primary Agent) com:
     - Execution context (subtasks completadas, subtask actual, subtasks planeadas)
     - Nomes das tools disponíveis
     - Imagem Docker, idioma, timestamp
   - Renderiza a user message com a descrição da subtask actual
   - Cria message chain na DB

3. `PerformAgentChain()` é chamado. Cria o executor do Primary Agent com estas tools:
   - `pentester` (delegação → Scanner)
   - `coder` (delegação → Coder)
   - `searcher` (delegação → Searcher)
   - `memorist` (delegação → Memorist)
   - `adviser` (delegação → Adviser)
   - `installer` (delegação → Installer/Maintenance)
   - `done` (barrier → subtask completa)
   - `ask` (barrier → pedir input ao user, se configurado)

   **Nota:** O Primary Agent NÃO tem terminal, file, browser, search engines, nem vector DB tools directamente. É um puro coordenador — toda a execução é delegada a especialistas.

4. **O loop `performAgentChain()` começa** (max 100 iterações):

```
LOOP (max 100):
│
├── Chama LLM (Claude) com messages + tools
│
├── LLM respondeu com tool calls?
│   │
│   ├── NÃO → Reflector
│   │   O Reflector (agente separado, simple chain sem tools) analisa
│   │   a resposta do Orchestrator e gera uma instrução corretiva.
│   │   A instrução é adicionada à chain como mensagem humana.
│   │   O LLM é chamado outra vez. Max 3 tentativas.
│   │   Se falhar 3x → subtask falha.
│   │
│   └── SIM → Para cada tool call:
│       │
│       ├── É "done"?
│       │   → Guarda resultado na DB
│       │   → Subtask status = finished
│       │   → PARA o loop (return PerformResultDone)
│       │
│       ├── É "ask"?
│       │   → Guarda pergunta na DB
│       │   → Subtask status = waiting
│       │   → PARA o loop (return PerformResultWaiting)
│       │   → Quando o user responder, o loop retoma
│       │
│       └── É delegação ("pentester"/"coder"/"searcher"/etc)?
│           → Cria um NOVO performAgentChain() para esse agente
│           → O agente delegado tem o SEU prompt, as SUAS tools, o SEU limite
│           → Corre o loop até o agente chamar o seu barrier (hack_result, code_result, etc.)
│           → O resultado volta como tool response na chain do Orchestrator
│
│           Dentro do agente delegado, o loop é o MESMO performAgentChain():
│           │
│           ├── É "terminal"? (Scanner, Installer)
│           │   → Executa o comando no Docker container via docker exec
│           │   → Captura stdout/stderr
│           │   → Guarda em term_logs na DB
│           │   → Retorna output ao agente
│           │
│           ├── É "file"? (Scanner, Installer)
│           │   → Lê ou escreve ficheiro no container
│           │   → Retorna conteúdo ou confirmação
│           │
│           ├── É "browser"? (Scanner, Coder, Installer, Searcher)
│           │   → Faz request HTTP via scraper service
│           │   → Retorna HTML/screenshot
│           │
│           ├── É search engine? (Searcher)
│           │   → Faz request à API do search engine
│           │   → Retorna resultados
│           │
│           ├── É vector DB? (cada agente tem o seu par search/store)
│           │   → Pesquisa semântica no pgvector
│           │   → Retorna resultados relevantes
│           │
│           ├── É graphiti_search? (Scanner, Coder, Memorist, Enricher)
│           │   → Pesquisa temporal no knowledge graph Neo4j
│           │   → Retorna entidades e relações
│           │
│           └── É barrier (hack_result, code_result, etc.)?
│               → Guarda resultado
│               → PARA o loop do agente delegado
│               → Resultado volta ao Orchestrator como tool response
│
├── Tool call repetida 5+ vezes seguidas?
│   → Repeating Detector aborta para evitar loop infinito
│
├── 20+ tool calls no total?
│   → Mentor (Adviser agent) é chamado
│   → Analisa o progresso do Orchestrator
│   → Dá orientação ("tenta outra abordagem" ou "avança para o próximo teste")
│   → A orientação é injectada no tool response como "enhanced response"
│
├── Message chain ficou grande demais?
│   → Summarizer comprime mensagens antigas
│   → Mantém as últimas mensagens + resumo das anteriores
│
└── Volta ao início do loop
```

5. O loop termina quando:
   - O Orchestrator chama `done` → subtask completa (PerformResultDone)
   - O Orchestrator chama `ask` → subtask pausa (PerformResultWaiting)
   - Max iterações atingido → nas últimas 3 iterações, o Reflector força o agente a chamar `done`
   - Erro irrecuperável → subtask falha (PerformResultError)

**Agentes que podem correr dentro de uma subtask:**
- `Orchestrator` — sempre (é o Primary Agent, só delega)
- `Scanner` — se o Orchestrator delegar via `pentester()` tool call
- `Coder` — se o Orchestrator delegar via `coder()` tool call
- `Installer` — se o Orchestrator delegar via `installer()` tool call
- `Searcher` — se o Orchestrator delegar via `searcher()` tool call
- `Memorist` — se o Orchestrator delegar via `memorist()` tool call
- `Enricher` — automaticamente como primeiro estágio quando `adviser()` é chamado
- `Adviser` — se o Orchestrator delegar via `adviser()` tool call (após Enricher), OU automaticamente pelo Mentor
- `Reflector` — automaticamente quando o Orchestrator não usa tools

**Cada delegação é recursiva:** quando o Orchestrator chama `pentester("testa RLS")`, um novo `performAgentChain()` corre para o Scanner, com o prompt do Scanner, as tools do Scanner, e o limite do Scanner. Se o Scanner precisar, pode ele próprio delegar ao Coder, Searcher ou Installer (novo `performAgentChain()` recursivo).

### FASE 5.3 — Verificar se Task está Waiting

**Onde:** `task.go` → `Run()` → `if tw.IsWaiting() { return nil }`

Se a subtask chamou `ask` (pediu input ao user), o TaskWorker para e espera. Quando o user responder, o FlowWorker recebe o input, chama `task.PutInput()`, e o Task retoma de onde parou.

### FASE 5.4 — Refiner Ajusta Plano

**Onde:** `controller/subtasks.go` → `RefineSubtasks()` → `providers/provider.go` → `RefineSubtasks()`

**O que acontece:**

1. Busca à DB: subtasks completadas (com resultados) + subtasks planeadas (por executar).

2. Renderiza o prompt do Refiner com:
   - Subtasks completadas e os seus resultados
   - Subtasks planeadas (as que faltam)

3. Corre `performAgentChain()` com o Refiner agent (max 20 iterações).

4. O Refiner pode:
   - `subtask_patch` com operações:
     - `add` — adicionar nova subtask (ex: "encontrei RPC functions, testar sem auth")
     - `remove` — remover subtask que já não faz sentido (ex: "target não usa GraphQL")
     - `modify` — alterar título/descrição de uma subtask planeada
     - `reorder` — mudar a ordem das subtasks
   - Ou devolver `subtask_patch` com operações vazias (não muda nada)

5. As mudanças são aplicadas na DB:
   - Subtasks com status `created` podem ser removidas ou modificadas
   - Novas subtasks são criadas com status `created`
   - Subtasks já completadas ou em execução NUNCA são tocadas

**Agente que corre:** `Refiner` (max 20 iterações)

**E depois volta ao início do loop (FASE 5.1) — próxima subtask.**

---

## FASE 6 — Reporter Gera Resultado

**Onde:** `controller/task.go` → `Run()` → `Provider.GetTaskResult()` → `providers/provider.go` → `GetTaskResult()`

**Quando:** Depois de todas as subtasks terem sido executadas (a queue ficou vazia).

**O que acontece:**

1. Busca à DB: todas as subtasks e resultados.

2. Renderiza o prompt do Reporter com:
   - Todas as subtasks e resultados
   - Execution context completo

3. Corre `performAgentChain()` com o Reporter agent (max 20 iterações).

4. O Reporter:
   - Analisa todos os resultados
   - Aplica Judge Mode (100% certainty rule)
   - Remove falsos positivos
   - Classifica severidade
   - Gera o resultado final
   - Chama `report_result` (barrier) com o relatório

5. O resultado é guardado na DB no task.

6. O resultado é publicado como message log (tipo `report`).

7. Task status muda para `finished` (ou `failed` se o Reporter reportou falha).

**Agente que corre:** `Reporter` (max 20 iterações)

**Estado da DB após esta fase:**
```
tasks: { id: 1, status: "finished", result: "{ ... JSON report ... }" }
msg_logs: { type: "report", task_id: 1, content: "Full security assessment..." }
```

---

## FASE 7 — Cleanup

**Onde:** `controller/flow.go` — o FlowWorker volta a esperar input ou é finalizado.

**O que acontece:**

1. O TaskWorker.Run() retorna ao FlowWorker.
2. O FlowWorker muda o flow status para `waiting` (espera novo input) ou `finished`.
3. Se o flow é finalizado:
   - Docker containers são parados e removidos
   - Volumes são limpos
   - Flow status muda para `finished`

**No SecureDev:** como cada scan é um flow com um task, o flow termina aqui e o container é destruído.

---

## Resumo: Que agente corre em que fase

| Fase | O que acontece | Agente(s) |
|---|---|---|
| **1. Criar Flow** | Guardar na DB | Nenhum |
| **2. Preparar Ambiente** | Image Chooser, Language Chooser, Flow Descriptor, criar Docker | Nenhum (3 chamadas LLM simples) |
| **3. Criar Task** | Gerar título, guardar na DB | Nenhum (1 chamada LLM simples) |
| **4. Generator** | Criar plano de ataque (≤15 subtasks) | **Generator** (pode delegar a Memorist, Searcher) |
| **5. Loop** | Executar subtasks uma a uma | **Orchestrator** em todas (só delega). Pode delegar a **Scanner**, **Coder**, **Installer**, **Searcher**, **Memorist**, **Adviser** (via **Enricher**). **Reflector** se não usa tools. |
| **5.4 Refiner** | Ajustar plano após cada subtask | **Refiner** |
| **6. Reporter** | Gerar resultado final | **Reporter** |
| **7. Cleanup** | Destruir container | Nenhum |

---

## Chamadas LLM que NÃO são agentes

O PentAGI faz 4 chamadas LLM "simples" (sem tools, sem loop) antes dos agentes entrarem:

1. **Image Chooser** — decide qual Docker image usar
2. **Language Chooser** — detecta idioma do user
3. **Flow Descriptor** — gera título do flow
4. **Task Title** — gera título do task

Estas são simple chains: uma chamada, uma resposta, sem tools. Não passam pelo `performAgentChain()`.

No SecureDev, podemos simplificar: imagem é sempre Kali, idioma detectamos de outra forma, títulos podemos gerar mais simplesmente.

---

## Working Memory — Memória durante o scan

Cada scan tem 3 camadas de memória que permitem aos agentes saber o que já aconteceu:

### 1. Execution Context (automático, todos os agentes recebem)

Resumo auto-gerado a partir da DB. É injetado no system prompt de TODOS os agentes a cada chamada LLM. Atualiza-se a cada subtask completada.

**Onde no PentAGI:** `templates/prompts/execution_context.tmpl` + `full_execution_context.tmpl`

**Exemplo do que cada agente vê:**

```
EXECUTION CONTEXT:

Flow: "Security scan of app.example.com"
Task: "Full security assessment"

Completed subtasks:
  ✅ Subtask 1: "Extract Supabase config"
     Result: URL=https://xyz.supabase.co, key=eyJhbG...

  ✅ Subtask 2: "Schema discovery"
     Result: 15 tables found (users, orgs, payments, invoices...)
             5 RPC functions (soft_delete_org, transfer_funds...)

  ✅ Subtask 3: "RLS testing"
     Result: RLS MISSING on users and payments. orgs protected.

Current subtask:
  🔄 Subtask 4: "Auth testing"

Planned subtasks:
  ⏳ Subtask 5: "Security headers"
  ⏳ Subtask 6: "Test RPC functions without auth"
```

**Como é gerado:** Lê subtasks da DB (tabela `subtasks`), formata títulos + resultados curtos, renderiza no template.

**Importante:** É um RESUMO. Não inclui o output inteiro do nmap, nem todos os headers HTTP — só o resultado condensado. Os detalhes estão no vector store e no Docker volume.

### 2. Vector Store (pesquisa semântica, qualquer agente pode aceder)

Resultados de tools são auto-guardados como embeddings no pgvector DURANTE o scan. Qualquer agente pode pesquisar semanticamente.

**Onde no PentAGI:** `tools/memory.go` + `registry.go` → `allowedStoringInMemoryTools`

**Tools cujo output é auto-guardado (do PentAGI, 18 tools):**

```
terminal       → output de cada comando executado
file           → conteúdo de ficheiros lidos/escritos
browser        → conteúdo de páginas visitadas
google         → resultados de pesquisa
duckduckgo     → resultados de pesquisa
tavily         → resultados de pesquisa
traversaal     → resultados de pesquisa
perplexity     → resultados de pesquisa
sploitus       → exploits encontrados
searxng        → resultados de pesquisa
search         → resultados do Searcher agent
coder          → código gerado pelo Coder
pentester      → resultados do Scanner
advice         → conselhos do Adviser
maintenance    → resultados do Installer
```

**Como um agente pesquisa:**

```
Orchestrator: memorist("que tabelas foram encontradas no schema discovery?")
  → Memorist chama search_in_memory("tabelas schema discovery")
  → pgvector retorna: "15 tables found: users (id, email, name, role),
    orgs (id, name, org_key), payments (id, amount, user_id)..."
  → Resultado volta ao Orchestrator
```

**Diferença do Execution Context:** O execution context tem resumos curtos. O vector store tem os outputs COMPLETOS pesquisáveis por semântica.

### 3. Docker Volume (ficheiros partilhados entre agentes)

O container tem `/work/` onde qualquer agente com a tool `file` pode ler e escrever. Os ficheiros persistem durante todo o scan.

```
/work/
├── nmap_results.xml           ← Scanner guardou output do nmap
├── schema.json                ← Scanner guardou tabelas descobertas
├── js_bundle_analysis.txt     ← Scanner guardou secrets extraídos
├── race_condition.py          ← Coder escreveu script
├── race_results.json          ← Coder guardou resultados do script
├── rls_bypass.sql             ← Coder escreveu query de bypass
└── notes.md                   ← qualquer agente pode usar como scratchpad
```

**Como funciona:** O Scanner corre `terminal("nmap -sV -oX /work/nmap_results.xml target.com")`. Mais tarde, o Coder pode fazer `file("read", "/work/nmap_results.xml")` para ver os resultados. Não precisam de estar na mesma subtask — os ficheiros persistem no volume.

### Resumo das 3 camadas

| Camada | O que guarda | Quem vê | Como acede | Quando desaparece |
|---|---|---|---|---|
| **Execution Context** | Resumo de subtasks (título + resultado curto) | Todos (automático no prompt) | Injetado pelo sistema | Nunca (está na DB) |
| **Vector Store** | Outputs completos de tools como embeddings | Agentes com `search_in_memory` | Pesquisa semântica | Nunca (está na DB) |
| **Docker Volume** | Ficheiros criados durante o scan | Agentes com `file` tool | Leitura direta do ficheiro | Quando o container é destruído |

### Working Memory vs Long-Term Memory (Memorist)

Não confundir:

| | Working Memory | Long-Term Memory |
|---|---|---|
| **Duração** | Dentro de um scan | Entre scans |
| **Quem gere** | Automático (sistema) | Memorist (agente) |
| **Exemplo** | "tabela users tem RLS missing" | "apps Lovable têm sempre PDF.js vulnerável" |
| **Onde vive** | Execution context + vector store + Docker volume | Vector store (doc_type: guide, answer, code) |
| **Desaparece** | Docker volume: sim. DB: não. | Nunca |

O Memorist pode decidir guardar algo da working memory como long-term: `store_guide("SvelteKit form actions always return 200, test response body not status code")`. Isto persiste para scans futuros.

---

## Persistência e Recovery — Se o scan parar a meio

Tudo é guardado na DB a cada passo. Se o servidor crashar, o scan retoma de onde parou.

**Onde no PentAGI:** `controller/flow.go` → `LoadFlowWorker()` + `worker()` que retoma tasks incompletas.

```go
// No startup, o PentAGI carrega flows que ficaram a meio:
for _, task := range fw.tc.ListTasks(fw.ctx) {
    if !task.IsCompleted() && !task.IsWaiting() {
        fw.runTask("continue after loading", task)
    }
}
```

### O que é guardado em cada momento

| Momento | O que guarda | Tabela |
|---|---|---|
| Flow criado | status, target, model | `flows` |
| Container criado | docker_id, image, status | `containers` |
| Task criado | input, title, status | `tasks` |
| Generator cria subtasks | cada subtask (título, descrição) | `subtasks` |
| Subtask começa | status → `running` | `subtasks` |
| LLM responde | mensagem completa como JSON | `msg_chains` |
| Tool call executada | nome, args, resultado | `tool_calls` |
| Terminal output | stdout/stderr | `term_logs` |
| Vector store | embedding do output | `vector_store` |
| Subtask completa | status → `finished`, resultado | `subtasks` |
| Refiner ajusta | subtasks novas/removidas/modificadas | `subtasks` |
| Report final | resultado completo | `tasks` |
| Flow termina | status → `finished` | `flows` |

### Cenário: crash a meio da subtask 3

**Estado na DB:**
```
flow:      status=running
subtask 1: status=finished, result="Found Supabase config..."
subtask 2: status=finished, result="15 tables discovered..."
subtask 3: status=running, result=null         ← ficou a meio
subtask 4: status=created                      ← por executar
subtask 5: status=created                      ← por executar
msg_chains: conversa parcial da subtask 3
```

**Quando o server reinicia:**
```
1. LoadFlowWorker() → carrega flow da DB
2. LoadTaskWorker() → encontra task com subtasks incompletas
3. Subtask 1, 2 → status=finished, SKIP (não repete)
4. Subtask 3 → status=running, RESET para created (reinicia do zero)
5. Recria Docker container (o anterior pode ter morrido)
6. Retoma: executa subtask 3 desde o início
7. Continua subtask 4, 5...
8. Refiner + Reporter normalmente
```

**O que se perde:** A subtask que estava a meio é reiniciada. O progresso DENTRO dessa subtask (tool calls já feitos) perde-se. Mas tudo o que foi completado ANTES está intacto.

**O que NÃO se perde:** Subtasks completadas, os seus resultados, os tool calls guardados, os term logs, os embeddings no vector store. Tudo isto sobrevive ao crash.

---

## Related Notes

- [Docs Home](README.md)
- [[AGENT-ARCHITECTURE]]
- [[PROJECT-STRUCTURE]]
- [[DATABASE-SCHEMA]]
- [[USER-STORIES]]
