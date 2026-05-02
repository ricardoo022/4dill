# tests/unit/skills/

Testes unitários de `skills/loader.py` — parsing de frontmatter SKILL.md e geração do índice FASE.

## Ficheiros

| Ficheiro | Descricao |
|---|---|
| `test_loader.py` | Testa `load_fase_index()` e `load_fase_skill()` com fixtures de SKILL.md |

## O que é testado

- `load_fase_index()` gera string formatada com descrições limpas (remove prefixo `"Execute FASE X - "` e sufixo `"Invoke with /scan-fase-X {url}."`)
- `load_fase_skill()` retorna conteúdo completo do SKILL.md da fase pedida
- Prefixo `scan-` adicionado automaticamente ao nome da fase
- Falhas silenciosas: ficheiro em falta ou YAML inválido gera warning e é ignorado sem crash

## Módulo de produção

`src/pentest/skills/loader.py` — ver `docs/Epics/Generator agent/US-042-SKILL-LOADER-EXPLAINED.md`
