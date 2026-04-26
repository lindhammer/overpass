# Deployment Guide

This guide covers the Docker Compose homeserver deployment for Overpass: a private always-on Python worker that generates static briefings, plus public Caddy hosting for those generated files.

## Target Architecture

Overpass runs as two containers sharing one output volume:

```text
Internet / Telegram link
        |
        v
  https://briefs.example.com/briefings/YYYY-MM-DD.html
        |
        v
+------------------+        read-only shared volume        +----------------------+
| caddy            | <------------------------------------ | overpass-worker      |
| public container |                                       | private container    |
| HTTPS + static   |                                       | scheduler + renderer |
| /srv/overpass    |                                       | /app/output          |
+------------------+                                       +----------------------+
```

- `overpass-worker` is private. It is intended to stay running, schedule daily briefings now, later run live alerts, and write static HTML to `/app/output`.
- `caddy` is public. It serves the same output volume from `/srv/overpass` and handles HTTPS certificates.
- Telegram messages should link to Caddy, not the private worker. Set `web_base_url` in `config.yaml` to the public origin, such as `https://briefs.example.com`.

## Containerization

The `Dockerfile` builds a worker image for running Overpass in a predictable Linux environment:

- It uses the `python:3.12-slim` base image to match the supported Python version while keeping the image relatively small.
- It installs the package with `pip install -e .`, so the image runs the package from `/app` exactly as copied into the container.
- It sets `PYTHONPATH=/app`, which keeps package imports and default project-relative paths resolving under `/app`.
- It installs Playwright Chromium at build time with browser dependencies, so the HLTV scraper has a browser available when the container starts.
- It sets `PLAYWRIGHT_BROWSERS_PATH=/ms-playwright`, keeping browser binaries in a known image-level location rather than a user home cache.
- It creates and runs as a non-root `overpass` user.
- It creates writable `/app/output` and `/app/.cache` directories. In Compose these are backed by named volumes, so generated briefings and cache data persist across container recreation.

## Always-On Worker

The Compose service `overpass-worker` starts with the default command:

```bash
docker compose up -d overpass-worker
```

That command runs `overpass-worker` inside the container. The worker reads `config.schedule.daily_digest` and `config.timezone` from `config.yaml` to determine when to generate the daily briefing.

Scheduled runs skip today's briefing if the output file already exists. This protects against duplicate Telegram notifications and accidental duplicate generation after restarts.

To force a run immediately and bypass duplicate protection, use:

```bash
docker compose run --rm overpass-worker overpass-worker --run-now
```

The original one-shot CLI remains available inside the container:

```bash
docker compose run --rm overpass-worker overpass
```

Future live alerts are intended to fit into this same always-on worker process, but live alerts are not implemented yet.

## Caddy Static Hosting

Caddy is the public-facing container. The Python worker is not exposed to the internet and does not listen on public ports.

The `caddy` service mounts the named `overpass-output` volume read-only at `/srv/overpass` and serves it with `file_server`. Generated daily briefings are available at paths like:

```text
/briefings/YYYY-MM-DD.html
```

For example, if `web_base_url` is `https://briefs.example.com`, a briefing URL will look like:

```text
https://briefs.example.com/briefings/2026-04-26.html
```

For automatic TLS, TCP ports `80` and `443` must reach the Caddy container from the public internet. Caddy uses those ports for HTTP-to-HTTPS redirects, ACME challenges, and HTTPS traffic.

Before starting the deployment, replace `briefs.example.com` in both files:

- `deploy/Caddyfile`
- `config.yaml`, copied from `config.example.yaml`

Both values should point to the same public domain.

## From-Scratch Setup

These steps assume a fresh Ubuntu/Debian server and no prior Docker setup.

1. Install Docker and the Compose plugin on Ubuntu/Debian:

   ```bash
   sudo apt update
   sudo apt install -y docker.io docker-compose-plugin
   sudo systemctl enable --now docker
   sudo usermod -aG docker "$USER"
   ```

   Log out and back in so the new `docker` group membership applies. For other Linux distributions, use Docker's official installation instructions.

   Verify installation:

   ```bash
   docker --version
   docker compose version
   ```

2. Clone the repository:

   ```bash
   git clone https://github.com/lindhammer/overpass.git
   cd overpass
   ```

3. Create your config file:

   ```bash
   cp config.example.yaml config.yaml
   ```

