"""
Mock I-Way API Router — Simulates I-Way's insurance backend.

These endpoints represent I-Way's real systems that your Digital Twin
consumes via API calls. In production, these would be replaced by
actual I-Way service endpoints.

Routes:
  GET  /api/v1/knowledge-base
  GET  /api/v1/me
  GET  /api/v1/adherent/dossiers
  GET  /api/v1/adherent/beneficiaires
  GET  /api/v1/prestations
  GET  /api/v1/remboursements
  GET  /api/v1/reclamations
  POST /api/v1/reclamations
  POST /api/v1/support/escalade
"""

import uuid
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field

from backend.routers.auth import get_current_user, MOCK_USERS

logger = logging.getLogger("I-Way-Twin")

router = APIRouter(prefix="/api/v1", tags=["I-Way Mock API"])

# ==========================================================================
# KNOWLEDGE BASE — 30+ realistic I-Santé insurance Q&A entries
# ==========================================================================

MOCK_KB = [
    # ── Soins Dentaires ──
    {"id": 1, "question": "Quel est le plafond annuel pour les soins dentaires ?", "reponse": "Selon l'Article 4 de la convention, le plafond annuel pour les soins dentaires est de 600 TND par beneficiaire. Les protheses dentaires sont couvertes a 70% dans la limite de ce plafond. Les soins orthodontiques pour les enfants de moins de 16 ans beneficient d'un plafond supplementaire de 400 TND.", "cible": "Adherent", "tags": ["dentaire", "plafond", "couverture"]},
    {"id": 2, "question": "Quels soins dentaires sont couverts par I-Way ?", "reponse": "Les soins dentaires couverts comprennent: les consultations (100%), les soins conservateurs comme les plombages et detartrages (80%), les extractions simples (80%), les protheses dentaires fixes et amovibles (70% avec plafond de 600 TND), et les implants dentaires (50% avec plafond de 1000 TND par implant). Les soins esthetiques dentaires (blanchiment, facettes) ne sont pas couverts.", "cible": "Adherent", "tags": ["dentaire", "couverture", "soins"]},
    {"id": 3, "question": "Comment obtenir un accord prealable pour une prothese dentaire ?", "reponse": "Pour les protheses dentaires dont le montant depasse 200 TND, un accord prealable est requis. Envoyez le devis detaille du dentiste via votre espace 'Mes Prestations' > 'Demande d'accord prealable'. Le delai de reponse est de 48h ouvrees. En cas de non-reponse sous 5 jours ouvres, l'accord est considere comme tacitement accepte.", "cible": "Adherent", "tags": ["dentaire", "accord", "prothese"]},

    # ── Soins Optiques ──
    {"id": 4, "question": "Quels sont les plafonds pour les soins optiques ?", "reponse": "Les soins optiques sont couverts avec un plafond de 250 TND par an pour les verres et montures. Les lentilles de contact sont couvertes a hauteur de 150 TND par an sur prescription medicale. Le renouvellement est autorise tous les 2 ans sauf changement de correction superieur a 0.5 dioptrie. Les verres progressifs beneficient d'un supplement de 100 TND.", "cible": "Adherent", "tags": ["optique", "lunettes", "plafond", "lentilles"]},
    {"id": 5, "question": "Mon enfant a besoin de lunettes, quelle est la couverture ?", "reponse": "Pour les enfants de moins de 18 ans, les lunettes sont renouvelables chaque annee (au lieu de 2 ans pour les adultes). Le plafond est de 200 TND pour les montures et verres combines. Les verres anti-reflet et anti-lumiere bleue sont couverts a 100% pour les enfants scolarises sur presentation d'un certificat de scolarite.", "cible": "Adherent", "tags": ["optique", "enfant", "lunettes"]},

    # ── Pharmacie et Medicaments ──
    {"id": 6, "question": "Comment se faire rembourser les medicaments ?", "reponse": "Les medicaments prescrits sont rembourses a 80% pour les medicaments generiques et 60% pour les medicaments de marque. Les medicaments de confort ne sont pas couverts. Presentez votre ordonnance et la facture de la pharmacie via l'espace 'Remboursements'. Les medicaments a usage hospitalier sont couverts a 100% dans le cadre d'une hospitalisation.", "cible": "Adherent", "tags": ["pharmacie", "medicaments", "remboursement"]},
    {"id": 7, "question": "Existe-t-il un tiers payant pour les pharmacies ?", "reponse": "Oui, I-Way dispose d'un reseau de 450 pharmacies conventionnees en Tunisie offrant le tiers payant. Presentez votre carte d'adherent I-Way et vous ne payez que la part restante (20% pour les generiques, 40% pour les marques). La liste des pharmacies partenaires est disponible dans l'application I-Way Mobile ou sur le site web.", "cible": "Adherent", "tags": ["pharmacie", "tiers payant", "reseau"]},

    # ── Remboursements et Delais ──
    {"id": 8, "question": "Quel est le delai de remboursement ?", "reponse": "Les remboursements sont traites sous 48h ouvrees pour les feuilles de soins electroniques (FSE). Les feuilles papier peuvent prendre jusqu'a 15 jours ouvres. Les virements sont effectues sur le RIB enregistre dans votre espace. Vous recevez une notification par SMS et email a chaque virement. Les remboursements superieurs a 500 TND peuvent necessiter une verification supplementaire.", "cible": "Adherent", "tags": ["finance", "delai", "remboursement"]},
    {"id": 9, "question": "Comment suivre l'etat de mon remboursement ?", "reponse": "Connectez-vous a votre espace adherent et rendez-vous dans 'Mes Remboursements'. Chaque demande affiche un statut: En attente d'analyse, En cours de traitement, Valide, Vire, ou Rejete. En cas de rejet, le motif est indique et vous avez 30 jours pour fournir les pieces manquantes via la messagerie securisee.", "cible": "Adherent", "tags": ["remboursement", "suivi", "statut"]},

    # ── Maternite et Naissance ──
    {"id": 10, "question": "Quelle est la prime de naissance ?", "reponse": "La prime de naissance est de 300 TND par enfant, versee sur presentation de l'acte de naissance dans un delai de 30 jours suivant la naissance. En cas de naissances multiples, la prime est versee pour chaque enfant. La demande se fait via l'espace 'Mes Prestations' > 'Prime de naissance'. Les pieces requises: acte de naissance et certificat medical.", "cible": "Adherent", "tags": ["naissance", "prime", "famille"]},
    {"id": 11, "question": "Comment fonctionne le conge maternite ?", "reponse": "Le conge maternite est de 30 jours avant la date prevue et 40 jours apres l'accouchement. Les frais d'accouchement sont couverts a 100% dans les cliniques conventionnees. Les visites prenatales (8 consultations) et les echographies de suivi (3 echographies) sont prises en charge integralement. L'indemnite journaliere de maternite est egale a 66% du salaire moyen des 3 derniers mois.", "cible": "Adherent", "tags": ["maternite", "conge", "accouchement"]},
    {"id": 12, "question": "La FIV est-elle prise en charge ?", "reponse": "La fecondation in vitro (FIV) est couverte a 50% dans la limite de 3 tentatives, avec un plafond de 2000 TND par tentative. Les conditions: la patiente doit avoir moins de 43 ans, une ordonnance d'un specialiste en PMA, et un accord prealable du medecin conseil I-Way. Les examens prealables (bilans hormonaux, spermogramme) sont couverts a 80%.", "cible": "Adherent", "tags": ["maternite", "FIV", "fertilite"]},

    # ── Hospitalisation ──
    {"id": 13, "question": "Comment fonctionne la prise en charge hospitaliere ?", "reponse": "L'hospitalisation est couverte a 90% dans les etablissements conventionnes et 70% hors convention. Une entente prealable est obligatoire pour les hospitalisations programmees (delai de reponse: 48h). Les urgences sont prises en charge directement sur presentation de la carte d'adherent. La chambre individuelle est couverte avec un supplement de 50 TND/jour. Les frais d'accompagnant pour les enfants de moins de 12 ans sont couverts a 100%.", "cible": "Adherent", "tags": ["hospitalisation", "couverture", "urgence"]},
    {"id": 14, "question": "Que couvre l'hospitalisation ambulatoire ?", "reponse": "L'hospitalisation de jour (ambulatoire) est couverte a 85% sans necessiter d'accord prealable pour les actes de la nomenclature standard. Cela inclut: les chirurgies en ambulatoire, les chimiotherapies, les seances de dialyse, et les examens sous anesthesie. Le reste a charge est limite a 15% du tarif conventionne.", "cible": "Adherent", "tags": ["hospitalisation", "ambulatoire", "chirurgie"]},

    # ── Urgences ──
    {"id": 15, "question": "Que faire en cas d'urgence medicale ?", "reponse": "En cas d'urgence, rendez-vous aux services d'urgence les plus proches. Les frais seront pris en charge a 100% sur presentation de votre carte d'adherent. Si vous etes hospitalise en urgence, contactez le service client dans les 48h pour la prise en charge. Le numero d'urgence I-Way est le 71 800 800, disponible 24h/24 et 7j/7.", "cible": "Adherent", "tags": ["urgence", "hospitalisation", "contact"]},
    {"id": 16, "question": "Suis-je couvert pour une urgence a l'etranger ?", "reponse": "Oui, I-Way couvre les urgences medicales a l'etranger dans le cadre de la garantie 'Assistance Internationale'. La couverture inclut: les frais medicaux d'urgence (plafond 5000 EUR), le rapatriement sanitaire, et l'hospitalisation d'urgence. Contactez le numero d'assistance internationale +216 71 800 801 avant toute intervention. Une franchise de 100 EUR s'applique.", "cible": "Adherent", "tags": ["urgence", "etranger", "assistance"]},

    # ── Maladies Chroniques ──
    {"id": 17, "question": "Quelles sont les conditions pour les maladies chroniques ?", "reponse": "Les maladies chroniques (diabete, hypertension, asthme, etc.) beneficient d'une prise en charge a 100% apres validation du dossier par le medecin conseil. Le protocole de soins doit etre renouvele chaque annee. Les analyses de suivi trimestrielles sont couvertes integralement. La liste des 30 maladies chroniques reconnues est disponible sur le site I-Way.", "cible": "Adherent", "tags": ["chronique", "maladie", "couverture"]},
    {"id": 18, "question": "Comment declarer une maladie chronique ?", "reponse": "Pour declarer une maladie chronique: 1) Demandez a votre medecin traitant un certificat medical detaille, 2) Remplissez le formulaire 'Declaration ALD' disponible dans votre espace, 3) Joignez les resultats d'examens (datant de moins de 3 mois), 4) Envoyez le dossier complet. Le medecin conseil I-Way etudie votre dossier sous 10 jours ouvres.", "cible": "Adherent", "tags": ["chronique", "declaration", "ALD"]},

    # ── Administration et Beneficiaires ──
    {"id": 19, "question": "Comment ajouter un beneficiaire ?", "reponse": "Rendez-vous dans l'espace 'Ma Famille', cliquez sur 'Ajouter' et telechargez l'acte de naissance ou le livret de famille. Le beneficiaire sera actif sous 24h apres validation. Les beneficiaires eligibles: conjoint, enfants jusqu'a 21 ans (26 ans si etudiant), et parents a charge. Le cout supplementaire est de 15 TND/mois par beneficiaire.", "cible": "Adherent", "tags": ["administratif", "famille", "beneficiaire"]},
    {"id": 20, "question": "Comment obtenir ma carte d'adherent I-Way ?", "reponse": "Votre carte d'adherent est envoyee automatiquement dans les 10 jours suivant votre inscription. En cas de perte ou de non-reception, vous pouvez demander un duplicata via 'Mon Compte' > 'Ma Carte'. Le duplicata coute 10 TND et est envoye sous 5 jours. En attendant, vous pouvez utiliser la carte virtuelle dans l'application I-Way Mobile.", "cible": "Adherent", "tags": ["carte", "adherent", "duplicata"]},
    {"id": 21, "question": "Comment modifier mes coordonnees bancaires pour les remboursements ?", "reponse": "Pour modifier votre RIB: rendez-vous dans 'Mon Compte' > 'Informations bancaires'. Telechargez un RIB au format PDF ou une photo lisible. La modification prend effet sous 48h ouvrees. Attention: le RIB doit etre au nom de l'adherent principal. Pour les virements vers un compte tiers, une autorisation notariee est requise.", "cible": "Adherent", "tags": ["RIB", "banque", "compte"]},

    # ── Prestataires ──
    {"id": 22, "question": "Comment devenir prestataire conventionne I-Way ?", "reponse": "Pour devenir prestataire conventionne, soumettez votre dossier via le portail prestataire avec: copie du diplome, inscription a l'ordre, RIB professionnel, et attestation d'assurance RC. La commission de conventionnement se reunit mensuellement. Le taux de conventionnement varie selon la specialite. Les avantages: paiement garanti sous 72h et acces au tiers payant.", "cible": "Prestataire", "tags": ["convention", "prestataire", "inscription"]},
    {"id": 23, "question": "Comment facturer un acte hors nomenclature ?", "reponse": "Utilisez le code HN dans le formulaire de prestation et joignez le devis signe par le patient. L'accord prealable de la mutuelle est requis pour tout montant superieur a 200 TND. Le delai de reponse pour les accords prealables est de 48h ouvrees. Les actes HN sont rembourses selon le bareme I-Way applicable.", "cible": "Prestataire", "tags": ["facturation", "technique", "nomenclature"]},
    {"id": 24, "question": "Quel est le delai de paiement pour les prestataires ?", "reponse": "Les prestataires conventionnes sont payes sous 72h ouvrees apres validation de la facture electronique. Les factures papier necessitent un delai de 15 jours ouvres. Les bordereaux de paiement sont accessibles dans le portail prestataire. En cas de contestation, le prestataire dispose de 60 jours pour formuler une reclamation.", "cible": "Prestataire", "tags": ["paiement", "prestataire", "delai"]},

    # ── Reclamations et Support ──
    {"id": 25, "question": "Comment deposer une reclamation ?", "reponse": "Vous pouvez deposer une reclamation via: 1) L'espace 'Mes Reclamations' sur le site web, 2) L'application mobile I-Way, 3) Par courrier recommande a la Direction Qualite, 4) Par telephone au 71 800 800 (option 3). Chaque reclamation recoit un numero de reference et un accuse de reception sous 24h. Le delai de traitement est de 10 jours ouvres maximum.", "cible": "Adherent", "tags": ["reclamation", "support", "qualite"]},
    {"id": 26, "question": "Je ne suis pas satisfait d'un remboursement, que faire ?", "reponse": "Si vous contestez un montant de remboursement: 1) Verifiez le detail du calcul dans 'Mes Remboursements', 2) Si desaccord, cliquez sur 'Contester ce remboursement', 3) Joignez les justificatifs supplementaires, 4) Le service medical re-examine votre dossier sous 5 jours. En dernier recours, vous pouvez saisir le mediateur I-Way par courrier recommande.", "cible": "Adherent", "tags": ["contestation", "remboursement", "mediateur"]},

    # ── Prevention et Check-up ──
    {"id": 27, "question": "I-Way propose-t-il des bilans de sante gratuits ?", "reponse": "Oui, I-Way offre un bilan de sante annuel gratuit pour tous les adherents de plus de 40 ans. Ce bilan comprend: analyse sanguine complete, electrocardiogramme, controle ophtalmologique, et consultation medecin generaliste. Pour les femmes de plus de 50 ans, une mammographie est incluse. Prenez rendez-vous via 'Prevention' > 'Bilan annuel'.", "cible": "Adherent", "tags": ["prevention", "bilan", "sante"]},
    {"id": 28, "question": "Les vaccins sont-ils couverts ?", "reponse": "Les vaccins obligatoires du calendrier vaccinal tunisien sont couverts a 100% pour les adherents et leurs beneficiaires. Les vaccins recommandes (grippe saisonniere, hepatite B, HPV) sont couverts a 80%. Le vaccin contre la grippe est gratuit pour les adherents de plus de 65 ans et les personnes atteintes de maladies chroniques.", "cible": "Adherent", "tags": ["vaccin", "prevention", "couverture"]},

    # ── Adhesion et Contrats ──
    {"id": 29, "question": "Comment resilier mon contrat I-Way ?", "reponse": "La resiliation est possible a la date anniversaire du contrat avec un preavis de 2 mois. Envoyez un courrier recommande a la Direction Commerciale. En cas de changement d'employeur, le contrat est automatiquement suspendu. Le portage des droits est possible pendant 12 mois apres la fin du contrat moyennant le paiement de la cotisation a titre individuel.", "cible": "Adherent", "tags": ["resiliation", "contrat", "portabilite"]},
    {"id": 30, "question": "Quelles sont les formules disponibles chez I-Way ?", "reponse": "I-Way propose 3 formules: 1) Essentielle (35 TND/mois): couverture de base soins courants + hospitalisation, 2) Confort (55 TND/mois): formule Essentielle + optique + dentaire + prevention, 3) Gold (85 TND/mois): couverture complete incluant assistance internationale, tiers payant etendu, et plafonds doubles. Toutes les formules incluent le tiers payant en pharmacie.", "cible": "Adherent", "tags": ["formule", "tarif", "adhesion"]},

    # ── Kinesitherapie et Reeducation ──
    {"id": 31, "question": "Combien de seances de kinesitherapie sont couvertes ?", "reponse": "I-Way couvre jusqu'a 30 seances de kinesitherapie par an a 70% du tarif conventionne. Au-dela de 30 seances, une demande d'accord prealable avec certificat medical detaille est necessaire. Les seances post-operatoires sont couvertes a 100% dans la limite de 60 seances. La reeducation fonctionnelle en centre specialise est couverte a 90%.", "cible": "Adherent", "tags": ["kinesitherapie", "reeducation", "seances"]},

    # ── Analyses et Imagerie ──
    {"id": 32, "question": "Les IRM et scanners sont-ils couverts ?", "reponse": "Les examens d'imagerie medicale sont couverts comme suit: radiographies standard (100%), echographies (90%), scanners (80%), IRM (80% avec accord prealable). L'accord prealable pour IRM est delivre sous 24h. Les examens de medecine nucleaire (scintigraphie, PET-scan) necessitent toujours un accord prealable du medecin conseil.", "cible": "Adherent", "tags": ["imagerie", "IRM", "scanner", "radiologie"]},
    {"id": 33, "question": "Quelles analyses de laboratoire sont couvertes ?", "reponse": "Toutes les analyses prescrites par un medecin sont couvertes a 80% dans les laboratoires conventionnes. Les analyses de routine (NFS, glycemie, bilan lipidique) sont couvertes a 100% dans le cadre du bilan annuel. Les analyses genetiques et les tests rares necessitent un accord prealable. Le tiers payant est disponible dans 120 laboratoires partenaires.", "cible": "Adherent", "tags": ["analyses", "laboratoire", "biologie"]},
]

