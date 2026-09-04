"""Smoke test HTTP non destructif d'une instance TestPilot déjà démarrée."""

from __future__ import annotations

import argparse
import json
import ssl
import urllib.error
import urllib.request


def _get(url: str) -> tuple[int, dict, bytes]:
    try:
        with urllib.request.urlopen(url, timeout=10, context=ssl.create_default_context()) as rep:
            return rep.status, dict(rep.headers.items()), rep.read()
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers.items()), exc.read()


def verifier(base_url: str, *, allow_http: bool = False) -> dict:
    base = base_url.rstrip("/")
    if not allow_http and not base.startswith("https://"):
        raise RuntimeError("HTTPS est obligatoire (utiliser --allow-http seulement en local)")

    resultat = {}
    for path, attendu in (("/", 200), ("/api/health/live", 200),
                          ("/api/health/ready", 200), ("/api/openapi.json", 401),
                          ("/metrics", 404)):
        statut, entetes, corps = _get(base + path)
        if statut != attendu:
            raise RuntimeError(f"{path} répond {statut}, attendu {attendu}: {corps[:200]!r}")
        entetes_normalises = {nom.lower(): valeur for nom, valeur in entetes.items()}
        if entetes_normalises.get("x-content-type-options", "").lower() != "nosniff":
            raise RuntimeError(f"{path}: en-tête de sécurité nosniff absent")
        resultat[path] = statut

    statut, _, corps = _get(base + "/api/health/ready")
    payload = json.loads(corps)
    if statut != 200 or payload.get("status") != "ready":
        raise RuntimeError("la readiness ne confirme pas l'état ready")
    return resultat


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base_url")
    parser.add_argument("--allow-http", action="store_true")
    args = parser.parse_args(argv)
    try:
        resultat = verifier(args.base_url, allow_http=args.allow_http)
    except Exception as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps({"status": "ok", "checks": resultat}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
