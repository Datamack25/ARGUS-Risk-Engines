# 🛡️ Argus RISK — Analyse de transaction (LCB-FT & Fraude)

Plateforme Streamlit d'analyse transactionnelle. Sans réglage préalable, elle applique **47 typologies**
de fraude, de blanchiment et de LCB-FT à un fichier Excel/CSV, puis :

1. relève les transactions suspectes et calcule un score (opération et client) ;
2. **rédige un paragraphe de constats** décrivant ce qu'elle a remarqué, avec le détail par typologie ;
3. liste les **transactions concernées dans un tableau** (colonne *POURQUOI* = typologies détectées) ;
4. produit une note N2 (Word) et un classeur Excel.

## Les 47 typologies

| Famille | Préfixe | Exemples |
|---|---|---|
| Blanchiment & LCB-FT | `LCB` | passage rapide de fonds, société éphémère « taxi », compte de collecte, dispersion, flux croisés, compte dormant, immobilier, trusts/offshore, cryptoactifs |
| Fractionnement & espèces | `FRA` | sous 10 000 € en espèces, sous 3 000 €, montants identiques, montants ronds, espèces cumulées |
| Sanctions, PPE & juridictions | `SAN` | PPE/sanctions, pays à haut risque, hors SEPA, micro-transferts vers zones à risque (FT) |
| Fraude fiscale & sociale | `FIS` | paradis fiscaux, espèces récurrentes, facturation circulaire, résidence incohérente, abus de biens sociaux, fraude aux aides publiques (CPF…) |
| Travail illégal / dissimulé | `TRA` | salaires en espèces, paie informelle, salaires sans cotisations, retraits d'espèces |
| Fraude aux moyens de paiement & escroquerie | `FRD` | test de cartes, chargeback, multi-comptes IP, multi-cartes, compte tiers, KYC, fraude au président |
| Risques sectoriels | `SEC` | jeux (recharges compulsives, interdits, bonus), assurance (rachats anticipés, sinistres répétés) |

Inspirées des scénarios des plateformes de référence (NICE Actimize, SAS AML, Oracle FCCM, Feedzai,
Quantexa, Verafin…) et des typologies TRACFIN / GAFI.

## Nouveautés 2.2

- Interface tableau de bord : menu latéral marine, Import de données, Contexte KYC, Alertes, Moteur de règles, Paramètres.
- **Import multi-fichiers** consolidé, mapping dynamique des en-têtes (exact → alias → flou ≥ 85 % avec `thefuzz`),
  profils de mapping par client, rapport de décompte des lignes.
- Liste blanche d'opérations récurrentes, entités publiques (règle 01) et faux RIB (règle 02, FRD-10), fenêtre N = 5.
- Page **Contexte KYC** et référentiel `sectors_reference.csv` ; auto-enrichissement (`client_profiles_history.csv`,
  `fraud_patterns_learned.csv`) à chaque analyse validée ; tout est pilotable depuis Paramètres (Admin).
- Configuration active : `config_rules.json` (racine) ; journaux : dossier `config/`.

## Lancer en local

```bash
python -m venv .venv && source .venv/bin/activate     # Windows : .venv\Scripts\activate
pip install -r requirements.txt
streamlit run main.py
```

Sans fichier : bouton **🧪 Démonstration**. La page **📘 Guide d'utilisation**
détaille l'usage, le format des données, la mise à jour et le dépannage dans l'application.

## Pages (menu latéral)

| Page | Contenu |
|---|---|
| Tableau de bord | KPI, faux positifs évités, alertes par famille, dernières alertes LCB-FT |
| Import de données | Multi-fichiers, mapping dynamique des en-têtes, profils, rapport de lignes, **Analyser** |
| Contexte KYC | Fiche KYC par secteur + contexte de la transaction (majoration du score) |
| Alertes & analyse | Verdict, constats rédigés, tableau des transactions suspectes, exports, validation |
| Moteur de règles | Catalogue des typologies actives |
| Guide d'utilisation | Utilisation, format des données, mise à jour, dépannage |
| Paramètres (Admin) | Scores, typologies, listes, liste blanche, import & contexte, simulation, publication versionnée |

