---
tags: [architecture]
---

# SecureDev PentestAI — Agent Architecture

> Baseado na arquitetura do PentAGI (vxcontrol/pentagi), adaptado para web app security scanning focado em SMBs.

---

## Overview

O SecureDev PentestAI usa **12 agentes especializados** que colaboram via delegação por tool calls. Cada agente tem um prompt específico, um conjunto restrito de tools, e um papel definido no scan.

A principal diferença vs PentAGI: o conhecimento de segurança das **FASE 0-21** alimenta os prompts dos agentes (especialmente Generator e Scanner), em vez de o LLM inventar tudo do zero.

---

## Os 12 Agentes

### 1. Generator — Planeamento do Scan

**Papel:** Analisa o target e cria um plano de ataque adaptado (lista de subtasks).

**Quando corre:** Uma vez no início de cada Task (FASE 4 do [[EXECUTION-FLOW]]).

**Input que recebe no prompt:**

1. O input do user (ex: "scan https://app.example.com")
2. O resultado do FASE 0 (BackendProfile):
   ```json
   {
     "backend_type": "supabase",
     "supabase_url": "https://xyz.supabase.co",
     "anon_key": "eyJhbG...",
     "project_id": "xyz",
     "framework": "sveltekit",
     "primary_target": "app.example.com",
     "scan_path": ["fase-1", "fase-3", "fase-5", "fase-7", ...]
   }
   ```
3. Um **índice das fases** disponíveis — uma descrição curta de cada fase no `scan_path`, extraída automaticamente do campo `description` do frontmatter de cada SKILL.md em `lusitai-internal-scan/.claude/skills/`:
   ```
   Fases no scan_path deste target:
   - fase-1: Adaptive Reconnaissance — extrair configs, secrets, API keys, mapear attack surface
   - fase-3: RLS Testing — testar Row Level Security em tabelas Supabase
   - fase-5: Authentication Testing — password policies, user enumeration, rate limiting
   - fase-7: Security Headers — CSP, HSTS, CORS, X-Frame-Options
   - ...
   ```

**Nota importante:** O Generator recebe apenas o **índice** (uma linha por fase), NÃO a SKILL.md completa. As SKILL.md completas são injectadas depois no Scanner quando este executa cada subtask. O Generator só precisa de saber **o que** cada fase testa para criar o plano — o **como** é responsabilidade do Scanner.

**Output:** Lista de ≤15 subtasks ordenadas por prioridade, entregue via tool `subtask_list`. Cada subtask inclui um campo `fase` para o Scanner saber qual SKILL.md carregar.

**Tools (6 — confirmado no PentAGI `GetGeneratorExecutor`):**
- `terminal` (environment) — executar comandos no Docker container para reconhecimento activo
- `file` (environment) — ler/escrever ficheiros no container (ex: ler output de um nmap)
- `browser` (search, se disponível) — scraping de páginas web do target
- `searcher` (delegação) — delegar pesquisa externa (CVEs, técnicas, documentação)
- `memorist` (delegação) — consultar memória de scans anteriores
- `subtask_list` (barrier) — entregar o plano final (para o loop)

**Nota sobre terminal/file/browser:** O Generator **não é um planeador passivo**. Antes de criar o plano, pode fazer reconhecimento activo para complementar o FASE 0:
```
Generator pensa: "FASE 0 diz que é Supabase, mas quero saber mais"
  → terminal("curl -sI https://app.example.com")        ← verificar headers
  → terminal("nmap -sV -p 80,443 app.example.com")      ← scan de ports rápido
  → browser("https://app.example.com")                   ← ver a página
  → memorist("como correu o último scan de app Supabase?") ← experiência passada
  → searcher("SvelteKit + Supabase common vulnerabilities 2024")
  → subtask_list([...])                                   ← entrega plano informado
```

A tool `file` aqui é **I/O de ficheiros no Docker container** (ler `/work/scan.xml`, escrever `/work/script.py`). Não tem nada a ver com SKILL.md ou skills — é literal read/write de ficheiros no sandbox.

**Prompt inclui:**
- Resultado completo do FASE 0 (backend type, configs, keys, subdomínios)
- Índice das fases disponíveis no scan_path (uma linha por fase)
- Instruções para adaptar o plano ao target concreto
- Regra: incluir campo `fase` em cada subtask

**Limites:** Max 20 iterações do performAgentChain.

**Exemplo completo de execução:**

```
Input: "scan https://app.example.com"
FASE 0: { type: "supabase", url: "https://xyz.supabase.co", key: "eyJ...",
           framework: "sveltekit", scan_path: ["fase-1","fase-2","fase-3",...] }

Índice injectado no prompt:
  - fase-1: Adaptive Reconnaissance — configs, secrets, attack surface
  - fase-2: Schema Discovery — database schema, tabelas, relações
  - fase-3: RLS Testing — Row Level Security em Supabase
  - fase-4: Storage & Functions — buckets, Edge/RPC functions
  - fase-5: Authentication Testing — rate limiting, password policy
  - fase-6: WebSocket/Realtime Testing — subscription hijacking
  - fase-7: Security Headers — CSP, HSTS, CORS
  - fase-8: JWT Analysis — algorithm weaknesses, signature bypasses

Generator faz recon rápido:
  → terminal("curl -sI https://app.example.com") → "Server: Vercel, x-powered-by: SvelteKit"
  → memorist("supabase RLS bypasses?") → "Em 3/5 scans Supabase, RLS estava disabled"

Generator cria plano:
  subtask_list([
    { title: "Schema discovery", fase: "fase-2",
      description: "Enumerate tables via /rest/v1/ usando anon key eyJ..." },
    { title: "RLS testing", fase: "fase-3",
      description: "Test RLS on all discovered tables. Historicamente 60% falham." },
    { title: "RPC function testing", fase: "fase-4",
      description: "Discover and test RPC/Edge functions without auth" },
    { title: "Auth testing", fase: "fase-5",
      description: "Test /auth/v1/ rate limiting, enumeration, password policy" },
    { title: "JWT analysis", fase: "fase-8",
      description: "Decode anon key, test role escalation, check expiry" },
    { title: "WebSocket testing", fase: "fase-6",
      description: "Test realtime subscriptions for data leaks" },
    { title: "Storage testing", fase: "fase-4",
      description: "Check /storage/v1/ for public buckets" },
    { title: "Security headers", fase: "fase-7",
      description: "Analyze HTTP headers" },
    { title: "JS bundle analysis", fase: "fase-1",
      description: "Deep scan for hardcoded secrets, API paths" },
  ])
```

**O que acontece depois:** O Orchestrator recebe cada subtask. Quando delega ao Scanner, o sistema lê a SKILL.md da fase referenciada (ex: `scan-fase-3/SKILL.md`) e injecta o conteúdo completo no prompt do Scanner. O Scanner recebe instruções detalhadas de **como** executar o teste.

---

### 2. Orchestrator — Coordenação

**Papel:** Executa cada subtask delegando ao agente certo. É o Primary Agent.

**Quando corre:** Para cada subtask do plano.

**Input:** Descrição da subtask + execution context (o que já foi feito).

**Output:** Resultado da subtask via `done`.

**Tools:**
- `scanner` (delegação) — delegar testes de segurança
- `coder` (delegação) — delegar criação de scripts custom
- `searcher` (delegação) — delegar pesquisa
- `memorist` (delegação) — consultar memória
- `adviser` (delegação) — pedir orientação quando stuck
- `installer` (delegação) — delegar instalação de tools no container
- `done` (barrier) — completar subtask
- `ask` (barrier) — pedir input ao user