4. Create your environment file.

   If `.env.example` exists:

   ```bash
   cp .env.example .env
   ```

   If it does not exist, create `.env` manually and add the required API keys and tokens used by your config.

5. Set the public briefing origin in `config.yaml`:

   ```yaml
   web_base_url: "https://briefs.example.com" # this will affect what link is shown in the telegram message
   ```

6. Set the same domain in `deploy/Caddyfile`:

   ```caddyfile
   briefs.example.com { # set to ":2020" e.g. if you want port 2020 to be used
       root * /srv/overpass
       file_server
   }
   ```

7. Fill `.env` with your secrets, including Telegram, LLM, and collector API credentials.

8. Build the worker image locally:

   ```bash
   docker compose build overpass-worker
   ```

9. Start the deployment:

   ```bash
   docker compose up -d
   ```

10. Check logs:

    ```bash
    docker compose logs -f overpass-worker
    docker compose logs -f caddy
    ```

11. Force a test run:

    ```bash
    docker compose run --rm overpass-worker overpass-worker --run-now
    ```

12. Open the generated briefing using your configured domain and the date path printed in the worker logs.

## DNS and Router Requirements

- Create a DNS `A` record pointing your briefing domain to the server's public IPv4 address.
- Create a DNS `AAAA` record too if the server is reachable over public IPv6.
- On a homeserver router, forward TCP `80` and `443` from the public internet to the server running Docker.
- If the server is behind CGNAT, simple port forwarding will not work. Use a VPS reverse proxy, a tunnel, Cloudflare Tunnel, Tailscale Funnel, or a similar public ingress option instead.

## Operations

Check service status:

```bash
docker compose ps
```

Follow worker logs:

```bash
docker compose logs -f overpass-worker
```

Follow Caddy logs:

```bash
docker compose logs -f caddy
```

Force a real briefing run immediately:

```bash
docker compose run --rm overpass-worker overpass-worker --run-now
```

Generate a demo briefing without external API setup:

```bash
docker compose run --rm overpass-worker overpass --demo
```

Restart the worker:

```bash
docker compose restart overpass-worker
```

Update from local source changes and recreate services:

```bash
git pull
docker compose up -d --build
```

If you intentionally use registry-published images in a modified deployment, pull them before recreating services:

```bash
docker compose pull && docker compose up -d --build
```

The repository's default Compose file builds the worker locally, so `pull` is not required for the worker image.

## Verification

Validate the Compose file:

```bash
docker compose config
```

This command can print resolved environment values and secrets. Do not paste its output into public issues, chats, or logs.

Confirm the worker image builds:

```bash
docker compose build overpass-worker
```

Confirm the worker CLI exposes `--run-now`:

```bash
docker compose run --rm --no-deps overpass-worker overpass-worker --help
```

Check runtime paths inside the container:

```bash
docker compose run --rm --no-deps overpass-worker python -c "from pathlib import Path; from datetime import date; print(Path('/app/config.yaml')); print(Path('/app/output') / 'briefings' / f'{date.today().isoformat()}.html')"
```

Expected paths include `/app/config.yaml` and `/app/output/briefings/YYYY-MM-DD.html`.

## Troubleshooting

**Caddy certificate issuance fails**

Check that DNS points to the server, router/firewall forwarding allows public TCP `80` and `443`, and Caddy logs show successful ACME challenge traffic:

```bash
docker compose logs -f caddy
```

**Telegram links point to localhost or the wrong domain**

Set `web_base_url` in `config.yaml` to the public Caddy origin, then restart the worker. The value should not be `localhost` for a deployment used from Telegram.

**Generated briefing URL returns 404**

Check worker logs for generation errors, confirm the output volume contains the briefing, and verify the URL uses `/briefings/YYYY-MM-DD.html` on the configured Caddy domain.

**Worker cannot write output or cache files**

The named volumes may have incompatible ownership from an earlier run or manual changes. Recreate the affected volumes if you do not need their contents, or fix ownership from a temporary container with `chown` so the non-root `overpass` user can write to `/app/output` and `/app/.cache`.

**HLTV or Playwright scraping fails**

HLTV scraping is fragile and can break because of anti-scrape measures, rate limits, layout changes, or browser behavior. The image installs Chromium and dependencies at build time, but site-side changes can still require scraper updates.

**`docker compose config` shows secrets**

This is expected behavior because Compose resolves environment files and interpolation. Treat the output as sensitive and avoid sharing it publicly.

