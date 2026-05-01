---
tags: [evaluation]
---

# US-045: PortSwigger MVP Dataset (4 Labs) — Explicacao Detalhada

Este documento explica, em detalhe, a implementacao da `US-045` em `tests/evals/datasets/portswigger_mvp.json` e os testes de validacao em `tests/evals/test_portswigger_mvp.py`.

---

## Objetivo da US

A `US-045` estabelece um dataset curado de avaliacao para agentes ofensivos, contendo exatamente 4 labs PortSwigger representativos:

1. **SQL Injection** (`sqli-login-bypass`) — fase 3, exploração simples de autenticação
2. **XSS Refletida** (`xss-reflected-html-nothing-encoded`) — fase 6, injeção direta em HTML
3. **Autenticacao** (`auth-username-enum-different-responses`) — fase 4, enumeracao de usernames
4. **XXE** (`xxe-file-upload`) — fase 7, processamento de XML malicioso

Todos os labs são mapeados para o backend `custom_api`, fornecendo **ground truth fixo** (sem dependencia de deteção automática em runtime) para avaliacao estavel e reproduzivel.

---

## Ficheiros Alterados

| Ficheiro | Responsabilidade |
|---|---|
| `tests/evals/datasets/portswigger_mvp.json` | Dataset MVP com 4 labs, metadados, e subsets oficiais |
| `tests/evals/test_portswigger_mvp.py` | 26 testes de validacao (formato, integridade, conteudo) |

---

## 1) `tests/evals/datasets/portswigger_mvp.json`

### Estrutura de raiz (linhas 1-27)

```json
{
  "version": "1.0",
  "created": "2026-05-01",
  "description": "PortSwigger MVP Dataset: 4 labs across different vulnerability categories for agent evaluation baseline. All labs use custom_api backend for MVP stability.",
  "subsets": { ... },
  "summary": { ... },
  "labs": [ ... ]
}
```

| Campo | Tipo | Explicacao |
|---|---|---|
| `version` | string | Controlo de versao do dataset. Future-proofing para schema migration. |
| `created` | string | Data de criacao (ISO 8601). Rastreabilidade de dataset snapshots. |
| `description` | string | Resumo narrativo: tamanho, escopo, e restricoes (backend hardcoded). |
| `subsets` | object | Colecoes nomeadas de labs (ex: `quick` = MVP, futuro: `medium`, `full`). |
| `summary` | object | Metadados agregados consistentes com a realidade (sem drift manual). |
| `labs` | array | Catálogo completo de labs (cada um é um membro de um ou mais subsets). |

### Campo `subsets` — Subset `quick` (linhas 5-14)

```json
"subsets": {
  "quick": {
    "description": "MVP baseline: 4 representative labs (1 SQL injection, 1 XSS, 1 authentication, 1 XXE) covering distinct vulnerability types and agent tool paths.",
    "labs": [
      "sqli-login-bypass",
      "xss-reflected-html-nothing-encoded",
      "auth-username-enum-different-responses",
      "xxe-file-upload"
    ]
  }
}
```

| Campo | Propósito |
|---|---|
| `subsets.quick.description` | Explica propósito do subset: MVP deliberadamente pequeno, 4 categorias, cobertura de tool paths distintos. |
| `subsets.quick.labs` | Array de 4 `lab_id` strings (exatos, sem duplicatas). Referências para labs na raiz `labs[]`. |

**Porque `quick`?** Nomenclatura alinha com LangSmith dataset best practices: `quick` = baseline para feedback rápido, futuro `medium` / `full` para robustez aumentada.

### Campo `summary` (linhas 16-26)

```json
"summary": {
  "total_subsets": 1,
  "total_labs_quick": 4,
  "categories_covered": [
    "sql-injection",
    "xss",
    "authentication",
    "xxe"
  ],
  "avg_difficulty": "beginner",
  "backend_type": "custom_api"
}
```

