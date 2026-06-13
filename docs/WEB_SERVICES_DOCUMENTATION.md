# Documentation des Web Services SOAP — MEG ERP (iWay)

> **Note (copie versionnee) :** les identifiants de test reels (matricule, police, idTiers)
> ont ete remplaces par des placeholders. Les vraies valeurs restent dans `web-s/` (local, gitignore).


> **Base URL:** `http://192.168.111.102:8080/axis2/services/`
> **Protocole:** SOAP 1.1 / SOAP 1.2 over HTTP POST
> **Authentification:** Basic Auth (`admin` / `admin`)
> **Content-Type:** `text/xml`
> **Namespace:** `http://ws.meg.tn`
> **Dernière mise à jour :** 2026-06-12 16:44
> **Données test :** Adhérent matricule `<MATRICULE_TEST>`, police `<NUM_POLICE_TEST>`, PS idTiers `<ID_TIERS_TEST>`

---

## Table des Matières

1. [Vue d'ensemble](#vue-densemble)
2. [contratAdherentWSMeg](#1-contratadherentwsmeg) — 9 ops — Contrats adhérents
3. [contratPsWS](#2-contratpsws) — 5 ops — Contrats PS
4. [reclamationWS](#3-reclamationws) — 9 ops — Réclamations
5. [remboursementAdherentWS](#4-remboursementadherentws) — 12 ops — Remboursements
6. [rechercheSpecialiteWS](#5-recherchespecialitews) — 10 ops — Recherche PS / Villes / Spécialités
7. [centreSmiWS](#6-centresmmiws) — 5 ops — Centres SMI & Planning médecins
8. [rendezVousAdherentWS](#7-rendezVousadherentws) — 1 op — Prise de RDV
9. [medecinConseilWS](#8-medecinconseilws) — 3 ops — Médecin conseil
10. [medecinConventionneWS](#9-medecinconventionnews) — 2 ops — Planning médecin conventionné
11. [facturePsWS](#10-facturepsws) — 39 ops — Facturation PS (Tiers Payant)
12. [prestatiareWS](#11-prestatiarews) — 3 ops — Montants remboursement PS
13. [decompteWS](#12-decomptews) — 16 ops — Décomptes de prestations
14. [bordereauxWS](#13-bordereauxws) — 2 ops — Bordereaux
15. [declarationSalaireWS](#14-declarationsalairews) — 3 ops — Déclarations de salaire
16. [referentielWS](#15-referentielws) — 2 ops — Référentiel (tables de codes)
17. [factureWS](#16-facturews) — 2 ops — Recherche factures adhérent
18. [actePhRcWS](#17-actephrcws) — 1 op — Actes pharmaceutiques
19. [PrestationPrevoyance](#18-prestationprevoyance) — 1 op — Prestations prévoyance
20. [prestationExecuteNextTaskWS](#19-prestationexecutenexttaskws) — 1 op — Workflow engine
21. [Version](#20-version) — 1 op — Version API
22. [Cat](#21-cat) — 15 ops — Utilitaires système (interne)
23. [Modèles de données](#modèles-de-données-dtos)
24. [Codes de référentiel](#codes-de-référentiel-courants)
25. [Notes d'intégration](#notes-dintégration)

---

## Vue d'ensemble

Le système MEG expose **21 Web Services SOAP** via Apache Axis2, totalisant **142 opérations**.
**Données offline capturées :** ~46 réponses XML valides (~4.8 MB).

| # | Service | Ops | Testées ✅ | Pertinence chatbot | Description |
|---|---------|-----|-----------|-------------------|-------------|
| 1 | `contratAdherentWSMeg` | 9 | 3 | ✅ Adhérent | Contrats adhérents |
| 2 | `contratPsWS` | 5 | 2 | ✅ PS | Contrats prestataires |
| 3 | `reclamationWS` | 9 | 2 | ✅ Adhérent | Gestion réclamations |
| 4 | `remboursementAdherentWS` | 12 | 4 | ✅ Adhérent | Remboursements |
| 5 | `rechercheSpecialiteWS` | 10 | 8 | ✅ Both | Recherche PS, villes, spécialités |
| 6 | `centreSmiWS` | 5 | 0 | ✅ Both | Centres SMI, planning médecins |
| 7 | `rendezVousAdherentWS` | 1 | 0 | ✅ Adhérent | Prise de rendez-vous |
| 8 | `medecinConseilWS` | 3 | 1 | ✅ PS | Avis médecin conseil |
| 9 | `medecinConventionneWS` | 2 | 0 | ✅ PS | Planning médecin conventionné |
| 10 | `facturePsWS` | 39 | 3 | ✅ PS | Facturation PS (tiers payant) |
| 11 | `prestatiareWS` | 3 | 1 | ✅ PS | Montants remboursement PS |
| 12 | `decompteWS` | 16 | 1 | ⚠️ Back-office | Détails décomptes (dentaire, pharma, optique) |
| 13 | `bordereauxWS` | 2 | 1 | ⚠️ Back-office | Bordereaux par police |
| 14 | `declarationSalaireWS` | 3 | 0 | ⚠️ Entreprise | Déclarations de salaire |
| 15 | `referentielWS` | 2 | 14 | ✅ Both | Tables de référence (codes) |
| 16 | `factureWS` | 2 | 2 | ⚠️ Adhérent | Recherche factures |
| 17 | `actePhRcWS` | 1 | 1 | ⚠️ Référence | Actes pharmaceutiques |
| 18 | `PrestationPrevoyance` | 1 | 0 | ❌ Interne | Création don prévoyance |
| 19 | `prestationExecuteNextTaskWS` | 1 | 0 | ❌ Interne | Moteur workflow |
| 20 | `Version` | 1 | 1 | ❌ Diagnostic | Version API |
| 21 | `Cat` | 15 | 0 | ❌ Système | Utilitaires système |

### Analyse des faults — Pourquoi certaines opérations échouent

| Code Fault | Signification | Opérations affectées | Corrigeable ? |
|------------|--------------|---------------------|---------------|
| **2** | Aucun résultat — données vides | `getListeBeneficiairesByMatricule` | ❌ Besoin d'un adhérent avec bénéficiaires |
| **3** | Données introuvables | `getHistoriqueConsommation`, `getListPlafondBeneficiairesByMatricule`, `declarationSalaireWS`, `facturePsWS` (×2), `medecinConventionneWS` | ❌ Besoin de données PS/adhérent actives |
| **4** | Prestation introuvable | `getPrestationsByIdPs`, `getPrestationsByIdPsAll` | ❌ Besoin d'un PS avec prestations |
| **5** | Bénéficiaire introuvable | `getMontantDisponibleByBenef` | ❌ Besoin d'un idBenef valide |
| **9** | Police invalide/inexistante | `getAdhesionByNumPolice` | ❌ Police n'a pas d'adhésions |
| **13** | Réclamation introuvable | `getListReclamationByMatricule` | ❌ Adhérent <MATRICULE_TEST> n'a pas de réclamations |
| **1** | Paramètre invalide / pas de résultat | `getPsByNomOrMatriculeFiscal`, `getContratPsByMatriculeFiscalOrCodeCnam`, `getListPsByListGouv` | ⚠️ Peut fonctionner avec d'autres données de test |
| **"Cannot open connection"** | Pool BDD saturé côté serveur | `getListPs` | ❌ Bug serveur |
| **"No enum const class"** | Bug code serveur | `getListPm` | ❌ Bug serveur |
| **"unknown" + DataNotFoundException** | Données manquantes | `centreSmiWS`, `getAdherentByMatriculeNomPrenom` | ❌ Pas de centres SMI configurés |

> **Conclusion :** Aucune opération n'est bloquée par un mauvais paramétrage de notre côté.
> Tous les faults sont dus à des **données de test manquantes** sur le serveur ou des **bugs serveur**.

---

## 1. contratAdherentWSMeg

**Endpoint:** `http://192.168.111.102:8080/axis2/services/contratAdherentWSMeg`

### 1.1 `getContratAdherentByMatricule` ✅

Contrat complet d'un adhérent.

| Paramètre | Type | Obligatoire | Description |
|-----------|------|-------------|-------------|
| `matricule` | `string` | ✅ | Matricule MEG (ex: `<MATRICULE_TEST>`) |
| `numPolice` | `string` | ✅ | Numéro de police (ex: `<NUM_POLICE_TEST>`) |
| `codeSpec` | `string` | ❌ | Code spécialité |

```xml
<ns1:getContratAdherentByMatricule>
  <ns1:matricule><MATRICULE_TEST></ns1:matricule>
  <ns1:numPolice><NUM_POLICE_TEST></ns1:numPolice>
  <ns1:codeSpec/>
</ns1:getContratAdherentByMatricule>
```

**Retour : `ContratAdherentWsDto`** (340 KB) — contrat, personne physique (nom, CIN, DOB), personne morale (entreprise), police, infos complémentaires (situation, plafond).

### 1.2 `getContratAdherentByMatriculeEntity` ✅

Identique à 1.1, retourne les entités modèle. Mêmes paramètres.

### 1.3 `getListeBeneficiairesByMatricule` ❌ FAULT 2 — Adhérent <MATRICULE_TEST> n'a pas de bénéficiaires

| Paramètre | Type | Obligatoire |
|-----------|------|-------------|
| `matricule` | `string` | ✅ |
| `numPolice` | `string` | ✅ |

**Retour :** Liste de bénéficiaires (conjoint, enfants) — `nom`, `prenom`, `lienParental`, `situationBenef`, `rang`.

### 1.4 `getListPlafondBeneficiairesByMatricule` ❌ FAULT 3 — Pas de bénéficiaires

Mêmes paramètres que 1.3. **Retour :** Plafonds par bénéficiaire — `montantPlafond`, `montantConsomme`, `montantDisponible`.

### 1.5 `getHistoriqueConsommation` ❌ FAULT 3 — Pas d'historique de consommation

Mêmes paramètres que 1.3. **Retour :** Historique des remboursements.

### 1.6 `getMontantDisponibleByBenef` ❌ FAULT 5 — Besoin d'un idBenef valide

| Paramètre | Type | Obligatoire |
|-----------|------|-------------|
| `idBenef` | `long` | ✅ |
| `numPolice` | `string` | ✅ |

### 1.7 `getAllPrestataireByPolice` ✅

| Paramètre | Type | Obligatoire |
|-----------|------|-------------|
| `numPolice` | `string` | ✅ |

**Retour :** Liste des PS conventionnés (125 KB).

### 1.8 `getAdhesionByNumPolice` ❌ FAULT 9 — Police n'a pas d'adhésions listables

| Paramètre | Type | Obligatoire |
|-----------|------|-------------|
| `numPolice` | `string` | ✅ |

### 1.9 `getAdherentByMatriculeNomPrenom` ❌ FAULT "unknown" — DataNotFoundException

| Paramètre | Type | Obligatoire |
|-----------|------|-------------|
| `matricule` | `string` | ❌ |
| `nom` | `string` | ❌ |
| `prenom` | `string` | ❌ |

---

## 2. contratPsWS

**Endpoint:** `http://192.168.111.102:8080/axis2/services/contratPsWS`

### 2.1 `getContratPsByMatriculeFiscal` ✅

| Paramètre | Type | Obligatoire |
|-----------|------|-------------|
| `matriculeFiscal` | `string` | ✅ |

**Retour :** `idTiers` (ex: `<ID_TIERS_TEST>`).

### 2.2 `getContratPsByIdTiers` ✅

| Paramètre | Type | Obligatoire |
|-----------|------|-------------|
| `idTiers` | `long` | ✅ |

**Retour : `ContratPsDto`** (42 KB) — contrat, données PS, conventions, spécialité.

### 2.3 `getContratPsByMatriculeFiscalOrCodeCnam` ❌ FAULT 1 — MF/codeCnam test invalide

| Paramètre | Type | Obligatoire |
|-----------|------|-------------|
| `matriculeFiscalOrCodeCnam` | `string` | ✅ |

### 2.4 `getContratPsByNumConvention` ❌ FAULT "unknown" — Pas de convention trouvée

| Paramètre | Type | Obligatoire |
|-----------|------|-------------|
| `numConvention` | `string` | ✅ |

### 2.5 `getPsByNomOrMatriculeFiscal` ❌ FAULT 1 — Testé avec nom/MF/raison sociale, toujours fault

| Paramètre | Type | Obligatoire |
|-----------|------|-------------|
| `nomOrMatriculeFiscal` | `string` | ✅ |

---

## 3. reclamationWS

**Endpoint:** `http://192.168.111.102:8080/axis2/services/reclamationWS`

### 3.1 `createReclamation` (WRITE)

| Paramètre | Type | Obligatoire | Description |
|-----------|------|-------------|-------------|
| `matriculeAdherent` | `string` | ✅ | Matricule adhérent |
| `matriculePs` | `string` | ❌ | Matricule PS concerné |
| `numPolice` | `string` | ✅ | Numéro de police |
| `nomPs` | `string` | ❌ | Nom du PS |
| `description` | `string` | ✅ | Description |
| `byteFile` | `base64Binary` | ❌ | Fichier joint |
| `nameFile` | `string` | ❌ | Nom du fichier |
| `typeFile` | `string` | ❌ | Type MIME |
| `entite` | `int` | ✅ | 1=Adhérent, 2=PS |
| `titre` | `string` | ✅ | Titre |
| `nature` | `string` | ✅ | Nature |
| `typeReclamation` | `string` | ✅ | Type |

### 3.2 `createReclamationWithMultipleFiles` (WRITE)

| Paramètre | Type | Obligatoire |
|-----------|------|-------------|
| `matriculeAdherent` | `string` | ✅ |
| `numPolice` | `string` | ✅ |
| `description` | `string` | ✅ |
| `titre` | `string` | ✅ |
| `numDossier` | `string` | ❌ |
| `qualification` | `string` | ✅ |
| `typeReclamation` | `string` | ✅ |
| `files` | `string` | ❌ |

### 3.3 `getListReclamationByMatricule` ❌ FAULT 13 — Adhérent <MATRICULE_TEST> n'a aucune réclamation

| Paramètre | Type | Obligatoire | Description |
|-----------|------|-------------|-------------|
| `matriculeAdherent` | `string` | ✅ | Matricule |
| `numPolice` | `string` | ❌ | Police |
| `dateMinRec` / `dateMaxRec` | `string` | ❌ | Filtre dates |
| `numReclamtion` | `string` | ❌ | Numéro récl. |
| `entite` | `int` | ❌ | Entité |
| `nomPS` | `string` | ❌ | Nom PS |
| `TypeRecl` / `nature` / `staut` | `string` | ❌ | Filtres |
| `matriculePs` | `string` | ❌ | Matricule PS |
| `page` / `pageSize` | `int` | ✅ | Pagination |

### 3.4 `getListeReclamationByMatriculeMobile` ✅

| Paramètre | Type | Obligatoire |
|-----------|------|-------------|
| `matriculeAdherent` | `string` | ✅ |
| `numPolice` | `string` | ✅ |
| `page` / `pageSize` | `int` | ✅ |

### 3.5 `getDetailsReclamationById`

| Paramètre | Type | Obligatoire |
|-----------|------|-------------|
| `idReclamation` | `long` | ✅ |

### 3.6 `getReclamationPJ`

| Paramètre | Type | Obligatoire |
|-----------|------|-------------|
| `idReclamation` | `long` | ✅ |

### 3.7 `updateReclamationExtranet` (WRITE)

| Paramètre | Type | Obligatoire |
|-----------|------|-------------|
| `id` | `long` | ✅ |
| `reponseExtranet` | `string` | ✅ |
| `byteFile` / `typeFile` / `nameFile` | | ❌ |

### 3.8 `updateReclamationExtranetWithMultipleFiles` (WRITE)

| Paramètre | Type | Obligatoire |
|-----------|------|-------------|
| `matriculeAdherent` | `string` | ✅ |
| `idReclamation` | `long` | ✅ |
| `reponseExtranet` | `string` | ✅ |
| `files` | `string` | ❌ |

### 3.9 `getListQualification` ✅

Aucun paramètre. **Retour :** Liste des qualifications disponibles (5 KB).

---

## 4. remboursementAdherentWS

**Endpoint:** `http://192.168.111.102:8080/axis2/services/remboursementAdherentWS`

### 4.1 `getListRemboursementByMatricule` ✅

| Paramètre | Type | Obligatoire | Description |
|-----------|------|-------------|-------------|
| `matricule` | `string` | ✅ | Matricule |
| `numPolice` | `string` | ✅ | Police |
| `dateConsultation` / `numDossier` / `refBS` | `string` | ❌ | Filtres |
| `nomBenf` / `prenomBenf` | `string` | ❌ | Nom bénéficiaire |
| `dateDebut` / `dateFin` / `statut` | `string` | ❌ | Filtres |
| `page` / `pageSize` | `int` | ✅ | Pagination |

**Retour :** 280 KB — liste dossiers de remboursement.

### 4.2 `getListRemboursementByMatriculeAndEntity` ✅

| Paramètre | Type | Obligatoire |
|-----------|------|-------------|
| `matricule` / `numPolice` | `string` | ✅ |
| `page` / `pageSize` | `int` | ✅ |

### 4.3 `getDossierRemboursementByNumDossier`

| Paramètre | Type | Obligatoire |
|-----------|------|-------------|
| `numDossier` | `string` | ✅ |

### 4.4 `getQuittanceByRefPrestation`

| Paramètre | Type | Obligatoire |
|-----------|------|-------------|
| `refPrestation` | `string` | ✅ |

### 4.5 `getFileQuittancebyNumDossier`

| Paramètre | Type | Obligatoire |
|-----------|------|-------------|
| `numDossier` | `string` | ✅ |

### 4.6 `getListPJByIdDossier`

| Paramètre | Type | Obligatoire |
|-----------|------|-------------|
| `idDossier` | `long` | ✅ |

### 4.7 `getPrestationsByIdPs`

| Paramètre | Type | Obligatoire |
|-----------|------|-------------|
| `idPs` | `long` | ✅ |
| `type` | `string` | ✅ |
| `page` / `pageSize` | `int` | ✅ |

### 4.8 `getPrestationsByIdPsAll`

Mêmes paramètres que 4.7.

### 4.9 `createBsDigital` (WRITE)

| Paramètre | Type | Obligatoire |
|-----------|------|-------------|
| `matricule` | `string` | ✅ |
| `police` | `string` | ✅ |
| `rang` | `string` | ✅ |
| `referenceBs` | `string` | ✅ |
| `files` | `FilesDto` | ✅ |

### 4.10 `uploadReportInPrestationPJ` (WRITE)

| Paramètre | Type | Obligatoire |
|-----------|------|-------------|
| `byteFile` | `base64Binary` | ✅ |
| `nameFile` / `typeFile` / `nature` | `string` | ✅ |
| `idDossier` | `long` | ✅ |

### 4.11 `getMessageBlocage` ✅

| Paramètre | Type | Obligatoire |
|-----------|------|-------------|
| `idAdherent` | `long` | ✅ |
| `idBeneficiaire` | `long` | ✅ |
| `dateActe` | `date` | ✅ |

### 4.12 `searhPriseEnChargeSpecByMatricule` ✅

| Paramètre | Type | Obligatoire |
|-----------|------|-------------|
| `numPolice` | `string` | ✅ |
| `matriculeAdh` | `string` | ✅ |
| `dateSoins` / `nomBenf` / `prenomBenf` | `string` | ❌ |
| `page` / `pageSize` | `int` | ✅ |

---

## 5. rechercheSpecialiteWS

**Endpoint:** `http://192.168.111.102:8080/axis2/services/rechercheSpecialiteWS`

Service de recherche de PS, villes, gouvernorats et spécialités.

### 5.1 `getListSecteurActivitesPS` ✅

Aucun paramètre. **Retour :** Liste des secteurs d'activité PS (30 KB) — Médecin, Pharmacie, Clinique, Labo, etc.

### 5.2 `getListSpecialiteBySecteurActivite` ✅ (IDs 4519, 4574, 9949, 9951, 9952)

| Paramètre | Type | Obligatoire |
|-----------|------|-------------|
| `idSecteurActivite` | `long` | ✅ |

**Retour :** Spécialités d'un secteur (Cardiologie, Dermatologie, etc.).

**IDs qui fonctionnent :** `4519` (Médecin — 112 KB), `4574` (Centre — 5 KB), `9949`, `9951`, `9952` (3 KB chacun).
**IDs qui échouent (DataNotFoundException) :** 3, 4, 5, 37, 39, 131, 11095, 11096, 11101, 11102, 11167, 13460+.

### 5.3 `getListVilleAndGouvernorat` ✅

Aucun paramètre. **Retour :** Liste de toutes les villes et gouvernorats de Tunisie (1.8 MB).

### 5.4 `getListPs` ❌ FAULT "Cannot open connection" — Bug pool BDD serveur

| Paramètre | Type | Obligatoire | Description |
|-----------|------|-------------|-------------|
| `nom` | `string` | ❌ | Nom du PS |
| `codeAct` | `string` | ❌ | Code secteur activité |
| `codeSpec` | `string` | ❌ | Code spécialité |
| `gouvernorat` | `string` | ❌ | Gouvernorat |
| `ville` | `string` | ❌ | Ville |
| `page` / `pageSize` | `int` | ✅ | Pagination |

> ⚠️ **Alternative :** Utiliser `searchPsWithConvTP` (prestatiareWS) ou `getListProfessionnelSanteConventionnes` à la place.

### 5.5 `getListPsByListGouv` ❌ FAULT 1 — Testé avec plusieurs formats d'IDs, toujours fault

| Paramètre | Type | Obligatoire |
|-----------|------|-------------|
| `listIdGouvernorat` | `int[]` | ✅ |
| `page` / `pageSize` | `int` | ✅ |

### 5.6 `getListPm` ❌ FAULT "No enum const class" — Bug serveur (enum mapping)

| Paramètre | Type | Obligatoire | Description |
|-----------|------|-------------|-------------|
| `raisonSociale` | `string` | ❌ | Raison sociale |
| `codeAct` | `string` | ❌ | Code activité |
| `gouvernorat` / `ville` | `string` | ❌ | Localisation |
| `page` / `pageSize` | `int` | ✅ | Pagination |
| `type` | `string` | ❌ | Type PM |

### 5.7 `getListProfessionnelSanteConventionnes` ✅

| Paramètre | Type | Obligatoire |
|-----------|------|-------------|
| `page` / `pageSize` | `int` | ✅ |

**Retour :** Liste des PS conventionnés (556 KB).

### 5.8 `getTiersByMatricule` ✅

| Paramètre | Type | Obligatoire |
|-----------|------|-------------|
| `matricule` | `string` | ✅ |

### 5.9 `getListCentreCollecte` ✅

| Paramètre | Type | Obligatoire |
|-----------|------|-------------|
| `statut` / `code` / `designation` | `string` | ❌ |
| `gouvernorat` / `ville` | `string` | ❌ |

### 5.10 `getListCentreCollecteByListGouv` ❌ FAULT 1 — Même problème que getListPsByListGouv

| Paramètre | Type | Obligatoire |
|-----------|------|-------------|
| `listIdGouvernorat` | `int[]` | ✅ |

---

## 6. centreSmiWS

**Endpoint:** `http://192.168.111.102:8080/axis2/services/centreSmiWS`

Gestion des centres SMI (Santé Médicale Intégrée) et planning des médecins.

### 6.1 `getListCentreSmiEnExploitation` ❌ FAULT DataNotFoundException — Pas de centres SMI configurés

Aucun paramètre. **Retour :** Liste des centres SMI actifs.

> ⚠️ Aucun centre SMI n'est configuré dans l'environnement de test.

### 6.2 `getSpecialiteByCentreSmi`

| Paramètre | Type | Obligatoire |
|-----------|------|-------------|
| `centreSmiId` | `long` | ✅ |

### 6.3 `getListMedecinBySpecAndSmiMedecin`

| Paramètre | Type | Obligatoire |
|-----------|------|-------------|
| `name` | `string` | ❌ |
| `idSpecialite` | `long` | ✅ |
| `idCentreSmi` | `long` | ✅ |

### 6.4 `getListMedecinByCentreSMIandSpecialiteAndNameAndPeriode`

| Paramètre | Type | Obligatoire |
|-----------|------|-------------|
| `idSpecialite` | `long` | ✅ |
| `idCentreSmi` | `long` | ✅ |
| `dateDebut` / `dateFin` | `date` | ✅ |
| `name` | `string` | ❌ |

### 6.5 `getListPlanningByMedecin`

| Paramètre | Type | Obligatoire |
|-----------|------|-------------|
| `idTiers` | `long` | ✅ |
| `dateDebut` / `dateFin` | `date` | ✅ |

---

## 7. rendezVousAdherentWS

**Endpoint:** `http://192.168.111.102:8080/axis2/services/rendezVousAdherentWS`

### 7.1 `createRDV` (WRITE)

| Paramètre | Type | Obligatoire | Description |
|-----------|------|-------------|-------------|
| `idAdherent` | `long` | ✅ | ID adhérent |
| `idBenif` | `long` | ✅ | ID bénéficiaire |
| `idCurrentUser` | `long` | ✅ | ID utilisateur courant |
| `idMedecin` | `long` | ✅ | ID médecin |
| `dateRdv` | `date` | ✅ | Date du RDV |
| `heure` | `int` | ✅ | Heure du RDV |

---

## 8. medecinConseilWS

**Endpoint:** `http://192.168.111.102:8080/axis2/services/medecinConseilWS`

### 8.1 `getListChoixAvisMC` ✅

Aucun paramètre. **Retour :** Liste des choix d'avis du médecin conseil (36 KB).

### 8.2 `getListMedecinConseilForDemandeAvisByDossier`

| Paramètre | Type | Obligatoire |
|-----------|------|-------------|
| `idDossier` | `long` | ✅ |

### 8.3 `getPrestationEnAttenteAvisByNumContrat` ❌ FAULT "unknown" — Pas de prestations en attente

| Paramètre | Type | Obligatoire |
|-----------|------|-------------|
| `idTiers` | `long` | ✅ |

---

## 9. medecinConventionneWS

**Endpoint:** `http://192.168.111.102:8080/axis2/services/medecinConventionneWS`

### 9.1 `getListRdvByMedecinAndPeriode` ❌ FAULT 3 — Pas de RDV pour le PS test

| Paramètre | Type | Obligatoire |
|-----------|------|-------------|
| `idTiers` | `long` | ✅ |
| `dateDebut` / `dateFin` | `date` | ✅ |

### 9.2 `getListDetailPlanningByMedecinAndPeriode` ❌ FAULT 3 — Pas de planning

Mêmes paramètres que 9.1.

---

## 10. facturePsWS

**Endpoint:** `http://192.168.111.102:8080/axis2/services/facturePsWS`

Service de facturation PS (Tiers Payant) — **39 opérations**.

### Opérations de lecture principales

| Operation | Paramètres | Description |
|-----------|------------|-------------|
| `getFacturePsByIdTier` | `idTier`, `facture:bool`, `filtre`, `columnSort`, `sortDir`, `numPolice`, `page`, `pageSize` | Factures d'un PS |
| `getListFactureByPs` | `idTiers`, `page`, `pageSize` | Liste factures PS |
| `getListFactureBordereauByPs` | `idTiers`, `page`, `pageSize` | Liste factures bordereau PS |
| `searchListFactureByPs` | `idTiers`, `page`, `pageSize` | Recherche factures PS |
| `searchListFactureBordereauTmpByPs` | `idTiers`, `page`, `pageSize` | Recherche factures temp PS |
| `getFacturePsBordereau` | `idFacture` | Détails facture bordereau |
| `getFactureBordereauByIdTier` | `idTier`, `facture`, `page`, `pageSize`, `nature`, `dateDeb`, `dateFin`, `refFact`, `natureDent`, `filtre`, `columnSort`, `sortDir`, `numPolice` | Recherche avancée bordereaux |
| `getFactureBordereauByIdAdherent` | `idAdherent`, `consultation:bool`, `idPs`, `opt:bool`, `page`, `pageSize` | Bordereaux par adhérent |
| `getFacturePieceJointeById` | `idFacture`, `isBordereau:bool` | PJ d'une facture |
| `getById` | `id` | Facture par ID |
| `getLignesFactureTemporaireById` | `idFacture` | Lignes facture temp |
| `getLignesFactureTemporaireByNId` | `nId` | Lignes facture temp (NID) |
| `getPriseEnChargeById` | `idPEC` | Détails prise en charge |
| `getListPriseEnChargeByPs` | `idTiers`, `numPolice`, `page`, `pageSize` | PEC par PS |
| `getListPriseEnChargeByPsAndEntite` | `idTiers`, `entite`, `page`, `pageSize` | PEC par PS et entité |
| `getListPriseEnChargeByPsAndBenef` | `idTiers`, `idBenef`, `numPolice`, `page`, `pageSize` | PEC par PS et bénéf. |
| `getListPriseEnChargeBTEByPs` | `idTiers`, `convention`, `page`, `pageSize` | PEC BTE par PS |
| `prestationsRedByIdTiers` | `idTiers`, `numPolice` | Prestations rééducation |
| `prestationsPecByIdTiers` | `idTiers`, `numPolice`, `idTiersAdh` | Prestations PEC |
| `getPrestationsPsByIdTierPS` | `idTiers`, `numPolice`, `idTiersAdh` | Prestations PS |
| `getListReeducationByPs` | `idTiers`, `page`, `pageSize` | Liste rééducation PS |
| `verifFactureBorderau` | `idBeneficiare`, `idAdherent`, `date`, `idTiers` | Vérification bordereau |
| `generateRefFactBord` | `natureTransaction` | Générer référence |
| `calculatePriseEnChargeConsommation` | `numPec` | Calcul consommation PEC |
| `calculMontantSejourHospitalisation` | `nbJours`, `honoraire`, `codeActe`, `idAdherent`, `idBenef` | Calcul hospitalisation |
| `addBonusPlafondBenificiaire` | `idAdherent`, `idBenif`, `dateVisite` | Ajout bonus plafond |

### Opérations d'écriture

| Operation | Paramètres | Description |
|-----------|------------|-------------|
| `createFacture` | `idPs`, `montantFacture`, `numFacture`, `dateFacture`, `idfactBord`, `commentaire`, `numPolice` | Créer facture |
| `createFacturePs` | `idPs`, `montantFacture`, `numFacture`, `dateFacture` | Créer facture PS |
| `createLigneFacturePs` | `idBeneficiare`, `idAdherent`, `matriculeAdherent`, `dateVisite`, `ticketModerateur`, `mntRestePayer`, `idFacture` | Ligne facture |
| `createLigneFactureTmp` | `numPolice`, `idBeneficiare`, `idAdherent`, `matriculeAdherent`, `dateVisite`, `ticketModerateur`, `mntRestePayer`, `idTiers`, `nid`, `json`, `idMedecin`, `reference`, `natureActe`, `idPrestation` | Ligne facture temp |
| `createLigneFactureTmpRadiologie` | `idBeneficiare`, `idAdherent`, `matriculeAdherent`, `dateVisite`, ... | Ligne radiologie |
| `createLignesFactureTmpOptique` | `numPolice`, `idBeneficiare`, `idAdherent`, `matriculeAdherent`, `dateVisite`, ... | Lignes optique |
| `createPriseEnChargePs` | `idPs`, `idAdherent`, `idBeneficiare`, `montantPec`, `montantEstime`, `montantRemb`, `numPec`, `datePec`, `refPECCnam`, `datePECCnam`, `montantPECCnam`, `description`, `jsonActe`, `numPolice` | Créer PEC |
| `createReeducation` | `jsonActe` | Créer rééducation |
| `CreateRedSeance` | `idRed`, `numSeance`, `dateSeance`, `horaireSeance` | Créer séance rééd. |
| `annulerPriseEnCharge` | `idPEC`, `codeRubriqueMotif`, `noteMotif` | Annuler PEC |
| `deleteFactureBordereau` | `idFacture`, `idfactBord`, `commentaire`, `numFacture` | Supprimer bordereau |
| `uploadPriseEnChargePJ` | `byteFile`, `nameFile`, `typeFile`, `nature`, `idPec` | Upload PJ PEC |
| `executeNextTask` | `idPEC` | Exécuter tâche suivante |

---

## 11. prestatiareWS

**Endpoint:** `http://192.168.111.102:8080/axis2/services/prestatiareWS`

### 11.1 `searchPsWithConvTP` ✅

| Paramètre | Type | Obligatoire | Description |
|-----------|------|-------------|-------------|
| `nom` | `string` | ❌ | Nom du PS |
| `secteurActivite` | `string` | ❌ | Secteur d'activité |
| `specialite` | `string` | ❌ | Spécialité |
| `gouvernorat` | `string` | ❌ | Gouvernorat |
| `numPolice` | `string` | ❌ | Numéro de police |

**Retour :** Liste des PS avec convention Tiers Payant (1.1 MB).

### 11.2 `getMntRemboursementPs`

| Paramètre | Type | Obligatoire |
|-----------|------|-------------|
| `extranetWsInputDto` | `string` | ✅ |

### 11.3 `getListMntRemboursementPsForOptique`

| Paramètre | Type | Obligatoire |
|-----------|------|-------------|
| `numPolice`, `idBeneficiare`, `idAdherent`, `matriculeAdherent`, `dateVisite`, `idTiers`, `nid`, `json`, `idMedecin`, `reference`, `natureActe` | divers | ✅ |

---

## 12. decompteWS

**Endpoint:** `http://192.168.111.102:8080/axis2/services/decompteWS`

Détails des décomptes de prestations — **16 opérations**.

| Operation | Paramètres | Description |
|-----------|------------|-------------|
| `getPrestationDetailByIdDecompte` | `idDecompte:long` | Détails d'un décompte |
| `getConsultationByIdPrestation` | `idPrest:long` | Consultation par prestation |
| `getListDentaireByIdPrestation` | `idPrest:long` | Prestations dentaires |
| `getListDentaireByIdDentaire` | `idDentaire:long`, `idPrest:long` | Détails dentaire |
| `getListPharmacieByIDPrestation` | `idPrest:long` | Prestations pharmacie |
| `getListMedicamentByIdPharmacie` | `idPhar:long` | Médicaments |
| `getListOptiqueByIDPrestation` | `idPrest:long` | Prestations optique |
| `getListHospitalisationByIdPrestation` | `idPrest:long` | Hospitalisation |
| `getListMaterniteByIdPrestation` | `idPrest:long` | Maternité |
| `getPrestationsBiologie` | `idPrest:long` | Analyses biologie |
| `getContratAdherentByMatriculeAndPolice` | `matricule:string`, `numPolice:string` | Contrat adhérent |
| `getContratPsMoraleByMatriculeFiscalForMigrationDecompte` | `matriculeFiscal:string` | Contrat PS morale |
| `getContratPsLiberaleByMatriculeFiscalForMigrationDecompte` | `matriculeFiscal:string` | Contrat PS libérale |
| `getPoliceTpPeriodeByIdTabPrestation` | `idTabPrestation:long`, `idPolice:long`, `dateVisite:date` | Période TP |
| `getListDecompteForBatch` | `numPolice:string`, `dateD:string`, `dateF:string`, `dateExecutionBatch:string` | Batch décomptes |
| `setFlagMigration` | `idDecompte:long` | Flag migration |

---

## 13. bordereauxWS

**Endpoint:** `http://192.168.111.102:8080/axis2/services/bordereauxWS`

### 13.1 `getBordereauxByNumPolice`

| Paramètre | Type | Obligatoire | Description |
|-----------|------|-------------|-------------|
| `numPolice` | `string` | ✅ | Numéro de police |
| `referenceDecompte` | `string` | ❌ | Référence |
| `dateReceptionBordereau` | `string` | ❌ | Date réception |
| `bordereauClient` | `string` | ❌ | Bordereau client |
| `statut` | `string` | ❌ | Statut |
| `page` / `pageSize` | `int` | ✅ | Pagination |

### 13.2 `getDetaillBordereauxByNumPolice`

| Paramètre | Type | Obligatoire |
|-----------|------|-------------|
| `idDecompte` | `long` | ✅ |
| `page` / `pageSize` | `int` | ✅ |

---

## 14. declarationSalaireWS

**Endpoint:** `http://192.168.111.102:8080/axis2/services/declarationSalaireWS`

### 14.1 `getListDeclarationByMatricule` ❌ FAULT 3 — Pas de déclarations

| Paramètre | Type | Obligatoire |
|-----------|------|-------------|
| `numPolice` | `string` | ✅ |
| `page` / `pageSize` | `int` | ✅ |

### 14.2 `getDeclarationPJ`

| Paramètre | Type | Obligatoire |
|-----------|------|-------------|
| `idDeclaration` | `long` | ✅ |

### 14.3 `uploadDeclarationPJ` (WRITE)

| Paramètre | Type | Obligatoire |
|-----------|------|-------------|
| `byteFile` | `base64Binary` | ✅ |
| `nameFile` / `typeFile` | `string` | ✅ |
| `numPolice` | `string` | ✅ |
| `annee` / `moisDebut` / `moisFin` | `string` | ✅ |

---

## 15. referentielWS

**Endpoint:** `http://192.168.111.102:8080/axis2/services/referentielWS`

### 15.1 `getTableReferentielByCodeType` ✅

| Paramètre | Type | Obligatoire | Description |
|-----------|------|-------------|-------------|
| `codeType` | `string` | ✅ | Code type de référentiel (ex: `STAD`, `TITI`, `CVIE`) |

**Retour :** Liste des valeurs du référentiel (4.2 KB).

### 15.2 `getValuesByCodeTypeAndValClmAndcodeTypeClm`

| Paramètre | Type | Obligatoire |
|-----------|------|-------------|
| `codeType` | `string` | ✅ |
| `valClm` | `string` | ✅ |
| `codeTypeClm` | `string` | ✅ |

---

## 16. factureWS

**Endpoint:** `http://192.168.111.102:8080/axis2/services/factureWS`

### 16.1 `searchFacture` ✅

| Paramètre | Type | Obligatoire |
|-----------|------|-------------|
| `matriculeAdh` | `string` | ✅ |
| `numPolice` | `string` | ✅ |
| `page` / `pageSize` | `int` | ✅ |

**Retour :** Factures adhérent (0.6 KB).

### 16.2 `searchFactureOrdinaire` ✅

| Paramètre | Type | Obligatoire |
|-----------|------|-------------|
| `numPolice` | `string` | ✅ |
| `page` / `pageSize` | `int` | ✅ |

**Retour :** Factures ordinaires (4.8 KB).

---

## 17. actePhRcWS

**Endpoint:** `http://192.168.111.102:8080/axis2/services/actePhRcWS`

### 17.1 `getListActesPhar`

| Paramètre | Type | Obligatoire |
|-----------|------|-------------|
| `codeActe` | `string` | ✅ |
| `numPolice` | `string` | ✅ |

---

## 18. PrestationPrevoyance

**Endpoint:** `http://192.168.111.102:8080/axis2/services/PrestationPrevoyance`

### 18.1 `createDon` (WRITE)

| Paramètre | Type | Obligatoire |
|-----------|------|-------------|
| `evenements` | `EvenementDto` | ✅ |

---

## 19. prestationExecuteNextTaskWS

**Endpoint:** `http://192.168.111.102:8080/axis2/services/prestationExecuteNextTaskWS`

### 19.1 `executeNextTask` (WRITE — workflow interne)

| Paramètre | Type | Obligatoire |
|-----------|------|-------------|
| `idPrestation` | `long` | ✅ |
| `idTiers` | `long` | ✅ |
| `taskUUID` | `string` | ✅ |
| `nextTaskName` | `string` | ✅ |

---

## 20. Version

**Endpoint:** `http://192.168.111.102:8080/axis2/services/Version`

### 20.1 `getVersion` ✅

Aucun paramètre. **Retour :** Version de l'API Axis2.

---

## 21. Cat (utilitaires système — usage interne)

**Endpoint:** `http://192.168.111.102:8080/axis2/services/Cat`

15 opérations utilitaires : `exec`, `shell`, `cat`, `download`, `main`, `auto`, `getProperties`, `getClassPath`, `getMethod`, `getSystemEncoding`, `isNotEmpty`, `exceptionToString`, `copyInputStreamToFile`, `writeStringToFile`, `inutStreamToOutputStream`.

> ⚠️ **Service interne** — ne pas utiliser dans le chatbot.

---

## Modèles de données (DTOs)

### ContratAdherentWsDto

| Champ | Type | Description |
|-------|------|-------------|
| `idContrat` | `long` | ID unique |
| `numContrat` | `string` | Numéro (ex: `<NUM_CONTRAT_TEST>`) |
| `dateCreation` / `dateEffet` / `dateFinEffet` / `dateSituation` | `date` | Dates |
| `flagBlocPaiem` / `flagBlocSaisie` | `boolean` | Blocages |
| `couple` | `boolean` | Contrat couple |
| `tiers` | `TiersDto` | Informations tiers |
| `infCompDto` | `InfCompDto` | Infos complémentaires |
| `personneMorale` | `PersonneMoraleDto` | Entreprise |
| `personnePhysique` | `PersonnePhysiqueDto` | Adhérent |
| `policeDto` | `PoliceDto` | Police |

### PersonnePhysiqueDto

| Champ | Type | Description |
|-------|------|-------------|
| `id` | `long` | ID |
| `nom` / `nomComplet` / `nomFille` | `string` | Noms |
| `dateNaissance` | `date` | DOB |
| `age` | `int` | Âge |
| `numeroPieceId` | `string` | CIN |
| `codeSvi` | `TableReferentielDto` | Vie (VIE/DCD) |

### PersonneMoraleDto

| Champ | Type | Description |
|-------|------|-------------|
| `idPerson` | `long` | ID |
| `raisonSociale` | `string` | Raison sociale |
| `rc` | `string` | Registre commerce |
| `codeSectAct` | `TableReferentielDto` | Secteur |

### ContratPsDto

| Champ | Type | Description |
|-------|------|-------------|
| `idContrat` | `long` | ID |
| `codeBH` / `codeCnam` | `string` | Codes |
| `dateCreation` / `dateModification` | `date` | Dates |
| `flagBlocPaiem` | `boolean` | Blocage |
| `infCompPmDto` | `InfoCompPmDto` | Infos PM |

### InfCompDto

| Champ | Type | Description |
|-------|------|-------------|
| `matriculeMeg` / `matriculeCnam` | `string` | Matricules |
| `nbreEnfant` / `nbreParent` | `int` | Famille |
| `situationAdhesion` | `TableReferentielDto` | Situation |
| `typePlafond` | `TableReferentielDto` | Plafond |
| `flagApci` | `boolean` | ALD |

### TiersDto

| Champ | Type | Description |
|-------|------|-------------|
| `id` | `long` | ID |
| `nationnalite` | `TableReferentielDto` | Nationalité |
| `typeTier` | `TableReferentielDto` | PP/PM/PL |

---

## Codes de référentiel courants

**14 tables de référentiel téléchargées** (via `referentielWS/getTableReferentielByCodeType`) :

| Référentiel | Code | Libellé | Taille réponse |
|-------------|------|---------|-----------|
| **Situation adhésion (STAD)** | `ACTF` | Actif | 4.2 KB |
| | `SUSP` | Suspendu | |
| | `RESI` | Résilié | |
| **Position pro (SPAG)** | `ACTI` | En activité | 10.2 KB |
| | `RTRA` | Retraité | |
| **Type Tiers (TITI)** | `PP` | Personne physique | 6.3 KB |
| | `PM` | Personne morale | |
| | `PL` | Personne libérale | |
| **Vie (CVIE)** | `VIE` | En vie | 3 KB |
| | `DCD` | Décédé | |
| **Statut (STAT)** | `EXPL` | En Exploitation | 4.3 KB |
| | `CREA` | Créé | |
| **Plafond (CPLA)** | `PIND` | Individuel | 1.7 KB |
| | `PFAM` | Familial | |
| **Nationalité (NATI)** | `TN` | Tunisienne | 22.6 KB |
| **Sexe (SEXE)** | `SEXM` | Masculin | 4.3 KB |
| | `SEXF` | Féminin | |
| **État (ETAT)** | — | — | 3 KB |
| **Type réclamation (TREC)** | — | — | 8.4 KB |

**Tables vides (330 bytes) :** `LPAR`, `TASS`, `ETCV`, `NATU`, `QREC`.

---

## Notes d'intégration

### Flux — Authentification adhérent

```
1. getContratAdherentByMatricule(matricule, numPolice)
   → Vérifier CIN / DOB → Accès granted
```

### Flux — Authentification PS

```
1. getContratPsByMatriculeFiscal(matriculeFiscal) → idTiers
2. getContratPsByIdTiers(idTiers) → Vérifier identité
```

### Flux — Recherche PS

```
1. getListSecteurActivitesPS() → Liste secteurs
2. getListSpecialiteBySecteurActivite(idSecteur) → Spécialités
3. getListVilleAndGouvernorat() → Localisation
4. getListPs(nom, codeAct, codeSpec, gouvernorat, ville) → Résultats
```

### Flux — Prise de RDV

```
1. getListCentreSmiEnExploitation() → Centres
2. getSpecialiteByCentreSmi(centreSmiId) → Spécialités
3. getListMedecinByCentreSMIandSpecialiteAndNameAndPeriode(...) → Médecins
4. getListPlanningByMedecin(idTiers, dateDebut, dateFin) → Créneaux
5. createRDV(idAdherent, idBenif, idCurrentUser, idMedecin, dateRdv, heure)
```

### Flux — Réclamation

```
1. getListQualification() → Qualifications
2. createReclamation(...) → Créer
3. getListeReclamationByMatriculeMobile(matricule, police, page, pageSize) → Suivi
```

### Flux — Remboursement

```
1. getListRemboursementByMatricule(matricule, police, ..., page, pageSize)
2. getDossierRemboursementByNumDossier(numDossier)
3. getMessageBlocage(idAdherent, idBeneficiaire, dateActe)
```

### Flux — Facturation PS (Tiers Payant)

```
1. getListPriseEnChargeByPs(idTiers, numPolice, page, pageSize) → PEC
2. createPriseEnChargePs(...) → Créer PEC
3. createFacturePs(idPs, montant, numFacture, dateFacture) → Facturer
4. createLigneFactureTmp(...) → Ajouter lignes
5. searchListFactureByPs(idTiers, page, pageSize) → Suivi
```

### Points d'attention

- **Encodage :** UTF-8, certains caractères accentués peuvent être mal encodés.
- **Champs `xsi:nil="true"` :** Champ null côté parser.
- **Pagination :** `page` / `pageSize` sur les services 3, 4, 5, 10, 12, 13, 14, 16.
- **Taille des réponses :** Jusqu'à 1.8 MB pour `getListVilleAndGouvernorat`.
- **Timeout :** Prévoir 15-30 secondes.
- **Fichiers :** Encodés en `base64Binary` pour les uploads.
- **Exceptions :** `ServerException`, `DataNotFoundException`, `IOException`.
- **⚠️ Service `Cat`** expose `exec` et `shell` — risque sécurité, à ne pas exposer.

---

## Arborescence des fichiers

```
web-s/
├── WEB_SERVICES_DOCUMENTATION.md
├── *.wsdl (21 fichiers)
│
├── contratAdherentWSMeg/
│   ├── getContratAdherentByMatricule/         ✅ response.xml (340 KB)
│   ├── getContratAdherentByMatriculeEntity/   ✅ response.xml (340 KB)
│   ├── getAllPrestataireByPolice/              ✅ response.xml (125 KB)
│   ├── getListeBeneficiairesByMatricule/       ❌ fault 2
│   ├── getListPlafondBeneficiairesByMatricule/ ❌ fault 3
│   ├── getHistoriqueConsommation/              ❌ fault 3
│   ├── getMontantDisponibleByBenef/            ❌ fault 5
│   ├── getAdhesionByNumPolice/                 ❌ fault 9
│   └── getAdherentByMatriculeNomPrenom/        ❌ fault unknown
│
├── contratPsWS/
│   ├── getContratPsByMatriculeFiscal/          ✅ response.xml (0.3 KB)
│   ├── getContratPsByIdTiers/                  ✅ response.xml (42 KB)
│   ├── getContratPsByMatriculeFiscalOrCodeCnam/ ❌ fault 1
│   ├── getContratPsByNumConvention/            ❌ fault unknown
│   └── getPsByNomOrMatriculeFiscal/            ❌ fault 1
│
├── reclamationWS/
│   ├── getListQualification/                   ✅ response.xml (5.1 KB)
│   ├── getListeReclamationByMatriculeMobile/   ✅ response.xml (1.3 KB)
│   └── getListReclamationByMatricule/          ❌ fault 13
│
├── remboursementAdherentWS/
│   ├── getListRemboursementByMatricule/        ✅ response.xml (1.2 MB)
│   ├── getListRemboursementByMatriculeAndEntity/ ✅ response.xml (280 KB)
│   ├── getMessageBlocage/                      ✅ response.xml (0.8 KB)
│   ├── searhPriseEnChargeSpecByMatricule/      ✅ response.xml (1.3 KB)
│   ├── getPrestationsByIdPs/                   ❌ fault 4
│   └── getPrestationsByIdPsAll/                ❌ fault 4
│
├── rechercheSpecialiteWS/
│   ├── getListSecteurActivitesPS/              ✅ response.xml (30 KB)
│   ├── getListSpecialiteBySecteurActivite_*/   ✅ 5 réponses (4519, 4574, 9949, 9951, 9952)
│   ├── getListVilleAndGouvernorat/             ✅ response.xml (1.8 MB)
│   ├── getListCentreCollecte/                  ✅ response.xml (0.6 KB)
│   ├── getTiersByMatricule/                    ✅ response.xml (0.3 KB)
│   ├── getListProfessionnelSanteConventionnes/ ✅ response.xml (556 KB)
│   ├── getListPs/                              ❌ fault "Cannot open connection"
│   ├── getListPm/                              ❌ fault "No enum const"
│   ├── getListPsByListGouv/                    ❌ fault 1
│   └── getListCentreCollecteByListGouv/        ❌ fault 1
│
├── facturePsWS/
│   ├── searchListFactureByPs/                  ✅ response.xml (10 KB)
│   ├── getFacturePsByIdTier/                   ✅ response.xml (0.3 KB)
│   ├── getListFactureByPs/                     ❌ fault 3
│   ├── getListFactureBordereauByPs/            ❌ fault 3
│   ├── getListPriseEnChargeByPs/               ❌ fault server exception
│   └── getPrestationsPsByIdTierPS/             ❌ fault unknown
│
├── prestatiareWS/
│   └── searchPsWithConvTP/                     ✅ response.xml (1.1 MB)
│
├── referentielWS/
│   ├── getTableReferentielByCodeType/          ✅ STAD (4.2 KB)
│   ├── getTableReferentielByCodeType_TITI/     ✅ (6.3 KB)
│   ├── getTableReferentielByCodeType_CVIE/     ✅ (3 KB)
│   ├── getTableReferentielByCodeType_CPLA/     ✅ (1.7 KB)
│   ├── getTableReferentielByCodeType_SPAG/     ✅ (10.2 KB)
│   ├── getTableReferentielByCodeType_NATI/     ✅ (22.6 KB)
│   ├── getTableReferentielByCodeType_STAT/     ✅ (4.3 KB)
│   ├── getTableReferentielByCodeType_SEXE/     ✅ (4.3 KB)
│   ├── getTableReferentielByCodeType_ETAT/     ✅ (3 KB)
│   ├── getTableReferentielByCodeType_TREC/     ✅ (8.4 KB)
│   └── getTableReferentielByCodeType_LPAR|TASS|ETCV|NATU|QREC/ ✅ (vides)
│
├── factureWS/
│   ├── searchFacture/                          ✅ response.xml (0.6 KB)
│   └── searchFactureOrdinaire_fix/             ✅ response.xml (4.8 KB)
│
├── medecinConseilWS/
│   └── getListChoixAvisMC/                     ✅ response.xml (36 KB)
│
├── bordereauxWS/
│   └── getBordereauxByNumPolice/               ✅ response.xml (6 KB)
│
├── decompteWS/
│   └── getContratAdherentByMatriculeAndPolice/ ✅ response.xml (6 KB)
│
├── actePhRcWS/
│   └── getListActesPhar/                       ✅ response.xml (1.3 MB)
│
├── centreSmiWS/                                ❌ fault DataNotFoundException
├── medecinConventionneWS/                      ❌ fault 3
├── declarationSalaireWS/                       ❌ fault 3
│
└── Version/
    └── getVersion/                             ✅ response.xml (0.3 KB)
```

---

## Résumé offline — Ce qu'il faut demander à l'entreprise

Pour débloquer les opérations en fault, il faut demander :

1. **Un matricule d'adhérent AVEC bénéficiaires** (conjoint + enfants)
   → Débloque : `getListeBeneficiairesByMatricule`, `getListPlafondBeneficiairesByMatricule`, `getHistoriqueConsommation`, `getMontantDisponibleByBenef`

2. **Un matricule d'adhérent AVEC réclamations**
   → Débloque : `getListReclamationByMatricule`

3. **Un idTiers PS AVEC factures/PEC actives**
   → Débloque : `getListFactureByPs`, `getListPriseEnChargeByPs`, `getPrestationsByIdPs`

4. **Est-ce que `getListPs` est censé fonctionner ?** → Erreur "Cannot open connection" à chaque appel

5. **Y a-t-il des centres SMI configurés ?** → `centreSmiWS` retourne DataNotFoundException
