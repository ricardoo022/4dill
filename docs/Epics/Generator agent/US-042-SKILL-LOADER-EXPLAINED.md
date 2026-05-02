---
tags: [agents]
---

# US-042: Skill Index Loading — Explicacao Detalhada

Este documento explica o modulo de **Extracção e Limpeza de Descricoes de SKILL.md** implementado em `src/pentest/skills/loader.py`. O modulo extrai informacao estruturada do frontmatter YAML dos ficheiros de fase, permitindo que o Generator agent compreenda o proposito de cada fase sem consumir contexto excessivo.

---

## Contexto: Por que Extrair Descricoes?

### O Problema: Context Window Limitado

O Generator agent precisa fazer um plano de pentest. Para isto, deve saber:

1. Quais fases estao disponiveis no scan_path
2. O que cada fase faz (proposito e objetivos)
3. Em que ordem executa

Cada ficheiro `SKILL.md` contem ~2-5 KB de conteudo (frontmatter + descricao completa + instrucoes tecnicas). Se carregassemos 22 fases completas:

```
22 fases × 3 KB media = 66 KB de texto
Tokens equivalentes (aprox 1 token por 4 chars): 66,000 / 4 = 16,500 tokens
```

Para um LLM com contexto de 100K tokens, isto deixa so 83.5K para:
- System prompt (Generator instructions)
- Historico de conversa
- Target information
- Tool outputs
- Espaco para proxima resposta do LLM

**Resultado**: Context explorado antes de comecar a pensar.

### A Solucao: Extrair So Descricoes

Cada `SKILL.md` tem frontmatter com metadata:

```yaml
---
name: fase-1
description: Execute FASE 1 - Reconnaissance and mapping. Invoke with /scan-fase-1 {url}.
fase: 1
---
# Full content (2-4 KB)
...
```

Extraindo SO a descricao:

```
22 fases × 100 chars media descricao = 2.2 KB
Tokens: 2,200 / 4 = 550 tokens
```

**Resultado**: 2% do custo anterior. O LLM pode ler todas as fases com contexto de sobra.

### Arquitetura de Uso

```
Generator Agent
├── System Prompt (fixed, ~3KB)
├── load_fase_index() → "Fases disponiveis:\n- fase-1: ...\n- fase-3: ...\n..."
│   (injected into prompt, ~600 tokens)
├── Target Info (user input, ~1KB)
├── LLM pensa e planeia (~5KB reasoning)
└── Agent executa plano
```

Quando a fase completa e necessaria (ex: para debug), `load_fase_skill()` le o ficheiro inteiro.

---

## Logica de Extracao e Limpeza

Ficheiro: `src/pentest/skills/loader.py`

### Passo 1: Parsing do Frontmatter

```python
def _parse_frontmatter(content: str) -> dict:
    """Extract YAML frontmatter from the start of a file."""
    if not content.startswith("---"):
        return {}

    parts = content[3:].split("---", 1)
    if len(parts) < 2:
        return {}

    frontmatter_str = parts[0].strip()

    try:
        return yaml.safe_load(frontmatter_str) or {}
    except yaml.YAMLError as e:
        logger.warning(f"Failed to parse YAML frontmatter: {e}")
        return {}
```

#### Fluxo Linha a Linha

| Etapa | Codigo | Descricao |
|---|---|---|
| 1 | `if not content.startswith("---")` | Verifica se ficheiro comeca com delimitador YAML |
| 2 | `content[3:].split("---", 1)` | Remove primeira linha `---`, divide por proxima `---` |
| 3 | `parts[0].strip()` | Extrai conteudo entre delimitadores e remove whitespace |
| 4 | `yaml.safe_load(frontmatter_str)` | Converte YAML em dicionario Python de forma segura |
| 5 | `except yaml.YAMLError` | Captura erros de YAML invalido (sintaxe malformada) |
| 6 | `logger.warning(...)` | Registra erro para auditoria sem falhar o fluxo |

#### Exemplo Concreto

```
Input (ficheiro raw):
---
name: fase-1
description: Execute FASE 1 - Recon
fase: 1
---
# Body...

Step 1: Starts with "---"? Yes
Step 2: Split by "---": ["\nname: fase-1\ndescription: ...", "\n# Body..."]
Step 3: Strip: "name: fase-1\ndescription: Execute FASE 1 - Recon\nfase: 1"
Step 4: yaml.safe_load(): {"name": "fase-1", "description": "Execute...", "fase": 1}
Output: dict com 3 keys
```

