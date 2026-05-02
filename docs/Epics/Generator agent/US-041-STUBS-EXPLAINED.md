---
tags: [agents]
---

# US-041: Stubs para 'memorist' e 'searcher' — Explicacao Detalhada

Este documento explica o padrão de **Placeholder Tools** usado em `src/pentest/tools/stubs.py` e `src/pentest/models/tool_args.py`. Os stubs sao ferramentas proxy que permitem o LLM chamar tools ainda nao implementadas, sem provocar crashes no grafo ou hallucinations no agente.

---

## Contexto: Por que Stubs?

### O Problema: Agentes Incompletos

O Generator agent precisa do seguinte fluxo de planeamento:

```
1. LLM recebe target info
2. LLM considera: "Deveria verificar se ja temos dados anteriores?"
3. LLM chama tool 'memorist' (recuperar scans anteriores)
4. Se sim: contextualiza o plano com dados passados
5. Se nao: continua planejamento
6. LLM considera: "Deveria fazer buscas externas por CVEs?"
7. LLM chama tool 'searcher' (buscar vulnerabilidades)
8. Finalmente: LLM submete plano (barrier tool)
```

Problema: `memorist` (agente dedicado de memoria) e `searcher` (agente dedicado de busca) ainda nao existem. Se removemos as tools do agente, o LLM:

1. **Hallucina** — "Vou chamar memorist" (tool nao existe)
2. **Erra** — "Tool memorist not found"
3. **Trava** — Agent loop para

Solucao: **Stubs** — tools que existem, retornam mensagens graceis, e guiam o LLM de volta ao planeamento.

### O Beneficio de Stubs

| Aspecto | Sem Stubs | Com Stubs |
|---|---|---|
| LLM tenta chamar memorist | Error: unknown tool | Tool executa, retorna decline message |
| Agent loop | Falha | Continua planejando |
| LLM aprendicado | Hallucina memorist | Conhece memorist, sabe que e tentativa futura |
| Transicao futura | Complexa (reescrever LLM) | Simples (substituir factory) |
| Testes | Impossivel testar fluxos completos | Possivel testar com stubs |

### Arquitetura Futura (Veja AGENT-ARCHITECTURE.md)

Quando `memorist` estiver pronto, substiuimos o stub:

```python
# Hoje (stub)
from pentest.tools.stubs import memorist

# Amanha (sub-graph factory)
from pentest.tools.factories import create_memorist_tool

def create_memorist_tool(llm):
    """Cria um StructuredTool que delegua para um sub-graph.

    Quando chamado, pausa o grafo do Generator, inicia um sub-graph
    isolado que executa o agente de Memory, retorna resultado, resume.
    """
    # Sub-graph memory agent vai aqui
    ...
```

---

## Schemas: MemoristAction e ComplexSearch

Ficheiro: `src/pentest/models/tool_args.py`

### MemoristAction

```python
class MemoristAction(BaseModel):
    """Schema for memorist tool calls."""

    question: str = Field(..., description="Question about previous scan data")
    message: str = Field(..., description="Short internal description of the memorist operation")
```

| Campo | Tipo | Obrigatorio | Descricao |
|---|---|---|---|
| `question` | `str` | Sim | Pergunta concreta sobre dados anteriores (ex: "Que portas estavam abertas no scan anterior?") |
| `message` | `str` | Sim | Descricao humana para logs/audit (ex: "Query memory for open ports") |

**Exemplo de uso:**

```python
memorist.run({
    "question": "What framework versions were discovered in previous scans?",
    "message": "Query memory for framework context"
})
```

### ComplexSearch

```python
class ComplexSearch(BaseModel):
    """Schema for searcher tool calls."""

    question: str = Field(..., description="Question for external search")
    message: str = Field(..., description="Short internal description of the searcher operation")
```

| Campo | Tipo | Obrigatorio | Descricao |
|---|---|---|---|
| `question` | `str` | Sim | Pergunta para busca externa (ex: "Find CVEs in Django 3.2.5 affecting authentication") |
| `message` | `str` | Sim | Descricao humana para logs/audit (ex: "Search for Django CVEs") |

