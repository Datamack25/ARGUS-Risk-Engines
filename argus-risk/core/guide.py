"""Contenu du guide intégré (bouton « Guide d'utilisation & mise à jour »)."""

from . import config as cfg

_START = f"""
### Démarrer en 5 étapes

Au premier lancement, l'**Accueil** affiche une carte de bienvenue (état du moteur, de la whitelist et des référentiels) ; dès qu'une analyse a été effectuée, il devient un **tableau de bord exécutif** (KPI, volumes, taux d'exemption whitelist, dernières analyses).

Le **menu latéral** donne accès à toutes les pages : Accueil, Import de données, Contexte KYC,
Alertes & analyse, Moteur de règles, Guide, Paramètres (Admin).

1. **Importer un ou plusieurs fichiers** (Excel `.xlsx`/`.xls` ou CSV) dans *Import de données* : ils sont
   consolidés et analysés ensemble (les croisements entre fichiers sont donc détectés). Pas de fichier sous la main ?
   **🧪 Démonstration** ou **📄 Modèle de fichier**.
2. **Vérifier le mapping des en-têtes** : la carte *Mapping dynamique des en-têtes* montre, pour chaque fichier,
   la correspondance champ standard → colonne (✔ automatique, ≈ approximative ≥ 85 %). Si une colonne est mal reconnue,
   ouvrez *Ajuster le mapping* (listes déroulantes), **✨ Match automatique** pour recommencer, ou **💾 Enregistrer le profil**
   pour réutiliser ce mapping pour le même client / format. Le *rapport d'import* décompte exactement les lignes
   (lues, vides ou parasites, montants illisibles, exclues, analysées).
3. *(Facultatif)* Renseigner la page **Contexte KYC** (secteur, pays d'origine / destination, moyen de paiement, type et
   secteur de la contrepartie, effet générateur) : le contexte majore le score des opérations déjà alertées.
4. Cliquer sur **📊 Analyser** : la page **Alertes & analyse** affiche le verdict, les indicateurs, un
   **paragraphe de synthèse**, le **détail par typologie**, le **tableau des transactions suspectes** (colonne *POURQUOI*),
   puis trois onglets : Synthèse, Toutes les opérations (colonnes QUALIFICATION et FICHIER_SOURCE) et Exports.
5. **Les fichiers sont générés automatiquement** à la fin de l'analyse : note N2 (Word) et classeur Excel (boutons de téléchargement en haut de la page, copies dans `exports/`), journal `analyses_history.csv` et, hors démonstration, `client_profiles_history.csv` / `fraud_patterns_learned.csv` (désactivable dans Paramètres › Import & contexte). Le tableau des transactions suspectes indique la **contrepartie et son IBAN**.

Le **Tableau de bord** résume la dernière analyse : faux positifs évités (liste blanche, entités publiques),
alertes par famille et dernières alertes LCB-FT. Le **Moteur de règles** présente le catalogue des 47 typologies.

### Liste blanche, entités publiques et faux RIB
- Une opération récurrente validée (loyer, impôt, abonnement…) reçoit le score 0 et la qualification
  « Exclusion Récurrente Validée » — jamais pour une PPE, des espèces ou un pays à risque.
- Une entité publique (DGFiP, URSSAF, Douanes…) citée avec un IBAN du **bon pays** est exemptée ; avec un IBAN
  **étranger ou à risque**, la règle FRD-10 (usurpation d'entité publique / faux RIB) lève une alerte de score 95.
- Fenêtre comportementale : les détecteurs de fractionnement, rebond et vélocité examinent en priorité les
  **N dernières transactions** du client (N = 5 par défaut, réglable).

### Niveaux de risque

| Score | Niveau | Action recommandée |
|---|---|---|
| 0 – {cfg.THRESHOLD_N1 - 1} | Faible | Aucune alerte |
| {cfg.THRESHOLD_N1} – {cfg.THRESHOLD_N2 - 1} | Modéré (N1) | Revue documentaire KYC, contrôle de cohérence |
| {cfg.THRESHOLD_N2} – {cfg.SCORE_CAP} | Élevé (N2) | Dossier d'investigation, note de suspicion, déclaration éventuelle |

Le score d'une opération est la **somme des poids** des typologies déclenchées, plafonnée à
{cfg.SCORE_CAP}. Le **score client** retient le score maximal de ses opérations, majoré de
{cfg.CLIENT_DIVERSITY_BONUS} points par typologie distincte supplémentaire.
"""