### Passo 2: Limpeza da Descricao

```python
def _clean_description(fase_name: str, raw_description: str) -> str:
    """Clean the description by removing boilerplate text."""
    # Remove "Execute FASE X - " pattern
    cleaned = re.sub(r"Execute FASE \d+ - ", "", raw_description)

    # Remove "Invoke with /scan-fase-X {url}." pattern
    cleaned = re.sub(r"Invoke with /scan-fase-\d+ \{url\}\.", "", cleaned)

    # Clean up extra whitespace
    cleaned = cleaned.strip()

    return cleaned
```

#### Padroes Removidos

O modulo remove dois padroes de boilerplate recorrentes em descricoes de SKILL.md:

| Padrao | Exemplo Raw | Depois de Limpar |
|---|---|---|
| "Execute FASE X - " | "Execute FASE 1 - Reconnaissance and mapping" | "Reconnaissance and mapping" |
| "Invoke with /scan-fase-X {url}." | "... Invoke with /scan-fase-1 {url}." | "..." |

#### Regex Disseccao

```python
re.sub(r"Execute FASE \d+ - ", "", raw_description)
       ↑    ↑     ↑   ↑ ↑ ↑
       |    |     |   | | └─ Literal " - "
       |    |     |   | └─ Uma ou mais digitos 0-9
       |    |     |   └─ Literal "FASE "
       |    |     └─ Literal "Execute "
       |    └─ Raw string (\ nao escapa)
       └─ Replacer: encontra e substitui por ""
```

Resultado: Captura variantes como "Execute FASE 1 -", "Execute FASE 12 -", etc.

#### Exemplo Completo

```python
raw = "Execute FASE 3 - RLS Testing in Supabase. Invoke with /scan-fase-3 {url}."

# After first regex
cleaned = "RLS Testing in Supabase. Invoke with /scan-fase-3 {url}."

# After second regex
cleaned = "RLS Testing in Supabase."

# After strip
cleaned = "RLS Testing in Supabase"

return "RLS Testing in Supabase"
```

---

## APIs Principais: load_fase_index e load_fase_skill

### load_fase_index: Gerar Indice para Prompt

```python
def load_fase_index(scan_path: list[str], skills_dir: str) -> str:
    """Load descriptions for all fases in the scan_path."""
    if not scan_path:
        return ""

    skills_root = Path(skills_dir)
    entries = []

    for fase_name in scan_path:
        # Convert "fase-1" to "scan-fase-1"
        skill_dir_name = (
            f"scan-{fase_name}"
            if not fase_name.startswith("scan-")
            else fase_name
        )

        skill_file = skills_root / skill_dir_name / "SKILL.md"

        if not skill_file.exists():
            logger.warning(f"SKILL file not found: {skill_file}")
            continue

        try:
            with open(skill_file, encoding="utf-8") as f:
                content = f.read()

            frontmatter = _parse_frontmatter(content)
            description = frontmatter.get("description", "")

            if not description:
                logger.warning(f"No description in frontmatter of {skill_file}")
                continue

            cleaned = _clean_description(fase_name, description)
            entries.append(f"- {fase_name}: {cleaned}")

        except Exception as e:
            logger.warning(f"Error reading SKILL file {skill_file}: {e}")
            continue

    if not entries:
        return ""

    header = "Fases disponíveis no scan_path deste target:"
    return header + "\n" + "\n".join(entries)
```

#### Fluxo e Garantias de Resiliencia

| Etapa | Cenario Feliz | Cenario Erro | Acao |
|---|---|---|---|
| 1 | Ficheiro existe | Ficheiro nao existe (fase removida/renomeada) | Log warning, skip entry, continuar |
| 2 | YAML e valido | YAML malformado | Log warning (interno de _parse_frontmatter), skip entry |
| 3 | Description presente | Description em branco/faltante | Log warning, skip entry |
| 4 | Read succeeds | Permissao negada, disco cheio, etc | Catch Exception, log warning, continuar |
| 5 | 1+ entradas | 0 entradas (todas falharam) | Return empty string (agente tratara) |

**Resultado**: Nunca raise excecao. Agente continua com dados parciais.

#### Exemplo de Output

