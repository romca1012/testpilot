# Initialise le banc de mesure (lot 04) sur un poste Windows — équivalent de scripts/banc_init.sh.
#   .\scripts\banc_init.ps1 [-Version 17.0]
param([string]$Version = "17.0")
$ErrorActionPreference = "Stop"
$racine = Split-Path -Parent $PSScriptRoot
Set-Location $racine
$modules = "sale_management,purchase,stock,account,crm,project,tp_bugs_injectes"

$cle = "ODOO_IMAGE_" + $Version.Replace(".", "_")
$ligne = Get-Content banc/images.env | Where-Object { $_ -match "^$cle=" } | Select-Object -First 1
if (-not $ligne) { throw "Version $Version inconnue : aucune ligne $cle dans banc/images.env" }
$env:ODOO_IMAGE = $ligne.Substring($cle.Length + 1)
if (-not $env:BANC_PORT) { $env:BANC_PORT = "18069" }

function Compose { docker compose -f compose.banc.yml @args; if ($LASTEXITCODE -ne 0) { throw "docker compose $args a échoué" } }

Write-Host "== Banc Odoo $Version ($env:ODOO_IMAGE), port $env:BANC_PORT"
docker compose -f compose.banc.yml down -v --remove-orphans 2>$null | Out-Null
Compose up -d db
do { Start-Sleep -Seconds 2; $etat = (docker compose -f compose.banc.yml ps --format "{{.Health}}" db) } until ($etat -eq "healthy")

Write-Host "== Création de la base (données de démo) et installation des modules — quelques minutes"
Compose run --rm -T odoo odoo -d banc -i "base,$modules" --load-language=fr_FR --stop-after-init --log-level=warn

Write-Host "== Neutralisation"
Compose run --rm -T odoo odoo neutralize -d banc

Write-Host "== Comptes de test et langue fr_FR"
Get-Content banc/init_comptes.py -Raw | docker compose -f compose.banc.yml run --rm -T odoo odoo shell -d banc --no-http --log-level=warn
if ($LASTEXITCODE -ne 0) { throw "création des comptes échouée" }

Write-Host "== Démarrage"
Compose up -d odoo
for ($i = 0; $i -lt 60; $i++) {
    try { Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:$($env:BANC_PORT)/web/login" | Out-Null; Write-Host "== Banc prêt : http://127.0.0.1:$($env:BANC_PORT) (base « banc », admin / admin)"; exit 0 } catch { Start-Sleep -Seconds 3 }
}
throw "Le banc ne répond pas sur le port $env:BANC_PORT"
