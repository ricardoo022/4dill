---
tags: [agents, docker]
---

# US-016: File Operations - EXPLAINED

## Architecture Decisions

The implementation of `read_file` and `write_file` in the `DockerClient` provides the ability for agents to interact with the filesystem inside the Kali Linux sandbox containers.

### In-memory Tar Archives
Instead of mounting host directories for every single file operation or using complex `docker exec` combinations, we use the native Docker API methods `get_archive` and `put_archive`.
- **Read Operation:** Uses `container.get_archive(path)` which returns a tar stream. The implementation reads this stream into memory, extracts the first member (the requested file), and decodes it as UTF-8.
- **Write Operation:** Uses `container.put_archive(parent_dir, tar_data)`. The implementation creates a tar archive in memory using the `tarfile` module, containing the file content, and uploads it to the container.

This approach is:
1. **Surgical:** It doesn't rely on the `/work` volume mount for all operations, allowing interaction with files anywhere in the container (though we default to `/work`).
2. **Efficient:** It avoids the overhead of spawning a new process via `exec` for reading/writing.
3. **Robust:** It handles parent directory creation automatically via a quick `mkdir -p` before writing.

### Security and Constraints
- **Size Limits:** To prevent memory exhaustion, we enforce `max_read_file_size` and `max_write_file_size` (configured in `DockerConfig`).
- **UTF-8 Sanitization:** Since agents primarily work with text, we decode reads as UTF-8 with `errors="replace"`, ensuring that binary or corrupted data doesn't crash the agent loop.
- **Path Normalization:** Any relative path provided is automatically prepended with `/work/`, ensuring a consistent working environment for the agents.

## Models and Queries

This US is implemented directly in the `DockerClient` class in `src/pentest/docker/client.py`. It does not introduce new database models but relies on the `ContainerStatus` to ensure the container is running before attempting file operations.

## How to run tests

To verify the file operations, run the integration tests for the Docker client:

```bash
pytest tests/integration/docker/test_client.py -k "file"
```

These tests verify:
- Writing a file and reading it back.
- Writing to nested directories (automatic `mkdir -p`).
- Handling non-existent files.
- Enforcing size limits.
- Proper UTF-8 decoding with error replacement.

## Related Notes

- [[README]]
- [[USER-STORIES]]
- [[DATABASE-SCHEMA]]
- [[Epics/Docker Sandbox/US-013-DOCKER-CLIENT-EXPLAINED]]
- [[Epics/Docker Sandbox/US-014A-IMAGE-MANAGEMENT-EXPLAINED]]