```
Input:
scan_path = ["fase-1", "fase-3", "fase-5"]
skills_dir = "/workspace/skills"

Processing:
- fase-1: SKILL.md exists, description extracted and cleaned
- fase-3: SKILL.md exists, description extracted and cleaned
- fase-5: SKILL.md not found → warning logged, skipped

Output:
"Fases disponíveis no scan_path deste target:
- fase-1: Reconnaissance and mapping
- fase-3: RLS Testing in Supabase
"
```

Este texto sera injetado no system prompt do Generator.

### load_fase_skill: Ler Ficheiro Completo

```python
def load_fase_skill(fase: str, skills_dir: str) -> str:
    """Load the complete SKILL.md content for a given fase."""
    # Convert "fase-1" to "scan-fase-1"
    skill_dir_name = f"scan-{fase}" if not fase.startswith("scan-") else fase

    skills_root = Path(skills_dir)
    skill_file = skills_root / skill_dir_name / "SKILL.md"

    if not skill_file.exists():
        logger.warning(f"SKILL file not found: {skill_file}")
        return ""

    try:
        with open(skill_file, encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        logger.warning(f"Error reading SKILL file {skill_file}: {e}")
        return ""
```

#### Proposito

Enquanto `load_fase_index()` extrai apenas a descricao para o prompt, `load_fase_skill()` retorna o **ficheiro completo** (frontmatter + corpo inteiro).

Casos de uso futuros:

1. **Scanner agent** (US-044?): Precisa de instrucoes completas para executar fase. Chama `load_fase_skill("fase-1", skills_dir)` para obter todas as instrucoes tecnicas.

2. **Debugging**: Se o Generator falhar numa fase, operador pode chamar `load_fase_skill()` para ver detalhes completos.

3. **Auditoria**: Registar quale ficheiro SKILL foi usado para cada fase do plano.

#### Exemplo

```python
skill_content = load_fase_skill("fase-1", "/workspace/skills")
# Returns entire SKILL.md file (frontmatter + ~3KB de conteudo)

print(skill_content[:200])
# ---
# name: fase-1
# description: Execute FASE 1 - Reconnaissance and mapping
# fase: 1
# ---
#
# # Reconnaissance and Mapping
#
# This phase...
```

---

## Testes: Layer 1 Patterns

Ficheiro: `tests/unit/skills/test_loader.py`

Seguindo padroes de `test-patterns.md`, usamos **Layer 1 tests** (unit tests rapidos sem dependencias externas).

### Estrategia de Mocking: tmp_path Fixture

```python
def test_load_single_fase(tmp_path) -> None:
    """Load a single fase."""
    # Create mock SKILL.md file
    skill_dir = tmp_path / "scan-fase-1"
    skill_dir.mkdir()
    skill_file = skill_dir / "SKILL.md"
    skill_file.write_text(
        """---
title: Reconnaissance
description: Execute FASE 1 - Map the attack surface. Invoke with /scan-fase-1 {url}.
---
# Body
"""
    )

    result = load_fase_index(["fase-1"], str(tmp_path))
    assert "fase-1" in result
    assert "Fases disponíveis no scan_path" in result
    assert "Map the attack surface" in result
    assert "Execute FASE" not in result
```

#### Como Funciona tmp_path

| Aspecto | Detalhe |
|---|---|
| O que e | Fixture pytest que cria temporary directory isolado para cada teste |
| Ciclo | Setup (criada) → Teste roda → Teardown (apagada automaticamente) |
| Isolacao | Cada teste tem seu proprio directorio — nao ha conflitos |
| Utilizacao | `tmp_path / "scan-fase-1"` cria caminhos relativos seguros |
| Limpeza | Pytest gerencia automaticamente — nao precisa de `shutil.rmtree()` |

#### Vantagens

1. **Sem dependencias externas**: Nao precisa de ficheiros SKILL.md reais
2. **Rapido**: Directorios em memoria (nao em disco)
3. **Seguro**: Nao toca ficheiros do projeto real
4. **Parametrizavel**: Cada teste controla exatamente que estrutura cria
5. **Reproducivel**: Mesmo teste rodado 100 vezes produz resultado identico

### Cobertura de Testes

18 testes totais, 4 categorias:

#### 1. TestParseFrontmatter (4 testes)

```python
def test_parse_valid_frontmatter(self) -> None:
    """Parse valid frontmatter with YAML content."""
    content = """---
title: Test SKILL
description: This is a test description
fase: 1
---
# Body content
"""
    result = _parse_frontmatter(content)
    assert result["title"] == "Test SKILL"
    assert result["description"] == "This is a test description"
    assert result["fase"] == 1
```

