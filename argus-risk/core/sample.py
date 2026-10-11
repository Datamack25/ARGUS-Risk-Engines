"""Jeu de données de démonstration et modèle de fichier.

Contient des clients ordinaires et des scénarios suspects injectés volontairement
pour déclencher la plupart des 46 typologies du catalogue.
"""

import zlib
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

COLUMNS = [
    "ID_TRANSACTION", "DATE", "ID_CLIENT", "NOM_CLIENT", "LIBELLE", "MONTANT", "SENS",
    "MOYEN_PAIEMENT", "PAYS", "PAYS_RESIDENCE", "PPE_SANCTION", "NOM_TITULAIRE_COMPTE",
    "CONTREPARTIE", "IP", "BIN_CARTE", "STATUT_KYC", "CANAL", "INTERDIT_ANJ",
]


def demo_dataframe(seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    start = datetime(2026, 9, 1, 9, 0)
    t0 = start + timedelta(days=10, hours=2)
    rows = []

    def add(client, name, when, amount, sens, moyen="CB", libelle="", pays="FR", ppe="NON",
            titulaire=None, cp="", ip=None, bin_="", kyc="OK", canal="ONLINE", interdit="NON",
            residence="FR"):
        rows.append({
            "ID_TRANSACTION": "", "DATE": when, "ID_CLIENT": client, "NOM_CLIENT": name,
            "LIBELLE": libelle or ("VIREMENT RECU" if sens == "CREDIT" else "PAIEMENT"),
            "MONTANT": round(float(amount), 2), "SENS": sens, "MOYEN_PAIEMENT": moyen, "PAYS": pays,
            "PAYS_RESIDENCE": residence, "PPE_SANCTION": ppe, "NOM_TITULAIRE_COMPTE": titulaire or name,
            "CONTREPARTIE": cp,
            "IP": ip or f"92.{rng.integers(1, 250)}.{rng.integers(1, 250)}.{rng.integers(1, 250)}",
            "BIN_CARTE": bin_ or str(400000 + zlib.crc32(client.encode()) % 99999), "STATUT_KYC": kyc,
            "CANAL": canal, "INTERDIT_ANJ": interdit,
        })

    # 1) Clients ordinaires -----------------------------------------------------
    for i in range(1, 31):
        cid, name = f"C{i:03d}", f"CLIENT NORMAL {i:02d}"
        for _ in range(int(rng.integers(5, 10))):
            when = start + timedelta(days=int(rng.integers(0, 28)), hours=int(rng.integers(8, 21)),
                                     minutes=int(rng.integers(0, 60)))
            credit = rng.random() < 0.6
            add(cid, name, when, rng.uniform(15, 250), "CREDIT" if credit else "DEBIT",
                moyen=str(rng.choice(["CB", "VIR_SEPA", "PRELEVEMENT"])),
                cp=f"TIERS {int(rng.integers(1, 12)):02d}")

    # 2) Scénarios suspects ------------------------------------------------------
    # S01 — rebond rapide + compte bénéficiaire d'un tiers
    add("S01", "MARTIN ALICE", t0, 6000, "CREDIT", moyen="VIR_SEPA")
    add("S01", "MARTIN ALICE", t0 + timedelta(hours=2), 5600, "DEBIT", moyen="VIR_SEPA",
        titulaire="DUPONT JEAN", cp="FR7612345000010000000000001")

    # S02 — fractionnement d'espèces (point de vente) + espèces récurrentes
    for k in range(7):
        add("S02", "BERNARD PAUL", t0 + timedelta(hours=7 * k), rng.uniform(8200, 9900), "CREDIT",
            moyen="CASH", libelle="ENCAISSEMENT ESPECES", canal="RETAIL")

    # S03 — test de cartes, IP partagée, multi-cartes, chargeback
    ip = "185.22.14.9"
    for k in range(6):
        add("S03", "LEROY MARC", t0 + timedelta(minutes=4 * k), rng.uniform(1, 5), "CREDIT",
            ip=ip, bin_=str(410000 + k))
    add("S03", "LEROY MARC", t0 + timedelta(days=6), 300, "CREDIT", libelle="CHARGEBACK CB", ip=ip)
    for cid in ("S04", "S05", "S06"):
        add(cid, f"JOUEUR {cid}", t0 + timedelta(days=1), 80, "CREDIT", ip=ip)

    # S07 — PPE, montants ronds, pays à risque
    add("S07", "DURAND SOPHIE", t0 + timedelta(days=2), 12000, "CREDIT", moyen="VIR_SEPA",
        ppe="OUI", pays="IR")
    add("S07", "DURAND SOPHIE", t0 + timedelta(days=3), 15000, "CREDIT", moyen="VIR_SEPA", pays="IR")

    # S08 — multi-virements rapides, dispersion vers de nombreux bénéficiaires, pays multiples
    for k, country in enumerate(["NG", "AE", "TR", "MA", "NG", "TR"]):
        add("S08", "ROUX THOMAS", t0 + timedelta(hours=3 * k), 2500, "DEBIT", moyen="VIR_SEPA",
            libelle="VIREMENT EMIS", pays=country, cp=f"BENEF {k}")
    for k in range(3):
        add("S08", "ROUX THOMAS", t0 + timedelta(days=2, hours=k), 3200, "DEBIT", moyen="VIR_SEPA",
            libelle="VIREMENT EMIS", cp=f"BENEF {6 + k}")

    # S09 — compte dormant réactivé + KYC défaillant
    add("S09", "FABRE CLAIRE", datetime(2025, 8, 12, 10, 0), 200, "CREDIT")
    add("S09", "FABRE CLAIRE", t0 + timedelta(days=5), 20000, "DEBIT", libelle="RACHAT TOTAL",
        kyc="EXPIRE")

    # S10 — flux croisés et facturation circulaire (montants miroirs)
    for k in range(3):
        add("S10", "ALPHA TRADING SARL", t0 + timedelta(days=k), 3000, "CREDIT", moyen="VIR_SEPA",
            cp="BETA HOLDING")
        add("S10", "ALPHA TRADING SARL", t0 + timedelta(days=k, hours=5), 3000, "DEBIT",
            moyen="VIR_SEPA", cp="BETA HOLDING")

    # S11 — jeux : nuit, ronds, recharges compulsives, bonus, gains vidés, interdit
    for k in range(4):
        add("S11", "GARCIA LUC", datetime(2026, 9, 15, 3, 10) + timedelta(minutes=20 * k), 6000,
            "CREDIT", moyen="VIR_SEPA", interdit="OUI")
    for k in range(6):
        add("S11", "GARCIA LUC", t0 + timedelta(days=4, minutes=15 * k), 50, "CREDIT", interdit="OUI")
    add("S11", "GARCIA LUC", t0 + timedelta(days=8), 100, "CREDIT", libelle="BONUS BIENVENUE")
    add("S11", "GARCIA LUC", t0 + timedelta(days=8, hours=6), 90, "DEBIT", libelle="RETRAIT")

    # S12 — assurance : rachats rapprochés, sinistres répétés
    add("S12", "PETIT ANNE", t0, 15000, "CREDIT", moyen="VIR_SEPA", libelle="PRIME UNIQUE")
    add("S12", "PETIT ANNE", t0 + timedelta(days=20), 7000, "DEBIT", moyen="VIR_SEPA",
        libelle="RACHAT PARTIEL")
    for k in range(3):
        add("S12", "PETIT ANNE", t0 + timedelta(days=30 + 10 * k), 800, "DEBIT",
            libelle="INDEMNISATION SINISTRE")

    # S13 — opération immobilière atypique + structure opaque
    add("S13", "MOREAU PIERRE", t0 + timedelta(days=3), 120000, "DEBIT", moyen="VIR_SEPA",
        libelle="ACQUISITION IMMOBILIER NOTAIRE", cp="OFFICE NOTARIAL")
    add("S13", "MOREAU PIERRE", t0 + timedelta(days=4), 8000, "DEBIT", moyen="VIR_SEPA",
        libelle="VIREMENT TRUST OFFSHORE", pays="KY", cp="CAYMAN TRUST LTD")

    # S14 — remises de chèques répétées
    for k in range(5):
        add("S14", "SIMON JULIE", t0 + timedelta(days=k), rng.uniform(300, 900), "CREDIT",
            moyen="CHEQUE", libelle="REMISE CHEQUE")

    # S15 — société éphémère (« taxi ») : nombreux donneurs d'ordre, sorties ≈ entrées
    for k in range(10):
        add("S15", "ECLAIR SERVICES SARL", t0 + timedelta(days=k % 7, hours=k), 3500, "CREDIT",
            moyen="VIR_SEPA", cp=f"DONNEUR {k}")
    for k in range(5):
        add("S15", "ECLAIR SERVICES SARL", t0 + timedelta(days=5 + k % 3, hours=k), 6900, "DEBIT",
            moyen="VIR_SEPA", cp="HOLDING PRIVEE SA")

    # S16 — fiscal : paradis fiscal, résidence incohérente, dirigeant, cryptoactifs, ronds
    for k in range(3):
        add("S16", "LAMBERT HUGO", t0 + timedelta(days=k), 2000, "DEBIT", moyen="VIR_SEPA",
            pays="PA", libelle="VIREMENT", cp="PANAMA CONSULTING")
    for k in range(3):
        add("S16", "LAMBERT HUGO", t0 + timedelta(days=10 + 10 * k), 6000, "DEBIT", moyen="VIR_SEPA",
            libelle="PRELEVEMENT COMPTE COURANT ASSOCIE")
    add("S16", "LAMBERT HUGO", t0 + timedelta(days=4), 2500, "DEBIT", libelle="ACHAT USDT BINANCE")

    # S17 — travail dissimulé : salaires en espèces, retraits d'espèces, paie informelle
    for k in range(4):
        add("S17", "BATIPRO RENOV", t0 + timedelta(days=3 * k), 1200, "DEBIT", moyen="CASH",
            libelle="SALAIRE OUVRIER ESPECES", cp=f"OUVRIER {k}")
    add("S17", "BATIPRO RENOV", t0 + timedelta(days=5), 4000, "DEBIT", moyen="CASH",
        libelle="RETRAIT ESPECES")
    for k in range(7):
        add("S17", "BATIPRO RENOV", t0 + timedelta(days=6 + k), 900, "DEBIT", moyen="VIR_SEPA",
            libelle="PAIE OUVRIER", cp=f"SALARIE {k}")

    # S18 — fraude aux aides publiques (CPF) : reçu puis reversé
    add("S18", "FORMATION EXPRESS SAS", t0, 4500, "CREDIT", moyen="VIR_SEPA",
        libelle="AIDE CPF MONCOMPTEFORMATION")
    add("S18", "FORMATION EXPRESS SAS", t0 + timedelta(days=2), 4300, "DEBIT", moyen="VIR_SEPA",
        libelle="VIREMENT", cp="PRIVE")

    # S19 — nouveau bénéficiaire important (fraude au président)
    for k in range(6):
        add("S19", "SOCIETE NORMALE SA", t0 - timedelta(days=20 - 3 * k), 800, "DEBIT",
            moyen="VIR_SEPA", cp="FOURNISSEUR HABITUEL")
    add("S19", "SOCIETE NORMALE SA", t0 + timedelta(days=1), 45000, "DEBIT", moyen="VIR_SEPA",
        libelle="VIREMENT URGENT", pays="AE", cp="NEW TRADE FZE")

    # S20 — petits transferts vers zone à risque (FT) + montants identiques répétés
    for k in range(4):
        add("S20", "NOUR KARIM", t0 + timedelta(days=3 * k), 150, "DEBIT", moyen="VIR_SEPA",
            pays="SY", libelle="ENVOI FAMILLE", cp="BENEF SY")
    for k in range(5):
        add("S20", "NOUR KARIM", t0 + timedelta(days=2 * k), 990, "DEBIT", moyen="VIR_SEPA", cp=f"B{k}")

    # S21 — fractionnement sous le seuil de 3 000 €
    for k in range(4):
        add("S21", "COLIN MARIE", t0 + timedelta(hours=10 * k), rng.uniform(2600, 2990), "CREDIT",
            moyen="VIR_SEPA", cp=f"DONNEUR {k}")

    # S22 — usurpation d'entité publique : « DGFIP » mais IBAN étranger (faux RIB)
    add("S22", "ATELIER MODERNE SARL", t0, 4800, "DEBIT", moyen="VIR_SEPA", pays="NG",
        libelle="REGULARISATION URGENTE DGFIP", cp="NG93 0000 1111 2222 3333")
    # S23 — cas légitimes (aucune alerte) : impôt vers la DGFiP française, loyer récurrent
    add("S23", "SCI DU PARC", t0, 5200, "DEBIT", moyen="VIR_SEPA", pays="FR",
        libelle="PAIEMENT IMPOT DGFIP", cp="FR76 1000 0000 0000 0000 0000 001")
    add("S23", "SCI DU PARC", t0 + timedelta(days=1), 1200, "DEBIT", moyen="PRELEVEMENT", libelle="LOYER OCTOBRE",
        cp="BAILLEUR HABITUEL")

    # Opérations techniques exclues
    add("C001", "CLIENT NORMAL 01", t0, 4.5, "DEBIT", libelle="FRAIS DE TENUE DE COMPTE")
    add("C002", "CLIENT NORMAL 02", t0, 12.0, "DEBIT", libelle="COMMISSION")

    df = pd.DataFrame(rows, columns=COLUMNS).sort_values("DATE").reset_index(drop=True)
    df["ID_TRANSACTION"] = [f"T{i + 1:05d}" for i in range(len(df))]
    return df


def template_dataframe() -> pd.DataFrame:
    """Modèle de fichier : en-têtes complets + quelques lignes d'exemple."""
    return demo_dataframe().head(5)
