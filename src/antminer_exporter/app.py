import json
import os
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import httpx
from prometheus_client import CollectorRegistry, Gauge, generate_latest
from prometheus_client.exposition import CONTENT_TYPE_LATEST


LISTEN_ADDR = os.getenv("EXPORTER_LISTEN_ADDR", "0.0.0.0")
LISTEN_PORT = int(os.getenv("EXPORTER_LISTEN_PORT", "9154"))
USERNAME = os.getenv("ANTMINER_USER", "root")
PASSWORD = os.getenv("ANTMINER_PASSWORD", "root")
TIMEOUT = float(os.getenv("ANTMINER_TIMEOUT_SECONDS", "5"))
ALLOWED_TARGETS = {
    item.strip()
    for item in os.getenv("ANTMINER_ALLOWED_TARGETS", "").split(",")
    if item.strip()
}

COMMANDS = ("summary", "stats", "pools", "warning", "get_system_info", "miner_type")


def to_float(value):
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        cleaned = value.strip().replace(",", "")
        if not cleaned:
            return None
        try:
            return float(cleaned)
        except ValueError:
            return None
    return None


def status_value(value):
    if value is None:
        return 0.0
    text = str(value).strip().lower()
    if text in {"s", "ok", "alive", "true", "1", "normal"}:
        return 1.0
    return 0.0


def first_obj(payload, key):
    value = payload.get(key) if isinstance(payload, dict) else None
    if isinstance(value, list) and value:
        return value[0]
    if isinstance(value, dict):
        return value
    return {}


def fetch_json(client, target, command):
    response = client.get(f"http://{target}/cgi-bin/{command}.cgi")
    response.raise_for_status()
    return response.json()


def collect_target(target):
    started = time.monotonic()
    data = {}
    error = None
    try:
        auth = httpx.DigestAuth(USERNAME, PASSWORD)
        with httpx.Client(auth=auth, timeout=TIMEOUT) as client:
            for command in COMMANDS:
                try:
                    data[command] = fetch_json(client, target, command)
                except (httpx.HTTPError, json.JSONDecodeError) as exc:
                    if command in {"miner_type", "warning"}:
                        data[command] = {}
                    else:
                        raise exc
    except Exception as exc:  # Export scrape failure as metrics instead of crashing.
        error = str(exc)
    return data, time.monotonic() - started, error


