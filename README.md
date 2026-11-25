# ERP RH Burkina — PME de moins de 100 salariés

Application de gestion des ressources humaines et de la paie adaptée au droit burkinabè, conçue pour qu'une PME puisse
répondre, pièces à l'appui, à un contrôle de l'inspection du travail.

- **Aucune installation complexe** : Python 3.9+ uniquement, aucune bibliothèque à télécharger, aucun accès Internet requis.
- **Données chez vous** : un seul fichier `data/erp_rh.db` (SQLite), sauvegardé automatiquement chaque jour.
- **Utilisation dans le navigateur** (Chrome, Edge, Firefox), en français.

## 1. Démarrage

| Système | Action |
|---|---|
| Windows | Installer Python depuis python.org (cocher « Add Python to PATH »), puis double-cliquer `Lancer_ERP.bat` |
| Linux / macOS | `./lancer.sh` |
| Découverte | `Lancer_DEMO.bat` (ou `./lancer.sh --demo`) : entreprise fictive de 13 salariés — identifiant `admin`, mot de passe `Demo2026burkina` |

Au premier lancement réel, l'écran crée le compte administrateur. Ensuite, dans l'ordre :

1. **Paramètres → Entreprise** : raison sociale, IFU, RCCM, n° employeur CNSS, inspection du ressort.
2. **Paramètres → Paie / Barème IUTS / Droit du travail** : **valider le référentiel légal** (voir § 5).
3. **Paramètres → Utilisateurs** : un compte nominatif par personne (jamais de compte partagé).
4. **Employés**, puis pour chacun : contrat, visite médicale d'embauche, pièces du dossier. Pour une reprise en cours
   d'année, saisir le « solde de congés repris » et sa date de référence.
5. **Conformité → Suivi des obligations légales** : renseigner statut, échéance et preuve de chaque obligation.

## 2. Modules

