# tests/unit/recon/

Testes unitários de `recon/` — detectores de backend FASE 0 com HTTP mockado.

## Ficheiros

| Ficheiro | Descricao |
|---|---|
| `test_supabase.py` | Testa detecção de Supabase: URL patterns, anon keys, probe `/rest/v1/` |
| `test_firebase.py` | Testa detecção de Firebase: extracção de `firebaseConfig` e `initializeApp` |
| `test_custom_api.py` | Testa detecção de frameworks (Next.js, SvelteKit, Express, Django), probes OpenAPI/GraphQL |
| `test_subdomains.py` | Testa descoberta de subdomínios: prefixos comuns, SSL SANs, links HTML |
| `test_orchestrator.py` | Testa fluxo completo: subdomain discovery → detectors → `BackendProfile` |

## O que é testado

- Cada detector identifica o backend correto a partir de HTML/JS mockado
- Detectors retornam `None` (não crash) quando o padrão não é encontrado
- `BackendProfile` agrega resultados e define `scan_path` correto
- Concorrência no `subdomains.py`: semaphore limita pedidos paralelos

## Módulo de produção

`src/pentest/recon/` — FASE 0, sem equivalente no PentAGI
