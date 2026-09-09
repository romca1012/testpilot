"""ÉTAPE 1 du chantier « graphe applicatif » — MESURER le domaine avant de décider quoi construire.

    PYTHONUTF8=1 python scripts/crawl_domaine.py [--max-pages N] [--json FICHIER]

**AUCUN appel LLM.** Crawl déterministe par Playwright : on lit l'application, on ne devine rien.
C'est exactement ce que ce chantier reproche à l'agent — le script ne peut pas se le permettre.

Répond à : *quelle est la taille réelle du domaine à couvrir ?* — la question que l'audit avait
posée sans y répondre, et dont dépend le choix (a) graphe complet / (b) graphe partiel + patterns /
(c) pas de graphe.

────────────────────────────────────────────────────────────────────────────────
MÉTHODE — ce qui est compté, ce qui ne l'est PAS, et pourquoi
────────────────────────────────────────────────────────────────────────────────

**Point d'entrée** : `playwright_login` (le helper partagé — le même que les tests), qui dépose sur
`/my/home`. On ajoute `/myservices` comme seconde racine : c'est le catalogue, et `0020` a mesuré
qu'il n'est **pas** atteignable depuis le dépôt de l'auth sans navigation explicite.

**PÉRIMÈTRE : le PORTAIL, pas le back-office Odoo.** Décision structurante, à assumer :
  • `/web/*`, `/odoo/*`, `/web#...` sont l'**interface d'administration** d'Odoo — des milliers de
    vues génériques, livrées par l'éditeur, que TestPilot ne teste pas. Le projet sous test
    s'appelle « Portail Sapian » : c'est le portail client qui est le produit.
  • Les compter gonflerait le domaine d'un ordre de grandeur **sans rapport avec ce qu'on teste**,
    et fausserait la décision (a)/(b)/(c) — on conclurait « domaine immense » à tort.
  • ⚠️ **Si un jour un cas de test vise le back-office, cette mesure est caduque** et il faut la
    refaire avec un autre périmètre. C'est dit ici pour que personne ne le découvre après coup.

**Exclus aussi** : `/web/session/logout` (tue la session du crawl), les assets statiques
(`/web/static`, `.css`, `.js`, images), les liens externes, les `mailto:`/`tel:`.

**Normalisation des routes** : `/formulaire/1` et `/formulaire/2` sont la **même** route
paramétrée → `/formulaire/{id}`. C'est LA mesure qui tranche entre (a) et (b) : si le domaine est
fait de quelques gabarits × N identifiants, il est « grand mais structuré en patterns répétitifs ».
Le préfixe de langue (`/en/…`, `/fr/…`) est retiré : Odoo l'ajoute par redirection.

**Ce qu'on compte pour un formulaire** : les champs porteurs d'un `name` (c'est ce que les steps
ciblent). Les `<select>` sont détaillés avec leurs options réelles — le cœur de `0019`.

**Transitions** : un lien/onglet/bouton qui mène à une AUTRE route normalisée. Les onglets qui ne
changent pas d'URL (`href="#..."`, cas de « Ordinateurs ») sont comptés à part : ils ne sont pas
des transitions de route, mais ils **changent l'état de la page** — et c'est précisément ce que
`0020` a montré qu'un test doit savoir.
"""

import argparse
import json
import re
import sys
import types
from collections import defaultdict
from pathlib import Path
from urllib.parse import urljoin, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "behave_runtime" / "steps_library"))

from playwright.sync_api import sync_playwright  # noqa: E402

import _base_helpers as H  # noqa: E402
from testpilot import config  # noqa: E402
from testpilot.generation import domain_model  # noqa: E402

RACINES = ["/my/home", "/myservices"]