# ==========================================================================
# PER-USER MOCK DATA — Rich test data for each persona
# ==========================================================================

MOCK_BENEFICIAIRES = {
    "12345": [
        {"id": "B1", "nom": "Mansour", "prenom": "Sami", "lien": "Enfant", "date_naissance": "2015-06-12", "age": 11, "scolarise": True},
        {"id": "B2", "nom": "Mansour", "prenom": "Karim", "lien": "Conjoint", "date_naissance": "1980-04-23"},
        {"id": "B3", "nom": "Mansour", "prenom": "Lina", "lien": "Enfant", "date_naissance": "2019-11-08", "age": 7, "scolarise": True},
    ],
    "99999": [
        {"id": "B4", "nom": "Zaid", "prenom": "Yasmine", "lien": "Conjoint", "date_naissance": "1982-09-15"},
    ]
}

MOCK_DOSSIERS = {
    "12345": [
        {"id": "DOS-8892", "type": "Santé Gold", "statut": "Actif", "date_effet": "2023-01-01", "formule": "Gold", "prime_mensuelle": "85 TND", "beneficiaires": 4},
        {"id": "DOS-9901", "type": "Prévoyance Famille", "statut": "Actif", "date_effet": "2024-03-01", "formule": "Confort", "prime_mensuelle": "55 TND"},
        {"id": "DOS-7543", "type": "Assistance Internationale", "statut": "Actif", "date_effet": "2024-01-01", "couverture": "Europe + Turquie"},
    ],
    "99999": [
        {"id": "DOS-P001", "type": "Convention Prestataire", "statut": "Actif", "date_effet": "2022-06-01", "specialite": "Cardiologie", "taux_conventionnement": "92%"},
    ],
}

