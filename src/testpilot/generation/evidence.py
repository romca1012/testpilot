"""Preuves UI contextualisées ; un schéma RPC n'est pas une observation de page."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from urllib.parse import urlsplit

from testpilot.generation.gherkin_mots_cles import DEBUT_CONTEXTE, DEBUT_REGLE, DEBUT_SCENARIO


def _adresse_complete(url: str, base_url: str) -> str:
    """Même règle que l'exécution (`_base_helpers.ouvrir_page`, `url_dans_l_application`) : un chemin est RATTACHÉ à
    l'adresse du projet, chemin de celle-ci compris. Étape 2 (A61, 2026-10-20) : `urljoin("http://h/app", "/acces")` donnait
    `http://h/acces` alors que le test ouvre `http://h/app/acces` — la preuve, relevée sur la vraie page, ne correspondait
    jamais, et le cas restait à relire sur tout projet hébergé sous un chemin."""
    url = (url or '').strip()
    if re.match(r'^[A-Za-z][A-Za-z0-9+.-]*://', url) or not base_url:
        return url
    return base_url.rstrip('/') + '/' + url.lstrip('/')


def page_identity(url: str, base_url: str = '') -> str:
    """Conserve langue, identifiant et fragment de vue ; aucun rapprochement deviné."""
    parts = urlsplit(_adresse_complete(url, base_url))
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
                                          'data_mask', 'inputmask', 'cadre')
                    if key in f} for f in fields],
        'submission': submission,
    })
    return ctx.observations[-1]['id']


# A61 (porteur, 2026-10-20 : « une génération doit être prête à lancer ») — mesuré sur un projet web : l'étape générique
# `j'ouvre la page "/acces"` n'était pas reconnue comme une navigation (seule l'écriture Odoo « navigue vers » l'était) ;
# tous les champs d'un test web sortaient « sans preuve » et le cas restait à relire, preuve pourtant présente.
_NAVIGATION = re.compile(r'(?:navigue\s+vers\s+(?:l\'URL\s+du\s+portail\s+)?|ouvre\s+la\s+page\s+)"(?P<url>[^"]+)"', re.IGNORECASE)
# Étape 2 (A61) : après un clic, une connexion ou un retour à l'accueil, la page atteinte n'est plus celle que le texte a
# nommée — même règle que `litteraux_observes.controler_feature`. La page devient INCONNUE (règle A64 : une preuve d'écran
# récente, de la même cible, où le champ était visible). Mesuré : `j'ouvre la page "/"` puis un clic sur « Contrôle
# d'accès » — le champ était cherché sur « / », et le cas restait à relire.
# Étape 2 (A61) : une saisie « dans le cadre "X" » ne se prouve que par un champ vu DANS ce cadre ; une saisie hors cadre,
# que par un champ du document principal (l'exécution ne cherche pas ailleurs).
_DANS_LE_CADRE = re.compile(r'dans\s+le\s+cadre\s+"(?P<cadre>[^"]+)"', re.IGNORECASE)
_PAGE_QUITTEE = re.compile(r"\bje clique\b|\bje me connecte\b|\bj'accède à la page d'accueil\b|"
                           r"\bje navigue vers le menu\b", re.IGNORECASE)


def contextual_warnings(feature: str, evidence: list[dict], *, target_sha256: str = '',
                        base_url: str = '', max_age_seconds: int = 86400,
                        reference_time: datetime | None = None) -> list[dict]:
    """Un champ que le test renseigne doit avoir été VU à l'écran (source « ui », visible, récent, même cible) — sur la page
    où le test l'emploie quand le texte la nomme (`j'ouvre la page …`, `navigue vers …`). Arrivé par un clic (menu, lien),
    le texte ne nomme pas la page : une preuve d'écran de la version (recopiée de version en version), récente et de la
    même cible, où le champ était visible, suffit (A61, mesuré sur un test qui clique « Contrôle d'accès » : le champ avait
    été vu sur la page atteinte, le cas restait à relire). Pire cas : le champ n'existe pas sur la page atteinte — l'étape
    de saisie échoue à l'exécution (erreur technique), jamais un « conforme ». Jamais un schéma RPC à la place d'une
    observation d'écran.

    `reference_time` (étape 2, A67) : l'âge d'une preuve se mesure au moment où le test a été ÉCRIT, pas au moment où l'on
    affiche le cas — sinon un cas devenait « à relire » tout seul 24 h après sa génération, et la raison d'un cas bloqué
    changeait sans que rien n'ait changé. Sans `reference_time` (pendant l'écriture), c'est maintenant."""
    from testpilot.generation.smoke_check import _extraire_champ_valeur
    warnings = []
    route = None
    background_route = None
    route_du_contexte_general = None   # le Contexte de la fonctionnalité vaut aussi dans ses règles (revue, étape 2)
    dans_une_regle = False
    in_background = False
    now = reference_time or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    def fresh(item):
        try:
            observe = datetime.fromisoformat(item.get('observed_at', ''))
            if observe.tzinfo is None:
                observe = observe.replace(tzinfo=timezone.utc)
            age = (now - observe).total_seconds()
            return 0 <= age <= max_age_seconds
        except (ValueError, TypeError):
            return False
    for number, line in enumerate(feature.splitlines(), 1):
        if DEBUT_REGLE.match(line):
            dans_une_regle = True
            route = background_route = route_du_contexte_general
            in_background = False
        if DEBUT_CONTEXTE.match(line):
            in_background = True
        if DEBUT_SCENARIO.match(line):
            route = background_route
            in_background = False
        nav = _NAVIGATION.search(line)
        if nav:
            route = page_identity(nav.group('url'), base_url)
        elif _PAGE_QUITTEE.search(line):
            route = None
        if (nav or _PAGE_QUITTEE.search(line)) and in_background:
            background_route = route
            if not dans_une_regle:
                route_du_contexte_general = route
        field = _extraire_champ_valeur(line)
        if not field:
            continue
        name, _ = field
        usable = [e for e in evidence if e.get('source') == 'ui'
                  and fresh(e)
                  and (not target_sha256 or e.get('target_sha256') == target_sha256)
                  and (route is None or page_identity(e.get('resource', ''), base_url) == route)]
        dans = _DANS_LE_CADRE.search(line)

        def au_bon_endroit(f):
            return (dans.group('cadre') in (f.get('cadre') or [])) if dans else not f.get('cadre')
        if any(name in {f.get('name') for f in e.get('fields', [])
                        if f.get('visible') is True and au_bon_endroit(f)} for e in usable):
            continue
        warnings.append({'kind': 'champ_ui_non_verifie', 'step': name, 'line': number,
                         'message': f'Le champ « {name} » ne possède pas de preuve UI '
                                    'visible, datant de moins de 24 h, sur cette page pour cette cible. Un schéma RPC ou une '
                                    'autre vue ne suffit pas. Observer après navigation.'})
    return warnings
