# Local Flagsmith lab

This setup provisions Flagsmith, its task processor, and PostgreSQL on a development machine. It uses the same official image digests as the submitted run. The dashboard is served on the loopback interface at [127.0.0.1:18711](http://127.0.0.1:18711).

Install Python 3.10 or later, Docker Engine with Compose v2, and the official Flagsmith CLI v2. Allow about 4 GB for Docker. Run the following from the repository root.

```sh
python deploy/local_instance.py secrets
docker compose --env-file .local/flagsmith-host/local.env -f deploy/compose.yaml up -d
python deploy/local_instance.py connect
```

The first launch runs database migrations. The connection helper waits for the API, creates a local administrator, project and environment, connects the PostgreSQL experimentation warehouse, then writes private configuration under `.local/flagsmith-host/`. The lab login is stored in `context.json`. Keep this directory private.

Set the following variable in the shell where you run the experiment commands in the project README.

```sh
export AFTERDROP_ENV_FILE=.local/flagsmith-host/experiment.env
```

In PowerShell, use `$env:AFTERDROP_ENV_FILE='.local/flagsmith-host/experiment.env'`. Place `flagsmith` on your PATH or set `FLAGSMITH_CLI` to its executable path.

To stop the lab and keep its data, run the command below. Use the same Compose file and secrets file with `up -d` to resume it.

```sh
docker compose --env-file .local/flagsmith-host/local.env -f deploy/compose.yaml stop
```

The embedded warehouse is intended for experimentation in a development environment. [Flagsmith self-hosting documentation](https://docs.flagsmith.com/experimentation/self-hosting)

To reproduce alongside a saved lab, use a different Compose project name (`-p afterdrop-review`), set `AFTERDROP_PORT` to an unused loopback port and `AFTERDROP_STATE_DIR` to a new private directory under `.local/`. Use that directory's `local.env` for Compose and `experiment.env` for the experiment runner. Keep the same variables across all commands. This gives the reproduction its own database volume, credentials and server endpoint.