**Exemplo de uso:**

```python
searcher.run({
    "question": "Find active exploits for Apache Struts 2.5.11",
    "message": "Search for Apache Struts vulnerabilities"
})
```

---

## Implementacao: stubs.py

Ficheiro: `src/pentest/tools/stubs.py`

### Imports e Logger Setup

```python
import logging

from langchain_core.tools import tool

from pentest.models.tool_args import ComplexSearch, MemoristAction

logger = logging.getLogger(__name__)
```

| Import | Proposito |
|---|---|
| `logging` | Criar logger para warning quando stub e chamado |
| `@tool` decorator | Registar a funcao como LangChain tool com schema binding |
| `ComplexSearch`, `MemoristAction` | Schemas Pydantic que validam argumentos |
| `logger = logging.getLogger(__name__)` | Logger modular (identifica origem: `pentest.tools.stubs`) |

### Memorist Tool

```python
@tool(args_schema=MemoristAction)
def memorist(question: str, message: str) -> str:
    """Placeholder for memorist tool (not yet implemented).

    The memorist tool retrieves and contextualizes data from previous scans.
    This is a stub that gracefully declines the request until implementation.

    Args:
        question: Question about previous scan data
        message: Short internal description

    Returns:
        Graceful decline message
    """
    logger.warning("Stub handler called for memorist: %s", question)
    return (
        "No previous scan data available. The Memorist agent is not yet implemented. "
        "Proceed with planning based on the target information provided."
    )
```

#### Disseccao Linha a Linha

| Linha | Explicacao |
|---|---|
| `@tool(args_schema=MemoristAction)` | LangChain decorator. Liga a funcao como tool. `args_schema=MemoristAction` força validacao Pydantic dos argumentos antes de executar. |
| `def memorist(question: str, message: str) -> str:` | Assinatura clara. Recebe 2 strings obrigatorias, retorna string. |
| `logger.warning("Stub handler called for memorist: %s", question)` | Log a chamada. Util em producao para auditoria: "Sistema tentou usar memorist com pergunta: ...". O `%s` evita concatenacao string e melhora performance. |
| `return ("No previous scan..." + "Proceed with planning...")` | Mensagem estrategia. **Nao e apenas "not implemented"**. Diz ao LLM: nao temos dados anteriores, continua planejando sem eles. Guia o LLM de volta ao caminho de planeamento. |

#### Porque a Mensagem e Importante

Considerar duas respostas:

```python
# Resposta 1 (ruim)
return "Not implemented"
# LLM pensa: "Hmm, tool falhou. Vou tentar novamente? Vou chamar outra coisa?"
# Resultado: Confusao, retry loop

# Resposta 2 (boa) — a nossa
return (
    "No previous scan data available. The Memorist agent is not yet implemented. "
    "Proceed with planning based on the target information provided."
)
# LLM pensa: "Ah, memória vazia e o agente nao esta pronto. Vou continuar planejando sem dados anteriores."
# Resultado: Decisao clara, retoma planeamento
```

A mensagem e uma **instrucao embutida** que redireciona o LLM.

### Searcher Tool

```python
@tool(args_schema=ComplexSearch)
def searcher(question: str, message: str) -> str:
    """Placeholder for searcher tool (not yet implemented).

    The searcher tool performs external searches for reconnaissance data.
    This is a stub that gracefully declines the request until implementation.

    Args:
        question: Question for external search
        message: Short internal description

    Returns:
        Graceful decline message
    """
    logger.warning("Stub handler called for searcher: %s", question)
    return (
        "External search is not yet available. The Searcher agent is not yet implemented. "
        "Proceed with planning based on the target information provided."
    )
```

Estrutura identica ao `memorist`. A unica diferenca:

- `args_schema=ComplexSearch` em vez de `MemoristAction`
- Mensagem adaptada para contexto de busca