# Back-office et assets : hors périmètre (voir la docstring — décision assumée).
# ⚠️ `/@/…` : artefact de l'ÉDITEUR de site Odoo (17+). Ce ne sont pas des routes du portail —
# elles plantent ou expirent systématiquement (mesuré : ~20 `Page crashed` au 1ᵉʳ crawl). Les
# compter gonflerait le domaine de doublons injouables.
# `/website/add/…` : idem, outillage d'édition.
# `nav_tabs_content_…` : une ANCRE (`href="#nav_tabs_content_…"`) qu'un `urljoin` transforme en
# faux chemin. C'est un onglet interne (`0020`), pas une route — compté à part.
_HORS_PERIMETRE = re.compile(
    r"^/(web|odoo)(/|$|#)|^/@/|^/website/add/|/web/static|/web/session/logout"
    r"|nav_tabs_content|/export(/|$)|\.(css|js|png|jpg|jpeg|svg|ico|woff2?)$",
    re.IGNORECASE)

# Exclusion GÉNÉRIQUE (connecteur `web`, audit multi-connecteurs 2026-09-08) : sans convention
# d'URL à connaître (pas de `/web`, `/odoo` — c'est spécifique à Odoo), on ne peut exclure QUE ce
# qui est universel — les assets statiques. Une application maison décidera de son propre
# périmètre plus tard si besoin (ex. un motif fourni au moment de la création du projet) ; ce
# premier jet ne devine rien de plus.
_HORS_PERIMETRE_GENERIQUE = re.compile(
    r"\.(css|js|png|jpg|jpeg|svg|ico|woff2?|pdf)$", re.IGNORECASE)
def normalise(path: str) -> str:
    """`/en/formulaire/12` → `/formulaire/{id}`. Le gabarit, pas l'instance.

    Délègue à `domain_model.normaliser_route` : le runtime apprend désormais des règles indexées
    sur la route, et les deux doivent produire EXACTEMENT la même clé.
    """
    return domain_model.normaliser_route(path)