MOCK_PRESTATIONS = {
    "12345": [
        {"id": "PREST-101", "date": "2024-02-10", "acte": "Consultation Généraliste", "medecin": "Dr. Mahjoub", "montant": 45.00, "rembourse": 36.00, "statut": "Remboursé"},
        {"id": "PREST-102", "date": "2024-03-15", "acte": "Détartrage Dentaire", "medecin": "Dr. Chaabane", "montant": 80.00, "rembourse": 64.00, "statut": "Remboursé"},
        {"id": "PREST-103", "date": "2024-04-02", "acte": "Echographie Abdominale", "medecin": "Dr. Ben Salah", "montant": 120.00, "rembourse": 108.00, "statut": "Remboursé"},
        {"id": "PREST-104", "date": "2024-04-10", "acte": "Consultation Ophtalmologue", "medecin": "Dr. Trabelsi", "montant": 65.00, "rembourse": 52.00, "statut": "En cours"},
        {"id": "PREST-105", "date": "2024-04-12", "acte": "Analyses Sanguines (Bilan lipidique)", "medecin": "Lab. Pasteur", "montant": 55.00, "rembourse": 44.00, "statut": "En cours"},
    ],
    "99999": [
        {"id": "PREST-550", "date": "2024-02-14", "acte": "Echographie Cardiaque", "patient": "Mme. Ben Ali", "montant": 150.00, "statut": "Facturé"},
        {"id": "PREST-551", "date": "2024-03-20", "acte": "ECG de repos", "patient": "M. Gharbi", "montant": 80.00, "statut": "Facturé"},
        {"id": "PREST-552", "date": "2024-04-05", "acte": "Consultation Cardiologique", "patient": "Mme. Jlassi", "montant": 90.00, "statut": "En attente"},
    ],
}

