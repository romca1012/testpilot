"""Le contexte navigateur FIGÉ d'un projet : langue, fuseau horaire, taille de fenêtre (lot 07c, C3).

Pourquoi figer. Un navigateur lancé sans réglage prend la langue et le fuseau de la MACHINE qui le lance : la même campagne
n'affichait pas les mêmes dates, les mêmes libellés ni la même mise en page sur un poste de développement, sur le serveur de
staging ou en CI. Un libellé traduit différemment (« Sondages » / « Surveys », mesuré sur Sapian le 2026-09-22), une date
affichée dans un autre fuseau ou un bouton replié sous un viewport étroit sont des différences que le verdict prendrait pour un
défaut — ou, pire, qui masqueraient un vrai. Le contexte est donc **décidé par le projet** (défauts `fr-FR`, `Europe/Paris`,
1440×900), passé au sous-processus par `runtime_env`, et **le même** pour l'exploration (connecteurs) et l'exécution
(`behave_runtime/environment.py`) : l'agent doit voir ce que le test verra.

Module PUR : aucune I/O, aucun réseau, aucun LLM.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

logger = logging.getLogger(__name__)

DEFAUT_LOCALE = "fr-FR"
DEFAUT_TIMEZONE = "Europe/Paris"
DEFAUT_LARGEUR = 1440
DEFAUT_HAUTEUR = 900

# Bornes du viewport : en deçà, la plupart des applications passent en affichage mobile (un autre test) ; au-delà, une capture
# et une trace deviennent énormes sans rien apporter.
LARGEUR_MIN, LARGEUR_MAX = 320, 3840
HAUTEUR_MIN, HAUTEUR_MAX = 320, 2160

# Noms des variables d'environnement du sous-processus. DUPLIQUÉS dans `behave_runtime/environment.py` (le harnais ne dépend pas
# du paquet applicatif) — même raison et même test d'accord que les sidecars (`tests/test_contexte_navigateur.py`).
ENV_LOCALE = "TESTPILOT_BROWSER_LOCALE"
ENV_TIMEZONE = "TESTPILOT_BROWSER_TIMEZONE"
ENV_VIEWPORT = "TESTPILOT_BROWSER_VIEWPORT"

# `fr`, `fr-FR`, `en-US`, `zh-Hant-TW` : la forme BCP 47 usuelle, sans en valider le fond (Playwright/Chromium le fait).
_LOCALE_RE = re.compile(r"^[A-Za-z]{2,3}(-[A-Za-z0-9]{2,8}){0,2}$")
_VIEWPORT_RE = re.compile(r"^\s*(\d{2,5})\s*[xX×]\s*(\d{2,5})\s*$")


@dataclass(frozen=True)
class ContexteNavigateur:
    locale: str = DEFAUT_LOCALE
    timezone_id: str = DEFAUT_TIMEZONE
    largeur: int = DEFAUT_LARGEUR
    hauteur: int = DEFAUT_HAUTEUR

    @property
    def viewport(self) -> str:
        return f"{self.largeur}x{self.hauteur}"

    def kwargs(self) -> dict:
        """Les arguments de `browser.new_context(...)` de Playwright."""
        return {"locale": self.locale, "timezone_id": self.timezone_id,
                "viewport": {"width": self.largeur, "height": self.hauteur}}

    def env(self) -> dict[str, str]:
        """Les variables d'environnement transmises au sous-processus Behave."""
        return {ENV_LOCALE: self.locale, ENV_TIMEZONE: self.timezone_id, ENV_VIEWPORT: self.viewport}


def _lire_viewport(texte: str) -> tuple[int, int] | None:
    m = _VIEWPORT_RE.match(texte or "")
    return (int(m.group(1)), int(m.group(2))) if m else None


def erreurs(locale: str = "", timezone_id: str = "", viewport: str = "") -> list[str]:
    """Les défauts de forme d'un réglage, en français clair — vide = valide. Une chaîne VIDE est valide : elle veut dire « le défaut »."""
    problemes: list[str] = []
    if locale and not _LOCALE_RE.match(locale.strip()):
        problemes.append(f"langue « {locale} » invalide (attendu : fr-FR, en-US…)")
    if timezone_id:
        try:
            ZoneInfo(timezone_id.strip())
        except (ZoneInfoNotFoundError, ValueError, OSError):
            problemes.append(f"fuseau horaire « {timezone_id} » inconnu (attendu : Europe/Paris, America/New_York…)")
    if viewport:
        dims = _lire_viewport(viewport)
        if dims is None:
            problemes.append(f"taille de fenêtre « {viewport} » invalide (attendu : 1440x900)")
        elif not (LARGEUR_MIN <= dims[0] <= LARGEUR_MAX and HAUTEUR_MIN <= dims[1] <= HAUTEUR_MAX):
            problemes.append(f"taille de fenêtre {dims[0]}x{dims[1]} hors bornes "
                             f"({LARGEUR_MIN}-{LARGEUR_MAX} x {HAUTEUR_MIN}-{HAUTEUR_MAX})")
    return problemes


def resoudre(locale: str = "", timezone_id: str = "", viewport: str = "") -> ContexteNavigateur:
    """Un contexte complet : chaque champ vide OU invalide retombe sur son défaut.

    Une valeur invalide ne devrait jamais arriver jusqu'ici (l'API la refuse à la saisie) ; si elle arrive — base éditée à la main —
    on retombe sur le défaut EN LE DISANT, plutôt que de planter une campagne entière pour une faute de frappe.
    """
    locale, timezone_id, viewport = (locale or "").strip(), (timezone_id or "").strip(), (viewport or "").strip()
    for probleme in erreurs(locale, timezone_id, viewport):
        logger.warning("[contexte navigateur] %s — le défaut est utilisé pour ce champ", probleme)
    ok_locale = locale if locale and not erreurs(locale=locale) else DEFAUT_LOCALE
    ok_tz = timezone_id if timezone_id and not erreurs(timezone_id=timezone_id) else DEFAUT_TIMEZONE
    dims = _lire_viewport(viewport) if viewport and not erreurs(viewport=viewport) else None
    largeur, hauteur = dims if dims else (DEFAUT_LARGEUR, DEFAUT_HAUTEUR)
    return ContexteNavigateur(ok_locale, ok_tz, largeur, hauteur)


def depuis_projet(project: dict | None) -> ContexteNavigateur:
    """Le contexte d'un PROJET (colonnes `browser_locale`, `browser_timezone`, `browser_viewport` ; vide = défaut)."""
    p = project or {}
    return resoudre(p.get("browser_locale") or "", p.get("browser_timezone") or "", p.get("browser_viewport") or "")


def depuis_env(environ) -> ContexteNavigateur:
    """Le contexte lu dans l'environnement du sous-processus (absent = défaut)."""
    return resoudre(environ.get(ENV_LOCALE, ""), environ.get(ENV_TIMEZONE, ""), environ.get(ENV_VIEWPORT, ""))
