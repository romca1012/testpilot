"""Un document Markdown → un PDF lisible, imprimable, transmissible.

    python scripts/doc_en_pdf.py docs/ONBOARDING.md            → docs/ONBOARDING.pdf
    python scripts/doc_en_pdf.py docs/ONBOARDING.md /tmp/x.pdf

**Pourquoi un script et pas une conversion à la main.** Un PDF est une COPIE : le jour où le
document source change, la copie ment sans le dire. En faire une commande d'une ligne est le seul
moyen qu'elle soit régénérée au lieu d'être corrigée à la main — ou pire, oubliée.

**Pourquoi Chromium et pas un convertisseur dédié.** Playwright est déjà installé pour exécuter
les tests : aucune dépendance nouvelle, et le rendu est celui d'un navigateur — les tableaux, les
emojis et les accents sortent comme à l'écran. Le prix à payer est de tenir une feuille de style
d'impression, ci-dessous.
"""

from __future__ import annotations

import sys
from pathlib import Path

from markdown_it import MarkdownIt
from playwright.sync_api import sync_playwright

# ── Feuille de style d'IMPRESSION ────────────────────────────────────────────
# Fond blanc, texte noir : un thème sombre à l'écran devient illisible sur papier et vide une
# cartouche d'encre. Les règles `break-*` évitent les coupures qui rendent un document pénible :
# un titre seul en bas de page, une ligne de tableau séparée de son en-tête.
STYLE = """
@page { size: A4; margin: 18mm 16mm 20mm 16mm; }
* { box-sizing: border-box; }
body {
  font-family: "Segoe UI", -apple-system, system-ui, sans-serif;
  font-size: 10.2pt; line-height: 1.55; color: #14171f; background: #fff;
  margin: 0; -webkit-print-color-adjust: exact; print-color-adjust: exact;
}
h1, h2, h3, h4 { line-height: 1.25; break-after: avoid; page-break-after: avoid; }
h1 { font-size: 21pt; margin: 0 0 .6em; letter-spacing: -.4pt; }
h2 {
  font-size: 15pt; margin: 1.9em 0 .7em; padding-bottom: .28em;
  border-bottom: 1.5px solid #d3d8e0; break-before: auto;
}
h3 { font-size: 11.8pt; margin: 1.5em 0 .5em; color: #1f2733; }
h4 { font-size: 10.6pt; margin: 1.2em 0 .4em; }
p, ul, ol { margin: 0 0 .75em; }
li { margin-bottom: .3em; }
strong { color: #000; font-weight: 650; }
a { color: #1a4fa0; text-decoration: none; }
code {
  font-family: Consolas, "Cascadia Mono", monospace; font-size: .87em;
  background: #f2f4f7; border: 1px solid #e2e6ec; border-radius: 3px; padding: .07em .32em;
}
pre {
  background: #f7f8fa; border: 1px solid #e2e6ec; border-left: 3px solid #9aa6b8;
  border-radius: 4px; padding: .75em .9em; overflow: hidden;
  font-size: 8.6pt; line-height: 1.42; white-space: pre-wrap; word-wrap: break-word;
  break-inside: avoid; page-break-inside: avoid;
}
pre code { background: none; border: 0; padding: 0; font-size: inherit; }
blockquote {
  margin: 1em 0; padding: .7em 1em; background: #f6f8fb;
  border-left: 3px solid #7f8ea8; border-radius: 0 4px 4px 0;
}
blockquote p:last-child { margin-bottom: 0; }
table {
  width: 100%; border-collapse: collapse; margin: .9em 0; font-size: 9.2pt;
  break-inside: auto;
}
thead { display: table-header-group; }   /* l'en-tête se répète si le tableau change de page */
tr { break-inside: avoid; page-break-inside: avoid; }
th, td { border: 1px solid #d8dde5; padding: .45em .6em; text-align: left; vertical-align: top; }
th { background: #eef1f6; font-weight: 650; }
tbody tr:nth-child(even) { background: #fafbfd; }
hr { border: 0; border-top: 1px solid #dde2e9; margin: 2em 0; }
"""

# Pied de page : la pagination et la DATE d'impression. Sans la date, on ne sait pas si le PDF
# qu'on a sous les yeux est encore à jour — c'est le défaut de toute copie.
PIED = """
<div style="width:100%; font-size:7.5pt; color:#7b8494; padding:0 16mm;
            font-family:'Segoe UI',sans-serif; display:flex; justify-content:space-between;">
  <span>{titre}</span>
  <span>page <span class="pageNumber"></span> / <span class="totalPages"></span></span>
</div>
"""


def convertir(source: Path, sortie: Path) -> Path:
    md = MarkdownIt("commonmark").enable(["table", "strikethrough"])
    corps = md.render(source.read_text(encoding="utf-8"))
    titre = source.stem

    html = (
        f'<!doctype html><html lang="fr"><head><meta charset="utf-8">'
        f"<title>{titre}</title><style>{STYLE}</style></head><body>{corps}</body></html>"
    )

    with sync_playwright() as p:
        navigateur = p.chromium.launch()
        page = navigateur.new_page()
        # `set_content` plutôt qu'un fichier temporaire : rien à nettoyer, et aucun chemin
        # Windows à échapper dans une URL `file://`.
        page.set_content(html, wait_until="load")
        page.emulate_media(media="print")
        page.pdf(
            path=str(sortie),
            format="A4",
            print_background=True,
            display_header_footer=True,
            header_template="<div></div>",   # vide, mais requis : sinon Chromium en met un
            footer_template=PIED.format(titre=titre),
            margin={"top": "18mm", "bottom": "20mm", "left": "16mm", "right": "16mm"},
        )
        navigateur.close()
    return sortie


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    source = Path(sys.argv[1])
    if not source.exists():
        print(f"introuvable : {source}")
        return 1
    sortie = Path(sys.argv[2]) if len(sys.argv) > 2 else source.with_suffix(".pdf")
    convertir(source, sortie)
    print(f"{sortie}  ({sortie.stat().st_size // 1024} ko)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
