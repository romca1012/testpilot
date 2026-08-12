<script setup lang="ts">
// Réglages d'INSTANCE — ils valent pour toute l'installation, pas pour un projet (2026-08-04).
//
// ⚠️ **La PROVENANCE de chaque valeur est affichée**, et ce n'est pas un détail d'esthétique :
// la base l'emporte sur la variable d'environnement, qui l'emporte sur le défaut du code. Un
// exploitant qui a posé `TESTPILOT_SERVICE_ACCOUNT` et qui voit autre chose doit comprendre
// pourquoi en un coup d'œil — sinon il cherche une heure, ou pire, conclut que ça ne marche pas.
import { computed, onMounted, ref } from 'vue'
import { api, type SettingOut } from '../lib/api'
import { useSession } from '../lib/useSession'
import Button from '../components/ui/Button.vue'

const { session } = useSession()
// ⚠️ Indicatif seulement — le SERVEUR est la seule vraie garde (403 sinon, `routes/settings.py`).
// Ça évite juste à un Testeur/Dev de remplir un champ qui serait de toute façon refusé.
const estAdmin = computed(() => session.value?.role === 'admin')

const reglages = ref<SettingOut[]>([])
const brouillon = ref<Record<string, string>>({})
const loading = ref(true)
const enregistrement = ref('')
const erreur = ref('')
const succes = ref('')

const PROVENANCE: Record<string, { label: string; hint: string }> = {
  db: { label: 'réglé ici', hint: 'Valeur enregistrée depuis cet écran. Elle a la priorité sur la variable d\'environnement.' },
  env: { label: 'variable d\'environnement', hint: 'Valeur fournie par la configuration du serveur (TESTPILOT_*). Enregistrer ici la remplacera.' },
  default: { label: 'défaut', hint: 'Personne n\'a rien réglé : c\'est la valeur d\'usine.' },
}

// ⚠️ Le TITRE de chaque section était codé en dur (« Compte de service ») jusqu'au 2026-08-11 —
// un 2ᵉ réglage (les références cliquables) se serait affiché sous ce même titre, illisible.
// `service_account_name` a lui-même disparu de l'écran le 2026-08-12 (demande du porteur : ça
// n'a plus à être un réglage modifiable) — la table ne garde donc plus qu'une seule entrée, mais
// la structure reste prête pour le prochain réglage générique.
const TITRES: Record<string, string> = {
  reference_url_template: 'Références cliquables',
}

// ── Notifications par email (2026-08-12) ──────────────────────────────────────
// Écran DÉDIÉ plutôt que la boucle générique ci-dessus : 7 champs SMTP alignés en une ligne par
// réglage recréerait exactement le problème signalé par le porteur (« onglet réglages mal
// utilisé »). Ces clés sont donc RETIRÉES de la liste générique (`reglagesGeneriques`).
const CLES_SMTP = new Set([
  'notifications_enabled', 'smtp_host', 'smtp_port', 'smtp_username', 'smtp_password',
  'smtp_from', 'smtp_use_tls',
])
const reglagesGeneriques = computed(() => reglages.value.filter((r) => !CLES_SMTP.has(r.key)))

const smtpHote = ref('')
const smtpPort = ref('587')
const smtpUtilisateur = ref('')
// ⚠️ JAMAIS préremplie avec la valeur reçue (un masque fixe, jamais le vrai secret) — vide =
// « je ne change pas le mot de passe existant », exactement comme l'explique le texte d'aide.
const smtpMotDePasse = ref('')
const smtpMotDePasseDefini = ref(false)
const smtpExpediteur = ref('')
const smtpTls = ref(true)
const notificationsActivees = ref(false)
const smtpEnregistrement = ref(false)
const smtpErreur = ref('')
const smtpSucces = ref('')
const smtpTestDestinataire = ref('')
const smtpTestEnCours = ref(false)
const smtpTestResultat = ref('')