| Campo | Valor | Explicacao |
|---|---|---|
| `total_subsets` | 1 | Só existe `quick` neste MVP. Validado por teste `test_summary_total_subsets_matches_actual`. |
| `total_labs_quick` | 4 | Contagem literal dos labs em `subsets.quick.labs`. Validado por `test_summary_total_labs_quick_matches_actual`. |
| `categories_covered` | [4 categorias] | Conjunto ordenado de categorias unicas. Validado por `test_summary_categories_covered_matches_actual`. |
| `avg_difficulty` | "beginner" | Dificuldade media dos 4 labs (todos "beginner" neste MVP). Informativo para runners. |
| `backend_type` | "custom_api" | **Hardcoded para MVP.** Simplifica avaliacao: nao requer deteção em runtime. |

**Porque hardcoded?** O MVP foca em signal/custo: 4 labs bem escolhidos com backend fixo, nao em cobertura geral de tipos de backend. Futuras US podem implementar deteção dinamica.

### Campo `labs` — Estrutura por lab (linhas 28-65)

Cada lab é um objeto com 7 campos obrigatorios:

```json
{
  "lab_id": "sqli-login-bypass",
  "lab_url": "https://portswigger.net/web-security/sql-injection/lab-login-bypass",
  "category": "sql-injection",
  "fase_phase": 3,
  "expected_vulnerability": "SQL injection vulnerability allowing login bypass",
  "difficulty": "beginner",
  "expected_backend_type": "custom_api"
}
```

| Campo | Tipo | Exemplo | Propósito |
|---|---|---|---|
| `lab_id` | string | "sqli-login-bypass" | Identificador unico. Referenciado por `subsets.quick.labs[]`. |
| `lab_url` | string | "https://portswigger.net/..." | Link direto ao lab. Input para spinup automation (US-046). |
| `category` | string | "sql-injection" | Tipo de vulnerabilidade (enum: sql-injection, xss, authentication, xxe). |
| `fase_phase` | integer | 3 | Mapeamento FASE. Fase do Scanner correspondente (1-21). |
| `expected_vulnerability` | string | "SQL injection vulnerability allowing login bypass" | Descricao exata da vulnerabilidade. Ground truth para LLM judge. |
| `difficulty` | string | "beginner" | Enum (beginner, intermediate, advanced). Todos sao "beginner" no MVP. |
| `expected_backend_type` | string | "custom_api" | **Hardcoded.** Backend da aplicacao. Fixo em MVP (todas = "custom_api"). |

### Mapping entre subsets e labs: Exemplo

```
subsets.quick.labs = ["sqli-login-bypass", "xss-reflected-html-nothing-encoded", ...]
                      ↓                      ↓
labs[0].lab_id = "sqli-login-bypass"  labs[1].lab_id = "xss-reflected-html-nothing-encoded"
```

Um runner percorre `subsets.quick.labs`, resolve cada ID em `labs[]`, e executa spinup + eval.

---

## 2) `tests/evals/test_portswigger_mvp.py` — 26 Testes

### Arquitetura de testes

```
TestPortSwiggerMVPFormat (5 testes)
  └─ Validacao de JSON, campos obrigatorios, tipos

TestPortSwiggerMVPQuickSubset (3 testes)
  └─ Critérios de aceitacao: 4 labs, cobertura de 4 categorias

TestPortSwiggerMVPLabIntegrity (6 testes)
  └─ Integridade de lab: sem duplicatas, campos requeridos, backend, URLs, difficulty, fase

TestPortSwiggerMVPSummary (4 testes)
  └─ Consistencia de metadados: contagens, categorias, tipo de backend

TestPortSwiggerMVPContent (8 testes)
  └─ Conteudo: categorias presentes, lab_ids corretos
```

### Fixture: `mvp_dataset` (linhas 20-25)

```python
@pytest.fixture
def mvp_dataset():
    """Load the PortSwigger MVP dataset."""
    with open(DATASET_PATH) as f:
        data = json.load(f)
    return data
```

Carrega o JSON uma unica vez por teste. Garante consistencia e performance.

### Bloco 1: TestPortSwiggerMVPFormat (linhas 28-56)

