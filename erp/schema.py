# -*- coding: utf-8 -*-
"""Schéma de la base, référentiel légal paramétrable et données initiales."""
from .core import connect, audit

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL, fullname TEXT NOT NULL, role TEXT NOT NULL,
  pwd_hash TEXT NOT NULL, pwd_salt TEXT NOT NULL, must_change INTEGER DEFAULT 0, failed INTEGER DEFAULT 0, locked_until REAL DEFAULT 0,
  active INTEGER DEFAULT 1, created_at TEXT);
CREATE TABLE IF NOT EXISTS sessions(token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL, csrf TEXT, created_at REAL, last_seen REAL, ip TEXT);
CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY, ts TEXT, user TEXT, action TEXT, entity TEXT, entity_id TEXT, details TEXT, prev_hash TEXT, hash TEXT);
CREATE TABLE IF NOT EXISTS params(key TEXT PRIMARY KEY, value TEXT, label TEXT, grp TEXT, source TEXT, ordre INTEGER);
CREATE TABLE IF NOT EXISTS iuts_bareme(id INTEGER PRIMARY KEY, borne_inf REAL, borne_sup REAL, taux REAL);
CREATE TABLE IF NOT EXISTS feries(id INTEGER PRIMARY KEY, date TEXT NOT NULL, libelle TEXT NOT NULL, type TEXT, notes TEXT);
CREATE TABLE IF NOT EXISTS employees(id INTEGER PRIMARY KEY, matricule TEXT UNIQUE NOT NULL, nom TEXT NOT NULL, prenoms TEXT NOT NULL, sexe TEXT,
  date_naissance TEXT, lieu_naissance TEXT, nationalite TEXT, piece_type TEXT, piece_numero TEXT, situation_famille TEXT, nb_enfants INTEGER DEFAULT 0,
  nb_charges INTEGER DEFAULT 0, adresse TEXT, telephone TEXT, email TEXT, contact_urgence TEXT, cnss_no TEXT, date_embauche TEXT NOT NULL,
  emploi TEXT, departement TEXT, categorie TEXT, statut TEXT, mode_remuneration TEXT, salaire_base REAL DEFAULT 0, sursalaire REAL DEFAULT 0,
  ind_logement REAL DEFAULT 0, ind_transport REAL DEFAULT 0, ind_fonction REAL DEFAULT 0, primes_fixes REAL DEFAULT 0,
  mode_paiement TEXT, banque TEXT, compte TEXT, handicap TEXT, conge_solde_initial REAL DEFAULT 0, conge_date_reference TEXT,
  date_sortie TEXT, motif_sortie TEXT, notes TEXT);
CREATE TABLE IF NOT EXISTS contracts(id INTEGER PRIMARY KEY, employee_id INTEGER NOT NULL REFERENCES employees(id), type TEXT NOT NULL, reference TEXT,
  date_debut TEXT NOT NULL, date_fin TEXT, essai_fin TEXT, essai_renouvele TEXT, motif TEXT, visa_inspection TEXT, visa_date TEXT, permis_travail TEXT,
  permis_expire TEXT, statut TEXT, notes TEXT);
CREATE TABLE IF NOT EXISTS leaves(id INTEGER PRIMARY KEY, employee_id INTEGER NOT NULL REFERENCES employees(id), type TEXT NOT NULL, date_debut TEXT NOT NULL,
  date_fin TEXT NOT NULL, jours REAL, statut TEXT, motif TEXT, valide_par TEXT, notes TEXT);
