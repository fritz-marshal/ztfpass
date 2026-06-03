# ztfpass

**Minimal passthrough from SkyPortal to the ZTF scheduler queue API** — the one
capability Kowalski still provided at Caltech. It replaces the whole Kowalski
deployment with just this endpoint.

SkyPortal's ZTF facility API talks to `…/api/triggers/ztf`; Kowalski forwarded
that, over an SSH tunnel to the mountain, to the scheduler's `/queues`. `ztfpass`
does exactly that and nothing else, so it's a drop-in for SkyPortal:

```
SkyPortal  ──HTTP──>  ztfpass  ──SSH tunnel──>  ZTF scheduler (/queues)
        Authorization: Bearer <access_token>
```

## Endpoints (identical to Kowalski's)

| Method | Path | Body | Forwards to scheduler |
|---|---|---|---|
| `GET` | `/api/triggers/ztf` | — | `GET /queues` → queue contents |
| `PUT` | `/api/triggers/ztf` | `{queue_name, validity_window_mjd, targets, queue_type, user}` | `PUT /queues` |
| `DELETE` | `/api/triggers/ztf` | `{queue_name, user}` | `DELETE /queues` |
| `PUT` | `/api/triggers/ztf.test` | trigger body | validates only, never forwards |
| `GET` | `/healthz` | — | liveness (no auth) |

Response envelope matches Kowalski: `{"status": "success"|"error", "message": …, "data": …}`.
Status-code semantics preserved: scheduler `201` → `submitted`; scheduler `200`
on PUT → `409 already exists`; `GET`/`DELETE` `200` → success.

## Auth

`Authorization: Bearer <token>`, where `<token>` is one of `auth.tokens` in the
config — i.e. the allocation `access_token` configured in SkyPortal. No other
Kowalski auth machinery is carried over (no user DB). `auth.tokens` is a list,
so each consumer can have its own token and be revoked independently; rotate by
adding the new token, updating SkyPortal, then removing the old.

**Run it behind TLS.** A bearer token is only as safe as the transport, so in
production ztfpass must sit behind an HTTPS-terminating reverse proxy
(nginx/traefik/caddy, or your existing ingress) — the container speaks plain
HTTP on `:4000` and expects TLS upstream, exactly as Kowalski ran behind nginx.

Future hardening (deferred): restrict to SkyPortal's GCP egress IP once a static
egress IP is reserved — as a second factor *alongside* the token, not instead of
it.

## Configure

Copy `config.example.yaml` → `config.yaml` (gitignored) and fill the SSH-tunnel
fields (same keys Kowalski used under `config["ztf"]`) and the bearer token(s).
Secrets can instead come from env: `ZTF_MOUNTAIN_IP/_PORT/_USERNAME/_PASSWORD/
_BIND_IP/_BIND_PORT`, `ZTFPASS_AUTH_TOKENS` (comma-separated). Config path via
`$ZTFPASS_CONFIG` (default `./config.yaml`).

## Run (local)

```
pip install -e .
ztfpass --config config.yaml --host 0.0.0.0 --port 4000
# or: python -m ztfpass --port 4000
```

## Run (Docker — the deployment unit)

```
cp config.example.yaml config.yaml      # fill in tunnel creds + bearer token(s)
docker compose up -d --build            # serves on :4000
```

- Secrets stay **out of the image**: `config.yaml` is mounted read-only at
  runtime (`/config/config.yaml`). Alternatively, delete the volume and pass
  secrets via `environment:` (`ZTF_MOUNTAIN_*`, `ZTFPASS_AUTH_TOKENS`).
- Non-root user; built-in `HEALTHCHECK` hits `/healthz`.
- Plain Docker equivalent:
  ```
  docker build -t ztfpass .
  docker run -d -p 4000:4000 -v "$PWD/config.yaml:/config/config.yaml:ro" ztfpass
  ```

Point SkyPortal's ZTF allocation at this service: set `app.ztf.protocol/host/port`
(and the allocation `access_token`) so `ZTF_URL` resolves to ztfpass.

## Develop / test

```
pip install -e ".[dev]"
pytest                 # offline — a fake scheduler stands in for the SSH tunnel
ruff check . && ruff format --check .
```

The SSH-tunnel forwarder (`scheduler.SSHTunnelSchedulerClient`) is injected, so
the app is fully tested without a tunnel or a live scheduler.