MOCK_REMBOURSEMENTS = {
    "12345": [
        {"id": "VIR-2024-01", "date": "2024-02-12", "montant": 36.00, "motif": "Consultation Dr. Mahjoub", "status": "Payé", "rib": "****4521"},
        {"id": "VIR-2024-02", "date": "2024-03-18", "montant": 64.00, "motif": "Détartrage Dr. Chaabane", "status": "Payé", "rib": "****4521"},
        {"id": "VIR-2024-03", "date": "2024-04-05", "montant": 108.00, "motif": "Echographie Dr. Ben Salah", "status": "Payé", "rib": "****4521"},
        {"id": "VIR-2024-04", "date": "2024-04-15", "montant": 96.00, "motif": "Ophtalmologue + Analyses", "status": "En traitement", "rib": "****4521"},
    ],
    "99999": [
        {"id": "VIR-P-01", "date": "2024-03-01", "montant": 230.00, "motif": "Bordereau Février 2024 (3 actes)", "status": "Payé"},
        {"id": "VIR-P-02", "date": "2024-04-01", "montant": 170.00, "motif": "Bordereau Mars 2024 (2 actes)", "status": "Payé"},
    ]
}

MOCK_RECLAMATIONS = {
    "12345": [
        {"id": "TICKET-001", "date": "2023-12-01", "objet": "Carte non reçue", "statut": "Clôturé", "resolution": "Duplicata envoyé le 05/12/2023"},
        {"id": "TICKET-002", "date": "2024-03-10", "objet": "Remboursement tarif hors convention", "statut": "En cours", "resolution": None},
    ],
    "99999": [
        {"id": "TICKET-P01", "date": "2024-02-20", "objet": "Retard de paiement bordereau Janvier", "statut": "Clôturé", "resolution": "Virement effectué le 25/02"},
    ]
}