**Nota importante:** O Orchestrator **NÃO tem** `terminal` nem `file`. É um puro coordenador — toda a execução é delegada a especialistas (Scanner para testes, Coder para scripts, Installer para setup).

**Prompt inclui:** Contexto da subtask atual, subtasks completadas, subtasks planeadas.

**Limites:** Max 100 iterações.

**Comportamento:** Delega SEMPRE a especialistas. Inclui contexto filtrado e relevante em cada delegação. Nunca executa comandos directamente.

---

### 3. Scanner — Execução de Testes

**Papel:** O agente que realmente corre os testes de segurança. É o equivalente directo ao `pentester` do PentAGI, mantendo o mesmo papel de especialista delegado e o mesmo contrato de resultado.

**Quando corre:** Quando o Orchestrator delega um teste. Tal como no PentAGI, o Scanner corre como um agent loop isolado, com prompt próprio, tools próprias e fim explícito via barrier.

**Input:** Descrição do teste + contexto relevante (configs descobertas, keys, tabelas, endpoints, findings anteriores, etc). O estilo do input segue o `PentesterAction` do PentAGI: uma pergunta/tarefa detalhada para o especialista executar.

**Output:** Resultado via `hack_result`. Mantemos o shape do PentAGI `HackResult`, mas reinterpretamos `message` para a nossa arquitetura MCP: `result` (relatório técnico detalhado em inglês) + `message` (resumo curto interno para handoff entre agentes).

**Tools:**
- `terminal` — nmap, nuclei, sqlmap, curl, ffuf, etc.
- `file` — I/O de ficheiros **dentro do Docker container**. Serve para ler artefactos gerados pelo scan (`/work/nmap.xml`, `/work/response.txt`) e escrever scripts/outputs temporários (`/work/test.py`, `/work/report.md`). Não lê ficheiros do repo nem SKILL.md; é estritamente filesystem do sandbox.
- `browser` — fetch e parsing de páginas web. Hoje a tool suporta `markdown`, `html` e `links`: faz scraping básico do conteúdo HTTP e devolve texto processado para o agente analisar. **Não** tira screenshots, não corre JavaScript, e não é um browser interactivo real nesta fase.
- `sploitus` — motor de pesquisa web especializado em exploits/PoCs. Serve para procurar referências públicas, exploit code e proof-of-concept ligados a versões, produtos ou CVEs específicos. É uma source de pesquisa externa, não uma tool de execução local no container.
- `search_guide` / `store_guide` — guias de pentesting no vector DB
- `graphiti_search` — pesquisa temporal no knowledge graph (Neo4j)
- `searcher` (delegação) — pesquisar CVEs, técnicas
- `coder` (delegação) — pedir scripts custom
- `installer` (delegação) — instalar ferramentas no container
- `memorist` (delegação) — consultar técnicas anteriores
- `adviser` (delegação) — pedir orientação
- `hack_result` (barrier) — entregar resultado

**Nota de arquitectura:** Aqui seguimos o PentAGI de forma próxima. O Scanner não é uma tool simples nem um wrapper de terminal. É um especialista delegado completo, equivalente ao `pentester`: recebe uma tarefa, executa o seu próprio loop, usa as suas tools, pode delegar a outros especialistas, e termina apenas quando chama `hack_result`.

**Leitura correcta destas tools no Scanner:**
- `terminal` e `file` são as tools de execução local no sandbox Docker
- `browser` e `sploitus` são tools de pesquisa/fetch externo, usadas para recolher contexto e referências
- `searcher`, `coder`, `installer`, `memorist`, `adviser` são delegações para outros especialistas, não execução directa
- `hack_result` é a entrega final do Scanner para o Orchestrator

**Quando usar cada tool (seguindo a lógica do `pentester` no PentAGI):**
- `terminal` — usar para executar testes, scanners, HTTP requests, enumeração activa e qualquer comando de segurança que realmente produza evidência no sandbox. É a tool principal do Scanner.
- `file` — usar quando o output de um comando precisa de ser persistido, relido, transformado, ou quando é necessário escrever um artefacto temporário no container. Exemplo: guardar XML do `nmap`, ler um JSON de resposta, escrever um script curto em `/work`.
- `browser` — usar para ler uma página ou documentação específica já identificada, extrair links, ou converter HTML em texto analisável. Em linha com o PentAGI, é uma tool de leitura/fetch direccionado, não de automação interactiva.
- `sploitus` — usar quando o Scanner já conhece um produto, versão, serviço, fingerprint ou CVE e precisa de procurar PoCs, referências de exploit, ou tooling público relacionado. Não substitui a execução local; complementa-a.
- `search_guide` — usar para perguntar "como devo abordar este tipo de teste?" com base em metodologias reutilizáveis guardadas anteriormente.
- `store_guide` — usar apenas quando o Scanner descobre uma técnica ou workflow reutilizável que vale a pena guardar como conhecimento institucional, anonimizado.
- `graphiti_search` — usar primeiro ou cedo no processo para verificar histórico de execução, evitar trabalho repetido, recuperar técnicas que já funcionaram, ou perceber relações entre entidades/factos descobertos.
- `searcher` — delegar quando é preciso research mais profundo ou mais rápido do que o Scanner deve fazer directamente: CVEs, bypass techniques, documentação externa, comparação de versões, exploit intelligence.
- `coder` — delegar quando a hipótese exige script custom, automação específica, payload generation, parser ad hoc, concurrency testing, ou lógica que não cabe bem numa one-liner de terminal.
- `installer` — delegar quando falta uma ferramenta no container, quando uma dependência está quebrada, ou quando a execução exige preparar melhor o ambiente.
- `memorist` — delegar quando o valor principal vem de scans anteriores, padrões repetidos, ou técnicas previamente bem-sucedidas que não estão explícitas no execution context actual.
- `adviser` — delegar quando o Scanner está preso, quando há múltiplas estratégias possíveis, ou quando precisa de orientação táctica para decidir o próximo passo.
- `hack_result` — usar apenas no fim, quando o Scanner já tem evidência suficiente para fechar a tarefa com um relatório técnico detalhado e um resumo curto interno.

**Regra prática de decisão:**
- Preciso de PRODUZIR evidência nova no container → `terminal` / `file`
- Preciso de LER contexto externo ou referências públicas → `browser` / `sploitus`
- Preciso de REUTILIZAR memória ou conhecimento histórico → `graphiti_search` / `search_guide` / `memorist`
- Preciso de AJUDA especializada → `searcher` / `coder` / `installer` / `adviser`
- Já tenho evidência suficiente e vou FECHAR a tarefa → `hack_result`

**Importante:** O Scanner não "atira" só comandos e passa à frente. Tal como o `pentester` no PentAGI, o Scanner executa testes **e analisa os outputs desses testes**: lê respostas HTTP, interpreta output de ferramentas, decide se há evidência suficiente, escolhe próximos passos e só no fim entrega um `hack_result`. A validação final cross-scan e a remoção de falsos positivos continuam a ser responsabilidade do Reporter.

**Principal diferença vs PentAGI:** O Scanner recebe também a nossa skill da fase relevante. Se a subtask tiver `fase`, o sistema lê a `SKILL.md` correspondente (ex: `scan-fase-3/SKILL.md`) e injecta esse conteúdo completo no system prompt do Scanner. Ou seja: copiamos a arquitetura do `pentester`, mas o conhecimento operacional vem das nossas FASE skills em runtime.

**Prompt inclui:**
- A tarefa delegada no estilo PentAGI `pentester`
- Contexto técnico filtrado pelo Orchestrator
- Conhecimento específico da FASE relevante, injectado da `SKILL.md`
- Ferramentas disponíveis no container
- Regras de intensidade (max requests, sem exploração destrutiva)
- Integração com Graphiti para reutilizar técnicas que funcionaram em scans anteriores