_DATA = """
### Format du fichier

Une ligne = une opération. Les en-têtes sont reconnus sans tenir compte de la casse, des
accents ni des espaces (`Montant`, `MONTANT_EUR`, `amount` sont acceptés).

| Colonne | Statut | Rôle |
|---|---|---|
| `MONTANT` | **Obligatoire** | Montant de l'opération (virgule ou point acceptés) |
| `SENS` ou `TYPE_OPERATION` | Fortement conseillé | `CREDIT/DEBIT`, `ENTRANT/SORTANT`, `DEPOT/RETRAIT`… Sinon déduit du signe du montant |
| `DATE` | Fortement conseillé | Fenêtres glissantes (24 h, 7 j, 30 j…). Inclure l'**heure** pour l'activité nocturne et les rafales |
| `ID_CLIENT` / `NOM_CLIENT` | Conseillé | Regroupement par client. Sans identifiant, le fichier est traité comme un seul compte |
| `LIBELLE` | Conseillé | Filtrage des frais/rejets et mots-clés (chargeback, rachat, salaire, notaire, trust…) |
| `MOYEN_PAIEMENT` | Selon typologie | `CASH`, `CB`, `VIR_SEPA`… |
| `PAYS` / `PAYS_RESIDENCE` | Selon typologie | Pays de l'opération et résidence du client : code ISO2 (`FR`, `NG`) ou nom du pays |
| `NOM_TITULAIRE_COMPTE` | Selon typologie | Titulaire du compte de contrepartie (comparé à `NOM_CLIENT`) |
| `CONTREPARTIE` | Selon typologie | Bénéficiaire / donneur d'ordre / IBAN (flux croisés, collecte, dispersion, nouveau bénéficiaire) |
| `PPE_SANCTION` | Selon typologie | `OUI/NON` |
| `STATUT_KYC` | Selon typologie | `OK`, `KO`, `EXPIRE`, `INCOMPLET`… |
| `IP`, `BIN_CARTE` | Selon typologie | Multi-comptes, multi-cartes |
| `CANAL` | Selon typologie | `ONLINE`, `RETAIL`… |
| `INTERDIT_ANJ` | Jeux uniquement | `OUI/NON` |

Seule `MONTANT` est obligatoire ; plus le fichier est riche, plus le nombre de typologies évaluées est élevé.

**Important — typologies « Non évaluables »** : si une colonne requise manque, la typologie
n'est **pas** évaluée et le signale explicitement (onglet *Rapport Synthèse › Couverture*).
Une absence d'alerte sur une typologie non évaluable ne signifie jamais « pas de risque ».

**Opérations exclues automatiquement** : libellés contenant `REJET`, `RESTITUTION`,
`MAINLEVEE`, `TVA`, `COMMISSION`, `FRAIS`, `TCION`, `AGIOS`, `TAXE`, `AJUSTEMENT`
(modifiable dans `core/config.py`).
"""