---

## Testes: Layer 1 Patterns

Ficheiro: `tests/unit/tools/test_stubs.py`

### Padroes de Teste (Layer 1)

Seguimos os padroes definidos em `.claude/skills/test-us/references/test-patterns.md`:

```
Layer 1 = Unit tests (fast, local, no external deps)
- Pydantic model validation
- Tool input/output contracts
- Factory-generated instances
```

### Factories com Polyfactory

```python
from polyfactory.factories.pydantic_factory import ModelFactory

class MemoristActionFactory(ModelFactory):
    """Factory for generating MemoristAction instances."""
    __model__ = MemoristAction

class ComplexSearchFactory(ModelFactory):
    """Factory for generating ComplexSearch instances."""
    __model__ = ComplexSearch
```

**O que faz:**

| Operacao | Resultado |
|---|---|
| `MemoristActionFactory.build()` | Gera instancia valida random de `MemoristAction` com strings aleatorias |
| `ComplexSearchFactory.build()` | Gera instancia valida random de `ComplexSearch` com strings aleatorias |

**Por que:**

1. **Nao hardcoding**: Em vez de escrever `MemoristAction(question="Q", message="M")` sempre, gera dados realisticos
2. **Detecta mudancas futuras**: Se alguem adicionar campo obrigatorio a `MemoristAction`, factory falha automaticamente
3. **Reutilisavel**: Factories usadas em testes parametrizados, testes de integracao, etc.

### Teste 1: Validacao de MemoristAction

```python
def test_memorist_action_validation():
    """MemoristAction validates required fields."""
    # Missing required fields should raise ValidationError
    with pytest.raises(ValidationError):
        MemoristAction(question="test")  # Missing message

    with pytest.raises(ValidationError):
        MemoristAction(message="test")  # Missing question

    # Valid instance
    action = MemoristAction(question="What was found?", message="test")
    assert action.question == "What was found?"
    assert action.message == "test"
```

**Valida:**

1. Campos obrigatorios: `question` e `message` nao podem faltar
2. Pydantic valida automaticamente (definido com `Field(...)`)
3. Quando ambos presentes, instancia funciona

### Teste 2: Validacao de ComplexSearch

Identico ao anterior, mas para `ComplexSearch`.

### Teste 3: Factory Gera Instancias Validas

```python
def test_memorist_action_factory():
    """MemoristActionFactory generates valid instances."""
    action = MemoristActionFactory.build()
    assert isinstance(action, MemoristAction)
    assert isinstance(action.question, str)
    assert isinstance(action.message, str)
    assert len(action.question) > 0
    assert len(action.message) > 0
```

**Valida:**

1. Factory nao falha
2. Retorna tipo correto
3. Campos sao strings nao-vazias

### Teste 4: Ferramenta Retorna Mensagem Exata

```python
def test_memorist_tool_returns_stub_message():
    """Memorist tool returns exact stub message."""
    result = memorist.run(
        {"question": "What was previously found?", "message": "Query previous scan"}
    )
    expected = (
        "No previous scan data available. The Memorist agent is not yet implemented. "
        "Proceed with planning based on the target information provided."
    )
    assert result == expected
```

**Critico:**

1. Chama `.run(dict)` — o metodo que LangChain StructuredTool expoe
2. Valida que retorna **exatamente** a mensagem esperada
3. Regressao test: se alguem mudar a mensagem acidentalmente, falha

### Teste 5: Ferramenta com Input Factory-Generated

```python
def test_memorist_tool_with_factory_input():
    """Memorist tool accepts factory-generated input."""
    action = MemoristActionFactory.build()
    result = memorist.run({"question": action.question, "message": action.message})
    expected = (
        "No previous scan data available. The Memorist agent is not yet implemented. "
        "Proceed with planning based on the target information provided."
    )
    assert result == expected
```

**Valida:**

1. Ferramenta nao falha com input aleatorio
2. Ainda retorna mensagem consistente
3. Sem efeitos colaterais de input variavel