**Limites:** Max 100 iterações. Filtro de comandos destrutivos no terminal.

**Como o output flui pelo sistema:**
1. O Scanner usa `terminal`, `file`, `browser`, `sploitus`, memória e/ou delegação para produzir e interpretar evidência.
2. Quando conclui a tarefa, chama `hack_result(result, message)`.
3. O `hack_result` é o barrier do Scanner: o loop do Scanner termina e o `BarrierAwareToolNode` extrai os args da tool call.
4. Esse payload volta ao Orchestrator como tool response da delegação `scanner(...)`.
5. O Orchestrator usa esse resultado para decidir próximos passos: continuar, delegar ao Coder/Searcher/Installer, ou marcar a subtask como concluída.
6. Mais tarde, o Reporter recebe os `hack_result` agregados no execution context e faz a validação final cross-scan.

**Importante sobre `result` vs `message`:**
- `result` — relatório técnico detalhado, com evidência, comandos relevantes, outputs interpretados, limitações e conclusão do teste
- `message` — resumo curto interno para handoff/orquestração, útil para o Orchestrator, Refiner, logs e Reporter sem reler o relatório completo

**Regras de segurança no prompt:**
```
- Detect vulnerabilities, never exploit destructively
- Never execute DELETE, DROP, UPDATE on target data
- Max 30 requests per endpoint for rate limit testing
- If you find exposed data, read 1 record as proof, do not dump
- Never use Metasploit exploit modules
- Always clean up test data you create
```

---

### 4. Coder — Scripts Custom

**Papel:** Escreve scripts quando ferramentas standard não cobrem o cenário.

**Quando corre:** Quando Scanner ou Orchestrator precisam de testes custom.

**Input:** Descrição do que testar + contexto técnico.

**Output:** Resultado via `code_result`.

**Tools:**
- `browser` — scraping de páginas (se disponível)
- `search_code` / `store_code` — exemplos de código no vector DB
- `graphiti_search` — pesquisa temporal no knowledge graph (Neo4j)
- `searcher` (delegação) — pesquisar técnicas
- `installer` (delegação) — instalar dependências no container
- `memorist` (delegação) — consultar código anterior
- `adviser` (delegação) — pedir orientação
- `code_result` (barrier) — entregar resultado

**Nota:** O Coder **não tem** `terminal` nem `file` directamente. Gera código e plano de execução — a execução real é delegada ao Installer ou feita pelo Scanner que pediu o código.

**Prompt inclui:** Linguagens disponíveis (Python, Node.js, bash). Boas práticas de scripting para testes de segurança. Integração com knowledge graph para reutilizar código que funcionou.

**Limites:** Max 100 iterações.

**Casos de uso:**
- Race condition testing (requests concorrentes)
- Business logic testing (preços negativos, workflow bypass)
- WebSocket client custom para teste de subscriptions
- Parser custom para extrair dados de JS bundles complexos
- Chain de vulnerabilidades (combinar finding A + B)

---

### 5. Searcher — Pesquisa de Informação

**Papel:** Motor de conhecimento do sistema. Pesquisa na internet por CVEs, técnicas, versões vulneráveis, documentação e retorna respostas estruturadas. É o agente que dá acesso ao mundo exterior — sem ele, todos os agentes ficam limitados ao que o LLM já sabe.

**Quando corre:** Quando qualquer agente precisa de informação externa. É o agente mais transversal — usado pelo Generator (pesquisa antes de planear), Scanner (pesquisa durante testes), Coder (pesquisa de exemplos de código), Orchestrator (pesquisa para decisões de coordenação), e Refiner (pesquisa para ajustar plano).

**Input:** Query de pesquisa via `ComplexSearch` — contém `question` (query detalhada em inglês) e `message` (resumo curto interno da intenção da pesquisa).

**Output:** Resultado via `search_result` — contém `result` (resposta detalhada) e `message` (resumo curto).

#### Padrão de Delegação (Agent-to-Agent)

O Searcher é o **primeiro agente delegado** do sistema e estabelece o padrão que todos os futuros agentes de delegação seguem. Quando o Generator (ou qualquer agente) chama `search(question, message)`:

1. O graph do agente que chama **pausa** na execução da tool
2. É criado um **novo graph LangGraph** para o Searcher (nova message chain isolada)
3. O Searcher corre autonomamente com as suas próprias tools
4. Quando o Searcher chama `search_result` (barrier), o seu graph **para**
5. O resultado é retornado ao agente que chamou como tool response
6. O agente que chamou **continua** o seu loop

```
┌─────────────────────────────────────┐
│ GENERATOR (graph próprio)           │
│                                     │
│ LLM decide: "preciso pesquisar"    │
│ → chama tool: search(question=...) │
│                                     │
│ Dentro dessa tool call:             │
│ ┌─────────────────────────────────┐ │
│ │ SEARCHER (graph novo, isolado)  │ │
│ │ LLM → search_answer("query")   │ │  ← verifica memória primeiro
│ │ LLM → duckduckgo("query")      │ │  ← pesquisa web
│ │ LLM → browser("url")           │ │  ← lê página específica
│ │ LLM → store_answer(resposta)   │ │  ← guarda para futuro
│ │ LLM → search_result(answer)    │ │  ← barrier para o Searcher
│ │ Retorna: answer string          │ │
│ └─────────────────────────────────┘ │
│                                     │
│ Generator recebe resposta, continua │
└─────────────────────────────────────┘
```

A implementação usa uma **factory function** (`create_searcher_tool(llm, ...)`) que cria uma LangChain tool via closure. Quando chamada, a closure cria um novo Searcher graph, executa-o, e retorna o resultado. Este padrão será replicado para todos os agentes de delegação (Scanner, Coder, Installer, etc.).

**Referência PentAGI:** `handlers.go:674-850` → `GetSubtaskSearcherHandler` / `GetTaskSearcherHandler` criam handlers que chamam `performSearcher()`, que por sua vez cria um novo agent chain.

#### Tools (7 + condicionais)

**Sempre disponíveis:**
- `duckduckgo` — pesquisa web via scraping de `https://html.duckduckgo.com/html/`. Sem API key. Suporta regiões, safe search, time range. Max 10 resultados, 3 retries, 30s timeout
- `browser` — reutilizado do Epic 7 (US-040). HTTP client com httpx, retorna markdown/html/links. Trunca a 16KB. Para ler documentação, CVE details, blog posts
- `memorist` (delegação) — consultar memória de longo prazo. Stub até o Memorist agent ser implementado
- `search_result` (barrier) — entregar resultado final. Args: `result` (relatório detalhado em inglês) + `message` (resumo curto interno para handoff). O `BarrierAwareToolNode` extrai os args e para o loop
- `tavily` — pesquisa research-grade via `https://api.tavily.com/search`. Requer `TAVILY_API_KEY`. Suporta topic filtering, search depth (basic/advanced), domain inclusion/exclusion. Resultados com content, score, answers
- `search_answer` — pesquisa semântica no pgvector por Q&A pairs guardados. Requer Database (Epic 2). Envia 1-5 queries, filtradas por tipo (guide, vulnerability, code, tool, other). Threshold de similaridade 0.2, max 3 resultados por query

**Nota:** O Searcher **não tem `store_answer`**. Ver secção "Decisão: Quem guarda no Knowledge Database" abaixo.

**Não incluídos na v1 (adicionar depois se necessário):**
- `google` — Google Custom Search (requer API key + Engine ID)
- `perplexity` — pesquisa com LLM (requer API key)
- `searxng` — meta-search privado (requer instância self-hosted)
- `traversaal` — structured answers (requer API key)
- `sploitus` — pesquisa de exploits (requer API key)

