# Project instructions

## Frappe Docker environment

This project runs Frappe apps inside Docker. The Docker Compose directory on the host is:

```text
~/workspace/frappe-docker/masters-frappe16
```

The Compose service is named `frappe`.

### Interactive access

From the host, enter the running container and then the bench directory:

```bash
cd ~/workspace/frappe-docker/masters-frappe16
docker compose exec frappe bash
cd frappe-bench
```

The final command runs inside the container, relative to its initial working directory.

### Commands from an agent or non-interactive shell

Run Compose commands from the host Compose directory. Use `-T` for commands that do not need an interactive terminal:

```bash
cd ~/workspace/frappe-docker/masters-frappe16
docker compose exec -T frappe bash -c 'cd frappe-bench && bench version'
```

Use the same pattern for other Bench commands, replacing `bench version` with the required command. Keep the directory change and the command in the same shell invocation; separate tool calls may not preserve the working directory.

## Working rules

- Run Bench commands and Frappe runtime operations inside the `frappe` container, using its installed environment.
- Do not assume Bench or the project dependencies are installed on the host.
- Before editing, check the project structure and Docker volume mappings to identify the host source directory corresponding to the app inside the container. Do not assume the Compose directory is the app repository.
- For site-specific commands, identify the intended site and use `bench --site <site-name> ...`. If several sites exist and the target is unclear, ask which site to use.
- Use the existing Docker setup. Do not create a separate host bench or virtual environment unless requested.
- Run the relevant checks inside the container and report what was verified. If Docker or the container is unavailable, explain the blocker instead of claiming checks passed.