CREATE TABLE IF NOT EXISTS pay_periods(id INTEGER PRIMARY KEY, annee INTEGER, mois INTEGER, statut TEXT DEFAULT 'ouverte', cloture_le TEXT, cloture_par TEXT, UNIQUE(annee,mois));
CREATE TABLE IF NOT EXISTS pay_variables(id INTEGER PRIMARY KEY, period_id INTEGER NOT NULL REFERENCES pay_periods(id), employee_id INTEGER NOT NULL REFERENCES employees(id),
  jours_non_payes REAL DEFAULT 0, hs15 REAL DEFAULT 0, hs35 REAL DEFAULT 0, hs50 REAL DEFAULT 0, hs60 REAL DEFAULT 0, hs120 REAL DEFAULT 0,
  primes_imposables REAL DEFAULT 0, avantages_nature REAL DEFAULT 0, remboursements REAL DEFAULT 0, avance REAL DEFAULT 0, autres_retenues REAL DEFAULT 0,
  note TEXT, UNIQUE(period_id,employee_id));
CREATE TABLE IF NOT EXISTS payslips(id INTEGER PRIMARY KEY, period_id INTEGER NOT NULL REFERENCES pay_periods(id), employee_id INTEGER NOT NULL REFERENCES employees(id),
  brut REAL, base_cnss REAL, cnss_sal REAL, iuts REAL, retenues REAL, net REAL, cnss_pat REAL, tpa REAL, heures_sup REAL, data TEXT, calcule_le TEXT,
  UNIQUE(period_id,employee_id));
CREATE TABLE IF NOT EXISTS sanctions(id INTEGER PRIMARY KEY, employee_id INTEGER NOT NULL REFERENCES employees(id), date TEXT NOT NULL, type TEXT NOT NULL, motif TEXT,
  duree_jours REAL, date_explication TEXT, date_notification TEXT, notes TEXT);
CREATE TABLE IF NOT EXISTS medical(id INTEGER PRIMARY KEY, employee_id INTEGER NOT NULL REFERENCES employees(id), date TEXT NOT NULL, type TEXT, resultat TEXT,
  prochaine TEXT, medecin TEXT, notes TEXT);
CREATE TABLE IF NOT EXISTS accidents(id INTEGER PRIMARY KEY, employee_id INTEGER NOT NULL REFERENCES employees(id), date TEXT NOT NULL, heure TEXT, nature TEXT, lieu TEXT,
  circonstances TEXT, lesions TEXT, jours_arret REAL, temoins TEXT, declare_cnss_le TEXT, declare_inspection_le TEXT, notes TEXT);
CREATE TABLE IF NOT EXISTS trainings(id INTEGER PRIMARY KEY, employee_id INTEGER NOT NULL REFERENCES employees(id), intitule TEXT NOT NULL, organisme TEXT,
  date_debut TEXT, date_fin TEXT, heures REAL, cout REAL, notes TEXT);
CREATE TABLE IF NOT EXISTS representatives(id INTEGER PRIMARY KEY, employee_id INTEGER NOT NULL REFERENCES employees(id), mandat TEXT NOT NULL, college TEXT,
  date_election TEXT, date_fin_mandat TEXT, pv_reference TEXT, notes TEXT);
CREATE TABLE IF NOT EXISTS inspections(id INTEGER PRIMARY KEY, date TEXT NOT NULL, inspecteur TEXT, objet TEXT, observations TEXT, mise_en_demeure TEXT,
  delai TEXT, date_levee TEXT, statut TEXT, notes TEXT);
CREATE TABLE IF NOT EXISTS documents(id INTEGER PRIMARY KEY, employee_id INTEGER NOT NULL REFERENCES employees(id), type TEXT NOT NULL, reference TEXT, date TEXT,
  expire TEXT, emplacement TEXT, notes TEXT);