#### Comportamento do Agente

O Searcher segue uma **estratégia de pesquisa em cascata**:

1. **Verifica memória primeiro** (`search_answer`) — talvez um scan anterior já encontrou esta resposta
2. **Se não encontrou, pesquisa na web** — DuckDuckGo (rápido, grátis) ou Tavily (se disponível, melhor qualidade)
3. **Opcionalmente lê páginas** (`browser`) — para conteúdo mais detalhado de CVE details, documentação, etc.
4. **Guarda findings valiosos** (`store_answer`) — para scans futuros reutilizarem
5. **Entrega a resposta** via `search_result` — loop para

**Regras de eficiência no prompt:**
- Parar após 3-5 ações de pesquisa no máximo
- Se a primeira tool dá resposta suficiente, parar imediatamente
- Não usar mais de 2-3 tools diferentes para uma única query
- Combinar resultados apenas se individualmente incompletos
- Verificar contradições com no máximo 1 fonte adicional

#### Prompt

**System prompt inclui:**
- Papel e autorização (pentesting pré-autorizado, sem disclaimers sobre pesquisa de exploits)
- Prioridade de fontes: memória → tools especializadas → search engines gerais
- Regras de eficiência (max 3-5 ações, parar cedo)
- Protocolo de anonimização (IPs → `{ip}`, domínios → `{domain}`, credenciais → `{username}/{password}`, URLs → `{url}`)
- Como formatar resultados para consumo por outros agentes
- Instruções para usar `search_result` como entrega final

**User message inclui:**
- A questão concreta
- Contexto do task/subtask actual (para o Searcher entender o objectivo do scan)

**Referência PentAGI:** `searcher.tmpl` (144 linhas) + `question_searcher.tmpl` (30 linhas)

#### Limites

- Max **20 iterações** (na prática termina em 3-5)
- **Sem terminal, sem file** — o Searcher só pesquisa, nunca executa comandos
- Timeout de 30s por request HTTP
- Output truncado a 16KB por fonte (para não encher o contexto)

#### Decisão: Quem guarda no Knowledge Database

**Desvio do PentAGI:** No PentAGI, o Searcher guarda resultados imediatamente via `store_answer` — antes de qualquer validação. Isto cria risco de **envenenamento**: informação errada de web pages fica guardada e é reutilizada em scans futuros como se fosse facto confirmado.

**Decisão SecureDev:** O Searcher **não guarda nada**. Só pesquisa e retorna. O armazenamento acontece **a jusante**, depois dos findings serem validados:

```
Searcher encontra info → retorna ao agente que chamou → Scanner usa para testar
  → Scanner confirma vulnerabilidade real com evidências
  → Reporter valida finding (Judge Mode, 100% certainty)
  → Reporter guarda conhecimento confirmado via store_answer
```

**O que é guardado (só pelo Reporter):**
- Técnicas que **realmente funcionaram** ("Cloudflare bypass via User-Agent rotation funcionou em nginx 1.24")
- Vulnerabilidades **confirmadas com evidência** ("Supabase RLS disabled na tabela users — confirmado lendo 150 records")
- Código que **executou com sucesso** (scripts do Coder que o Scanner executou)

**O que NÃO é guardado:**
- Resultados de pesquisa web não verificados
- Info de CVEs de blogs sem confirmação
- Técnicas tentadas mas que não funcionaram

**Resultado:** O knowledge database contém apenas **conhecimento battle-tested** de scans reais. Zero risco de envenenamento por resultados web errados. O sistema fica mais inteligente com cada scan, mas apenas com base em **resultados provados**.

**Mitigações adicionais no `search_answer` (leitura):**
- **Threshold de similaridade** 0.2 — garbage irrelevante não aparece
- **Categorização por tipo** — retrieval filtrado por guide/vulnerability/code/tool/other
- **Anonimização** — dados sensíveis (IPs, domínios, credenciais) foram anonimizados no momento do store

#### Pydantic Models

```python
# Input — recebido do agente que delega
class ComplexSearch(BaseModel):
    question: str   # Query detalhada em inglês
    message: str    # Resumo curto interno da query

# Args dos search engines
class SearchAction(BaseModel):
    query: str              # Query curta e exacta
    max_results: int = 5    # Min 1, max 10
    message: str            # Descrição do que espera encontrar

# Barrier — resultado final do Searcher
class SearchResult(BaseModel):
    result: str    # Relatório/resposta detalhada em inglês
    message: str   # Resumo curto interno para handoff entre agentes

# Vector DB — pesquisa de Q&A pairs
class SearchAnswerAction(BaseModel):
    questions: list[str]    # 1-5 queries semânticas (inglês)
    type: str               # guide|vulnerability|code|tool|other
    message: str

# Vector DB — guardar findings (usado pelo Reporter, não pelo Searcher)
class StoreAnswerAction(BaseModel):
    answer: str      # Resposta em markdown (inglês)
    question: str    # Pergunta original (inglês)
    type: str        # guide|vulnerability|code|tool|other
    message: str
```

#### Exemplo Completo de Execução

```
Scanner delega: search("How to bypass Cloudflare WAF for rate limit testing on nginx 1.24?")

Searcher executa:
  → search_answer(["cloudflare WAF bypass", "rate limit testing nginx"], type="guide")
    ← "Encontrado: Em scan anterior, mudar User-Agent + adicionar delay 2s funcionou"

  → duckduckgo("cloudflare WAF bypass rate limit testing 2024", max_results=5)
    ← 5 resultados com snippets

  → browser("https://blog.example.com/cloudflare-bypass-techniques")
    ← Artigo completo em markdown

  → search_result(
      result="Found 3 techniques for bypassing Cloudflare WAF...",
      message="Encontradas 3 técnicas de bypass do Cloudflare WAF"
    )
    ← barrier — Searcher para

Scanner recebe: "Found 3 techniques for bypassing Cloudflare WAF..."
Scanner continua os seus testes informado pelas técnicas encontradas.

Posteriormente, se a técnica for confirmada com evidência real no scan,
o Reporter (não o Searcher) pode guardar conhecimento validado via `store_answer`.
```

---

### 6. Memorist — Memória de Longo Prazo

**Papel:** Guarda e recupera conhecimento de scans anteriores no vector DB.

**Quando corre:** Quando qualquer agente quer guardar ou consultar conhecimento.

**Input:** Query de pesquisa ou dados para guardar.

**Output:** Resultado via `memorist_result`.

**Tools:**
- `search_in_memory` — pesquisa semântica no vector DB
- `search_guide` / `store_guide` — guias de instalação/uso
- `search_answer` / `store_answer` — pares Q&A
- `search_code` / `store_code` — exemplos de código
- `memorist_result` (barrier) — entregar resultado

**Prompt inclui:** Como categorizar e anonimizar dados antes de guardar. Como fazer queries eficazes ao vector DB.

**Limites:** Max 20 iterações.

**Sem terminal.** O Memorist só interage com o vector DB.

**Exemplos do que guarda:**
- "Apps Lovable sempre têm PDF.js desatualizado"
- "Supabase com RLS disabled é padrão FIND-001 severity CRITICAL"
- "SvelteKit form actions retornam sempre 200 — testar body, não status code"
- Script Python que funcionou para testar race conditions

---

### 7. Adviser — Orientação Estratégica + Mentor

**Papel duplo:**
1. **Adviser:** Dá orientação estratégica quando um agente pede ajuda
2. **Mentor:** Intervém automaticamente quando um agente está preso (20+ tool calls repetidos)

**Quando corre:**
- Por pedido: qualquer agente chama `adviser`
- Automático: execution monitor detecta loops ou 20+ tool calls