### Cobertura Total

| Teste | Type | Funcao |
|---|---|---|
| `test_memorist_action_validation` | Pydantic | Validar schema obrigatorio |
| `test_complex_search_validation` | Pydantic | Validar schema obrigatorio |
| `test_memorist_action_factory` | Factory | Factory gera instancias |
| `test_complex_search_factory` | Factory | Factory gera instancias |
| `test_memorist_tool_returns_stub_message` | Tool contract | Memorist retorna string exata |
| `test_searcher_tool_returns_stub_message` | Tool contract | Searcher retorna string exata |
| `test_memorist_tool_with_factory_input` | Integration | Memorist com input variavel |
| `test_searcher_tool_with_factory_input` | Integration | Searcher com input variavel |

**Total: 8 testes, todos Layer 1 (rapidos, sem dependencias externas)**

---

## Logging: Auditoria e Debugging

### Setup do Logger

```python
logger = logging.getLogger(__name__)
```

Quando `stubs.py` e importado, obtem um logger nomeado `pentest.tools.stubs` (por causa de `__name__`). Permite:

1. **Rastreabilidade**: Logs mostram exatamente que modulo executou
2. **Filtragem**: Producao pode ativar so logs de certos modulos
3. **Configuracao centralizada**: Sistema de logging global controla nivel (DEBUG, INFO, WARNING, ERROR)

### Chamadas de Log

```python
logger.warning("Stub handler called for memorist: %s", question)
logger.warning("Stub handler called for searcher: %s", question)
```

**Por que `warning` e nao `info`?**

- `info`: "Sistema a funcionar normalmente"
- `warning`: "Algo nao-ideal aconteceu (mas nao e erro)"

Usar stub = nao-ideal (ferramenta ainda nao implementada) mas sistema continua. `warning` e apropriado.

### Output de Log

```
WARNING:pentest.tools.stubs:Stub handler called for memorist: What was found in previous scans?
WARNING:pentest.tools.stubs:Stub handler called for searcher: Find CVEs for Django 3.2.5
```

Util em producao:
- Operador ve que memorist foi tentado
- Pode gerar relatorio: "Generator tentou chamar memorist 47 vezes"
- Prioriza implementacao de searcher vs memorist baseado em frequencia

---

## Fluxo Completo: Generator com Stubs

### Cenario: Planeamento Sem Dados Anteriores

```
[Turno 1]
LLM: "Vou verificar se temos dados anteriores"
tool_calls: [{"name": "memorist", "args": {"question": "Previous findings?", "message": "Check memory"}}]

Memorist Stub:
  logger.warning("Stub handler called for memorist: Previous findings?")
  return "No previous scan data available. The Memorist agent is not yet implemented. Proceed with planning..."

Result:
  "No previous scan data available. The Memorist agent is not yet implemented. Proceed with planning based on the target information provided."

LLM Recebe:
  "Ah, memoria vazia. Continuo planejando do zero."

[Turno 2]
LLM: "Vou buscar CVEs externos"
tool_calls: [{"name": "searcher", "args": {"question": "CVEs in Nginx 1.20?", "message": "Search for nginx"}}]

Searcher Stub:
  logger.warning("Stub handler called for searcher: CVEs in Nginx 1.20?")
  return "External search is not yet available. The Searcher agent is not yet implemented. Proceed with planning..."

Result:
  "External search is not yet available. The Searcher agent is not yet implemented. Proceed with planning based on the target information provided."

LLM Recebe:
  "Busca externa nao disponivel. Vou continuarplanejando com informacao local."

[Turno 3]
LLM: "Ja tenho plano suficiente. Vou submeter"
tool_calls: [{"name": "subtask_list", "args": {"subtasks": [...], "message": "Pentest plan ready"}}]

Barrier Tool:
  barrier_hit = True
  Agent Termina com sucesso

Resultado Final:
  - Plano completo criado
  - Memorist e Searcher foram tentados (graciosamente recusados)
  - Sistema continuo funcionando
  - Logs mostram que memorist/searcher foram solicitados
```