| Module | Contenu |
|---|---|
| Employés | Fiche complète (état civil, CNSS, emploi, catégorie, rémunération, charges IUTS), ancienneté, préavis applicable |
| Contrats | CDI, CDD, essai, stage, apprentissage, temporaire ; visa de l'inspection et permis de travail des non-nationaux |
| Congés & absences | Droits acquis (2,5 j/mois + majoration d'ancienneté), contrôle du solde et des chevauchements, validation |
| Paie | Variables du mois, calcul CNSS / IUTS / TPA, prime d'ancienneté, heures supplémentaires majorées, prorata, bulletins, **clôture irréversible** |
| Discipline | Registre des sanctions avec dates d'explication et de notification |
| Santé & sécurité | Visites médicales (aptitude seulement), registre des accidents du travail, contrôle du délai de déclaration |
| Formation | Actions, heures, coûts |
| Représentants | Délégués du personnel, CSST, délégués syndicaux, fins de mandat |
| Conformité | ~25 contrôles automatiques + suivi des 21 obligations de l'employeur avec preuves |
| Dossier Inspection | Chaque question habituelle de l'inspecteur → l'état qui y répond ; dossier annuel complet imprimable |
| Rapports | 19 états (registre d'employeur en 3 fascicules, livre de paie, CNSS, IUTS/TPA, main-d'œuvre, CDD, SMIG…), tous exportables vers Excel (CSV) |
| Documents | Attestation et certificat de travail, simulation du solde de tout compte |

### Cycle mensuel de paie
`Paie` → ouvrir la période → saisir les **variables** (absences non payées, heures sup., primes, avances) →
**Calculer** → contrôler le livre de paie → imprimer les bulletins → **Clôturer** → états CNSS et IUTS/TPA.
Une période clôturée ne peut plus être modifiée (réouverture réservée à l'administrateur, avec motif tracé).
Chaque bulletin conserve une copie figée des taux et de la situation du salarié au moment du calcul.

### Jour du contrôle
`Dossier Inspection` → « Éditer le dossier complet » → Ctrl+P (PDF ou papier). Vous pouvez aussi créer à l'inspecteur un
compte de profil **Consultation seule**. Consignez ensuite la visite, les observations et les mises en demeure : elles
alimentent le fascicule 3 du registre d'employeur et les alertes de délai.

## 3. Sécurité

| Mesure intégrée | Détail |
|---|---|
| Comptes nominatifs, 4 profils | Administrateur, Gestionnaire RH, Gestionnaire de paie, Consultation seule |
| Mots de passe | Hachage PBKDF2-SHA256 salé (310 000 itérations), 10 caractères minimum, changement imposé à la première connexion |
| Anti-intrusion | Verrouillage après 5 échecs, déconnexion après 30 min d'inactivité, jeton anti-CSRF sur chaque action, cookie HttpOnly/SameSite=Strict, en-têtes CSP |
| Piste d'audit inviolable | Chaque création, modification, suppression, connexion, clôture est journalisée ; les écritures sont chaînées par empreinte SHA-256 : toute altération est détectée (Paramètres → Journal d'audit) |
| Intégrité de la paie | Clôture irréversible, bulletins figés |
| Registre | Un salarié ayant un historique ne peut pas être supprimé (seulement « sorti ») |
| Sauvegardes | Automatique chaque jour au démarrage + bouton manuel ; 60 conservées dans `data/sauvegardes/` |
| Réseau | Par défaut, accessible uniquement depuis le poste lui-même (127.0.0.1) |

**Ce qui reste à votre charge** (aucun logiciel ne peut le faire à votre place) :

- **Chiffrer le disque** du poste (BitLocker sous Windows) : la base n'est pas chiffrée au repos.
- **Copier `data/sauvegardes/`** chaque semaine sur un support externe chiffré conservé hors des locaux. Restauration :
  arrêter l'ERP, remplacer `data/erp_rh.db` par une sauvegarde, redémarrer.
- **Accès à plusieurs postes** : utiliser HTTPS, sinon les mots de passe circulent en clair sur le réseau :
  ```bash
  openssl req -x509 -newkey rsa:2048 -nodes -days 825 -keyout key.pem -out cert.pem -subj "/CN=erp-rh"
  ```
  ```bash
  python erp_rh.py --host 0.0.0.0 --cert cert.pem --key key.pem
  ```
- **Données personnelles** : déclarer le traitement à la CIL (loi n°001-2021/AN), limiter les accès au strict nécessaire,
  ne saisir aucun diagnostic médical.

## 4. Formules de paie

```
Brut       = (base + sursalaire + indemnités + primes fixes) × jours payés/30
             + prime d'ancienneté + heures sup. majorées + primes du mois + avantages en nature
CNSS       = min(brut, plafond) × 5,5 % (salarié) ; 16 % employeur (pensions 5,5 + prest. familiales 7 + risques prof. 3,5)
Base IUTS  = brut – exonérations (logement, transport, fonction, plafonnées) – CNSS salarié – abattement (20 % cadres / 25 % autres, sur le salaire de base)
             arrondie à la centaine inférieure
IUTS       = barème progressif × (1 – réduction pour charges : 8 / 10 / 12 / 14 %)
TPA        = (brut – exonérations) × 3 %
Net        = brut – avantages en nature – CNSS – IUTS – avances – retenues + remboursements de frais
```

## 5. Référentiel légal : à valider avant la première paie réelle

Aucun taux n'est codé en dur : tout se modifie dans **Paramètres**, et chaque changement est tracé.
Le droit social burkinabè a beaucoup évolué en 2026 ; les valeurs livrées sont un point de départ, pas un avis juridique.

| Point | Valeur livrée | À faire |
|---|---|---|
| Code du travail du 6 mai 2026 (remplace la loi 028-2008) | CDD : 2 renouvellements, 3 contrats, 24 mois ; dommages-intérêts plafonnés à 24 mois | Les durées d'essai, de préavis, les seuils (délégués, CSST) sont ceux de l'ancien régime : **à confronter au texte publié et à ses décrets d'application** |
| Plafond CNSS | 800 000 FCFA/mois | **À confirmer auprès de la CNSS** (ancien plafond : 600 000) |
| IUTS | Barème 0 – 12,1 – 13,9 – 15,7 – 18,4 – 21,7 – 25 % ; abattements 20/25 % ; exonérations logement 20 % ≤ 75 000, transport et fonction 5 % ≤ 30 000 | **À confirmer avec la DGI / la dernière loi de finances**, y compris l'assiette des pourcentages |
| SMIG | 45 000 FCFA (décret de 2023) | Vérifier l'absence de revalorisation |
| Jours fériés | 11 jours chômés et payés (loi de janvier 2026) | Dates des fêtes mobiles à ajuster selon les communiqués |
| Convention collective | Interprofessionnelle de 1974 (ancienneté 3 % dès 3 ans + 1 %/an ; licenciement 25/30/40 %) | Adapter si une convention sectorielle s'applique (salaires catégoriels notamment) |

Non couvert par cette version : salaires minima catégoriels par convention (le contrôle porte sur le SMIG), téléchargement
de pièces scannées (seuls la référence et l'emplacement sont suivis), télédéclarations e-CNSS / eSINTAX (les états servent
de base de saisie), pointage horaire.

## 6. Technique

```
erp_rh.py          lancement            erp/paie.py       règles de calcul (fonctions pures)
erp/core.py        serveur, sécurité    erp/entites.py    formulaires génériques
erp/schema.py      base + référentiel   erp/rapports.py   conformité, états, dossier inspection
erp/vues.py        écrans               tests/            12 tests automatiques
```

```bash
python -m unittest discover -s tests -v
```