**Input:** Contexto do problema + histórico de tentativas.

**Output:** Texto com orientação (simple chain, sem tools).

**Tools:** Nenhum. O Adviser só pensa e aconselha.

**Prompt inclui:** Conhecimento geral de pentesting. Padrões comuns de problemas. Quando sugerir abortar vs tentar abordagem diferente.

**Exemplo de intervenção como Mentor:**
```
Scanner tentou 20x testar rate limiting com curl mas target está atrás de Cloudflare.
Mentor: "Cloudflare bloqueia requests rápidos do mesmo IP. Tenta:
1. Adicionar delays entre requests (2s)
2. Variar User-Agent headers
3. Se continuar bloqueado, documenta como 'rate limiting enforced by WAF' e avança"
```

---

### 8. Installer — Setup de Ferramentas

**Papel:** Instala e configura ferramentas no Docker container em runtime.

**Quando corre:** Quando o Orchestrator, Scanner ou Coder precisam de uma ferramenta que não está no container.

**Input:** Descrição do que instalar/configurar.

**Output:** Resultado via `maintenance_result`.

**Tools:**
- `terminal` — apt install, pip install, configuração
- `file` — escrever configs, scripts de setup
- `browser` — download de ferramentas (se disponível)
- `search_guide` / `store_guide` — guias de instalação no vector DB
- `memorist` (delegação) — consultar instalações anteriores
- `searcher` (delegação) — pesquisar documentação
- `adviser` (delegação) — pedir orientação
- `maintenance_result` (barrier) — entregar resultado

**Prompt inclui:** Docker image actual, ferramentas já instaladas. Boas práticas de instalação (não quebrar dependências existentes).

**Limites:** Max 100 iterações.

**Casos de uso:**
- Instalar ferramenta específica (`apt install sqlmap`)
- Configurar environment (variáveis, PATH)
- Setup de ferramentas custom (compilar de source)
- Resolver dependências em conflito

---

### 9. Enricher — Enriquecimento de Contexto

**Papel:** Adiciona contexto e detalhes a pedidos antes do Adviser responder. É o primeiro estágio de um pipeline two-stage (Enricher → Adviser).

**Quando corre:** Automaticamente como parte do pipeline do Adviser. Quando qualquer agente pede `advice`, o sistema corre Enricher primeiro para juntar contexto, depois passa ao Adviser.

**Input:** A pergunta do agente + outputs de tools relevantes.

**Output:** Resultado via `enricher_result`.

**Tools:**
- `search_in_memory` — pesquisa semântica no vector DB
- `graphiti_search` — pesquisa no knowledge graph
- `enricher_result` (barrier) — entregar contexto enriquecido

**Prompt inclui:** Como encontrar contexto relevante. Que tipo de informação o Adviser precisa para dar bons conselhos.

**Limites:** Max 20 iterações.

**Exemplo:**
```
Scanner pede advice: "Target retorna 403 em /api/users, como contornar?"

Enricher pesquisa:
  - Vector DB: encontra guia sobre bypass de 403 em Cloudflare
  - Graphiti: encontra que em scan anterior, mudar User-Agent funcionou

Enricher entrega contexto enriquecido ao Adviser.
Adviser responde com orientação informada por experiência real.
```

---

### 10. Refiner — Ajuste do Plano

**Papel:** Depois de cada subtask completada, revê o plano e ajusta subtasks restantes.

**Quando corre:** Automaticamente após cada subtask.

**Input:** Subtasks completadas + resultados + subtasks planeadas.

**Output:** Lista atualizada de subtasks via `subtask_patch`.

**Tools:**
- `subtask_patch` (barrier) — add/remove/modify subtasks

**Prompt inclui:** O plano original. Resultados até agora. Critérios para quando expandir (findings críticos) vs quando skip (target não tem a feature).

**Limites:** Max 20 iterações.

**Exemplo:**
```
Subtask 3 completada: "Schema discovery encontrou 20 tabelas e 5 RPC functions"

Refiner ajusta:
- ADD: "Testar RLS em tabelas: users, organisations, payments, invoices"
- ADD: "Testar RPC functions sem auth: soft_delete_org, transfer_funds"
- REMOVE: "GraphQL testing" (target não usa GraphQL)
- MODIFY: "Auth testing" → adicionar context sobre endpoints descobertos
```

---

### 11. Reflector — Correção de Erros

**Papel:** Corrige agentes que devolvem texto em vez de tool calls.

**Quando corre:** Automaticamente quando um agente responde sem usar tools.

**Input:** A resposta em texto do agente + contexto da tarefa.

**Output:** Texto com instrução corretiva (simple chain, sem tools).

**Tools:** Nenhum. O Reflector analisa o erro e dá instruções ao agente.

**Limites:** Max 3 tentativas recursivas. Se falhar 3x, subtask falha.

**Exemplo:**
```
Scanner respondeu: "I would recommend testing the /api/users endpoint"
Reflector: "You must USE the terminal tool to actually test it.
Run: curl -s https://target.com/api/users -H 'apikey: xxx'
Use the terminal tool now."
```

---

### 12. Reporter — Validação + JSON Final + Knowledge Storage

**Papel:** Recebe todos os findings, valida, remove falsos positivos, gera JSON final. **Também é responsável por guardar conhecimento confirmado** no vector DB para reutilização em scans futuros.

**Quando corre:** No final de todas as subtasks.

**Input:** Todos os resultados das subtasks + execution context completo.

**Output:** JSON validado contra Pydantic `ScanReport` via `report_result`.

**Tools:**
- `store_answer` — guarda conhecimento confirmado no pgvector (técnicas que funcionaram, vulnerabilidades confirmadas, código validado). Anonimiza dados sensíveis antes de guardar. Categoriza por tipo (guide, vulnerability, code, tool, other)
- `report_result` (barrier) — entregar relatório final

**Nota:** O `store_answer` está no Reporter (e não no Searcher) por decisão de arquitectura — ver secção "Decisão: Quem guarda no Knowledge Database" no Searcher. Apenas findings validados pelo Judge Mode são guardados, eliminando risco de envenenamento do knowledge database.

**Prompt inclui:**
- Pydantic schema (FindingType enum, Severity, Category)
- Judge Mode rules (100% certainty, no unverified findings)
- CVSS scoring guidelines
- Common inflation patterns to avoid
- GDPR fine calculation
- Instruções para guardar técnicas confirmadas via `store_answer`

**Limites:** Max 20 iterações.

**Judge Mode checklist no prompt:**
```
1. Every finding MUST have corresponding test evidence
2. Never invent vulnerabilities not tested
3. CVSS scores must match actual impact
4. If version unknown, mark as UNVERIFIED and lower severity
5. "Potentially vulnerable" ≠ "Vulnerable"
6. Availability-only issues are HIGH, not CRITICAL
```

**Knowledge storage — o que o Reporter guarda:**
```
Após validar finding "RLS disabled na tabela users":
  → store_answer(
      answer="## Supabase RLS Bypass\nTabela users sem RLS. GET /rest/v1/users retornou 150 records...",
      question="supabase RLS bypass techniques",
      type="vulnerability"
    )
```

---

## Tools por Agente (Resumo)