MOCK_ESCALATION_TICKETS = []


# --- Pydantic Models ---

class ReclamationInput(BaseModel):
    matricule: str
    objet: str
    message: str
    piece_jointe_base64: Optional[str] = None

class EscaladeInput(BaseModel):
    matricule: str
    conversation_id: str = Field(default_factory=lambda: f"conv-{uuid.uuid4().hex[:8]}")
    chat_history: List[Dict[str, Any]] = Field(..., description="Full JSON history of the chat")
    reason: Optional[str] = "User request"


# --- Endpoints ---

@router.get("/knowledge-base", tags=["RAG Source"])
async def get_knowledge_base():
    """Extrait l'ensemble des règles métier pour l'indexation vectorielle."""
    return {"count": len(MOCK_KB), "items": MOCK_KB}


@router.get("/me", tags=["Profile"])
async def get_me(matricule: str = Depends(get_current_user)):
    """Récupère les informations d'identité de l'utilisateur connecté."""
    user = MOCK_USERS[matricule]
    return {k: v for k, v in user.items() if k != "password"}


@router.get("/adherent/dossiers", tags=["Métier"])
async def get_dossiers(matricule: str = Depends(get_current_user)):
    return MOCK_DOSSIERS.get(matricule, [])


@router.get("/adherent/beneficiaires", tags=["Métier"])
async def get_beneficiaires(matricule: str = Depends(get_current_user)):
    return MOCK_BENEFICIAIRES.get(matricule, [])