| Teste | Proposito |
|---|---|
| `test_parse_valid_frontmatter` | Confirma parsing correto de YAML valido |
| `test_parse_empty_frontmatter` | YAML vazio retorna dict vazio (nao erro) |
| `test_parse_no_frontmatter` | Conteudo sem `---` retorna dict vazio |
| `test_parse_invalid_yaml` | YAML malformado retorna dict vazio + warning |

**Importancia**: Garante que _parse_frontmatter nunca falha (sempre retorna dict).

#### 2. TestCleanDescription (5 testes)

```python
def test_remove_execute_prefix(self) -> None:
    """Remove 'Execute FASE X -' prefix."""
    raw = "Execute FASE 1 - Reconnaissance and mapping"
    result = _clean_description("fase-1", raw)
    assert "Execute FASE" not in result
    assert result == "Reconnaissance and mapping"
```

| Teste | O que valida |
|---|---|
| `test_remove_execute_prefix` | Padrao "Execute FASE X -" removido |
| `test_remove_invoke_suffix` | Padrao "Invoke with /scan-fase-X {url}." removido |
| `test_remove_both_patterns` | Ambos padroes removidos simultaneamente |
| `test_preserve_content` | Conteudo importante preservado |
| `test_already_formatted` | Descricoes ja formatadas preservadas |

**Importancia**: Confirma que limpeza nao destroi conteudo util.

#### 3. TestLoadFaseIndex (6 testes)

```python
def test_load_single_fase(self, tmp_path) -> None:
    """Load a single fase."""
    skill_dir = tmp_path / "scan-fase-1"
    skill_dir.mkdir()
    skill_file = skill_dir / "SKILL.md"
    skill_file.write_text("""---
description: Execute FASE 1 - Map the attack surface. Invoke with /scan-fase-1 {url}.
---
# Body
""")

    result = load_fase_index(["fase-1"], str(tmp_path))
    assert "fase-1" in result
    assert "Fases disponíveis no scan_path" in result
```

| Teste | Cenario |
|---|---|
| `test_load_single_fase` | Uma fase, sucesso |
| `test_load_multiple_fases` | Multiplas fases, todas com sucesso |
| `test_missing_file_warning` | Ficheiro nao existe → warning logged |
| `test_invalid_yaml_warning` | YAML invalido → warning logged |
| `test_empty_scan_path` | Sem fases → retorna string vazia |
| `test_scan_prefix_already_present` | Prefix "scan-" ja presente → nao duplica |

**Importancia**: Valida resiliencia (errors nao causam excecoes).

#### 4. TestLoadFaseSkill (3 testes)

```python
def test_load_skill_content(self, tmp_path) -> None:
    """Load complete SKILL.md content."""
    skill_dir = tmp_path / "scan-fase-1"
    skill_dir.mkdir()
    skill_file = skill_dir / "SKILL.md"
    content = """---
title: Test
---
# Body
This is the full content.
"""
    skill_file.write_text(content)

    result = load_fase_skill("fase-1", str(tmp_path))
    assert "# Body" in result
    assert "This is the full content" in result
```

| Teste | Validacao |
|---|---|
| `test_load_skill_content` | Conteudo completo retornado |
| `test_load_skill_missing_file` | Ficheiro ausente → warning logged |
| `test_load_skill_with_scan_prefix` | Prefix "scan-" nao duplicado |

**Importancia**: Confirma que ficheiro completo e retornado com sucesso.

### Exemplo de Teste Parametrizado

Embora nao tenha sido usado aqui, o padrão Layer 1 tambem recomenda testes parametrizados:

```python
@pytest.mark.parametrize("raw,expected", [
    ("Execute FASE 1 - Test", "Test"),
    ("Execute FASE 5 - RLS Bypass", "RLS Bypass"),
    ("No boilerplate here", "No boilerplate here"),
])
def test_clean_multiple_patterns(raw, expected):
    result = _clean_description("fase-1", raw)
    assert result == expected
```

---

## Integracao com Generator Prompt

### Onde E Injetado

Ficheiro: `src/pentest/agents/generator.py` (futuro — US-043)

```python
from pentest.skills import load_fase_index

def create_generator_prompt(target_url: str, scan_path: list[str]) -> str:
    """Generate system prompt with fase index."""

    fase_index = load_fase_index(scan_path, SKILLS_DIR)

    prompt = f"""Tu es o Generator agent do PentAGI.

Responsabilidades:
1. Ler target info e scan_path
2. Gerar plano de penetration testing
3. Submeter plano via barrier tool

{fase_index}

Processa cada fase com cuidado...
"""

    return prompt
```