function chargerBrouillonSmtp() {
  const parCle = Object.fromEntries(reglages.value.map((r) => [r.key, r]))
  smtpHote.value = parCle['smtp_host']?.value || ''
  smtpPort.value = parCle['smtp_port']?.value || '587'
  smtpUtilisateur.value = parCle['smtp_username']?.value || ''
  smtpMotDePasseDefini.value = !!parCle['smtp_password']?.value
  smtpExpediteur.value = parCle['smtp_from']?.value || ''
  smtpTls.value = (parCle['smtp_use_tls']?.value || '1') === '1'
  notificationsActivees.value = (parCle['notifications_enabled']?.value || '') === '1'
}

async function charger() {
  loading.value = true
  erreur.value = ''
  try {
    reglages.value = await api.listSettings()
    brouillon.value = Object.fromEntries(reglages.value.map((r) => [r.key, r.value]))
    chargerBrouillonSmtp()
  } catch (e: any) {
    erreur.value = e?.message || 'Impossible de charger les réglages.'
  } finally {
    loading.value = false
  }
}
onMounted(charger)

async function enregistrer(cle: string) {
  enregistrement.value = cle
  erreur.value = ''
  succes.value = ''
  try {
    const maj = await api.setSetting(cle, brouillon.value[cle] ?? '')
    reglages.value = reglages.value.map((r) => (r.key === cle ? maj : r))
    // On réaligne le brouillon sur ce que le SERVEUR a retenu : effacer un réglage rend la main
    // à l'environnement, et le champ doit alors montrer la valeur qui s'applique vraiment — pas
    // la chaîne vide que l'utilisateur vient de saisir.
    brouillon.value[cle] = maj.value
    succes.value = 'Réglage enregistré.'
  } catch (e: any) {
    erreur.value = e?.message || 'Enregistrement impossible.'
  } finally {
    enregistrement.value = ''
  }
}

async function enregistrerSmtp() {
  smtpEnregistrement.value = true
  smtpErreur.value = ''
  smtpSucces.value = ''
  try {
    await Promise.all([
      api.setSetting('smtp_host', smtpHote.value.trim()),
      api.setSetting('smtp_port', smtpPort.value.trim() || '587'),
      api.setSetting('smtp_username', smtpUtilisateur.value.trim()),
      api.setSetting('smtp_from', smtpExpediteur.value.trim()),
      // ⚠️ « 0 » explicite, jamais une chaîne vide : une chaîne vide EFFACERAIT le réglage
      // (sémantique générale de `SettingRepo.ecrire`) et ferait retomber sur le défaut de
      // `config.py` — qui vaut « 1 » pour `smtp_use_tls`. Décocher se remettrait alors
      // silencieusement à activé, l'exact défaut que ce produit s'interdit ailleurs.
      api.setSetting('smtp_use_tls', smtpTls.value ? '1' : '0'),
      api.setSetting('notifications_enabled', notificationsActivees.value ? '1' : '0'),
      // Vide = « je ne change pas le mot de passe » : on ne l'envoie que si l'Admin a tapé
      // quelque chose — sinon l'API l'effacerait (même sémantique que tous les autres réglages).
      ...(smtpMotDePasse.value ? [api.setSetting('smtp_password', smtpMotDePasse.value)] : []),
    ])
    reglages.value = await api.listSettings()
    chargerBrouillonSmtp()
    smtpMotDePasse.value = ''
    smtpSucces.value = 'Notifications enregistrées.'
  } catch (e: any) {
    smtpErreur.value = e?.message || 'Enregistrement impossible.'
  } finally {
    smtpEnregistrement.value = false
  }
}

async function effacerMotDePasseSmtp() {
  if (!confirm('Effacer le mot de passe SMTP enregistré ?')) return
  smtpErreur.value = ''
  try {
    await api.setSetting('smtp_password', '')
    reglages.value = await api.listSettings()
    chargerBrouillonSmtp()
    smtpSucces.value = 'Mot de passe SMTP effacé.'
  } catch (e: any) {
    smtpErreur.value = e?.message || 'Effacement impossible.'
  }
}