def build_metrics(target):
    registry = CollectorRegistry()

    up = Gauge("antminer_up", "Whether the Antminer scrape succeeded.", registry=registry)
    scrape_duration = Gauge(
        "antminer_scrape_duration_seconds",
        "Antminer scrape duration in seconds.",
        registry=registry,
    )
    scrape_error = Gauge(
        "antminer_scrape_error",
        "Antminer scrape error marker.",
        ["error"],
        registry=registry,
    )

    hashrate_5s = Gauge(
        "antminer_hashrate_5s_ghs",
        "Antminer 5 second hashrate in GH/s.",
        registry=registry,
    )
    hashrate_30m = Gauge(
        "antminer_hashrate_30m_ghs",
        "Antminer 30 minute hashrate in GH/s.",
        registry=registry,
    )
    hashrate_avg = Gauge(
        "antminer_hashrate_avg_ghs",
        "Antminer average hashrate in GH/s.",
        registry=registry,
    )
    hashrate_ideal = Gauge(
        "antminer_hashrate_ideal_ghs",
        "Antminer ideal hashrate in GH/s.",
        registry=registry,
    )
    power = Gauge(
        "antminer_power_watts",
        "Antminer reported power draw in watts.",
        registry=registry,
    )
    efficiency = Gauge(
        "antminer_efficiency_j_per_th",
        "Antminer reported efficiency in J/TH.",
        registry=registry,
    )
    ambient_temp = Gauge(
        "antminer_ambient_temp_celsius",
        "Antminer reported ambient temperature in Celsius.",
        registry=registry,
    )

    fan_rpm = Gauge("antminer_fan_rpm", "Antminer fan RPM.", ["fan"], registry=registry)
    chain_hashrate = Gauge(
        "antminer_chain_hashrate_ghs",
        "Antminer chain hashrate in GH/s.",
        ["chain"],
        registry=registry,
    )
    chain_temp_chip = Gauge(
        "antminer_chain_temp_chip_celsius",
        "Antminer chain chip temperature in Celsius.",
        ["chain", "sensor"],
        registry=registry,
    )
    chain_temp_pcb = Gauge(
        "antminer_chain_temp_pcb_celsius",
        "Antminer chain PCB temperature in Celsius.",
        ["chain", "sensor"],
        registry=registry,
    )
    chain_asic_count = Gauge(
        "antminer_chain_asic_count",
        "Antminer chain ASIC count.",
        ["chain"],
        registry=registry,
    )
    status_ok = Gauge(
        "antminer_status_ok",
        "Antminer component status, 1 is healthy.",
        ["type"],
        registry=registry,
    )
    pool_alive = Gauge(
        "antminer_pool_alive",
        "Antminer pool status, 1 is alive.",
        ["pool"],
        registry=registry,
    )
    info = Gauge(
        "antminer_info",
        "Antminer static information.",
        ["miner_type", "firmware_type", "ipaddress"],
        registry=registry,
    )

    data, duration, error = collect_target(target)
    scrape_duration.set(duration)
    if error:
        up.set(0)
        scrape_error.labels(error[:120]).set(1)
        return generate_latest(registry)

    up.set(1)
    scrape_error.labels("").set(0)

    summary = first_obj(data.get("summary", {}), "SUMMARY")
    stats = first_obj(data.get("stats", {}), "STATS")
    system_info = data.get("get_system_info", {}) if isinstance(data.get("get_system_info"), dict) else {}
    miner_type = data.get("miner_type", {}) if isinstance(data.get("miner_type"), dict) else {}

    for gauge, keys in (
        (hashrate_5s, ("rate_5s",)),
        (hashrate_30m, ("rate_30m",)),
        (hashrate_avg, ("rate_avg",)),
        (hashrate_ideal, ("rate_ideal",)),
        (power, ("watt", "power")),
        (efficiency, ("jt", "efficiency")),
    ):
        value = None
        for source in (summary, stats):
            for key in keys:
                value = to_float(source.get(key))
                if value is not None:
                    break
            if value is not None:
                break
        if value is not None:
            gauge.set(value)

    value = to_float(stats.get("ambient_temp"))
    if value is not None:
        ambient_temp.set(value)

    fans = stats.get("fan") if isinstance(stats.get("fan"), list) else []
    for idx, rpm in enumerate(fans):
        value = to_float(rpm)
        if value is not None:
            fan_rpm.labels(str(idx)).set(value)

    chains = stats.get("chain") if isinstance(stats.get("chain"), list) else []
    for fallback_idx, chain in enumerate(chains):
        if not isinstance(chain, dict):
            continue
        chain_id = str(chain.get("index", fallback_idx))
        value = to_float(chain.get("rate_real"))
        if value is not None:
            chain_hashrate.labels(chain_id).set(value)
        value = to_float(chain.get("asic_num"))
        if value is not None:
            chain_asic_count.labels(chain_id).set(value)

        for sensor_idx, temp in enumerate(chain.get("temp_chip") or []):
            value = to_float(temp)
            if value is not None:
                chain_temp_chip.labels(chain_id, str(sensor_idx)).set(value)
        for sensor_idx, temp in enumerate(chain.get("temp_pcb") or []):
            value = to_float(temp)
            if value is not None:
                chain_temp_pcb.labels(chain_id, str(sensor_idx)).set(value)

    for item in summary.get("status") or []:
        if isinstance(item, dict):
            status_ok.labels(str(item.get("type", "unknown"))).set(status_value(item.get("status")))

    pools = data.get("pools", {}).get("POOLS") if isinstance(data.get("pools"), dict) else []
    if isinstance(pools, list):
        for fallback_idx, pool in enumerate(pools):
            if isinstance(pool, dict):
                pool_id = str(pool.get("index", fallback_idx))
                pool_alive.labels(pool_id).set(status_value(pool.get("status")))

    info.labels(
        str(miner_type.get("miner_type") or system_info.get("hostname") or "unknown"),
        str(system_info.get("firmware_type") or "unknown"),
        str(system_info.get("ipaddress") or target),
    ).set(1)

    return generate_latest(registry)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path in {"/healthz", "/-/healthy"}:
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok\n")
            return

        if parsed.path != "/metrics":
            self.send_response(404)
            self.end_headers()
            return

        target = parse_qs(parsed.query).get("target", [""])[0].strip()
        if not target:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"missing target query parameter\n")
            return

        if ALLOWED_TARGETS and target not in ALLOWED_TARGETS:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"target is not allowed\n")
            return

        output = build_metrics(target)
        self.send_response(200)
        self.send_header("Content-Type", CONTENT_TYPE_LATEST)
        self.end_headers()
        self.wfile.write(output)

    def log_message(self, fmt, *args):
        print("%s - - [%s] %s" % (self.address_string(), self.log_date_time_string(), fmt % args), flush=True)


def main():
    server = ThreadingHTTPServer((LISTEN_ADDR, LISTEN_PORT), Handler)
    print(f"antminer-exporter listening on {LISTEN_ADDR}:{LISTEN_PORT}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
