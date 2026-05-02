---
tags: [evaluation]
---

# Evaluation Targets

Targets vulneráveis para avaliar os agentes do LusitAI AI Pentest. Cada target é uma aplicação intencionalmente insegura, com vulnerabilidades documentadas, usada para:

1. **Gravar o dataset** — correr o Generator real contra o target, gravar inputs + tool calls + plano
2. **Extrair fixtures** — tool responses gravadas tornam-se fixtures determinísticas
3. **Ground truth** — vulnerabilidades conhecidas servem de referência para avaliar completude do plano

---

## Targets Docker (self-hosted, determinísticos)

### 1. DVGA — Damn Vulnerable GraphQL Application

| Campo | Valor |
|-------|-------|
| **Repo** | https://github.com/dolevf/Damn-Vulnerable-GraphQL-Application |
| **Imagem** | `dolevf/dvga` |
| **Porta** | 5013 |
| **Backend type** | GraphQL |
| **Setup** | `docker run -t -p 5013:5013 -e WEB_HOST=0.0.0.0 dolevf/dvga` |

**Vulnerabilidades documentadas:**
- Information Disclosure: introspection enabled, GraphiQL exposed, SSRF, stack traces
- Denial of Service: batch queries, deep recursion, field duplication, aliases
- Code Execution: OS command injection
- Injection: XSS, SQLi, HTML/log injection
- Authorization Bypass: JWT forgery, interface bypass, query deny list bypass
- Miscellaneous: weak passwords, arbitrary file write, path traversal

**FASEs esperadas no plano:** fase-1 (recon), fase-2 (API enumeration), fase-6 (injection), fase-7 (security headers), fase-8 (JWT analysis)

**Modos:** Beginner e Expert

---

### 2. django.nV — Vulnerable Django REST Framework App

| Campo | Valor |
|-------|-------|
| **Repo** | https://github.com/secfigo/django.nV (fork activo do original archived) |
| **Porta** | 8000 |
| **Backend type** | Custom API (Django DRF) |
| **Setup** | Ver README do repo (Docker disponível) |

**Vulnerabilidades documentadas:**
- SQL Injection (múltiplos endpoints)
- IDOR (Insecure Direct Object References)
- Mass Assignment (unprotected object properties)
- XSS (Cross-Site Scripting)
- CSRF (Cross-Site Request Forgery)
- Insecure Settings (DEBUG=True, weak SECRET_KEY)
- Tutorials built-in em `/taskManager/tutorials/`

**FASEs esperadas no plano:** fase-1 (recon), fase-2 (API enumeration), fase-5 (auth testing), fase-6 (injection), fase-7 (security headers)

---

### 3. OWASP Juice Shop

| Campo | Valor |
|-------|-------|
| **Repo** | https://github.com/juice-shop/juice-shop |
| **Imagem** | `bkimminich/juice-shop` |
| **Porta** | 3000 |
| **Backend type** | Custom API (Express/Node.js) |
| **Demo online** | `demo.owasp-juice.shop` (pode ser usada sem Docker) |
| **Setup** | `docker run -p 3000:3000 bkimminich/juice-shop` |

**Vulnerabilidades documentadas (100+):**
- Categorias: XSS, SQLi, authentication bypass, broken access control, sensitive data exposure, security misconfiguration, SSRF, XXE, insecure deserialization
- Dificuldade: 1-6 estrelas, progressão gradual
- Scoreboard integrado em `/#/score-board`

**FASEs esperadas no plano:** fase-1 (recon), fase-2 (API enumeration), fase-5 (auth), fase-6 (injection), fase-7 (headers), fase-9 (business logic)

---

## Targets Cloud (managed, reais)

### 4. Supabase App via Lovable (a criar)

| Campo | Valor |
|-------|-------|
| **Plataforma** | Lovable (lovable.dev) → deploy Supabase free-tier |
| **URL** | TBD (será documentado após criação) |
| **Backend type** | Supabase |
| **Custo** | Gratuito (Supabase free-tier + Lovable free) |

**Como criar:**
1. Criar app no Lovable (ex: "Task Manager" ou "Blog" com auth)
2. Lovable gera automaticamente app com Supabase backend
3. No Supabase Dashboard, introduzir misconfigurations intencionais:
   - **Desabilitar RLS** em 2+ tabelas: SQL `ALTER TABLE todos DISABLE ROW LEVEL SECURITY`
   - **Storage bucket público**: criar bucket com `public: true` e listagem habilitada
   - **Manter anon key exposta** no frontend (default do Lovable — já é "vulnerável")
4. **NÃO** expor service role key
5. Documentar URL, anon key, e misconfigurations no `backend_profile.json`

**Vulnerabilidades intencionais:**
- RLS disabled em tabelas (dados acessíveis via REST API com anon key) — **severity: high**
- Anon key exposta no frontend source — **severity: medium**
- Storage bucket público com listagem — **severity: medium**
- Sem rate limiting na auth API — **severity: medium**