def _inspecter_page(page):
    """Champs, options, liens, onglets — lu au DOM, en UN aller-retour.

    ⚠️ **Deux familles d'informations, deux usages** (enrichissement du 2026-07-21) :

    - **l'identité ACCESSIBLE** (`role`, `label`) — ce qu'un utilisateur voit. C'est ce que
      `getByRole`/`getByLabel` interrogent, et c'est **universel** : tout connecteur web en a une.
      Elle survit aux refontes de gabarit, là où un attribut `name` peut changer.
    - **le nom TECHNIQUE** (`name`) — indispensable pour VÉRIFIER l'état par RPC (il porte le
      champ du modèle Odoo). Propre au connecteur.

    Et les **CONTRAINTES** (`pattern`, `minlength`, `maxlength`, `min`, `max`, `step`) : sans
    elles, une valeur générée peut être refusée par le formulaire — et on diagnostiquerait à tort
    « l'application est cassée » alors que c'est la donnée du test qui l'est.
    """
    return page.evaluate("""() => {
        // Le libellé visible d'un champ : <label for=…>, label englobant, aria-label,
        // aria-labelledby, ou placeholder. Ordre = celui de la spec d'accessibilité.
        // ⚠️ Espaces NORMALISÉS : le HTML indenté rend un libellé suivi d'un retour à la ligne
        // et de vingt espaces. (Ne JAMAIS écrire de séquence d'échappement dans ce commentaire :
        // la chaîne est un littéral Python, qui la convertirait et couperait le commentaire JS.)
        // Un libellé non nettoyé ne correspondrait à aucun `getByLabel` et polluerait le prompt.
        // L'étoile des champs requis (« Montant HT * ») est retirée : elle n'appartient pas au nom.
        const propre = (t) => (t || '').replace(/\s+/g, ' ').replace(/\s*\*\s*$/, '').trim();
        const libelle = (el) => {
            if (el.getAttribute('aria-label')) return propre(el.getAttribute('aria-label'));
            const par = el.getAttribute('aria-labelledby');
            if (par) {
                const cible = document.getElementById(par);
                if (cible) return propre(cible.textContent);
            }
            if (el.id) {
                const lab = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
                if (lab) return propre(lab.textContent);
            }
            const englobant = el.closest('label');
            if (englobant) return propre(englobant.textContent);
            return propre(el.getAttribute('placeholder'));
        };
        // Le rôle ARIA effectif — explicite s'il est posé, sinon déduit du type d'élément.
        const role = (el) => {
            if (el.getAttribute('role')) return el.getAttribute('role');
            const tag = el.tagName.toLowerCase();
            if (tag === 'select') return el.multiple ? 'listbox' : 'combobox';
            if (tag === 'textarea') return 'textbox';
            const t = (el.type || '').toLowerCase();
            return ({checkbox: 'checkbox', radio: 'radio', file: 'button', number: 'spinbutton',
                     email: 'textbox', tel: 'textbox', url: 'textbox', search: 'searchbox',
                     password: 'textbox', date: 'textbox', text: 'textbox'})[t] || 'textbox';
        };

        const champs = [];
        document.querySelectorAll('input[name], select[name], textarea[name]').forEach(el => {
            const tag = el.tagName.toLowerCase();
            const entry = {name: el.getAttribute('name'), tag,
                           type: (el.type || '').toLowerCase(),
                           required: el.required === true,
                           visible: !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length),
                           // ── Identité ACCESSIBLE (universelle, résiste aux refontes) ──
                           role: role(el),
                           label: libelle(el).slice(0, 120)};
            // ── CONTRAINTES de saisie : ce qui rend une valeur ACCEPTABLE ──
            const c = {};
            if (el.getAttribute('pattern')) c.pattern = el.getAttribute('pattern');
            if (el.getAttribute('minlength')) c.minlength = +el.getAttribute('minlength');
            if (el.getAttribute('maxlength')) c.maxlength = +el.getAttribute('maxlength');
            if (el.getAttribute('min') !== null) c.min = el.getAttribute('min');
            if (el.getAttribute('max') !== null) c.max = el.getAttribute('max');
            if (el.getAttribute('step')) c.step = el.getAttribute('step');
            if (el.getAttribute('accept')) c.accept = el.getAttribute('accept');
            // ⚠️ `title` porte la REGLE EN FRANÇAIS, et c'est souvent le SEUL endroit ou elle
            // existe. Mesure du 2026-07-22 : `numero_facture1` n'a AUCUN `pattern`, mais son
            // title dit « Veuillez saisir des groupes de sept chiffres. » L'agent y ecrivait
            // « FAC-TEST-001 » ; le champ filtre les non-chiffres, il reste « 001 », le
            // navigateur refuse, et le verdict accusait l'application. La regle etait ecrite
            // dans la page, lisible, en clair — et le crawl la jetait.
            if (el.getAttribute('title')) c.regle_lisible = el.getAttribute('title').slice(0, 200);
            if (Object.keys(c).length) entry.contraintes = c;
            if (tag === 'select') {
                entry.options = Array.from(el.options).map(o => [o.value, (o.text||'').trim()]);
            }
            champs.push(entry);
        });
        // ── Éléments ACTIONNABLES (boutons, soumissions) — par leur identité accessible ──
        // Sans eux, l'agent devait deviner le libellé du bouton d'envoi. Mesuré : « soumission
        // absente » était l'un des deux motifs d'alerte les plus fréquents au smoke-check.
        const actions = [];
        document.querySelectorAll(
            'button, input[type=submit], input[type=button], a[role=button], [role=button]'
        ).forEach(el => {
            const nom = propre(el.getAttribute('aria-label') || el.value || el.textContent);
            if (!nom) return;
            actions.push({role: 'button', label: nom.slice(0, 80),
                          soumet: (el.type || '').toLowerCase() === 'submit'
                                  || el.closest('form') !== null,
                          visible: !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length)});
        });
        const liens = [];
        document.querySelectorAll('a[href]').forEach(a => {
            liens.push({href: a.getAttribute('href'), text: (a.textContent||'').trim().slice(0,40),
                        role: a.getAttribute('role')});
        });
        const formulaires = Array.from(document.querySelectorAll('form')).map(f => ({
            action: f.getAttribute('action') || '', method: (f.method||'get').toLowerCase(),
            champs: f.querySelectorAll('input[name], select[name], textarea[name]').length,
        }));
        return {champs, actions, liens, formulaires, titre: document.title};
    }""")