```python
class TestPortSwiggerMVPFormat:
    """Test basic dataset format and structure."""

    def test_dataset_file_exists(self):
        """Dataset file should exist at expected location."""
        assert DATASET_PATH.exists(), f"Dataset not found at {DATASET_PATH}"

    def test_dataset_json_parses(self):
        """Dataset should be valid JSON."""
        with open(DATASET_PATH) as f:
            data = json.load(f)
        assert data is not None

    def test_dataset_has_required_top_level_fields(self, mvp_dataset):
        """Dataset should have version, created, description, subsets, summary, labs."""
        required_fields = ["version", "created", "description", "subsets", "summary", "labs"]
        for field in required_fields:
            assert field in mvp_dataset, f"Missing required field: {field}"
```

| Teste | Responsabilidade |
|---|---|
| `test_dataset_file_exists` | Ficheiro fisicamente presente. |
| `test_dataset_json_parses` | JSON valido (sem syntax errors). |
| `test_dataset_has_required_top_level_fields` | Campos de raiz existem (`version`, `created`, ...). |
| `test_dataset_version_is_string` | `version` é string (tipo checking). |
| `test_dataset_has_quick_subset` | Subset `quick` existe com `labs` e `description`. |

### Bloco 2: TestPortSwiggerMVPQuickSubset (linhas 59-81)

```python
class TestPortSwiggerMVPQuickSubset:
    """Test acceptance criteria for the 'quick' subset."""

    def test_quick_subset_has_exactly_four_labs(self, mvp_dataset):
        """Per US-045: quick subset must have exactly 4 labs."""
        quick_labs = mvp_dataset["subsets"]["quick"]["labs"]
        assert len(quick_labs) == 4, f"Expected 4 labs in quick subset, got {len(quick_labs)}"

    def test_quick_subset_covers_four_categories(self, mvp_dataset):
        """Quick subset should cover 4 different vulnerability categories."""
        quick_lab_ids = mvp_dataset["subsets"]["quick"]["labs"]
        labs_by_id = {lab["lab_id"]: lab for lab in mvp_dataset["labs"]}
        categories = {labs_by_id[lab_id]["category"] for lab_id in quick_lab_ids}
        assert len(categories) == 4, f"Expected 4 categories, got {len(categories)}: {categories}"
```

| Teste | Linha(s) | Explicacao |
|---|---|---|
| `test_quick_subset_has_exactly_four_labs` | 62-65 | Aceita de US-045: `len(subsets.quick.labs) == 4` exactamente. |
| `test_quick_subset_lab_ids_valid` | 67-73 | Cada lab_id em `quick.labs` existe em `labs[]` (valida referencias). |
| `test_quick_subset_covers_four_categories` | 75-81 | 4 categorias unicas entre os 4 labs (cada lab numa categoria diferente). |

### Bloco 3: TestPortSwiggerMVPLabIntegrity (linhas 84-135)

```python
def test_no_duplicate_lab_ids(self, mvp_dataset):
    """All lab_ids must be unique."""
    lab_ids = [lab["lab_id"] for lab in mvp_dataset["labs"]]
    assert len(lab_ids) == len(set(lab_ids)), "Duplicate lab_ids found"

def test_all_labs_have_required_fields(self, mvp_dataset):
    """Each lab must have all required fields."""
    required_fields = [
        "lab_id", "lab_url", "category", "fase_phase",
        "expected_vulnerability", "difficulty", "expected_backend_type"
    ]
    for lab in mvp_dataset["labs"]:
        for field in required_fields:
            assert field in lab, f"Lab {lab.get('lab_id', 'UNKNOWN')} missing field: {field}"

def test_all_labs_have_custom_api_backend(self, mvp_dataset):
    """Per US-045 MVP: all labs must have expected_backend_type == 'custom_api'."""
    for lab in mvp_dataset["labs"]:
        assert lab["expected_backend_type"] == "custom_api", \
            f"Lab {lab['lab_id']} has backend_type {lab['expected_backend_type']}, expected 'custom_api'"
```

