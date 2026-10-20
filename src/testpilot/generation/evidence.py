"""Preuves UI contextualisées ; un schéma RPC n'est pas une observation de page."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from urllib.parse import urljoin, urlsplit


def page_identity(url: str, base_url: str = '') -> str:
    """Conserve langue, identifiant et fragment de vue ; aucun rapprochement deviné."""
    parts = urlsplit(urljoin(base_url, url))
    origin = f'{parts.scheme.lower()}://{parts.netloc.lower()}' if parts.netloc else ''
    return origin + (parts.path.rstrip('/') or '/') + ('?' + parts.query if parts.query else '') + (
        '#' + parts.fragment if parts.fragment else '')


def record_observation(ctx, *, source: str, resource: str, fields: list[dict],
                       language: str = '', submission=None) -> str:
    ctx.observations.append({
        'id': f'observation-{len(ctx.observations) + 1}', 'source': source,
        'resource': resource, 'target_sha256': ctx.target_sha256,
        'observed_at': datetime.now(timezone.utc).isoformat(), 'language': language,
        'fields': [{key: f[key] for key in ('name', 'type', 'tag', 'label', 'required', 'options',
                                          'visible', 'min', 'max', 'maxlength', 'pattern',
                                          'minlength', 'inputmode', 'placeholder', 'title',
                                          'data_mask', 'inputmask')
                    if key in f} for f in fields],
        'submission': submission,
    })
    return ctx.observations[-1]['id']


# A61 (porteur, 2026-10-20 : « une génération doit être prête à lancer ») — mesuré sur un projet web : l'étape générique
# `j'ouvre la page "/acces"` n'était pas reconnue comme une navigation (seule l'écriture Odoo « navigue vers » l'était) ;
# tous les champs d'un test web sortaient « sans preuve » et le cas restait à relire, preuve pourtant présente.
_NAVIGATION = re.compile(r'(?:navigue\s+vers\s+(?:l\'URL\s+du\s+portail\s+)?|ouvre\s+la\s+page\s+)"(?P<url>[^"]+)"', re.IGNORECASE)


def contextual_warnings(feature: str, evidence: list[dict], *, target_sha256: str = '',
                        base_url: str = '', max_age_seconds: int = 86400) -> list[dict]:
    """Un champ que le test renseigne doit avoir été VU à l'écran (source « ui », visible, récent, même cible) — sur la page
    où le test l'emploie quand le texte la nomme (`j'ouvre la page …`, `navigue vers …`). Arrivé par un clic (menu, lien),
    le texte ne nomme pas la page : une preuve d'écran de la version (recopiée de version en version), récente et de la
    même cible, où le champ était visible, suffit (A61, mesuré sur un test qui clique « Contrôle d'accès » : le champ avait
    été vu sur la page atteinte, le cas restait à relire). Pire cas : le champ n'existe pas sur la page atteinte — l'étape
    de saisie échoue à l'exécution (erreur technique), jamais un « conforme ». Jamais un schéma RPC à la place d'une
    observation d'écran."""
    from testpilot.generation.smoke_check import _extraire_champ_valeur
    warnings = []
    route = None
    background_route = None
    in_background = False
    now = datetime.now(timezone.utc)
    def fresh(item):
        try:
            age = (now - datetime.fromisoformat(item.get('observed_at', ''))).total_seconds()
            return 0 <= age <= max_age_seconds
        except (ValueError, TypeError):
            return False
    for number, line in enumerate(feature.splitlines(), 1):
        if line.strip().startswith(('Contexte:', 'Background:')):
            in_background = True
        if line.strip().startswith(('Scénario:', 'Scenario:', 'Plan du scénario:')):
            route = background_route
            in_background = False
        nav = _NAVIGATION.search(line)
        if nav:
            route = page_identity(nav.group('url'), base_url)
            if in_background:
                background_route = route
        field = _extraire_champ_valeur(line)
        if not field:
            continue
        name, _ = field
        usable = [e for e in evidence if e.get('source') == 'ui'
                  and fresh(e)
                  and (not target_sha256 or e.get('target_sha256') == target_sha256)
                  and (route is None or page_identity(e.get('resource', ''), base_url) == route)]
        if any(name in {f.get('name') for f in e.get('fields', [])
                        if f.get('visible') is True} for e in usable):
            continue
        warnings.append({'kind': 'champ_ui_non_verifie', 'step': name, 'line': number,
                         'message': f'Le champ « {name} » ne possède pas de preuve UI '
                                    'visible, datant de moins de 24 h, sur cette page pour cette cible. Un schéma RPC ou une '
                                    'autre vue ne suffit pas. Observer après navigation.'})
    return warnings
