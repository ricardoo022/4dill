---
tags: [docker]
---

# US-014a: Image Management (Pull, Fallback, Cache) — Explicacao Detalhada

Este documento explica linha a linha a implementacao de `US-014a` em `src/pentest/docker/client.py`, com foco nos metodos `_pull_image()` e `ensure_image()`.

---

## Contexto

O objetivo do story e garantir que o `DockerClient` consegue sempre resolver uma imagem utilizavel:

1. tentar cache local
2. fazer pull da imagem pedida se nao existir localmente
3. usar imagem fallback (`docker_default_image`) quando o pull falha
4. falhar de forma explicita com `DockerImageError` se imagem pedida e fallback falharem

Isto desbloqueia `US-014b`, que depende de receber uma imagem final resolvida antes de criar o container.

---

## Referencia PentAGI (Go)

No PentAGI, a logica vive em `RunContainer()` + `pullImage()`:

```go
if err := dc.pullImage(ctx, config.Image); err != nil {
    logger.WithError(err).Warnf("failed to pull image '%s' and using default image", config.Image)
    if err := fallbackDockerImage(); err != nil {
        defer updateContainerInfo(database.ContainerStatusFailed, "")
        return database.Container{}, err
    }
}
```

```go
func (dc *dockerClient) pullImage(ctx context.Context, imageName string) error {
    images, err := dc.client.ImageList(...)
    if err != nil { ... }
    if len(images) > 0 {
        return nil
    }
    pullStream, err := dc.client.ImagePull(ctx, imageName, image.PullOptions{})
    if err != nil { ... }
    defer pullStream.Close()
    if _, err := io.Copy(io.Discard, pullStream); err != nil { ... }
    return nil
}
```

Na versao Python, a mesma intencao foi mantida, com uma adaptacao importante: timeout explicito do pull via `concurrent.futures`.

---

## Codigo Python alvo

Ficheiro: `src/pentest/docker/client.py`

- `_pull_image()` — linhas 233-247
- `ensure_image()` — linhas 249-290

---

## `_pull_image()` (linhas 233-247) — linha a linha

```python
233. def _pull_image(self, image: str) -> None:
234.     """Pull an image with the configured timeout."""
235.     if self._pull_timeout <= 0:
236.         self._client.images.pull(image)
237.         return
238.
239.     executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
240.     future = executor.submit(self._client.images.pull, image)
241.     try:
242.         future.result(timeout=self._pull_timeout)
243.     except concurrent.futures.TimeoutError:
244.         future.cancel()
245.         raise
246.     finally:
247.         executor.shutdown(wait=False, cancel_futures=True)
```

| Linha | Explicacao |
|---|---|
| 233 | Define helper privado para encapsular pull + timeout. |
| 234 | Docstring curta: responsabilidade unica do metodo. |
| 235 | Caso especial: timeout `<= 0` significa "sem timeout". |
| 236 | Faz pull direto no docker-py (`images.pull`). |
| 237 | Sai imediatamente no caminho sem timeout. |
| 239 | Cria thread pool de 1 worker para controlar timeout externamente. |
| 240 | Submete o `images.pull` para execucao assincrona via `Future`. |
| 241 | Inicia bloco de controlo de erros/timeout. |
| 242 | Espera resultado ate ao limite `self._pull_timeout` (segundos). |
| 243 | Captura timeout explicito da espera do `Future`. |
| 244 | Cancela o `Future` para evitar trabalho pendente no lado Python. |
| 245 | Re-lanca o timeout para o caller (`ensure_image`) decidir fallback. |
| 246 | Garante limpeza de recursos, com erro ou sem erro. |
| 247 | Fecha executor sem bloquear (`wait=False`) e cancela futures pendentes. |

**Nota de design:** esta abordagem implementa o acceptance criterion de timeout configuravel sem mudar a API publica.

---

## `ensure_image()` (linhas 249-290) — linha a linha

```python
249. def ensure_image(self, image: str) -> str:
250.     """Ensure an image is available locally, with fallback to default image."""
251.     try:
252.         self._client.images.get(image)
253.         logger.info("docker_image_cache_hit", extra={"image": image})
254.         return image
255.     except docker.errors.ImageNotFound:
256.         pass
257.
258.     try:
259.         self._pull_image(image)
260.         logger.info("docker_image_pulled", extra={"image": image})
261.         return image
262.     except (
263.         concurrent.futures.TimeoutError,
264.         docker.errors.APIError,
265.         docker.errors.ImageNotFound,
266.     ) as exc:
267.         logger.warning(
268.             "docker_image_pull_failed_using_fallback",
269.             extra={
270.                 "requested_image": image,
271.                 "fallback_image": self._def_image,
272.                 "error": str(exc),
273.             },
274.         )
275.
276.     try:
277.         self._pull_image(self._def_image)
278.         logger.info(
279.             "docker_image_fallback_used",
280.             extra={"requested_image": image, "resolved_image": self._def_image},
281.         )
282.         return self._def_image
283.     except (
284.         concurrent.futures.TimeoutError,
285.         docker.errors.APIError,
286.         docker.errors.ImageNotFound,
287.     ) as exc:
288.         raise DockerImageError(
289.             f"Failed to pull requested image '{image}' and fallback image '{self._def_image}': {exc}"
290.         ) from exc
```