| Agent | terminal | file | browser | search engines | vector DB | graphiti | delegação | barrier |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **Generator** | ✅ | ✅ | ✅ | — | — | — | searcher, memorist | subtask_list |
| **Orchestrator** | — | — | — | — | — | — | scanner, coder, searcher, memorist, adviser, installer | done, ask |
| **Scanner** | ✅ | ✅ | ✅ | — | guide | ✅ | coder, searcher, memorist, adviser, installer | hack_result |
| **Coder** | — | — | ✅ | — | code | ✅ | searcher, memorist, adviser, installer | code_result |
| **Installer** | ✅ | ✅ | ✅ | — | guide | — | searcher, memorist, adviser | maintenance_result |
| **Searcher** | — | — | ✅ | ✅ | answer (read) | — | memorist | search_result |
| **Memorist** | — | — | — | — | ✅ (all) | ✅ | — | memorist_result |
| **Enricher** | — | — | — | — | ✅ | ✅ | — | enricher_result |
| **Adviser** | — | — | — | — | — | — | — | *(simple chain)* |
| **Refiner** | — | — | — | — | — | — | memorist, searcher | subtask_patch |
| **Reflector** | — | — | — | — | — | — | — | *(simple chain)* |
| **Reporter** | — | — | — | — | answer (write) | — | — | report_result |

**Nota vector DB:** Cada agente tem acesso ao seu próprio par search/store:
- Scanner/Installer: `search_guide` / `store_guide` (guias de pentesting e setup)
- Coder: `search_code` / `store_code` (exemplos de código)
- Searcher: `search_answer` (leitura de pares Q&A — sem store, só lê)
- Reporter: `store_answer` (escrita de conhecimento confirmado — só guarda findings validados)
- Memorist: `search_in_memory` (acesso a tudo)

### Princípio: Least Privilege
- Agentes que **executam** (Scanner, Installer) → terminal + file
- Agentes que **coordenam** (Orchestrator) → só delegação, zero execução directa
- Agentes que **geram código** (Coder) → sem terminal, delega execução ao Installer
- Agentes que **pesquisam** (Searcher) → browser + search engines, sem terminal
- Agentes que **enriquecem** (Enricher) → vector DB + graphiti, sem tools activos
- Agentes que **pensam** (Adviser, Reflector) → zero tools, só texto
- Agentes que **planeiam** (Generator, Refiner) → só tools de controlo + delegação
- Agentes que **lembram** (Memorist) → vector DB + graphiti
- Agentes que **reportam** (Reporter) → só report_result

---

## Fluxo de Execução

```
User submete URL
    │
    ▼
┌─ OWNERSHIP VERIFICATION ─────────────────────────────┐
│  Verificar sd_verify_{token} via meta/DNS/well-known  │
│  Se falha → scan abortado                             │
└───────────────────────────────────────────────────────┘
    │
    ▼
┌─ FASE 0: Backend Detection ──────────────────────────┐
│  Detectar: Supabase / Firebase / Custom API           │
│  Extrair: configs, keys, project ID                   │
└───────────────────────────────────────────────────────┘
    │
    ▼
┌─ GENERATOR ──────────────────────────────────────────┐
│  Input: URL + backend detection result                │
│  Output: Lista de ≤15 subtasks adaptadas ao target    │
│  Usa: conhecimento FASE 1-21 como guia                │
└───────────────────────────────────────────────────────┘
    │
    ▼
┌─ EXECUTION LOOP ─────────────────────────────────────┐
│                                                       │
│  for each subtask:                                    │
│    │                                                  │
│    ├── Orchestrator recebe subtask                    │
│    │   ├── Delega para Scanner (testes)               │
│    │   ├── Delega para Coder (scripts custom)         │
│    │   ├── Delega para Installer (setup tools)        │
│    │   ├── Delega para Searcher (pesquisa)            │
│    │   ├── Chama Adviser se stuck (via Enricher)      │
│    │   └── done() quando completa                     │
│    │                                                  │
│    ├── Se agente não usa tools:                       │
│    │   └── Reflector corrige (max 3x)                 │
│    │                                                  │
│    ├── Se 20+ tool calls:                             │
│    │   └── Adviser/Mentor intervém                    │
│    │                                                  │
│    ├── Se contexto muito grande:                      │
│    │   └── Summarizer comprime                        │
│    │                                                  │
│    └── Refiner ajusta subtasks restantes              │
│                                                       │
└───────────────────────────────────────────────────────┘
    │
    ▼
┌─ REPORTER (Judge Mode) ──────────────────────────────┐
│  1. Recolhe todos os findings                         │
│  2. Valida evidências (100% certainty rule)           │
│  3. Remove falsos positivos                           │
│  4. Classifica severidade (CVSS)                      │
│  5. Gera JSON validado contra Pydantic ScanReport     │
└───────────────────────────────────────────────────────┘
    │
    ▼
deep-scan.json (entregue ao cliente)
```

---

## Filtro de Comandos Destrutivos

O terminal tem um filtro que bloqueia comandos destrutivos antes de executar no Docker:

```
BLOQUEADOS:
- Metasploit exploit modules (msfconsole.*exploit)
- SQL destructivo (DROP TABLE, DELETE FROM, TRUNCATE)
- HTTP destructivo (curl -X DELETE contra target)
- System destructivo (rm -rf, mkfs, dd if=/dev/zero)
- DoS patterns (fork bombs, flood, --stress)
- Data exfiltration em massa (mysqldump, pg_dump contra target)

PERMITIDOS:
- Todos os scans (nmap, nuclei, sqlmap --level=1, ffuf)
- HTTP requests (GET, POST para testar)
- File operations dentro do container
- Instalação de tools (pip install, apt install)
- Scripts custom do Coder
```

---

## Infraestrutura

```
┌─────────────────────────────────────────┐
│  SecureDev PentestAI Backend (Python)   │
│  ├── LangChain/LangGraph (agentes)     │
│  ├── Agent Engine (orquestração)        │
│  ├── PostgreSQL + pgvector (state + DB) │
│  ├── Neo4j + Graphiti (knowledge graph) │
│  └── Docker SDK (gestão de containers)  │
├─────────────────────────────────────────┤
│  Por cada scan:                         │
│  ├── Docker Container (Kali Linux)      │
│  │   └── nmap, nuclei, sqlmap, etc.     │
│  └── Volume isolado: /work/scan-{id}    │
├─────────────────────────────────────────┤
│  LLM Provider                           │
│  └── Claude (Anthropic API, primary)    │
│  └── Multi-provider (OpenAI, etc.)      │
└─────────────────────────────────────────┘
```

---

## Comparação PentAGI → SecureDev

| PentAGI | SecureDev | Diferença |
|---|---|---|
| Primary Agent | Orchestrator | Mesmo papel — puro coordenador, só delega |
| Generator | Generator | Usa FASE como guia em vez de inventar |
| Refiner | Refiner | Mesmo papel |
| Reporter | Reporter | + Judge Mode + Pydantic validation + store_answer (knowledge storage) |
| Pentester | Scanner | Renomeado, foco em detecção não exploração |
| Coder | Coder | Mesmo papel — sem terminal, delega execução |
| Searcher | Searcher | Sem store_answer (movido para Reporter) + search engines condicionais |
| Memorist | Memorist | Mesmo papel + graphiti_search |
| Adviser | Adviser | Mesmo papel (inclui Mentor automático) |
| Reflector | Reflector | Mesmo papel |
| Installer | Installer | Mesmo papel — setup de ferramentas no container |
| Enricher | Enricher | Mesmo papel — two-stage pipeline com Adviser |
| Summarizer | *(built-in)* | Simple chain com prompt próprio, não é agente com tools |
| Assistant | *(removido)* | Não há modo interativo no scan automático via MCP |

---

## Context Passing entre Agentes

### Princípio: Cada agente tem a sua message chain ISOLADA

Os agentes **não vêem as conversas uns dos outros**. O contexto é passado de forma controlada pelo Orchestrator.

### 3 mecanismos de context passing

**1. Mensagem de delegação (Orchestrator → Especialista)**

O Orchestrator filtra e inclui só o contexto relevante para a tarefa:

```
BOM — contexto filtrado:
scanner("Testa RLS nas tabelas users e orgs.
  Supabase URL: https://xyz.supabase.co
  Anon key: eyJhbG...
  Tabelas descobertas: users, orgs, payments")

MAU — dump de tudo:
scanner("Testa RLS. Aqui estão TODOS os resultados de todas as fases anteriores...")
```

O prompt do Orchestrator diz:
> "When delegating to specialists, provide COMPREHENSIVE context relevant to THEIR task. Do NOT dump all findings — only what's relevant."

**2. Execution Context (injetado no system prompt de todos)**

Resumo do estado do scan — não o detalhe completo:

```
EXECUTION CONTEXT:
  Flow: "Scan https://app.example.com"
  Task: "Full security scan"

  Completed subtasks:
    ✅ "Backend detection" → Supabase, project=xyz
    ✅ "Schema discovery" → 15 tables, 5 RPC functions
    ✅ "RLS testing" → 3 tables unprotected

  Current subtask:
    🔄 "Auth testing"

  Planned subtasks:
    ⏳ "WebSocket testing"
    ⏳ "JS bundle analysis"
```

Todos os agentes vêem este resumo. Dá o "big picture" sem poluir com detalhes.

**3. Resultado via barrier tool (Especialista → Orchestrator)**

```
Scanner executa testes → hack_result("RLS missing em users. Proof: GET returned 150 records")
                              │
                              ▼
Orchestrator recebe como tool response na SUA chain
                              │
                              ▼
Orchestrator decide: passar ao Coder? ao Refiner? guardar para o Reporter?
```

### O que cada agente VÊ vs NÃO VÊ

| Agente | Vê | Não vê |
|---|---|---|
| **Orchestrator** | Todos os resultados (via tool responses) | Conversas internas dos especialistas |
| **Scanner** | Contexto da delegação + execution context | Resultados do Coder, Searcher |
| **Coder** | Contexto da delegação + execution context | Conversas do Scanner |
| **Searcher** | Query de pesquisa | Nada do scan |
| **Memorist** | Query de memória | Nada do scan |
| **Reporter** | Execution context completo + todos os resultados | Conversas internas |

### Como a informação chega ao Reporter

O Reporter **não vê** as message chains dos outros agentes. Não vê as pesquisas do Searcher, as conversas internas do Scanner, nem os tool calls do Generator. Vê apenas:

1. **Execution context** — resumo estruturado de todas as subtasks e resultados
2. **hack_result** de cada Scanner — findings concretos com evidências

```
Quem pode chamar o Searcher (delegação):
  Generator    → search("SvelteKit vulns?")    → resposta usada para PLANEAR
  Scanner      → search("bypass Cloudflare?")  → resposta usada para TESTAR
  Coder        → search("websocket example?")  → resposta usada para CODIFICAR
  Orchestrator → search("tools for GraphQL?")  → resposta usada para COORDENAR
  Refiner      → search("add CORS testing?")   → resposta usada para AJUSTAR PLANO

Fluxo da informação até ao Reporter:
  Searcher retorna ao agente que chamou (tool response na chain desse agente)
  → A pesquisa é CONSUMIDA pelo agente, pode ser summarizada ao longo do tempo
  → Scanner produz hack_result (findings concretos com evidência de teste)
  → Todos os hack_results alimentam o Execution Context
  → Reporter recebe Execution Context + hack_results

  O Reporter trabalha com RESULTADOS DE TESTES, não com resultados de pesquisa.
  Por isso é o lugar certo para store_answer — só vê findings confirmados.
```

### Gestão do tamanho do contexto

| Problema | Solução |
|---|---|
| Chain do Orchestrator cresce demais | **Summarizer** comprime mensagens antigas |
| Execution context fica enorme | É sempre um **resumo** (título + resultado curto) |
| Detalhes perdem-se ao comprimir | Guardados na **DB**, pesquisáveis via **Memorist** |
| Especialista recebe lixo irrelevante | Orchestrator **filtra** na delegação |

### Melhoria futura: Sumarização inteligente

Quando um agente delega ao Searcher e recebe uma resposta detalhada (ex: lista de CVEs com versões e exploits), essa resposta vive na message chain do agente que chamou. Se o agente fizer muitos tool calls depois, o **Summarizer** pode comprimir essa resposta — perdendo detalhes técnicos importantes (CVE numbers, versões específicas).

**Mitigações actuais:**
- O Summarizer preserva as mensagens mais recentes intactas, só comprime as antigas
- O LLM que faz sumarização é instruído para manter detalhes técnicos
- Na prática, o Generator tem max 20 iterações e termina em 5-10 — a chain raramente fica longa o suficiente

**Melhorias a considerar no futuro:**
- **Summarizer com preservação de factos** — extrair factos chave (CVEs, versões, IPs) antes de comprimir e mantê-los como metadata
- **Pinned messages** — marcar certas tool responses como "não comprimir" (ex: resultados de Searcher, configs do FASE 0)
- **Structured context window** — separar factos (sempre visíveis) de narrativa (comprimível)

Isto é mais relevante para o Scanner (max 100 iterações) do que para o Generator. Implementar quando tivermos métricas reais de tamanho de chains.

---

## Gestão de Conhecimento — 3 Camadas

O sistema tem 3 fontes de conhecimento distintas, cada uma com o seu mecanismo de acesso:

### 1. FASE Skills (conhecimento de pentesting estruturado)

**O que é:** 22 SKILL.md files em `lusitai-internal-scan/.claude/skills/` com instruções detalhadas para cada fase de um pentest (FASE 0-21). Este é o conhecimento proprietário do SecureDev — testado em dezenas de scans reais.

**Exemplos:**
- `scan-fase-1/SKILL.md` — Adaptive Reconnaissance (extrair configs, secrets, attack surface)
- `scan-fase-3/SKILL.md` — RLS testing em Supabase
- `scan-fase-5/SKILL.md` — Authentication testing
- `scan-fase-14/SKILL.md` — Authenticated testing com sessões reais

**Como os agentes acedem: Skill Selection (não RAG)**

O Generator escolhe quais fases são relevantes para o target. Quando cria subtasks, inclui a referência à fase:

```
subtask: {
  title: "RLS testing",
  description: "Test RLS on discovered tables",
  fase: "scan-fase-3"  ← referência à skill
}
```

Quando o Scanner recebe esta subtask, o sistema:
1. Lê `scan-fase-3/SKILL.md`
2. Injecta o conteúdo no system prompt do Scanner para esta subtask
3. O Scanner segue as instruções da skill adaptando ao target concreto

**Porquê Skill Selection em vez de RAG:**
- São apenas 22 docs estruturados com scope claro — não são milhares de docs não-estruturados
- Cada skill é injectada inteira (sem perda de contexto por chunking)
- O Generator já sabe o backend type → sabe exactamente quais fases aplicam
- Zero latência (leitura directa de ficheiro vs pesquisa semântica)
- Fiabilidade — o agente recebe a skill completa, não fragmentos

**Mapping backend → fases (definido no Generator prompt):**

| Backend | Fases |
|---------|-------|
| Supabase | FASE 1-21 (path completo) |
| Firebase | FASE 1, 7, 10-13 |
| Custom API | FASE 1, 7, 10-13 |
| Static/Unknown | FASE 1, 7 (minimal) |

### 2. Vector Store / pgvector (memória de scans anteriores)

**O que é:** Resultados de tool calls, guias, código, e Q&A de scans anteriores guardados como embeddings no pgvector.

**Como os agentes acedem: RAG via Memorist**

Qualquer agente pode delegar ao Memorist: `memorist("como testar rate limiting em SvelteKit?")`. O Memorist faz pesquisa semântica no vector store e retorna resultados relevantes.

