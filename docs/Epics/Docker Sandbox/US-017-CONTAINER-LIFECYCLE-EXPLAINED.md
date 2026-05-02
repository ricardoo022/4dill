---
tags: [docker]
---

# US-017: Container Lifecycle (Stop and Remove) - EXPLAINED

## Architecture Decisions
To ensure scan environments are cleaned up after completion or failure, we implemented graceful shutdown and removal of Docker containers.

1.  **Graceful Error Handling**: Both `stop_container` and `remove_container` handle `docker.errors.NotFound` exceptions. If a container is already gone (e.g., manually removed or failed to start), the system logs a warning and proceeds to update the database state, ensuring idempotency.
2.  **Sequential Operations**: `remove_container` always calls `stop_container` first. This ensures that we attempt to stop the container before forcing removal. Removal is performed with `force=True` and `v=True` to ensure all associated volumes (non-persistent) are also cleaned up.
3.  **Database Synchronization**: Every lifecycle event (stopping, deletion) is immediately persisted to the PostgreSQL database using the `AsyncSession`. This allows the UI and other agents to track the exact state of the infrastructure.

## Implementation Details

### Models and Queries
-   We utilize the existing `update_container_status` query from `src/pentest/database/queries/containers.py`.
-   New statuses added to `ContainerStatus` enum: `STOPPED`, `DELETED`.

### Docker Client Methods
-   `stop_container(container_id: str, db_id: int)`: Stops the container and sets DB status to `stopped`.
-   `remove_container(container_id: str, db_id: int)`: Stops, then removes the container and sets DB status to `deleted`.

## How to Run Tests
Integration tests require a running Docker daemon and a reachable PostgreSQL database.

```bash
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/pentagidb_test \
.venv/bin/pytest tests/integration/docker/test_lifecycle.py -v
```

## Related Notes

- [[US-014B-CONTAINER-CREATION-STARTUP-EXPLAINED]] — run_container(), DB lifecycle STARTING → RUNNING / FAILED
- [[US-018-STARTUP-CLEANUP-EXPLAINED]] — cleanup de containers órfãos no arranque do sistema
- [[US-016-File-Operations-EXPLAINED]] — read_file() / write_file() dentro do container
- [[US-015-CONTAINER-EXEC-EXPLAINED]] — exec_command() com timeout e detach
- [[US-013-DOCKER-CLIENT-EXPLAINED]] — DockerClient init, config, network setup