### Exemplo de Prompt Injetado

```
Tu es o Generator agent do PentAGI.

Responsabilidades:
1. Ler target info e scan_path
2. Gerar plano de penetration testing
3. Submeter plano via barrier tool

Fases disponíveis no scan_path deste target:
- fase-1: Reconnaissance and mapping
- fase-3: RLS Testing in Supabase
- fase-5: CORS Policy Evaluation

Processa cada fase com cuidado...
```

Aproximadamente 450 tokens (em vez de 16.500 tokens se carregassemos ficheiros completos).

---

## Fluxo Completo: Esquema End-to-End

### Inicia o Generator Agent

```
User: "Pentest https://vulnerable-app.local, scan_path: [fase-1, fase-3, fase-5]"

↓

Generator receives:
- target_url: "https://vulnerable-app.local"
- scan_path: ["fase-1", "fase-3", "fase-5"]

↓

System prompt is built:
- load_fase_index(["fase-1", "fase-3", "fase-5"], SKILLS_DIR)
  → "Fases disponíveis...\n- fase-1: ...\n- fase-3: ...\n- fase-5: ..."

↓

LLM sees:
"Tu es o Generator. As fases deste scan sao:
- fase-1: Reconnaissance
- fase-3: RLS Testing
- fase-5: CORS Evaluation

Processa cada uma..."

↓

LLM pensa:
"Preciso planejar um pentest com estas 3 fases. Vou:
1. Fazer recon em fase-1
2. Testar RLS em fase-3
3. Verificar CORS em fase-5

Plano:
- Scan para identificar tecnologias
- Teste de autorizacao
- Headers de seguranca
[...]"

↓

LLM submete plano:
tool_call: subtask_list(subtasks=[...], message="Plan ready")

↓

Barrier Hit → Agent Termina com Sucesso
```

---

## Resilencia e Logging

### Estrategia de Logging

O modulo usa `logging.warning()` para todos os erros nao-criticos:

```python
logger = logging.getLogger(__name__)  # "pentest.skills.loader"

logger.warning("SKILL file not found: /path/to/scan-fase-1/SKILL.md")
logger.warning("No description in frontmatter of /path/to/scan-fase-1/SKILL.md")
logger.warning("Failed to parse YAML frontmatter: mapping values are not allowed here")
```

Em producao, operador pode:
- Ativar logs: `logging.basicConfig(level=logging.WARNING)`
- Filtrar: `logging.getLogger("pentest.skills.loader").setLevel(logging.DEBUG)`
- Guardar: Redirecionar para ficheiro de auditoria

### Exemplos de Mensagens

```
WARNING:pentest.skills.loader:SKILL file not found: /skills/scan-fase-999/SKILL.md
WARNING:pentest.skills.loader:No description in frontmatter of /skills/scan-fase-1/SKILL.md
WARNING:pentest.skills.loader:Failed to parse YAML frontmatter: syntax error on line 3
WARNING:pentest.skills.loader:Error reading SKILL file /skills/scan-fase-5/SKILL.md: [Errno 13] Permission denied
```

---

## Resumo: Extraccion de Descricoes como Estrategia de Contexto

| Aspecto | Impacto |
|---|---|
| Context Window | 16.500 tokens → 550 tokens (3% do custo) |
| Resiliencia | Nenhuma excecao; erros logados e ignorados |
| Qualidade | LLM conhece todas as fases; pode planejar melhor |
| Performance | ~100ms para extrair 22 fases (ficheiros em disco) |
| Manutencao | Se fase e renomeada/movida, log avisa; Generator continua |
| Futuro | `load_fase_skill()` preparado para Scanner agent ler completo |

---

## Related Notes

- [Docs Home](../../README.md)
- [[US-037-BASE-GRAPH-EXPLAINED]] — StateGraph, BarrierAwareToolNode
- [[US-041-STUBS-EXPLAINED]] — Placeholder tools
- [[US-043-GENERATOR-PROMPTS-EXPLAINED]] — Como o índice entra na renderização do prompt
- [[AGENT-ARCHITECTURE]] — Arquitetura geral de agentes
- [[USER-STORIES]] — Contexto de stories que introduzem skills e prompts
- **src/pentest/skills/loader.py** — Implementacao completa
- **tests/unit/skills/test_loader.py** — Testes Layer 1