**O que guarda (auto-persistido durante scans):**
- Outputs de terminal, browser, search engines
- Guias que funcionaram (`store_guide`)
- Código reutilizável (`store_code`)
- Respostas de pesquisa (`store_answer`)

**Porquê RAG aqui:** Centenas/milhares de resultados não-estruturados de scans passados. Pesquisa semântica é a única forma eficiente de encontrar o que é relevante.

### 3. Knowledge Graph / Neo4j + Graphiti (relações entre entidades)

**O que é:** Grafo temporal de entidades e relações descobertas durante scans. Diferente do vector store (que guarda texto), o knowledge graph guarda **relações**: porta 443 → nginx 1.24 → CVE-2024-7890.

**Como os agentes acedem: `graphiti_search` tool**

Disponível para Scanner, Coder, Memorist e Enricher. Suporta 7 tipos de pesquisa:
- `temporal_window` — o que aconteceu num período
- `entity_relationships` — traversal do grafo
- `successful_tools` — técnicas que funcionaram (min N vezes)
- `recent_context` — findings mais recentes
- `episode_context` — reasoning completo de um agente
- `entity_by_label` — entidades por tipo
- `diverse_results` — anti-redundância

**Porquê Knowledge Graph aqui:** Relações entre entidades não se representam bem em vector stores. "Esta versão de nginx tem este CVE que se explora com esta técnica" é um grafo, não um embedding.

### Resumo: 3 Camadas

| Camada | O que guarda | Como acede | Quando usar |
|--------|-------------|------------|-------------|
| **FASE Skills** | Instruções de pentesting (22 docs) | Skill Selection → injectado no prompt | Cada subtask recebe a skill da sua fase |
| **Vector Store** | Resultados de scans passados | RAG via Memorist | Reutilizar técnicas, código, guias |
| **Knowledge Graph** | Relações entre entidades | graphiti_search tool | Encontrar padrões, CVEs, chains |

---

## Decisões de Arquitetura

### Porquê terminal em vez de tools estruturadas?
- Ferramentas de segurança (nmap, nuclei, sqlmap) são binários Linux
- Terminal dá flexibilidade total ao agente
- O agente combina ferramentas, faz pipes, scripts
- Container Docker (Kali) já tem 100+ ferramentas instaladas

### Porquê filtro de comandos?
- SecureDev scan apps em produção de clientes SMB
- Destrutivos (DELETE, DROP, exploit) podem causar dano real
- O filtro bloqueia antes de executar, retorna erro ao agente
- PentAGI não tem filtro porque assume autorização total

### Porquê Generator + FASE como guia?
- FASE 0-21 são 22 skills testadas em dezenas de scans (ver secção "Gestão de Conhecimento")
- O Generator usa Skill Selection para escolher fases relevantes ao target
- Cada subtask recebe a skill da sua fase injectada no prompt do agente
- Resultado: plano inteligente informado por experiência real
- Melhor que PentAGI (inventa do zero) ou fases fixas (não adapta)

### Porquê Memorist?
- SecureDev vai fazer centenas de scans
- Padrões repetem-se (apps Lovable, Supabase patterns, SvelteKit quirks)
- Vector DB permite pesquisa semântica ("como testar rate limiting em SvelteKit?")
- O sistema fica mais inteligente com cada scan

### Porquê Adviser/Mentor?
- Agentes autónomos podem ficar presos em loops
- Reflector corrige "sem tool calls" mas não corrige "tool calls erradas"
- Mentor intervém quando detecta 20+ tool calls repetidos
- Sugere abordagem alternativa ou recomenda skip

---

## Decisões Técnicas LangGraph

### Porquê `StateGraph` custom em vez de `create_agent()`?

O LangChain oferece `create_agent()` que cria automaticamente um loop LLM + tool execution. Não usamos porque:

- **Barrier pattern não suportado.** O `create_agent()` não tem conceito de "barrier tool" — uma tool que quando chamada para o loop e extrai os args como resultado. O nosso `BarrierAwareToolNode` wrapa o `ToolNode` standard e adiciona esta detecção. Isto é o mecanismo core de todos os agentes (Generator para com `subtask_list`, Searcher para com `search_result`, Scanner para com `hack_result`, etc.).
- **Controlo sobre routing.** Precisamos de routing condicional após tool execution (barrier_hit → END, senão → call_llm). O `create_agent()` não expõe este nível de controlo.
- **Reutilização.** O `create_agent_graph()` é genérico — muda tools, barrier_names, e max_iterations para ter qualquer agente. Um factory de agents nosso.

Se no futuro `create_agent()` suportar hooks pós-tool-execution ou barrier detection, reconsideramos.

### RetryPolicy no node LLM

Todos os agentes usam `RetryPolicy(max_attempts=3, initial_interval=1.0)` no node `call_llm`:

```python
from langgraph.types import RetryPolicy

workflow.add_node(
    "call_llm", call_llm,
    retry_policy=RetryPolicy(max_attempts=3, initial_interval=1.0)
)
```

Protege contra erros transientes (HTTP 429 rate limit, network timeout, API server error). Sem retry, um 429 do Claude crasha o graph inteiro — especialmente problemático em sub-graphs (Searcher dentro do Generator), onde o erro borbulha para o agente parent.

### Sub-graphs sem checkpointer (ephemeral)

Os agentes delegados (Searcher, Coder, etc.) criam um graph **novo por invocação**, sem `MemorySaver` ou outro checkpointer. Isto é intencional:

- Cada pesquisa do Searcher é independente — não precisa de persistência entre invocações
- O graph é descartado após retornar o resultado ao agente parent
- Menos overhead (sem writes à DB por cada step)

**Quando precisaremos de checkpointer:** Se implementarmos o barrier `ask` (pausa para input do utilizador) num sub-graph, o checkpointer será necessário para retomar a execução após a resposta. Isso é futuro — para já, sub-graphs são ephemeral.

### Streaming em sub-graphs (melhoria futura)

Actualmente todos os agentes usam `graph.invoke()` — sem streaming. Quando o Searcher corre dentro de um tool call do Generator, o utilizador não vê nada durante 30-60 segundos.

**Melhoria futura:** Usar `get_stream_writer()` do LangGraph para emitir eventos de progresso:

```python
from langgraph.config import get_stream_writer

def call_llm(state):
    writer = get_stream_writer()
    writer({"event": "searching", "tool": "duckduckgo", "query": "..."})
    # ...
```

Isto permitiria ao MCP server enviar updates em tempo real ao cliente: "Pesquisando DuckDuckGo...", "Lendo página...", "Resultado pronto". Não é crítico para a v1, mas melhora significativamente a UX.

---

## Próximos Passos

1. **Database** (Epic 2) — SQLAlchemy models, migrations, CRUD
2. **Docker Sandbox** (Epic 3) — container lifecycle, exec, file ops
3. **Knowledge Graph** (Epic 6) — Neo4j + Graphiti client
4. **Agentes** — um por um, cada agente implementa as suas tools
5. **Agent Engine** — `performAgentChain` em LangGraph (core loop)
6. **Controller** — Flow → Task → Subtask lifecycle
7. **Testes E2E** — dar URL, receber relatório

---

## Related Notes

- [Docs Home](README.md)
- [[EXECUTION-FLOW]]
- [[PROJECT-STRUCTURE]]
- [[USER-STORIES]]
- [[US-037-BASE-GRAPH-EXPLAINED]]
- [[US-038-BARRIERS-EXPLAINED]]
- [[US-054-SEARCH-MODELS-EXPLAINED]]
- [[US-055-SEARCH-RESULT-BARRIER-EXPLAINED]]