_UPDATE = f"""
### Mettre à jour la plateforme

Version actuelle : **{cfg.VERSION}** ({cfg.LAST_UPDATE}). Chaque règle métier se modifie dans
un fichier dédié, **sans toucher à l'interface** :

| Je veux… | Où le faire |
|---|---|
| Changer **seuils, poids, typologies, listes de pays, liste blanche** | Page **🔐 Administration** (sans toucher au code) |
| Changer un **seuil**, un **poids** ou une **fenêtre de temps** d'une typologie | `core/typologies.py` |
| **Ajouter / remplacer** une typologie | `core/typologies.py` (+ `core/engine.py` si nouveau détecteur) |
| Modifier les **niveaux** N1/N2, le plafond de score, les **exclusions** | `core/config.py` |
| Mettre à jour les **pays à risque**, la zone SEPA, les statuts KYC | `core/reference_lists.py` |
| Accepter un **nouveau nom de colonne** (alias) | `core/data.py` (dictionnaire `CANONICAL`) |
| Changer le **texte du guide** | `core/guide.py` |
| Modifier le **rapport Word** | `core/report.py` |
| Changer **couleurs / mise en page** | `core/ui.py` (bloc CSS) et `.streamlit/config.toml` |
| Modifier une **page** (accueil, analyse, guide, typologies) | `views/*.py` |
| Changer le **nom de l'auteur** du pied de page | `core/config.py` (`AUTHOR`) |

#### Exemple 1 — modifier un seuil
Dans `core/typologies.py`, trouver la typologie (ex. `FRA-05`) et changer le paramètre :

```python
T("FRA-05", "Espèces cumulées atypiques", 30,
  "Flux d'espèces cumulés ≥ 8 000 € sur 30 jours.",
  "cash_cumul", threshold=8000, window_h=30 * DAY, methods=CASH),   # ← threshold=8000
```
Penser à mettre à jour le texte du signal d'alerte (4ᵉ argument).

#### Exemple 2 — ajouter ou remplacer une typologie
Ajouter (ou remplacer) un appel `T(...)` dans le tuple `TYPOLOGIES`. Le préfixe du code
(`LCB`, `FRA`, `SAN`, `FIS`, `TRA`, `FRD`, `SEC`) détermine la famille ; un contrôle `assert`
exige au moins 30 typologies à codes uniques. Détecteurs disponibles : `pass_through`,
`structuring`, `cash_cumul`, `velocity`, `high_risk_country`, `non_sepa`, `third_party`,
`round_amounts`, `night_activity`, `pep`, `kyc_failure`, `micro_testing`, `chargeback`,
`multi_account_ip`, `multi_card`, `velocity_change`, `anj_banned`, `dormant`,
`cross_flows`, `large_single`, `keyword`, `keyword_early`, `tax_haven`, `shell_company`, `fan_in`, `fan_out`, `multi_country`,
`repeated_amount`, `mirror_amounts`, `residence_mismatch`, `missing_keyword`, `new_beneficiary`.

#### Exemple 3 — créer un nouveau détecteur
Dans `core/engine.py` : écrire une fonction `d_mon_detecteur(ctx, p)` qui retourne un tableau
booléen (une valeur par opération), l'enregistrer dans le dictionnaire `DETECTORS`, puis
déclarer ses colonnes requises dans `DETECTOR_REQUIRES` (`core/typologies.py`).

#### Calendrier de maintenance conseillé
- **Après chaque plénière du GAFI** (février, juin, octobre) et chaque mise à jour de la liste UE
  des pays tiers à haut risque : mettre à jour `HIGH_RISK_COUNTRIES`, `TAX_HAVENS` et la date de validation
  `REFERENCE_LISTS_REVIEWED`.
- **Trimestriellement** : recalibrer seuils et poids à partir du taux de faux positifs observé.
- **À chaque évolution réglementaire** (ANJ, ACPR, TRACFIN) : revoir libellés et seuils.

#### Déployer une mise à jour (Git)
```bash
git pull
# ... modifier les fichiers ...
python -m pytest                      # vérifie que les 47 typologies s'exécutent
streamlit run main.py                 # test local avec les données de démonstration
git add -A && git commit -m "Mise à jour seuil FRA-05 et pays à risque"
git push                              # Streamlit Community Cloud redéploie automatiquement
```
Incrémenter `VERSION` et `LAST_UPDATE` dans `core/config.py` à chaque livraison.
"""

