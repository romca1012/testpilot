// Verrouillage du défilement de page pendant qu'une superposition (modale, palette de
// commandes…) est ouverte — trouvé manquant sur les 3 fenêtres modales de l'app en comparant à
// une référence externe accessible (2026-08-13) : sans lui, la page DERRIÈRE l'overlay défile
// encore à la molette, ce qui désynchronise ce qu'on voit de ce qu'on peut atteindre au clavier.
//
// Un COMPTEUR, pas un booléen : si un jour une modale s'ouvre par-dessus une autre, le scroll ne
// doit revenir qu'à la fermeture de la DERNIÈRE — un booléen partagé le redonnerait trop tôt.
let verrous = 0
let etatPrecedent: { overflow: string; paddingRight: string } | null = null

export function verrouillerScroll() {
  verrous += 1
  if (verrous > 1) return

  const body = document.body
  // Compense la largeur de la barre de défilement qui disparaît : sans ça, le contenu « saute »
  // de quelques pixels à l'ouverture (largeur de page qui change), un artefact visuel distrayant.
  const largeurBarre = window.innerWidth - document.documentElement.clientWidth
  etatPrecedent = { overflow: body.style.overflow, paddingRight: body.style.paddingRight }
  body.style.overflow = 'hidden'
  if (largeurBarre > 0) {
    const actuel = Number.parseFloat(window.getComputedStyle(body).paddingRight) || 0
    body.style.paddingRight = `${actuel + largeurBarre}px`
  }
}

export function deverrouillerScroll() {
  verrous = Math.max(0, verrous - 1)
  if (verrous > 0 || !etatPrecedent) return
  document.body.style.overflow = etatPrecedent.overflow
  document.body.style.paddingRight = etatPrecedent.paddingRight
  etatPrecedent = null
}
