# Agent Guidelines

## Project Scope

This repository contains a Prometheus exporter and Grafana dashboard for the
modern Bitmain Antminer web API.

Keep changes focused on:

- `src/antminer_exporter/app.py` for exporter behavior.
- `dashboards/antminer-s21.json` for Grafana dashboard updates.
- `README.md` for user-facing setup and compatibility notes.
- `alerts/` for portable Grafana-managed and Prometheus alert rules.
- `docker-compose.yml`, `Dockerfile`, and packaging files for deployment.

## Safety Rules

- Do not commit real miner passwords, pool URLs, pool usernames, wallet
  addresses, public miner IPs, or production `.env` files.
- Keep examples generic. Use private LAN examples such as `192.168.0.250` and
  `192.168.0.251` unless documentation-only addresses are clearly required.
- Do not add pool URL or pool user labels to metrics.
- Prefer read-only Antminer endpoints. Do not call configuration, reboot,
  password, or network mutation endpoints from exporter code.

## Exporter Rules

- Preserve the blackbox-style scrape contract:
  `GET /metrics?target=<miner-ip>`.
- Keep target allowlisting through `ANTMINER_ALLOWED_TARGETS`.
- Keep exporter bind settings under `EXPORTER_LISTEN_ADDR` and
  `EXPORTER_LISTEN_PORT`.
- On miner scrape failure, return Prometheus text format with
  `antminer_up 0`; do not crash the exporter process.
- Avoid adding high-cardinality labels. Static miner details belong only in
  `antminer_info`.

## Compatibility

- The known-tested target is Antminer S21+ with modern Bitmain web firmware.
- Treat S21/S21 Pro and other modern models as likely compatible until verified.
- Older cgminer/bmminer TCP API support is out of scope for this exporter.
- Hydro-specific coolant and pump metrics are planned, but should be added only
  after sanitized API response examples are available.

## Validation

Before committing code or dashboard changes, run the relevant checks:

```bash
PYTHONPATH=src python -m py_compile src/antminer_exporter/app.py
docker build -t antminer-exporter:local .
docker compose config
promtool check rules alerts/prometheus/antminer.rules.yaml
```

For dashboard changes, validate that `dashboards/antminer-s21.json` is valid
JSON and can be imported into Grafana.

For alert changes, validate that Grafana provisioning YAML remains parseable
and that live Grafana-managed rules do not expose secrets in labels or
annotations.