_TROUBLE = """
### Dépannage

| Message / symptôme | Cause probable | Solution |
|---|---|---|
| « Colonne MONTANT introuvable » | En-tête de montant non reconnu | Choisir la colonne dans *Ajuster le mapping* (Import de données) |
| Beaucoup de typologies « Non évaluables » | Colonnes absentes du fichier | Consulter *Couverture* et ajouter les colonnes listées |
| Aucune alerte alors que le fichier est suspect | Sens ou dates non reconnus | Vérifier `SENS`/`TYPE_OPERATION` et le format de `DATE` (JJ/MM/AAAA hh:mm) |
| Pays non pris en compte | Nom de pays inhabituel | Utiliser les codes ISO2 (`FR`, `NG`) |
| Caractères illisibles (CSV) | Encodage | Enregistrer en UTF-8 ou fournir un `.xlsx` |
| Fichier trop volumineux | Limite d'import | Augmenter `maxUploadSize` dans `.streamlit/config.toml` |
| Trop de faux positifs | Seuils trop bas | Relever les seuils de la typologie concernée (voir *Mettre à jour*) |

**Confidentialité** : les fichiers sont traités en mémoire et ne sont pas conservés par
l'application. Ne déposez des données réelles que sur un environnement conforme à vos règles
internes (RGPD, secret bancaire) ; le dossier `data/` et les fichiers Excel/CSV sont exclus de
Git par `.gitignore`.

**Rappel** : les résultats sont une **aide à la décision**. La qualification et la décision de
déclaration restent de la responsabilité de l'analyste N2 et du responsable LCB-FT.
"""

_ADMIN = """
### Administration (Head of Compliance)

La page **⚙️ Paramètres (Admin)** du menu latéral permet de piloter le moteur
**sans modifier le code**. Elle est protégée par un mot de passe (`ADMIN_PASSWORD`, à définir dans
*Streamlit Cloud › Manage app › Settings › Secrets*).

| Onglet | Ce que l'on peut faire |
|---|---|
| **Vue d'ensemble** | Version publiée, typologies actives, circuit de modification |
| **Scores & seuils** | Seuils N1/N2, plafond du score, bonus de diversité client, mots exclus |
| **Typologies** | Activer/désactiver, changer le poids, le texte du signal et tous les seuils/fenêtres/mots-clés ; **créer une typologie personnalisée** à partir d'un détecteur existant |
| **Listes de référence** | Pays à haut risque, paradis fiscaux, zone SEPA, statuts KYC, date de dernière validation |
| **Liste blanche** | Exempter un client (motif obligatoire) |
| **Import & contexte** | Fenêtre N, liste blanche d'opérations (ET/OU), entités publiques, taux de change, synonymes d'en-têtes, barèmes de contexte, apprentissage, référentiel des secteurs et fichiers d'auto-enrichissement |
| **Simulation** | Comparer version publiée et brouillon : alertes gagnées (*below-the-line*) et perdues (*above-the-line*) |
| **Publication & historique** | Publier avec motif obligatoire, voir l'historique avant/après, restaurer une version, exporter/importer `config_rules.json` |

#### Circuit recommandé
1. Modifier le **brouillon** (rien n'est appliqué aux analyses à ce stade).
2. **Simuler** l'impact sur un jeu de données représentatif et conserver l'export Excel comme preuve de test.
3. **Publier** : auteur et motif obligatoires, validation technique automatique.
4. Chaque publication est **versionnée et tracée** (avant/après, auteur, date) ; une version antérieure peut être restaurée.

#### Rendre les modifications permanentes
Sur Streamlit Cloud, le disque est réinitialisé à chaque redéploiement. Après publication, cliquez sur
**Exporter la configuration publiée**, puis déposez `config_rules.json` (à la racine du dépôt), les CSV `sectors_reference.csv`,
`client_profiles_history.csv`, `fraud_patterns_learned.csv` (et si besoin `config/history.jsonl`, `config/audit_log.jsonl`)
sur GitHub : la configuration est rechargée à chaque démarrage.

#### Sécurité
Choisissez un mot de passe long et unique, ne versionnez jamais `secrets.toml`, et limitez l'accès à
l'application (Streamlit Cloud › Sharing) aux personnes habilitées.
"""

SECTIONS = {
    "🚀 Utiliser la plateforme": _START,
    "🗂️ Format des données": _DATA,
    "🔧 Mettre à jour": _UPDATE,
    "🔐 Administration": _ADMIN,
    "🩺 Dépannage": _TROUBLE,
}