| Teste | Proposito |
|---|---|
| `test_no_duplicate_lab_ids` | Unicidade de chaves. |
| `test_all_labs_have_required_fields` | 7 campos obrigatorios presentes em cada lab. |
| `test_all_labs_have_custom_api_backend` | **Aceita de US-045 hardcoding:** todos = "custom_api". |
| `test_all_lab_urls_are_strings` | URLs sao HTTPS strings. |
| `test_all_labs_have_valid_difficulty` | `difficulty ∈ {beginner, intermediate, advanced}`. |
| `test_all_labs_have_integer_fase_phase` | `fase_phase` é integer em [1, 21]. |

### Bloco 4: TestPortSwiggerMVPSummary (linhas 138-157)

```python
def test_summary_total_labs_quick_matches_actual(self, mvp_dataset):
    """Summary.total_labs_quick should match actual quick subset size."""
    expected = len(mvp_dataset["subsets"]["quick"]["labs"])
    actual = mvp_dataset["summary"]["total_labs_quick"]
    assert actual == expected, f"Summary says {actual} labs, actually {expected}"

def test_summary_categories_covered_matches_actual(self, mvp_dataset):
    """Summary.categories_covered should match actual categories in quick subset."""
    quick_lab_ids = mvp_dataset["subsets"]["quick"]["labs"]
    labs_by_id = {lab["lab_id"]: lab for lab in mvp_dataset["labs"]}
    actual_categories = sorted({labs_by_id[lab_id]["category"] for lab_id in quick_lab_ids})
    expected_categories = sorted(mvp_dataset["summary"]["categories_covered"])
    assert actual_categories == expected_categories, \
        f"Summary categories {expected_categories} don't match actual {actual_categories}"
```

**Proposito:** Impede "drift" manual — summary é **derivado** dos dados reais, nao uma fonte independente.

| Teste | Validacao |
|---|---|
| `test_summary_total_labs_quick_matches_actual` | `summary.total_labs_quick == len(subsets.quick.labs)` |
| `test_summary_categories_covered_matches_actual` | `summary.categories_covered == sorted(unique categories)` |
| `test_summary_total_subsets_matches_actual` | `summary.total_subsets == len(subsets)` |
| `test_summary_backend_type_is_custom_api` | `summary.backend_type == "custom_api"` |

### Bloco 5: TestPortSwiggerMVPContent (linhas 160-216)

```python
def test_has_sql_injection_lab(self, mvp_dataset):
    """MVP should include a SQL injection lab."""
    categories = [lab["category"] for lab in mvp_dataset["labs"]]
    assert "sql-injection" in categories

def test_sqli_lab_has_correct_id(self, mvp_dataset):
    """SQL injection lab should be sqli-login-bypass."""
    sqli_labs = [lab for lab in mvp_dataset["labs"] if lab["category"] == "sql-injection"]
    assert len(sqli_labs) == 1
    assert sqli_labs[0]["lab_id"] == "sqli-login-bypass"
```

Validacao de conteudo: cada uma das 4 categorias está presente, e o lab_id é exato.

| Teste | Validacao |
|---|---|
| `test_has_sql_injection_lab` | "sql-injection" ∈ categorias |
| `test_has_xss_lab` | "xss" ∈ categorias |
| `test_has_authentication_lab` | "authentication" ∈ categorias |
| `test_has_xxe_lab` | "xxe" ∈ categorias |
| `test_sqli_lab_has_correct_id` | sqli_lab.lab_id == "sqli-login-bypass" |
| `test_xss_lab_has_correct_id` | xss_lab.lab_id == "xss-reflected-html-nothing-encoded" |
| `test_auth_lab_has_correct_id` | auth_lab.lab_id == "auth-username-enum-different-responses" |
| `test_xxe_lab_has_correct_id` | xxe_lab.lab_id == "xxe-file-upload" |

---

## Exemplo Completo: Fluxo de Utilizacao do Dataset

### 1. Runner carrega o dataset

```python
import json

with open("tests/evals/datasets/portswigger_mvp.json") as f:
    dataset = json.load(f)
```

### 2. Itera sobre labs no subset `quick`

