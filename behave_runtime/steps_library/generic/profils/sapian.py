"""Profil d'instance SAPIAN, volet PLAYWRIGHT (steps qui ne touchent que `context.page`) — lot 06
(D6, F6).

Sort du socle commun (`generic/_generic_steps.py`, `_base_helpers.py`) tout ce qui suppose CETTE
instance précise : le champ `name` du formulaire de ticket Helpdesk auto-généré par Odoo
(`force_name_field`), et le champ métier `agence` du portail Sapian (`select_first_agence`, orphelin
de tout step à ce jour — conservé plutôt que supprimé, au cas où un cas généré s'y référerait).

Copié par le runner sous `steps/_profil_generic.py` (nom CANONIQUE) SEULEMENT quand le projet
déclare `profil_instance` ET que ce fichier existe pour lui (`BehaveRunner._profil_files`) — jamais
inclus par défaut. Ses `@given`/`@when` sont alors auto-enregistrés par Behave, comme tout fichier de
`steps/`.
"""

from behave import given, when
from playwright.sync_api import TimeoutError as PlaywrightTimeout

from _base_helpers import ElementIntrouvableError


def force_name_field(page, value):
    """Set the hidden name field using the JS native setter to bypass Odoo auto-generation.

    ⚠️ **Délibérément NON migré vers `locate_field`** (étape 2.1 du plan de consolidation,
    2026-09-15 — revu, pas oublié). Le champ ciblé (`[name="name"]`) n'est pas un identifiant
    TECHNIQUE générique que l'agent a extrait de l'annuaire — c'est une connaissance Odoo câblée
    en dur ici (Odoo auto-génère ce champ, et cette fonction existe pour contourner CETTE
    particularité précise). Migrer vers `locate_field` ne rendrait rien plus générique : sur une
    application sans cette particularité, cette fonction ne serait de toute façon jamais appelée.

    ⚠️ **`[name="name"]` résout le `<div class="o_field_widget">` englobant, pas le contrôle
    lui-même** — même trou que celui corrigé dans `locate_field` (Sapian, 2026-09-23) : le web
    client Odoo (OWL) pose le nom technique sur le conteneur, jamais sur l'`<input>`/`<textarea>`
    interne. Sans descendre dedans, `querySelector('[name="name"]')` renvoie le conteneur, dont
    aucun prototype de setter natif ne s'applique (`HTMLInputElement`/`HTMLTextAreaElement`
    exigent le VRAI élément de formulaire). Le tag réel varie aussi selon la vue (mesuré :
    `<textarea>` sur le formulaire de ticket Helpdesk) — le setter choisi doit s'adapter.
    """
    safe = value.replace("\\", "\\\\").replace("'", "\\'")
    # Ancré sur l'élément : sans cette attente, un champ rendu tardivement → `querySelector` nul →
    # le setter ne faisait RIEN, en silence (le nom restait celui auto-généré par Odoo).
    page.locator('[name="name"]').wait_for(state="attached", timeout=8000)
    page.evaluate(f"""
        (() => {{
            const conteneur = document.querySelector('[name="name"]');
            const el = conteneur && conteneur.matches('input, textarea')
                ? conteneur
                : (conteneur ? conteneur.querySelector('input, textarea') : null);
            if (el) {{
                const proto = el.tagName.toLowerCase() === 'textarea'
                    ? window.HTMLTextAreaElement.prototype
                    : window.HTMLInputElement.prototype;
                const setter = Object.getOwnPropertyDescriptor(proto, 'value').set;
                setter.call(el, '{safe}');
                el.dispatchEvent(new Event('input', {{ bubbles: true }}));
            }}
        }})()
    """)


def select_first_agence(page):
    """Sélectionne la première agence disponible dans le champ métier `agence`.

    ⚠️ **Délibérément NON migré vers `locate_field`** (étape 2.1 du plan de consolidation,
    2026-09-15 — revu, pas oublié). `agence` est un champ MÉTIER précis du portail Sapian, pas un
    identifiant technique quelconque extrait de l'annuaire par l'agent — son nom technique
    (`name="agence"`) est connu et fixe par construction. Faire passer cette résolution par la
    cascade générique n'apporterait rien : une application sans ce champ n'appelle de toute façon
    jamais cette fonction.
    """
    select = page.locator("select[name='agence']")
    # Ancré sur l'élément (plus de `count()` instantané ni de sleep fixe).
    try:
        select.first.wait_for(state="attached", timeout=8000)
    except PlaywrightTimeout:
        raise ElementIntrouvableError(f"Champ 'agence' introuvable sur {page.url}")
    options = select.locator("option")
    for i in range(options.count()):
        val = options.nth(i).get_attribute("value")
        if val and val.strip():
            select.first.select_option(val)
            return
    raise ElementIntrouvableError(f"Aucune option disponible dans le champ 'agence' sur {page.url}")


@given('je force le nom du ticket à "{value}"')
@when('je force le nom du ticket à "{value}"')
def step_force_name(context, value):
    force_name_field(context.page, value)