CREATE TABLE IF NOT EXISTS obligations(id INTEGER PRIMARY KEY, libelle TEXT NOT NULL, reference TEXT, frequence TEXT, statut TEXT, echeance TEXT, preuve TEXT, notes TEXT);
CREATE INDEX IF NOT EXISTS ix_c_emp ON contracts(employee_id);
CREATE INDEX IF NOT EXISTS ix_l_emp ON leaves(employee_id);
CREATE INDEX IF NOT EXISTS ix_ps_per ON payslips(period_id);
"""

V = "À VÉRIFIER"
CT = "Code du travail (loi du 6 mai 2026 ; à défaut de texte d'application, pratique issue de la loi 028-2008/AN)"
CCI = "Convention collective interprofessionnelle du 9 juillet 1974"
CGI = "Code général des impôts (IUTS) et lois de finances"
CSS_ = "Code de sécurité sociale (loi 015-2006/AN modifiée par la loi 004-2021/AN)"

# (clé, valeur, libellé, groupe, source)
PARAMS = [
    # --- entreprise
    ("raison_sociale", "", "Raison sociale", "entreprise", ""),
    ("forme_juridique", "", "Forme juridique", "entreprise", ""),
    ("secteur_activite", "", "Secteur d'activité", "entreprise", ""),
    ("adresse", "", "Adresse / siège", "entreprise", ""),
    ("ville", "Ouagadougou", "Ville", "entreprise", ""),
    ("telephone", "", "Téléphone", "entreprise", ""),
    ("email", "", "E-mail", "entreprise", ""),
    ("ifu", "", "N° IFU", "entreprise", ""),
    ("rccm", "", "N° RCCM", "entreprise", ""),
    ("cnss_employeur", "", "N° employeur CNSS", "entreprise", ""),
    ("representant_legal", "", "Représentant légal", "entreprise", ""),
    ("qualite_representant", "Gérant", "Qualité du représentant", "entreprise", ""),
    ("convention_collective", CCI, "Convention collective applicable", "entreprise", ""),
    ("inspection_ressort", "", "Inspection du travail du ressort", "entreprise", ""),
    ("date_ouverture", "", "Date de déclaration d'ouverture (AAAA-MM-JJ)", "entreprise", ""),
    # --- paie
    ("smig_mensuel", "45000", "SMIG mensuel (FCFA)", "paie", "Décret de 2023 fixant le SMIG (45 000 F ; 259,62 F/h)"),
    ("heures_mois", "173.33", "Heures mensuelles de référence (40 h/sem.)", "paie", CT),
    ("cnss_plafond", "800000", "Plafond mensuel des salaires soumis à cotisation CNSS", "paie", "Arrêté n°2022-067/MFPTPS du 30/08/2022 — " + V + " auprès de la CNSS (ancien plafond : 600 000)"),
    ("cnss_taux_sal", "5.5", "CNSS – part salariale pensions (%)", "paie", CSS_),
    ("cnss_taux_pension_pat", "5.5", "CNSS – part patronale pensions (%)", "paie", CSS_),
    ("cnss_taux_pf", "7", "CNSS – prestations familiales, part patronale (%)", "paie", CSS_),
    ("cnss_taux_rp", "3.5", "CNSS – risques professionnels, part patronale (%)", "paie", CSS_),
    ("tpa_taux", "3", "Taxe patronale et d'apprentissage (%)", "paie", CGI),
    ("abatt_cadre", "20", "IUTS – abattement forfaitaire cadres (% du salaire de base)", "paie", CGI + " — " + V),
    ("abatt_non_cadre", "25", "IUTS – abattement forfaitaire non-cadres (% du salaire de base)", "paie", CGI + " — " + V),
    ("exo_logement_pct", "20", "IUTS – exonération indemnité de logement (% du brut)", "paie", CGI + " — " + V),
    ("exo_logement_plafond", "75000", "IUTS – plafond mensuel exonération logement", "paie", CGI + " — " + V),
    ("exo_transport_pct", "5", "IUTS – exonération indemnité de transport (% du brut)", "paie", CGI + " — " + V),
    ("exo_transport_plafond", "30000", "IUTS – plafond mensuel exonération transport", "paie", CGI + " — " + V),
    ("exo_fonction_pct", "5", "IUTS – exonération indemnité de fonction (% du brut)", "paie", CGI + " — " + V),
    ("exo_fonction_plafond", "30000", "IUTS – plafond mensuel exonération fonction", "paie", CGI + " — " + V),
    ("charges_1", "8", "IUTS – réduction pour 1 charge (%)", "paie", CGI + " — " + V),
    ("charges_2", "10", "IUTS – réduction pour 2 charges (%)", "paie", CGI + " — " + V),
    ("charges_3", "12", "IUTS – réduction pour 3 charges (%)", "paie", CGI + " — " + V),
    ("charges_4", "14", "IUTS – réduction pour 4 charges et plus (%)", "paie", CGI + " — " + V),
    ("hs15", "15", "Heures sup. 41e à 48e heure – majoration (%)", "paie", CT),
    ("hs35", "35", "Heures sup. au-delà de la 48e heure – majoration (%)", "paie", CT),
    ("hs50", "50", "Heures sup. de nuit jours ouvrables – majoration (%)", "paie", CT),
    ("hs60", "60", "Heures sup. de jour dimanche/jour férié – majoration (%)", "paie", CT),
    ("hs120", "120", "Heures sup. de nuit dimanche/jour férié – majoration (%)", "paie", CT),
    ("anc_seuil", "3", "Prime d'ancienneté – années requises", "paie", CCI),
    ("anc_taux", "3", "Prime d'ancienneté – taux au seuil (% du salaire de base)", "paie", CCI),
    ("anc_increment", "1", "Prime d'ancienneté – % par année supplémentaire", "paie", CCI),
    ("anc_max", "25", "Prime d'ancienneté – taux maximum (%)", "paie", CCI + " — " + V),
    # --- droit du travail
    ("duree_hebdo", "40", "Durée légale hebdomadaire (heures)", "travail", CT),
    ("hs_contingent_annuel", "0", "Contingent annuel d'heures sup. par salarié (0 = pas de contrôle)", "travail", "Textes d'application — à renseigner"),
    ("conge_jours_mois", "2.5", "Congés payés – jours calendaires acquis par mois", "travail", CT),
    ("conge_bonus_20", "2", "Congés – jours supplémentaires après 20 ans", "travail", CT),
    ("conge_bonus_25", "4", "Congés – jours supplémentaires après 25 ans", "travail", CT),
    ("conge_bonus_30", "6", "Congés – jours supplémentaires après 30 ans", "travail", CT),
    ("conge_solde_alerte", "60", "Alerte si solde de congés supérieur à (jours)", "travail", "Seuil interne"),
    ("essai_cadre_mois", "3", "Essai – cadres, agents de maîtrise, techniciens (mois)", "travail", CT + " — " + V),
    ("essai_employe_mois", "1", "Essai – employés payés au mois (mois)", "travail", CT + " — " + V),
    ("essai_ouvrier_jours", "8", "Essai – travailleurs payés à l'heure ou à la journée (jours)", "travail", CT + " — " + V),
    ("preavis_cadre_mois", "3", "Préavis – cadres, agents de maîtrise, techniciens (mois)", "travail", CT + " — " + V),
    ("preavis_mensuel_mois", "1", "Préavis – employés payés au mois (mois)", "travail", CT + " — " + V),
    ("preavis_horaire_jours", "8", "Préavis – travailleurs payés à l'heure/journée (jours)", "travail", CT + " — " + V),
    ("cdd_max_renouv", "2", "CDD – nombre maximal de renouvellements", "travail", "Code du travail du 6 mai 2026"),
    ("cdd_max_contrats", "3", "CDD – nombre maximal de CDD avec le même travailleur", "travail", "Code du travail du 6 mai 2026"),
    ("cdd_duree_max_mois", "24", "CDD – durée maximale cumulée (mois)", "travail", "Code du travail du 6 mai 2026"),
    ("lic_taux_1", "25", "Indemnité de licenciement – % du salaire mensuel moyen par année (1 à 5 ans)", "travail", CCI),
    ("lic_taux_2", "30", "Indemnité de licenciement – % par année (6 à 10 ans)", "travail", CCI),
    ("lic_taux_3", "40", "Indemnité de licenciement – % par année (au-delà de 10 ans)", "travail", CCI),
    ("dommages_max_mois", "24", "Licenciement abusif – plafond des dommages-intérêts (mois de salaire)", "travail", "Code du travail du 6 mai 2026"),
    ("seuil_dp", "11", "Délégués du personnel obligatoires à partir de (travailleurs)", "travail", CT + " — " + V),
    ("mandat_dp_ans", "2", "Durée du mandat des délégués (ans)", "travail", CT + " — " + V),
    ("seuil_csst", "30", "Comité de sécurité et santé au travail à partir de (travailleurs)", "travail", CT + " — " + V),
    ("age_min", "16", "Âge minimum d'admission à l'emploi", "travail", CT),
    ("visite_med_mois", "12", "Périodicité de la visite médicale (mois)", "travail", CT + " / OST"),
    ("at_delai_h", "48", "Délai de déclaration d'un accident du travail (heures)", "travail", CSS_),
    ("maternite_semaines", "14", "Congé de maternité (semaines)", "travail", CT),
    # --- sécurité
    ("session_minutes", "30", "Déconnexion automatique après inactivité (minutes)", "securite", ""),
    ("max_echecs", "5", "Verrouillage du compte après N échecs de connexion", "securite", ""),
    ("verrou_minutes", "15", "Durée du verrouillage (minutes)", "securite", ""),
    ("backups_conserves", "60", "Nombre de sauvegardes conservées", "securite", ""),
]

BAREME = [(0, 30000, 0), (30000, 50000, 12.1), (50000, 80000, 13.9), (80000, 120000, 15.7),
          (120000, 170000, 18.4), (170000, 250000, 21.7), (250000, None, 25)]

CP = "Chômé et payé"
FERIES = [
    ("2026-01-01", "Jour de l'An", CP), ("2026-03-08", "Journée internationale de la femme", CP),
    ("2026-03-20", "Ramadan (Aïd el-Fitr) – date à confirmer", CP), ("2026-05-01", "Fête du Travail", CP),
    ("2026-05-14", "Ascension", CP), ("2026-05-15", "Journée des coutumes et traditions", CP),
    ("2026-05-27", "Tabaski (Aïd el-Kébir) – date à confirmer", CP), ("2026-08-15", "Assomption", CP),
    ("2026-08-25", "Mouloud – date à confirmer", CP), ("2026-12-11", "Fête nationale", CP), ("2026-12-25", "Noël", CP),
    ("2026-10-31", "Journée de commémoration (insurrection populaire)", "Commémoration (travaillée)"),
    ("2026-11-01", "Toussaint – journée de recueillement", "Commémoration (travaillée)"),
    ("2027-01-01", "Jour de l'An", CP), ("2027-03-08", "Journée internationale de la femme", CP),
    ("2027-03-10", "Ramadan (Aïd el-Fitr) – date à confirmer", CP), ("2027-05-01", "Fête du Travail", CP),
    ("2027-05-06", "Ascension", CP), ("2027-05-15", "Journée des coutumes et traditions", CP),
    ("2027-05-17", "Tabaski (Aïd el-Kébir) – date à confirmer", CP), ("2027-08-15", "Assomption / Mouloud – date à confirmer", CP),
    ("2027-12-11", "Fête nationale", CP), ("2027-12-25", "Noël", CP),
]

OBLIG = [
    ("Déclaration d'ouverture / d'existence de l'établissement à l'inspection du travail", "Code du travail", "Unique (et à chaque modification)"),
    ("Registre d'employeur tenu à jour (3 fascicules) et tenu à la disposition de l'inspecteur", "Code du travail", "Permanent"),
    ("Déclaration des mouvements de personnel (embauches / départs)", "Code du travail", "À chaque mouvement"),
    ("Déclaration annuelle de la situation de la main-d'œuvre", "Code du travail", "Annuelle (janvier)"),
    ("Règlement intérieur soumis au visa de l'inspecteur du travail, déposé et affiché", "Code du travail", "Unique (et à chaque modification)"),
    ("Affichages obligatoires : horaires de travail, règlement intérieur, adresse de l'inspection, consignes de sécurité, convention collective", "Code du travail", "Permanent"),
    ("Contrats de travail écrits ; CDD et contrats des travailleurs non nationaux visés par l'inspection", "Code du travail", "À chaque contrat"),
    ("Permis de travail des travailleurs non nationaux", "Code du travail du 6 mai 2026", "À chaque recrutement / renouvellement"),
    ("Immatriculation de l'employeur et de chaque travailleur à la CNSS", "Code de sécurité sociale", "À l'embauche"),
    ("Déclarations et paiement des cotisations CNSS", "Code de sécurité sociale", "Mensuelle ou trimestrielle selon l'effectif"),
    ("Déclaration et versement IUTS et TPA", "Code général des impôts", "Mensuelle"),
    ("Remise d'un bulletin de paie à chaque paie et tenue du registre des paiements", "Code du travail", "Mensuelle"),
    ("Élection des délégués du personnel (procès-verbal transmis à l'inspection)", "Code du travail", "Tous les 2 ans"),
    ("Comité de sécurité et santé au travail (CSST) – mise en place et réunions", "Code du travail", "Selon effectif ; réunions périodiques"),
    ("Affiliation à l'Office de santé des travailleurs (OST) ou service de santé au travail ; visites médicales d'embauche et périodiques", "Code du travail", "Annuelle"),
    ("Déclaration des accidents du travail et maladies professionnelles (CNSS et inspection)", "Code de sécurité sociale", "Sous 48 heures"),
    ("Évaluation des risques professionnels, registre de sécurité, trousse de premiers secours, EPI", "Code du travail", "Annuelle"),
    ("Convention collective applicable tenue à la disposition du personnel", "Code du travail", "Permanent"),
    ("Planning des départs en congé établi et communiqué", "Code du travail", "Annuelle"),
    ("Dispositif de prévention du harcèlement moral et sexuel", "Code du travail du 6 mai 2026", "Permanent"),
    ("Déclaration du traitement des données personnelles RH auprès de la CIL", "Loi 001-2021/AN (protection des données)", "Unique"),
]


def init_db():
    conn = connect()
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA)
    for i, (k, v, label, grp, src) in enumerate(PARAMS):
        conn.execute("INSERT OR IGNORE INTO params(key,value,label,grp,source,ordre) VALUES(?,?,?,?,?,?)", (k, v, label, grp, src, i))
        conn.execute("UPDATE params SET label=?, grp=?, source=?, ordre=? WHERE key=?", (label, grp, src, i, k))
    if not conn.execute("SELECT 1 FROM iuts_bareme").fetchone():
        conn.executemany("INSERT INTO iuts_bareme(borne_inf,borne_sup,taux) VALUES(?,?,?)", BAREME)
    if not conn.execute("SELECT 1 FROM feries").fetchone():
        conn.executemany("INSERT INTO feries(date,libelle,type) VALUES(?,?,?)", FERIES)
    if not conn.execute("SELECT 1 FROM obligations").fetchone():
        conn.executemany("INSERT INTO obligations(libelle,reference,frequence,statut) VALUES(?,?,?,'À faire')", OBLIG)
    if not conn.execute("SELECT 1 FROM audit").fetchone():
        audit(conn, "système", "INITIALISATION", "base", "", "Création de la base de données")
    conn.execute("DELETE FROM sessions")
    conn.commit()
    conn.close()
