#!/usr/bin/env bash
# Initialise le banc de mesure (lot 04) : base `banc` avec données de démo, modules de D9 et
# `tp_bugs_injectes`, neutralisation, deux comptes de test, langue fr_FR.
#
#   scripts/banc_init.sh [version Odoo : 16.0 | 17.0 | 18.0 — défaut 17.0]
#
# Idempotent en ce sens qu'il repart d'une base VIDE : `down -v` d'abord (le volume est jetable).
set -euo pipefail

VERSION="${1:-17.0}"
RACINE="$(cd "$(dirname "$0")/.." && pwd)"
cd "$RACINE"
COMPOSE=(docker compose -f compose.banc.yml)
MODULES="sale_management,purchase,stock,account,crm,project,tp_bugs_injectes"

CLE="ODOO_IMAGE_${VERSION//./_}"
IMAGE="$(grep -E "^${CLE}=" banc/images.env | cut -d= -f2- || true)"
if [ -z "$IMAGE" ]; then
  echo "Version ${VERSION} inconnue : aucune ligne ${CLE} dans banc/images.env" >&2
  exit 2
fi
export ODOO_IMAGE="$IMAGE"
export BANC_PORT="${BANC_PORT:-18069}"

echo "== Banc Odoo ${VERSION} ($IMAGE), port ${BANC_PORT}"
"${COMPOSE[@]}" down -v --remove-orphans >/dev/null 2>&1 || true
"${COMPOSE[@]}" up -d db
until [ "$("${COMPOSE[@]}" ps --format '{{.Health}}' db)" = "healthy" ]; do sleep 2; done

echo "== Création de la base (données de démo) et installation des modules — quelques minutes"
"${COMPOSE[@]}" run --rm -T odoo odoo -d banc -i "base,${MODULES}" --load-language=fr_FR \
  --stop-after-init --log-level=warn

echo "== Neutralisation (aucun envoi de courriel, aucun cron externe, aucun paiement réel)"
"${COMPOSE[@]}" run --rm -T odoo odoo neutralize -d banc

echo "== Comptes de test et langue fr_FR"
"${COMPOSE[@]}" run --rm -T odoo odoo shell -d banc --no-http --log-level=warn < banc/init_comptes.py

echo "== Démarrage"
"${COMPOSE[@]}" up -d odoo
for _ in $(seq 1 60); do
  if curl -fsS -o /dev/null "http://127.0.0.1:${BANC_PORT}/web/login"; then
    echo "== Banc prêt : http://127.0.0.1:${BANC_PORT} (base « banc », admin / admin)"
    exit 0
  fi
  sleep 3
done
echo "Le banc ne répond pas sur le port ${BANC_PORT}" >&2
exit 1