def crawler(ctx, nav, base_url, max_pages, *, racines=None, hors_perimetre=None, relogin=None):
    """BFS sur les routes NORMALISÉES. `ctx.page` peut être recréée : le navigateur crashe.

    ⚠️ **Un crawl n'a pas le droit de mourir en route** : il rendrait une mesure tronquée qui
    ressemble à une mesure complète — le motif que ce projet traque (« l'absence de signal prise
    pour un signal positif »). Mesuré au 1ᵉʳ passage : le navigateur meurt (`Page crashed`) après
    ~35 pages. On le relance et on continue, plutôt que de rendre 34 routes en les croyant toutes.

    `racines`/`hors_perimetre`/`relogin` (2026-09-08, multi-connecteurs) : `None` = défauts
    Odoo (`RACINES`, `_HORS_PERIMETRE`, `H.playwright_login`) — comportement STRICTEMENT
    inchangé pour l'appelant historique. `exploration_service.py` les fournit pour un connecteur
    `web` (racine `/`, exclusion `_HORS_PERIMETRE_GENERIQUE`, connexion générique).
    """
    racines = racines if racines is not None else RACINES
    hors_perimetre = hors_perimetre if hors_perimetre is not None else _HORS_PERIMETRE
    relogin = relogin if relogin is not None else H.playwright_login

    pages = {}
    transitions = defaultdict(set)
    onglets_internes = defaultdict(set)   # href="#..." : changent l'ÉTAT, pas la route
    a_voir = list(racines)
    vus_bruts = set()
    crashes = 0

    while a_voir and len(pages) < max_pages:
        chemin = a_voir.pop(0)
        cle = normalise(chemin)
        if cle in pages or chemin in vus_bruts:
            continue
        vus_bruts.add(chemin)
        try:
            page = ctx.page
            page.goto(urljoin(base_url, chemin), wait_until="networkidle", timeout=20000)
        except Exception as exc:
            premiere = str(exc).splitlines()[0][:70]
            print(f"    [!] {chemin} : {premiere}")
            if "crash" in premiere.lower() or "closed" in premiere.lower():
                # Le navigateur est mort : on le relance et on RE-AUTHENTIFIE, sinon toutes les
                # pages suivantes rendraient la page de login — un domaine mesuré à zéro champ.
                crashes += 1
                print(f"    [~] navigateur relancé ({crashes}) et ré-authentifié")
                try:
                    ctx.page = nav.new_page()
                    relogin(ctx)
                except Exception:
                    print("    [!!] relance impossible — mesure INCOMPLÈTE, à ne pas publier")
                    break
            continue

        # L'URL réelle après redirection : c'est elle qui fait foi.
        page = ctx.page
        reelle = normalise(page.url)
        if reelle in pages:
            continue
        infos = _inspecter_page(page)
        # ⚠️ On garde l'URL CONCRÈTE qui a réellement fonctionné (2026-07-21). La route est
        # normalisée (`/demande_avoir/{id}`) pour dédupliquer, mais un test doit naviguer vers une
        # URL RÉELLE. Sans cet exemple, l'agent INVENTE un identifiant : mesuré, il a écrit
        # `/demande_avoir/29789` — une page qui ne rend pas le formulaire, d'où un `TimeoutError`
        # sur un champ pourtant visible. Le crawl connaissait l'URL et la jetait.
        # ⚠️ Le préfixe de LANGUE est retiré (`/en/achat_siege/113` → `/achat_siege/113`).
        # Le crawl arrive souvent sur la version anglaise ; y envoyer un test ferait échouer
        # tous les steps à libellé français (« Envoyer » devient « Send »). On garde l'identifiant
        # concret — la seule chose qui manquait — sans imposer une locale.
        infos["url_exemple"] = domain_model.retirer_prefixe_langue(
            urlparse(page.url).path or reelle) or reelle
        pages[reelle] = infos
        print(f"  {len(pages):>3}. {reelle:<42} {len(infos['champs']):>2} champs  "
              f"{len(infos['formulaires'])} form")

        for lien in infos["liens"]:
            href = (lien["href"] or "").strip()
            if not href or href.startswith(("mailto:", "tel:", "javascript:")):
                continue
            if href.startswith("#"):
                onglets_internes[reelle].add(lien["text"] or href)
                continue
            cible = urlparse(urljoin(page.url, href))
            if cible.netloc and cible.netloc != urlparse(base_url).netloc:
                continue                      # hors du site
            if hors_perimetre.search(cible.path):
                continue                      # back-office / assets : hors périmètre
            cible_norm = normalise(cible.path)
            if cible_norm != reelle:
                transitions[reelle].add(cible_norm)
            if cible_norm not in pages:
                a_voir.append(cible.path)

    return pages, transitions, onglets_internes