## Structure

```
main.py                  Point d'entrée : navigation entre les pages
views/                   dashboard.py · home.py (import) · kyc_input.py · analysis.py · typologies.py · guide.py · admin.py
core/
  config.py              Valeurs par défaut : seuils, plafond, exclusions, version, auteur
  settings.py            Paramétrage administrable : brouillon, validation, versions, audit, accès admin
  ui.py                  Styles (thème clair imposé), bandeau, tableaux, pied de page
  typologies.py          Catalogue des 47 typologies (seuils, poids, paramètres)
  engine.py              Détecteurs vectorisés + scoring + profils clients
  narrative.py           Paragraphe de constats + tableau des transactions suspectes
  enrichment.py          Contexte KYC, secteurs, auto-enrichissement (CSV)
  profiles.py            Profils de mapping par client
  data.py                Lecture CSV/Excel, reconnaissance des colonnes, nettoyage
  reference_lists.py     SEPA, pays à risque, paradis fiscaux, statuts KYC (à tenir à jour)
  report.py              Note N2 (Word) et export Excel
  sample.py              Données de démonstration et modèle de fichier
  guide.py               Contenu du guide intégré
tests/                   test_engine.py · test_settings.py · test_import.py
.streamlit/config.toml   Thème clair et limites d'upload (doit être dans le dossier .streamlit)
.streamlit/secrets.toml.example   Modèle du secret ADMIN_PASSWORD
config_rules.json        Configuration publiée (racine)
sectors_reference.csv · client_profiles_history.csv · fraud_patterns_learned.csv
config/                  history.jsonl, audit_log.jsonl, mapping_profiles.json
```

## Scoring

Score d'une opération = somme des poids des typologies déclenchées (plafond 100) :
**0–39** Faible · **40–69** Modéré (N1) · **70–100** Élevé (escalade N2). Score client = score maximal
+ 5 points par typologie distincte supplémentaire. Une typologie dont les colonnes requises manquent est
**« Non évaluable »**, jamais silencieusement ignorée. Seule la colonne `MONTANT` est obligatoire.

## Administration (Head of Compliance)

Page **⚙️ Paramètres (Admin)** : protégée par `ADMIN_PASSWORD` (secret Streamlit). Circuit : brouillon → **simulation**
(alertes gagnées/perdues, ATL/BTL) → **publication** avec motif obligatoire → historique avant/après et
restauration. Les paramètres publiés sont stockés dans `config_rules.json` ; sur Streamlit Cloud le disque est
éphémère : exporter ce fichier et le déposer (avec les trois CSV) dans le dépôt GitHub.

## Mettre à jour (code)

| Besoin | Fichier |
|---|---|
| Seuil, poids, fenêtre, ajout/remplacement d'une typologie | `core/typologies.py` |
| Niveaux N1/N2, exclusions de libellés | `core/config.py` |
| Pays à risque (après chaque plénière GAFI), paradis fiscaux, SEPA | `core/reference_lists.py` |
| Nouveau détecteur | `core/engine.py` + `DETECTOR_REQUIRES` dans `core/typologies.py` |

```bash
python -m pytest        # doit rester vert
git add -A && git commit -m "Mise à jour ..." && git push
```

## ⚠️ Points d'attention

- Seuils et poids = **valeurs de départ** à calibrer avec la conformité (taux de faux positifs).
- `HIGH_RISK_COUNTRIES` et `TAX_HAVENS` sont des **listes de travail** à valider contre les publications
  officielles (GAFI, UE, OCDE) avant tout usage en production.
- Mots-clés de libellé (salaire, notaire, trust, crypto…) : à adapter au vocabulaire de vos fichiers.
- Aide à la décision : la qualification et la déclaration de soupçon relèvent de l'analyste N2 et du
  responsable LCB-FT. Ne versez jamais de données clients dans Git.