---

## Arquitetura Futura: Delegacao via Sub-graphs

Veja `docs/AGENT-ARCHITECTURE.md` para arquitetura completa de sub-graphs.

### Modelo Atual (Stubs)

```
Generator Agent
├── call_llm (pede plano)
├── tool_node
│   ├── memorist (stub) → "not implemented"
│   ├── searcher (stub) → "not implemented"
│   ├── terminal → executa comando
│   ├── file → le/escreve ficheiro
│   └── browser → faz HTTP request
└── barrier_node (subtask_list) → termina
```

Stubs permitem o grafo compilar e funcionar sem implementacoes completas.

### Modelo Futuro (Sub-graphs)

```
Generator Agent
├── call_llm (pede plano)
├── tool_node
│   ├── memorist (factory) → spawns Memorist Sub-graph
│   │   ├── Memorist Agent executa isoladamente
│   │   ├── Pesquisa historia de scans
│   │   └── Retorna dados contextualizados
│   │
│   ├── searcher (factory) → spawns Searcher Sub-graph
│   │   ├── Searcher Agent executa isoladamente
│   │   ├── Faz queries a databases publicas
│   │   └── Retorna CVEs e exploits
│   │
│   ├── [outras tools]...
│   │
│   └── [output -> input Generator agent]
└── barrier_node (subtask_list) → termina
```

### Transicao (Pseudocode)

```python
# Hoje (US-041)
from pentest.tools.stubs import memorist, searcher

tools = [memorist, searcher, terminal_tool, file_tool, browser_tool]

# Amanha (future release)
from pentest.tools.factories import create_memorist_tool, create_searcher_tool

memorist_agent = ... # agente dedicado
searcher_agent = ... # agente dedicado

def create_memorist_tool(memorist_agent):
    """Wrapper que pausa, spawns, retoma."""
    @tool(args_schema=MemoristAction)
    def memorist_delegator(question: str, message: str) -> str:
        # Pausa Generator graph
        # Inicia Memorist sub-graph isolado
        result = run_subgraph(memorist_agent, {"query": question})
        # Retoma Generator graph com resultado
        return result
    return memorist_delegator

tools = [
    create_memorist_tool(memorist_agent),
    create_searcher_tool(searcher_agent),
    ...
]
```

**Beneficio**: A interface para Generator mantem-se igual. So a implementacao interna muda.

---

## Resumo: Stubs como Ferramenta de Transicao

| Aspecto | Hoje (Stubs) | Amanha (Sub-graphs) |
|---|---|---|
| Memorist retorna | "Nao implementado, continua" | Dados contextualizados reais |
| Searcher retorna | "Nao implementado, continua" | CVEs e exploits de databases |
| Generator agent | Funciona plenamente com stubs | Funciona plenamente com sub-graphs |
| Esforco de transicao | Nenhum (mesma interface) | Implementar agentes separados |
| Code churn no Generator | Zero | Zero |
| Risco de regressao | Nenhum | Baixo (interface preservada) |

Stubs sao **investimento na estabilidade futura**.

---

## Related Notes

- [Docs Home](../../README.md)
- [[US-037-BASE-GRAPH-EXPLAINED]] — StateGraph, BarrierAwareToolNode, agent loop
- [[US-038-BARRIERS-EXPLAINED]] — Barrier tools e padroes de terminacao
- [[US-039-TERMINAL-FILE-EXPLAINED]] — Factory pattern com closures
- [[US-040-BROWSER-TOOL-EXPLAINED]] — Async HTTP, content processing
- [[AGENT-ARCHITECTURE]] — Sub-graphs, delegação e multi-agent orchestration
- **src/pentest/tools/stubs.py** — Implementacao completa
- **src/pentest/models/tool_args.py** — Schemas Pydantic
- **tests/unit/tools/test_stubs.py** — Testes Layer 1