**FASEs esperadas no plano:** fase-1 (recon), fase-2 (schema discovery), fase-3 (RLS testing), fase-4 (storage), fase-5 (auth), fase-7 (headers), fase-8 (JWT)

**Notas:**
- Free-tier pausa após 7 dias de inactividade — reactivar no dashboard antes de correr evals
- Limites: 500MB DB, 1GB storage, 50K auth users (suficiente para evals)
- A app pode ser recriada facilmente se o projecto expirar

---

### 5. Firebase App (a criar, opcional)

| Campo | Valor |
|-------|-------|
| **Plataforma** | Firebase Console (free-tier Spark plan) |
| **URL** | TBD |
| **Backend type** | Firebase |
| **Custo** | Gratuito |

**Como criar:**
1. Criar projecto no Firebase Console
2. Activar Realtime Database com regras inseguras:
   ```json
   {
     "rules": {
       ".read": true,
       ".write": true
     }
   }
   ```
3. Activar Firestore com regras inseguras:
   ```
   rules_version = '2';
   service cloud.firestore {
     match /databases/{database}/documents {
       match /{document=**} {
         allow read, write: if true;
       }
     }
   }
   ```
4. Activar Authentication (email/password)
5. Adicionar dados de teste

**Vulnerabilidades intencionais:**
- Realtime DB com `.read: true` (dump total via `/.json`) — **severity: critical**
- Firestore sem access control — **severity: critical**
- Firebase config exposta no frontend — **severity: medium**

**FASEs esperadas no plano:** fase-1 (recon), fase-2 (API enumeration), fase-3 (access control), fase-5 (auth), fase-7 (headers)

**Teste rápido:** `curl https://{project-id}-default-rtdb.firebaseio.com/.json` deve retornar dados

---

## Targets adicionais (para epics futuros)

### Next.js (CVE-2025-55182)
- **vuln-app-CVE-2025-55182** — https://github.com/zack0x01/vuln-app-CVE-2025-55182
- **React2Shell** — https://github.com/subzer0x0/React2Shell
- RCE via React Server Components (insecure deserialization)
- Docker disponível

### Supabase CTF
- **Hack the Base** — https://ctf.supabase.com/
- RLS bypass challenges online

### Security Testing Tools (referência)
- **Supabomb** — https://github.com/ModernPentest/supabomb — Supabase security scanner
- **FireBaseScanner** — https://github.com/shivsahni/FireBaseScanner — Firebase misconfiguration detection
- **FirebaseExploiter** — https://github.com/securebinary/firebaseExploiter — Firebase exploitation

### Curated Lists
- **awesome-vulnerable** — https://github.com/kaiiyer/awesome-vulnerable (200+ apps)
- **Vulhub** — https://github.com/vulhub/vulhub (100+ Docker Compose environments)
- **OWASP VWAD** — https://owasp.org/www-project-vulnerable-web-applications-directory/

---

## Mapping: Target → Cenário do Dataset

Todos os cenários usam targets reais com vulnerabilidades conhecidas. Sem cenários artificiais.

| # | Target | Backend Type | Vulns conhecidas | Ground truth |
|---|--------|-------------|-----------------|--------------|
| 1 | Lovable Supabase CRUD | Supabase | RLS off, public storage, anon key | `expected_findings/supabase_crud.json` |
| 2 | Lovable Supabase Auth | Supabase | Auth bypass, JWT, rate limiting | `expected_findings/supabase_auth.json` |
| 3 | DVGA | GraphQL | Introspection, SQLi, command injection, JWT | `expected_findings/dvga.json` |
| 4 | django.nV | Custom API (DRF) | SQLi, IDOR, mass assignment, XSS | `expected_findings/django_nv.json` |
| 5 | Juice Shop | Custom API (Express) | 100+ vulns multi-category | `expected_findings/juice_shop.json` |
| 6 | Firebase (opcional) | Firebase | Open rules, data dump | `expected_findings/firebase.json` |
| 7 | Juice Shop por IP | Unknown | Mesmas vulns, sem backend profile | Reutiliza `juice_shop.json` |

**Princípio:** cada cenário tem vulnerabilidades documentadas (`expected_findings`) que servem de ground truth. O evaluator `vulnerability_coverage` mede quantas o Generator cobriu.

---

## Referências

- [Supabase misconfiguration research](https://deepstrike.io/blog/hacking-thousands-of-misconfigured-supabase-instances-at-scale)
- [Firebase hacking guide](https://www.intigriti.com/researchers/blog/hacking-tools/hacking-google-firebase-targets)
- [Next.js security testing guide](https://deepstrike.io/blog/nextjs-security-testing-bug-bounty-guide)
- [Firebase misconfiguration exploitation](https://medium.com/@mustafamohammed789mm/firebase-misconfigurations-from-discovery-to-exploitation-0a282b81ad4f)
- [GraphQL API vulnerabilities](https://portswigger.net/web-security/graphql)

---

## Related Notes

- [Docs Home](../../README.md)
- [[LANGSMITH-EVALS-RESEARCH]]
- [[USER-STORIES]]
- [[PROJECT-STRUCTURE]]