@router.get("/prestations", tags=["Métier"])
async def get_prestations(matricule: str = Depends(get_current_user)):
    return MOCK_PRESTATIONS.get(matricule, [])


@router.get("/remboursements", tags=["Métier"])
async def get_remboursements(matricule: str = Depends(get_current_user)):
    return MOCK_REMBOURSEMENTS.get(matricule, [])


@router.get("/reclamations", tags=["Support"])
async def get_reclamations_history(matricule: str = Depends(get_current_user)):
    return MOCK_RECLAMATIONS.get(matricule, [])


@router.post("/reclamations", tags=["Support"])
async def create_reclamation(data: ReclamationInput, matricule: str = Depends(get_current_user)):
    new_ticket = {
        "id": f"TICKET-{uuid.uuid4().hex[:6].upper()}",
        "date": datetime.now().strftime("%Y-%m-%d"),
        "objet": data.objet,
        "statut": "Ouvert",
        "message_preview": data.message[:50] + "..."
    }
    if data.matricule not in MOCK_RECLAMATIONS:
        MOCK_RECLAMATIONS[data.matricule] = []
    MOCK_RECLAMATIONS[data.matricule].append(new_ticket)
    logger.info(f"📩 New Reclamation from {data.matricule}: {data.objet}")
    return {"status": "success", "ticket": new_ticket}


@router.post("/support/escalade", tags=["Support"])
async def escalate_to_human(data: EscaladeInput, matricule: str = Depends(get_current_user)):
    logger.warning(f"🚨 ESCALATION TRIGGERED for {data.matricule}")
    user = MOCK_USERS.get(data.matricule, {})
    ticket = {
        "case_id": f"CASE-{uuid.uuid4().hex[:8]}",
        "status": "escalated",
        "queue_position": 2,
        "estimated_wait": "5 minutes",
        "matricule": data.matricule,
        "client_name": f"{user.get('prenom', '')} {user.get('nom', '')}".strip(),
        "client_role": user.get("role", "Unknown"),
        "reason": data.reason,
        "chat_history": data.chat_history,
        "created_at": datetime.now().isoformat()
    }
    MOCK_ESCALATION_TICKETS.append(ticket)
    return {
        "status": "escalated",
        "queue_position": ticket["queue_position"],
        "estimated_wait": ticket["estimated_wait"],
        "case_id": ticket["case_id"]
    }


@router.get("/dashboard/tickets", tags=["Dashboard"])
async def get_escalation_tickets(matricule: str = Depends(get_current_user)):
    return MOCK_ESCALATION_TICKETS