```python
for lab_id in dataset["subsets"]["quick"]["labs"]:
    # Resolve lab_id -> lab object
    lab = next(lab for lab in dataset["labs"] if lab["lab_id"] == lab_id)

    # Spinup: usa `lab["lab_url"]`
    instance_url = spinup_portswigger_lab(lab["lab_url"])

    # Run agent
    result = run_agent(instance_url, target_backend=lab["expected_backend_type"])

    # Evaluate: usa `lab["expected_vulnerability"]` como ground truth
    score = evaluate(result, expected_vulnerability=lab["expected_vulnerability"])

    # Log
    print(f"{lab_id}: categoria={lab['category']}, score={score}")
```

### 3. Validacao de dataset durante pipeline

```bash
# Pre-run check (testes 1-26)
pytest tests/evals/test_portswigger_mvp.py -v

# Se tudo passar, runner prossegue
python -m evals.runner --dataset portswigger_mvp.json --subset quick
```

---

## Decisoes de Design

### 1. Porque "portswigger_mvp.json" em `tests/evals/datasets/`?

```
tests/evals/
  ├── portswigger_labs.json  (catálogo fonte, 676 labs)
  ├── datasets/
  │   └── portswigger_mvp.json  (curado, 4 labs)
  ├── spinup.py
  ├── evaluators/
  └── test_portswigger_mvp.py
```

**Separacao:** `portswigger_labs.json` é o catálogo completo; `datasets/portswigger_mvp.json` é a colecção curada para eval. Futuras US podem criar `datasets/portswigger_medium.json`, `datasets/openai_gpt4_logs.json`, etc.

### 2. Porque `expected_backend_type: custom_api` é hardcoded?

**MVP é deliberadamente pequeno.** Objetivos:

- **Signal/custo:** 4 labs bem escolhidos > dataset generico grande
- **Estabilidade:** sem deteção dinamica, ground truth é fixo
- **Simplicidade:** runner nao precisa de logica de deteção ou fallback

Futuras US podem introduzir backend dinamico ou mult-backend, uma vez que o eval harness esteja estavel.

### 3. Porque `subsets`?

LangSmith datasets permitem "tagged examples". Estrutura `subsets` permite:

```
subsets.quick → 4 labs (MVP baseline rápido)
subsets.medium → 10 labs (robustez media)  [futuro]
subsets.full → 50 labs (cobertura completa)  [futuro]
```

Um runner pode usar `--subset medium` para testes mais rigorosos.

---

## Questoes Frequentes

### P: Por que exatamente 4 labs? Porque nao 3 ou 5?

**R:** Aceita de US-045: 4 labs = 1 por categoria (sqli, xss, auth, xxe). Deliberadamente pequeno para feedback rápido. Futuro: scale para 10-50.

### P: Os lab_ids sao criacao nossa ou vem de PortSwigger?

**R:** Vem de PortSwigger. `lab_id` mapeia 1:1 com a entrada em `portswigger_labs.json` (catálogo oficial).

### P: Posso usar `portswigger_labs.json` diretamente em evals, sem curadoria?

**R:** Tecnicamente sim, mas nao recomendado:
- 676 labs = muito custo computacional para MVP
- Sem ground truth explícito = dificil avaliar correctness
- Sem categoria mapping = eval results sao ruido

Usar `portswigger_mvp.json` (curado, 4 labs, ground truth fixo).

### P: O `summary` pode ficar out-of-sync?

**R:** Sim. Por iso existem testes: `test_summary_*_matches_actual`. Se adicionar/remover labs manualmente, os testes falham antes de pushing.

### P: Quando migrar de `portswigger_mvp` para `portswigger_medium`?

**R:** Quando o eval harness estiver estavel (US-047+) e o overhead de 10 labs for aceitavel. Replicar structure de `portswigger_mvp.json`, aumentar para 10 labs curados, atualizar testes.

---

## Related Notes

- [[../../README.md]]
- [[EVAL-TARGETS]]
- [[LANGSMITH-EVALS-RESEARCH]]
- [[../../LANGCHAIN-SKILLS-GUIDE]]
