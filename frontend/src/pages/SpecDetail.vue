<script setup lang="ts">
// LA SPÉCIFICATION — l'écran qui manquait (lot 4 du déploiement, 2026-07-24).
//
// Le backend du CRUD existait depuis le 2026-07-20 ; aucun écran ne l'appelait. Conséquence
// concrète : un utilisateur ne pouvait ni créer ni relire une spécification — les seules qui
// existaient étaient les « enveloppes » créées automatiquement par la génération, une par cas.
// Le modèle du brief (une spec → N cas, un par angle) n'était donc atteignable par personne.
//
// Ce que cet écran fait, et rien de plus : nommer un document, l'écrire, le relire, voir les cas
// qui en sont nés. **Il ne génère rien et ne dépense rien** — la génération est un geste explicite
// (même principe que le lancement d'une campagne, décision 0022 n°8.c.1).
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { type CaseSummary, type GroupDetail } from '../lib/api'
import { useCas, useEnregistrerGroupe, useSupprimerGroupe, useUnGroupe } from '../lib/donnees'
import { MODELE_SPECIFICATION, estModeleNonRempli } from '../lib/modeleSpecification'
import { testStatusMeta, testStatusCode } from '../lib/status'
import Button from '../components/ui/Button.vue'
import Card from '../components/ui/Card.vue'
import Spinner from '../components/ui/Spinner.vue'

const route = useRoute()
const router = useRouter()
const pid = computed(() => route.params.pid as string)
const gid = computed(() => route.params.id as string)

const spec = ref<GroupDetail | null>(null)
const cas = ref<CaseSummary[]>([])
const chargement = ref(true)
const erreur = ref('')
const message = ref('')

const titre = ref('')
const document = ref('')
const enregistrement = ref(false)

// « Modifié » se compare au document CHARGÉ, pas à un drapeau posé à la première frappe : revenir
// à l'état initial doit éteindre le bouton, sinon on propose d'enregistrer un non-changement.
const modifie = computed(() =>
  !!spec.value && (titre.value !== spec.value.title || document.value !== spec.value.spec_content))

// Couche de données partagée : les cas du projet sont déjà en cache (l'arbre et la liste les
// affichent), la fiche ne les redemande donc pas — elle filtre ceux de cette spécification.
const { data: specData, isLoading: chargeSpec, error: erreurSpec } = useUnGroupe(gid)
const { data: casData } = useCas(pid)

watch(specData, (s) => {
  if (!s) return
  // ⚠️ Le brouillon en cours de frappe ne doit pas être écrasé par une revalidation de fond.
  // On juge l'écart AVANT de remplacer la référence serveur : le mesurer après la remplacerait
  // ferait toujours paraître le brouillon « modifié » (il diffère forcément du nouveau serveur),
  // et les champs ne seraient JAMAIS remplis — le premier chargement compris.
  const brouillonIntact = !spec.value
    || (titre.value === spec.value.title && document.value === spec.value.spec_content)
  spec.value = s
  if (brouillonIntact) { titre.value = s.title; document.value = s.spec_content }
}, { immediate: true })

watch([casData, specData], () => {
  cas.value = (casData.value ?? []).filter((c) => c.group_id === specData.value?.id)
}, { immediate: true })

watch(erreurSpec, (e) => { if (e) erreur.value = (e as any)?.message || 'Spécification introuvable.' })
watch(chargeSpec, (v) => { chargement.value = v && !specData.value }, { immediate: true })

const enregistrerSpec = useEnregistrerGroupe(pid)
const supprimerSpec = useSupprimerGroupe(pid)

async function enregistrer() {
  if (!spec.value || !titre.value.trim()) return
  enregistrement.value = true
  erreur.value = ''
  message.value = ''
  try {
    const maj = await enregistrerSpec.mutateAsync({
      id: spec.value.id, title: titre.value.trim(), spec_content: document.value,
    })
    spec.value = maj
    titre.value = maj.title
    document.value = maj.spec_content
    message.value = 'Spécification enregistrée.'
  } catch (e: any) {
    erreur.value = e?.message || 'Enregistrement impossible.'
  } finally {
    enregistrement.value = false
  }
}

function partirDuModele() {
  document.value = MODELE_SPECIFICATION
}

async function supprimer() {
  if (!spec.value) return
  if (!window.confirm(`Supprimer la spécification « ${spec.value.title} » ?`)) return
  try {
    await supprimerSpec.mutateAsync(spec.value.id)
    router.push({ name: 'cases', params: { pid: pid.value } })
  } catch (e: any) {
    // 409 : la spécification porte des cas. Le message du serveur dit combien — on le montre tel
    // quel plutôt qu'un « suppression impossible » qui n'apprend rien.
    erreur.value = e?.message || 'Suppression impossible.'
  }
}