async function envoyerTestSmtp() {
  if (!smtpTestDestinataire.value.trim()) return
  smtpTestEnCours.value = true
  smtpTestResultat.value = ''
  try {
    const r = await api.testSmtp(smtpTestDestinataire.value.trim())
    smtpTestResultat.value = r.succes
      ? 'Email envoyé — vérifiez la boîte de réception.'
      : `Échec : ${r.erreur}`
  } catch (e: any) {
    smtpTestResultat.value = `Échec : ${e?.message || 'erreur inconnue'}`
  } finally {
    smtpTestEnCours.value = false
  }
}
</script>

<template>
  <div class="mx-auto max-w-4xl p-6 md:p-8">
    <!-- ⚠️ Cet écran est HORS du shell de projet (les réglages ne dépendent d'aucun projet) : il
         doit donc porter lui-même son chemin de retour. Sans lui, on y arrive et on y reste. -->
    <RouterLink to="/" class="text-sm text-primary hover:underline">← Retour</RouterLink>
    <h1 class="mt-3 text-xl font-semibold">Réglages de l'instance</h1>
    <p class="mt-1 text-sm text-muted-foreground">
      Ces réglages valent pour toute l'installation, quels que soient les projets.
    </p>

    <p v-if="erreur" class="mt-4 rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">
      {{ erreur }}
    </p>
    <p v-if="succes" class="mt-4 rounded-md border border-success/30 bg-success/10 px-3 py-2 text-sm text-success">
      {{ succes }}
    </p>

    <p v-if="loading" class="mt-6 text-sm text-muted-foreground">Chargement…</p>

    <section v-for="r in reglagesGeneriques" :key="r.key"
             class="mt-6 rounded-lg border border-border bg-surface-raised p-4">
      <div class="flex items-center gap-2">
        <h2 class="font-medium">{{ TITRES[r.key] || r.key }}</h2>
        <span class="rounded-full border border-border px-2 py-0.5 text-xs text-muted-foreground"
              :title="PROVENANCE[r.source]?.hint">{{ PROVENANCE[r.source]?.label || r.source }}</span>
      </div>
      <p class="mt-1 text-sm text-muted-foreground">{{ r.description }}</p>

      <div class="mt-3 flex gap-2">
        <input v-model="brouillon[r.key]" :placeholder="r.value"
               :disabled="r.admin_only && !estAdmin"
               class="flex-1 rounded-md bg-surface border border-border px-3 py-2 focus:border-primary outline-none disabled:opacity-50 disabled:cursor-not-allowed" />
        <Button variant="primary" :disabled="enregistrement === r.key || (r.admin_only && !estAdmin)" @click="enregistrer(r.key)">
          {{ enregistrement === r.key ? 'Enregistrement…' : 'Enregistrer' }}
        </Button>
      </div>
      <!-- Écriture réservée à l'Admin (2026-08-11) — un gabarit mal réglé change ce que voit
           TOUTE l'équipe, sur tous les projets. Indicatif : le 403 serveur fait foi. -->
      <p v-if="r.admin_only && !estAdmin" class="mt-2 text-xs text-warning">
        Réservé au rôle Admin.
      </p>
      <p class="mt-2 text-xs text-subtle-foreground">
        Laisser le champ VIDE efface le réglage : la variable d'environnement du serveur, puis la
        valeur par défaut, reprennent la main.
      </p>
    </section>

    <!-- ════════ Notifications par email (2026-08-12) — écran dédié, pas la boucle générique ════════ -->
    <section v-if="!loading" class="mt-6 rounded-lg border border-border bg-surface-raised p-4">
      <h2 class="font-medium">Notifications par email</h2>
      <p class="mt-1 text-sm text-muted-foreground">
        Prévient l'auteur d'une campagne ou d'une automatisation quand elle se termine — lui
        seul, pas toute l'équipe. Désactivé par défaut.
      </p>
      <p v-if="smtpErreur" class="mt-3 rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">
        {{ smtpErreur }}
      </p>
      <p v-if="smtpSucces" class="mt-3 rounded-md border border-success/30 bg-success/10 px-3 py-2 text-sm text-success">
        {{ smtpSucces }}
      </p>

      <label class="mt-3 flex items-center gap-2 text-sm">
        <input v-model="notificationsActivees" type="checkbox" :disabled="!estAdmin" />
        Notifications activées
      </label>

      <div class="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2">
        <label class="block">
          <span class="text-xs text-muted-foreground">Hôte SMTP</span>
          <input v-model="smtpHote" placeholder="smtp.exemple.fr" :disabled="!estAdmin"
                 class="mt-1 w-full rounded-md bg-surface border border-border px-3 py-2 focus:border-primary outline-none disabled:opacity-50" />
        </label>
        <label class="block">
          <span class="text-xs text-muted-foreground">Port</span>
          <input v-model="smtpPort" placeholder="587" :disabled="!estAdmin"
                 class="mt-1 w-full rounded-md bg-surface border border-border px-3 py-2 focus:border-primary outline-none disabled:opacity-50" />
        </label>
        <label class="block">
          <span class="text-xs text-muted-foreground">Utilisateur</span>
          <input v-model="smtpUtilisateur" placeholder="(facultatif)" :disabled="!estAdmin"
                 class="mt-1 w-full rounded-md bg-surface border border-border px-3 py-2 focus:border-primary outline-none disabled:opacity-50" />
        </label>
        <label class="block">
          <span class="text-xs text-muted-foreground">Mot de passe</span>
          <input v-model="smtpMotDePasse" type="password"
                 :placeholder="smtpMotDePasseDefini ? 'Déjà défini — laisser vide pour le conserver' : '(facultatif)'"
                 :disabled="!estAdmin"
                 class="mt-1 w-full rounded-md bg-surface border border-border px-3 py-2 focus:border-primary outline-none disabled:opacity-50" />
          <button v-if="smtpMotDePasseDefini" type="button" @click="effacerMotDePasseSmtp"
                  :disabled="!estAdmin" class="mt-1 text-xs text-destructive hover:underline disabled:opacity-50">
            Effacer le mot de passe enregistré
          </button>
        </label>
        <label class="block sm:col-span-2">
          <span class="text-xs text-muted-foreground">Adresse d'expéditeur</span>
          <input v-model="smtpExpediteur" type="email" placeholder="testpilot@exemple.fr" :disabled="!estAdmin"
                 class="mt-1 w-full rounded-md bg-surface border border-border px-3 py-2 focus:border-primary outline-none disabled:opacity-50" />
        </label>
      </div>
      <label class="mt-3 flex items-center gap-2 text-sm">
        <input v-model="smtpTls" type="checkbox" :disabled="!estAdmin" />
        Chiffrer la connexion (STARTTLS)
      </label>

      <p v-if="!estAdmin" class="mt-2 text-xs text-warning">Réservé au rôle Admin.</p>

      <div class="mt-3">
        <button class="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-60"
                :disabled="smtpEnregistrement || !estAdmin" @click="enregistrerSmtp">
          {{ smtpEnregistrement ? 'Enregistrement…' : 'Enregistrer' }}
        </button>
      </div>

      <!-- Un relais mal configuré doit se voir tout de suite, pas silencieusement à la première
           vraie campagne — d'où ce bouton, indépendant de « Notifications activées ». -->
      <div class="mt-4 border-t border-border pt-3">
        <span class="text-xs text-muted-foreground">Envoyer un email de test</span>
        <div class="mt-1 flex gap-2">
          <input v-model="smtpTestDestinataire" type="email" placeholder="vous@exemple.fr" :disabled="!estAdmin"
                 class="flex-1 rounded-md bg-surface border border-border px-3 py-2 focus:border-primary outline-none disabled:opacity-50" />
          <button class="rounded-md border border-border px-4 py-2 text-sm hover:border-primary/40 disabled:opacity-60"
                  :disabled="smtpTestEnCours || !estAdmin || !smtpTestDestinataire.trim()" @click="envoyerTestSmtp">
            {{ smtpTestEnCours ? 'Envoi…' : 'Tester' }}
          </button>
        </div>
        <p v-if="smtpTestResultat" class="mt-2 text-sm"
           :class="smtpTestResultat.startsWith('Échec') ? 'text-destructive' : 'text-success'">
          {{ smtpTestResultat }}
        </p>
      </div>
    </section>
  </div>
</template>
