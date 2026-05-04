# Contributing

Contributions are welcome, especially compatibility reports for other Antminer
models and firmware versions.

## Development

Create a virtual environment and install dependencies:

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

Run the exporter from a checkout:

```bash
PYTHONPATH=src python -m antminer_exporter.app
```

Run syntax checks:

```bash
PYTHONPATH=src python -m py_compile src/antminer_exporter/app.py
```

## Compatibility Reports

When reporting a new supported model, include:

- Miner model and firmware version.
- Whether the web UI uses HTTP Digest authentication.
- Sanitized examples of `summary.cgi`, `stats.cgi`, `pools.cgi`, and
  `get_system_info.cgi` responses.
- Which metrics were populated and which were missing.

Do not include pool URLs, pool usernames, passwords, wallet addresses, or
publicly reachable miner IPs.