def _couverture_des_cas(pages):
    """Ce que les 3 cas EXISTANTS sollicitent réellement, comparé au domaine crawlé.

    On lit les `.feature`/steps en base (aucun LLM) et on cherche les noms de champs du crawl
    qui y apparaissent. Volontairement GROSSIER : un nom de champ cité n'est pas forcément
    exercé (il peut être dans un commentaire). On mesure une **borne haute** de la couverture —
    si même la borne haute est faible, la conclusion tient a fortiori.
    """
    import sqlite3
    conn = sqlite3.connect(f"file:{config.DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    textes = {}
    for r in conn.execute(
            "SELECT c.id, c.title, v.feature_content, v.steps_content FROM test_case c"
            " JOIN test_case_version v ON v.id = c.current_version_id"):
        textes[r["id"]] = ((r["feature_content"] or "") + "\n" + (r["steps_content"] or ""),
                           r["title"])
    conn.close()

    tous_champs = {(p, ch["name"]) for p, i in pages.items() for ch in i["champs"]}
    tous_selects = {(p, ch["name"]) for p, i in pages.items() for ch in i["champs"]
                    if ch["tag"] == "select"}
    corpus = "\n".join(t for t, _ in textes.values())

    champs_cites = {c for c in tous_champs if re.search(rf'\b{re.escape(c[1])}\b', corpus)}
    selects_cites = {c for c in tous_selects if re.search(rf'\b{re.escape(c[1])}\b', corpus)}
    routes_citees = {p for p in pages if p != "/" and
                     re.search(re.escape(p.replace("/{id}", "")), corpus)}
    return {
        "cas": {i: t for i, (_, t) in textes.items()},
        "champs": (len(champs_cites), len(tous_champs)),
        "selects": (len(selects_cites), len(tous_selects)),
        "routes": (len(routes_citees), len(pages)),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-pages", type=int, default=60)
    ap.add_argument("--json", default="")
    args = ap.parse_args()

    print("=" * 78)
    print("ÉTAPE 1 — MESURE DU DOMAINE (crawl déterministe, AUCUN LLM)")
    print("=" * 78)
    print(f"  cible     : {config.ODOO_URL}  (projet « Portail Sapian »)")
    print(f"  périmètre : le PORTAIL — le back-office Odoo (/web, /odoo) est EXCLU (cf. docstring)")
    print(f"  racines   : {', '.join(RACINES)}\n")

    with sync_playwright() as p:
        nav = p.chromium.launch()
        ctx = types.SimpleNamespace(
            page=nav.new_page(), odoo_url=config.ODOO_URL, odoo_db=config.ODOO_DB,
            odoo_user=config.ODOO_USER, odoo_password=config.ODOO_PASSWORD)
        H.playwright_login(ctx)
        print(f"  dépôt après authentification : {normalise(ctx.page.url)}\n")
        pages, transitions, onglets = crawler(ctx, nav, config.ODOO_URL, args.max_pages)
        try:
            nav.close()
        except Exception:
            pass          # le navigateur a pu mourir : la mesure, elle, est faite

    # ── Les chiffres ──────────────────────────────────────────────────────────
    formulaires = {p: i for p, i in pages.items() if i["formulaires"]}
    selects = [(p, ch) for p, i in pages.items() for ch in i["champs"] if ch["tag"] == "select"]
    selects_finis = [(p, ch) for p, ch in selects if ch.get("options")]
    n_champs = sum(len(i["champs"]) for i in pages.values())
    n_transitions = sum(len(v) for v in transitions.values())
    n_onglets = sum(len(v) for v in onglets.values())

    print("\n" + "=" * 78)
    print("LE CHIFFRE")
    print("=" * 78)
    print(f"  Routes distinctes (normalisées)        : {len(pages)}")
    print(f"  Pages portant au moins un formulaire   : {len(formulaires)}")
    print(f"  Champs nommés, tous formulaires        : {n_champs}")
    print(f"  <select> (dropdown)                    : {len(selects)}")
    print(f"    dont à options FINIES et énumérables : {len(selects_finis)}")
    print(f"  Transitions de route distinctes        : {n_transitions}")
    print(f"  Onglets internes (changent l'ÉTAT, pas la route) : {n_onglets}")

    print("\n-- Détail des formulaires " + "-" * 51)
    for chemin, infos in sorted(formulaires.items()):
        req = sum(1 for c in infos["champs"] if c["required"])
        sel = sum(1 for c in infos["champs"] if c["tag"] == "select")
        print(f"  {chemin:<40} {len(infos['champs']):>2} champs "
              f"({req} requis, {sel} select)")

    if selects_finis:
        print("\n-- Les <select> et leurs options RÉELLES (le cœur de 0019) " + "-" * 18)
        for chemin, ch in selects_finis:
            opts = ", ".join(v for v, _ in ch["options"][:5])
            suite = "…" if len(ch["options"]) > 5 else ""
            print(f"  {chemin:<28} {ch['name']:<22} {len(ch['options']):>2} options : {opts}{suite}")

    print("\n-- Transitions " + "-" * 62)
    for src in sorted(transitions):
        for dst in sorted(transitions[src]):
            print(f"  {src:<40} → {dst}")
    if onglets:
        print("\n-- Onglets internes (href='#…') — 0020 : ils changent l'état, PAS la route ---")
        for src in sorted(onglets):
            print(f"  {src:<40} : {', '.join(sorted(onglets[src])[:6])}")

    # ── Couverture des cas existants ──────────────────────────────────────────
    print("\n" + "=" * 78)
    print("COUVERTURE DES 3 CAS EXISTANTS (borne HAUTE — voir la docstring)")
    print("=" * 78)
    cov = _couverture_des_cas(pages)
    for i, titre in cov["cas"].items():
        print(f"  cas {i} : {titre}")
    print()
    for libelle, (cites, total) in (("Champs", cov["champs"]), ("Select", cov["selects"]),
                                    ("Routes", cov["routes"])):
        pct = (100 * cites / total) if total else 0
        print(f"  {libelle:<8} sollicités : {cites:>3} / {total:<3}  = {pct:5.1f} %")

    if args.json:
        Path(args.json).write_text(json.dumps({
            "pages": pages, "transitions": {k: sorted(v) for k, v in transitions.items()},
            "onglets_internes": {k: sorted(v) for k, v in onglets.items()},
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n  → données brutes : {args.json}")


if __name__ == "__main__":
    main()