| Linha | Explicacao |
|---|---|
| 249 | Define API publica do story: recebe imagem alvo, devolve imagem resolvida. |
| 250 | Docstring indica fallback para default. |
| 251 | Inicia tentativa de cache local (caminho rapido). |
| 252 | Procura imagem local no daemon (`images.get`). |
| 253 | Regista cache hit para observabilidade. |
| 254 | Retorna imagem original sem pull (cumpre "skip pull on cache hit"). |
| 255 | Captura apenas `ImageNotFound` para continuar fluxo normal de pull. |
| 256 | `pass` intencional: imagem nao existe localmente, segue para pull. |
| 258 | Segundo bloco: tentar pull da imagem pedida. |
| 259 | Chama helper com timeout (`_pull_image`). |
| 260 | Log de sucesso do pull da imagem pedida. |
| 261 | Retorna imagem original quando pull resulta. |
| 262-266 | Captura classes de erro consideradas "falha de pull" para ativar fallback. |
| 267 | Regista warning de fallback. |
| 268 | Nome de evento de log dedicado para este caso. |
| 269-273 | Inclui contexto completo: pedida, fallback e razao textual do erro. |
| 276 | Terceiro bloco: tenta pull da imagem fallback. |
| 277 | Pull da default image configurada (`self._def_image`). |
| 278-281 | Log de que fallback foi usado e qual a imagem final resolvida. |
| 282 | Retorna fallback como resultado efetivo. |
| 283-287 | Se fallback tambem falhar (timeout/API/notfound), captura erro final. |
| 288-290 | Levanta `DockerImageError` com mensagem explicita e chaining (`from exc`). |

**Decisao importante de comportamento:** fallback e ativado em falhas de pull, nao em erros arbitrarios no `images.get(...)` fora de `ImageNotFound`.

---

## Mapeamento para Acceptance Criteria (US-014a)

| Acceptance Criterion | Implementacao |
|---|---|
| Local check com `images.get` | `ensure_image()` linhas 251-256 |
| Pull quando nao existe localmente | `ensure_image()` linhas 258-261 |
| Fallback em falha de pull | `ensure_image()` linhas 262-282 |
| Retornar imagem efetiva usada | `return image` ou `return self._def_image` |
| Warning com imagem original + razao | `logger.warning(... extra={requested_image, error})` linhas 267-273 |
| `DockerImageError` quando ambas falham | linhas 283-290 |
| Timeout configuravel | `_pull_image()` linhas 239-245 com `self._pull_timeout` |
| Skip pull em cache hit | linhas 252-254 |

---

## Testes do story

### Unit (`tests/unit/docker/test_client.py`)

- `test_ensure_image_cache_hit_skips_pull`
- `test_ensure_image_pull_success_when_missing`
- `test_ensure_image_fallback_success_when_requested_pull_fails`
- `test_ensure_image_raises_when_requested_and_fallback_pull_fail`
- `test_ensure_image_timeout_attempts_fallback`
- `test_ensure_image_fallback_logs_warning_with_reason`

Estes testes cobrem os caminhos de sucesso, erro, timeout e logging sem depender de rede externa.

### Integration (`tests/integration/docker/test_client.py`)

- `test_ensure_image_success_with_real_daemon`
- `test_ensure_image_cache_hit_does_not_pull`

O fixture `existing_local_image` foi melhorado para tentar preparar uma imagem deterministica (`alpine:3.20`) antes de fazer skip.

---

## Fluxo resumido

```text
ensure_image(image)
  |
  +-- images.get(image) sucesso? ---- sim --> return image
  |                                   nao (ImageNotFound)
  |
  +-- _pull_image(image) sucesso? --- sim --> return image
  |                               nao --> warning + fallback
  |
  +-- _pull_image(default) sucesso? - sim --> return default
                                  nao --> raise DockerImageError
```

---

## Dependencias no Epic Docker Sandbox

```text
US-019 (utils/constants)
  |
  v
US-013 (DockerClient init)
  |
  v
US-014a (ensure_image + fallback)   <-- este documento
  |
  v
US-014b (run_container usa imagem resolvida)
```

`US-014a` e o ponto de resiliencia de imagem para os stories seguintes do ciclo de vida de containers.

---

## Related Notes

- [Docs Home](../../README.md)
- [[PROJECT-STRUCTURE]]
- [[DOCKER-DAEMON-TROUBLESHOOTING]]
- [[US-013-DOCKER-CLIENT-EXPLAINED]]
- [[US-019-CONTAINER-UTILITIES-EXPLAINED]]