// Générer DEPUIS cette spécification : on emmène vers l'écran de génération avec le document
// pré-rempli. C'est là, et pas ici, que la dépense est engagée et que l'humain valide le métier.
function genererDepuisLaSpec() {
  router.push({ name: 'case-new', params: { pid: pid.value }, query: { spec: String(spec.value!.id) } })
}

function ouvrirCas(id: number) {
  router.push({ name: 'case-detail', params: { pid: pid.value, id: String(id) } })
}
function statutDe(c: CaseSummary) {
  return testStatusMeta(testStatusCode(c.last_execution_status, c.last_functional_status))
}
</script>

<template>
  <div class="space-y-6">
    <button class="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
            @click="router.push({ name: 'cases', params: { pid } })">
      ← Cas de test
    </button>

    <div v-if="chargement" class="flex items-center gap-2 text-sm text-muted-foreground">
      <Spinner class="h-4 w-4" /> Chargement…
    </div>

    <template v-else-if="spec">
      <div>
        <p class="text-xs uppercase tracking-wider text-muted-foreground">Spécification</p>
        <input v-model="titre"
               class="mt-1 w-full bg-transparent text-2xl font-semibold tracking-tight outline-none focus:border-b focus:border-primary/50" />
        <p class="mt-1 text-sm text-muted-foreground">
          {{ spec.case_count }} cas de test {{ spec.case_count > 1 ? 'issus' : 'issu' }} de ce document
        </p>
      </div>

      <Card title="Le document">
        <p class="mb-3 text-sm text-muted-foreground">
          C'est ce texte que l'IA lira pour écrire les cas de test. Plus il est précis sur les
          <strong>données</strong> et les <strong>règles</strong>, moins l'outil a à deviner.
        </p>
        <textarea v-model="document" rows="18" spellcheck="false"
                  placeholder="Collez ici la spécification fonctionnelle, ou partez du modèle."
                  class="w-full rounded-md border border-border bg-surface-raised px-3 py-2 font-mono text-[13px] leading-relaxed outline-none focus:border-primary/50" />
        <div class="mt-3 flex flex-wrap items-center gap-3">
          <Button variant="primary" :loading="enregistrement" :disabled="!modifie || !titre.trim()"
                  @click="enregistrer">Enregistrer</Button>
          <button v-if="estModeleNonRempli(document)" class="text-sm text-primary hover:underline"
                  @click="partirDuModele">Partir du modèle</button>
          <span v-if="message" class="text-sm text-success">{{ message }}</span>
          <span v-if="erreur" class="text-sm text-destructive">{{ erreur }}</span>
        </div>
      </Card>

      <Card title="Les cas de test issus de cette spécification">
        <!-- ⚠️ Générer est un geste EXPLICITE, jamais un effet de bord de l'écriture du document :
             c'est là que la dépense est engagée et que l'humain valide le métier (§4bis). -->
        <div class="mb-3 flex flex-wrap items-center gap-3">
          <Button variant="primary" :disabled="estModeleNonRempli(document)" @click="genererDepuisLaSpec">
            Générer un cas de test depuis cette spécification
          </Button>
          <span v-if="estModeleNonRempli(document)" class="text-sm text-muted-foreground">
            Rédigez d'abord le document — un modèle vierge ne décrit rien à tester.
          </span>
        </div>

        <ul v-if="cas.length" class="divide-y divide-border text-sm">
          <li v-for="c in cas" :key="c.id"
              class="flex cursor-pointer items-center justify-between gap-3 py-2.5 hover:text-primary"
              @click="ouvrirCas(c.id)">
            <div class="min-w-0">
              <span class="text-muted-foreground tabular-nums mr-2">C{{ c.id }}</span>
              <span class="truncate">{{ c.title }}</span>
            </div>
            <span class="shrink-0 rounded-full px-2 py-0.5 text-[11px] font-medium"
                  :class="statutDe(c).badge">{{ statutDe(c).label }}</span>
          </li>
        </ul>
        <p v-else class="text-sm text-muted-foreground">
          Aucun cas n'est encore né de cette spécification.
        </p>
      </Card>

      <div class="flex items-center justify-between border-t border-border pt-4">
        <span class="text-xs text-muted-foreground">
          Empreinte du document : <span class="font-mono">{{ spec.spec_hash.slice(0, 12) || '—' }}</span>
        </span>
        <button class="text-sm text-destructive hover:underline" @click="supprimer">
          Supprimer cette spécification
        </button>
      </div>
    </template>

    <p v-else class="text-sm text-destructive">{{ erreur }}</p>
  </div>
</template>
