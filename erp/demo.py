# -*- coding: utf-8 -*-
"""Jeu de données FICTIF pour la démonstration (python erp_rh.py --demo)."""
import datetime as dt
from .core import connect, hash_pwd, audit, now_iso, today, params
from .vues import calculer

DEMO_USER, DEMO_PWD = "admin", "Demo2026burkina"

EMPS = [  # matricule, nom, prénoms, sexe, naissance, nationalité, embauche, emploi, service, catégorie, statut, base, logement, transport, fonction, charges, cnss
    ("M001", "OUEDRAOGO", "Aminata", "F", "1984-03-12", "Burkinabè", "2012-02-01", "Directrice générale", "Direction", "HC", "Cadre", 850000, 150000, 50000, 100000, 3, "1200456A"),
    ("M002", "SAWADOGO", "Issouf", "M", "1988-07-25", "Burkinabè", "2016-09-15", "Responsable administratif et financier", "Finance", "C2", "Cadre", 520000, 80000, 30000, 40000, 4, "1600789B"),
    ("M003", "KABORE", "Mariam", "F", "1992-11-02", "Burkinabè", "2019-01-07", "Comptable", "Finance", "B3", "Agent de maîtrise / technicien", 260000, 40000, 20000, 0, 2, "1900123C"),
    ("M004", "TRAORE", "Boukary", "M", "1990-05-18", "Burkinabè", "2018-06-01", "Chef d'atelier", "Production", "B2", "Agent de maîtrise / technicien", 230000, 35000, 20000, 15000, 3, "1800456D"),
    ("M005", "SOME", "Wendkuni Eric", "M", "1996-01-30", "Burkinabè", "2021-03-01", "Technicien de maintenance", "Production", "A3", "Employé", 145000, 20000, 15000, 0, 1, "2100789E"),
    ("M006", "ZONGO", "Fatimata", "F", "1998-09-09", "Burkinabè", "2022-10-03", "Assistante commerciale", "Commercial", "A2", "Employé", 120000, 15000, 15000, 0, 0, "2200321F"),
    ("M007", "COMPAORE", "Adama", "M", "1985-12-21", "Burkinabè", "2014-04-01", "Commercial terrain", "Commercial", "A3", "Employé", 160000, 20000, 25000, 0, 4, "1400654G"),
    ("M008", "DIALLO", "Oumar", "M", "1993-06-14", "Malienne", "2025-02-01", "Ingénieur procédés", "Production", "C1", "Cadre", 480000, 90000, 30000, 30000, 1, "2500987H"),
    ("M009", "NIKIEMA", "Rasmata", "F", "2000-02-27", "Burkinabè", "2025-06-01", "Opératrice de saisie", "Administration", "A1", "Employé", 85000, 10000, 10000, 0, 0, ""),
    ("M010", "BAMOGO", "Seydou", "M", "1979-08-05", "Burkinabè", "2003-05-02", "Magasinier", "Logistique", "A3", "Employé", 150000, 20000, 15000, 0, 4, "0300147J"),
    ("M011", "TAPSOBA", "Jean-Baptiste", "M", "1995-04-11", "Burkinabè", "2024-08-01", "Chauffeur-livreur", "Logistique", "O3", "Ouvrier", 75000, 8000, 10000, 0, 2, "2400258K"),
    ("M012", "HIEN", "Dar Clarisse", "F", "1997-10-19", "Burkinabè", "2023-01-09", "Chargée de clientèle", "Commercial", "A2", "Employé", 125000, 15000, 15000, 0, 1, "2300369L"),
    ("M013", "ILBOUDO", "Moussa", "M", "2001-07-07", "Burkinabè", "2026-09-01", "Agent d'entretien", "Administration", "O1", "Ouvrier", 42000, 0, 5000, 0, 0, "2600471M"),
]


def charger():
    conn = connect()
    if conn.execute("SELECT 1 FROM users").fetchone():
        conn.close()
        return
    h, s = hash_pwd(DEMO_PWD)
    conn.execute("INSERT INTO users(username,fullname,role,pwd_hash,pwd_salt,created_at) VALUES(?,?,?,?,?,?)", (DEMO_USER, "Administrateur démo", "admin", h, s, now_iso()))
    for k, v in dict(raison_sociale="SAHEL AGRO-TRANSFORMATION SARL (démo)", forme_juridique="SARL", secteur_activite="Agro-industrie", adresse="Zone d'activités de Kossodo, 01 BP 0000",
                     telephone="+226 25 00 00 00", ifu="00000000X", rccm="BF OUA 2012 B 0000", cnss_employeur="0000000Z", representant_legal="OUEDRAOGO Aminata",
                     qualite_representant="La Directrice générale", inspection_ressort="Direction régionale du travail du Kadiogo").items():
        conn.execute("UPDATE params SET value=? WHERE key=?", (v, k))
    t = today()
    ids = {}
    for (mat, nom, pre, sx, nais, nat, emb, emploi, serv, cat, stat, base, lg, tr, fn, ch, cnss) in EMPS:
        cur = conn.execute("INSERT INTO employees(matricule,nom,prenoms,sexe,date_naissance,lieu_naissance,nationalite,piece_type,piece_numero,situation_famille,nb_enfants,nb_charges,"
                           "date_embauche,emploi,departement,categorie,statut,cnss_no,mode_remuneration,salaire_base,ind_logement,ind_transport,ind_fonction,mode_paiement,banque,telephone) "
                           "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                           (mat, nom, pre, sx, nais, "Ouagadougou", nat, "CNIB" if nat == "Burkinabè" else "Passeport", "B" + mat[1:] * 3, "Marié(e)" if ch else "Célibataire", ch, ch,
                            emb, emploi, serv, cat, stat, cnss, "Mensuel", base, lg, tr, fn, "Virement bancaire" if base > 100000 else "Mobile money", "Banque démo", "+226 70 00 00 " + mat[2:]))
        ids[mat] = cur.lastrowid
    conn.execute("UPDATE employees SET conge_solde_initial=6, conge_date_reference=? WHERE date_embauche<?", (f"{t.year - 1}-07-01", f"{t.year - 1}-07-01"))
    C = "INSERT INTO contracts(employee_id,type,date_debut,date_fin,essai_fin,statut,motif,visa_inspection,visa_date,permis_travail,permis_expire) VALUES(?,?,?,?,?,?,?,?,?,?,?)"
    for mat, *_ in EMPS:
        emb = EMPS[[x[0] for x in EMPS].index(mat)][6]
        if mat == "M006":   # trois CDD successifs, le dernier en cours
            for a, b, st in (("2022-10-03", "2023-10-02", "Renouvelé"), ("2023-10-03", "2024-10-02", "Renouvelé"), ("2024-10-03", (t + dt.timedelta(days=20)).isoformat(), "En cours")):
                conn.execute(C, (ids[mat], "CDD", a, b, None, st, "Surcroît d'activité commerciale", "", None, "", None))
        elif mat == "M011":
            conn.execute(C, (ids[mat], "CDD", emb, "2026-07-31", None, "En cours", "Remplacement", "", None, "", None))   # CDD échu, relation poursuivie
        elif mat == "M008":
            conn.execute(C, (ids[mat], "CDI", emb, None, None, "En cours", "", "", None, "", None))                      # non-national sans visa
        elif mat == "M013":
            conn.execute(C, (ids[mat], "CDI", emb, None, (t + dt.timedelta(days=9)).isoformat(), "En cours", "", "", None, "", None))
        elif mat != "M009":                                                                                             # M009 : aucun contrat
            conn.execute(C, (ids[mat], "CDI", emb, None, None, "En cours", "", "", None, "", None))
    y = t.year
    L = "INSERT INTO leaves(employee_id,type,date_debut,date_fin,jours,statut,motif,valide_par) VALUES(?,?,?,?,?,?,?,?)"
    conn.execute(L, (ids["M003"], "Congé annuel", f"{y}-08-03", f"{y}-08-23", 21, "Approuvé", "Congé annuel", "admin"))
    conn.execute(L, (ids["M007"], "Congé annuel", f"{y}-04-06", f"{y}-05-05", 30, "Approuvé", "Congé annuel", "admin"))
    conn.execute(L, (ids["M012"], "Congé de maternité", f"{y}-02-02", f"{y}-05-10", 98, "Approuvé", "Certificat médical", "admin"))
    conn.execute(L, (ids["M005"], "Absence injustifiée", f"{y}-{max(1, t.month - 1):02d}-10", f"{y}-{max(1, t.month - 1):02d}-11", 2, "Approuvé", "", "admin"))
    conn.execute(L, (ids["M004"], "Congé annuel", (t + dt.timedelta(days=12)).isoformat(), (t + dt.timedelta(days=32)).isoformat(), 21, "Demandé", "", None))
    for mat in ("M001", "M002", "M003", "M004", "M005", "M007", "M010", "M012"):
        conn.execute("INSERT INTO medical(employee_id,date,type,resultat,prochaine,medecin) VALUES(?,?,?,?,?,?)", (ids[mat], EMPS[[x[0] for x in EMPS].index(mat)][6], "Embauche", "Apte", None, "OST Ouagadougou"))
        conn.execute("INSERT INTO medical(employee_id,date,type,resultat,prochaine,medecin) VALUES(?,?,?,?,?,?)",
                     (ids[mat], f"{y}-03-15", "Périodique", "Apte", f"{y + 1}-03-15", "OST Ouagadougou"))
    conn.execute("INSERT INTO accidents(employee_id,date,heure,nature,lieu,circonstances,lesions,jours_arret,declare_cnss_le,declare_inspection_le) VALUES(?,?,?,?,?,?,?,?,?,?)",
                 (ids["M004"], f"{y}-06-18", "10:30", "Accident du travail", "Atelier", "Chute d'une pièce lors d'une manutention", "Contusion pied droit", 5, f"{y}-06-19", f"{y}-06-19"))
    conn.execute("INSERT INTO sanctions(employee_id,date,type,motif,date_explication,date_notification) VALUES(?,?,?,?,?,?)",
                 (ids["M005"], f"{y}-{max(1, t.month - 1):02d}-14", "Avertissement écrit", "Absence injustifiée de deux jours", f"{y}-{max(1, t.month - 1):02d}-12", f"{y}-{max(1, t.month - 1):02d}-14"))
    conn.execute("INSERT INTO trainings(employee_id,intitule,organisme,date_debut,date_fin,heures,cout) VALUES(?,?,?,?,?,?,?)",
                 (ids["M003"], "SYSCOHADA révisé – clôture des comptes", "Cabinet démo", f"{y}-02-10", f"{y}-02-12", 21, 250000))
    conn.execute("INSERT INTO representatives(employee_id,mandat,college,date_election,date_fin_mandat,pv_reference) VALUES(?,?,?,?,?,?)",
                 (ids["M010"], "Délégué du personnel titulaire", "Employés-ouvriers", f"{y - 1}-03-20", f"{y + 1}-03-19", "PV n°01 transmis le 22/03"))
    conn.execute("INSERT INTO inspections(date,inspecteur,objet,observations,mise_en_demeure,delai,statut) VALUES(?,?,?,?,?,?,?)",
                 (f"{y}-05-12", "Inspecteur du travail (démo)", "Contrôle de routine", "Affichage des horaires absent dans l'atelier.", "Afficher les horaires et le règlement intérieur.",
                  f"{y}-06-12", "En cours de traitement"))
    conn.execute("UPDATE obligations SET statut='Conforme', preuve='Récépissé du ' || ? WHERE id IN (1,2,9,10,11,12,13)", (f"15/01/{y}",))
    # paie : trois derniers mois, les deux premiers clôturés
    m0 = t.replace(day=1)
    mois = []
    for _ in range(3):
        m0 = (m0 - dt.timedelta(days=1)).replace(day=1)
        mois.insert(0, m0)
    for i, m in enumerate(mois):
        cur = conn.execute("INSERT INTO pay_periods(annee,mois) VALUES(?,?)", (m.year, m.month))
        pid = cur.lastrowid
        conn.execute("INSERT INTO pay_variables(period_id,employee_id,hs15,hs35,primes_imposables) VALUES(?,?,?,?,?)", (pid, ids["M005"], 8, 4, 0))
        conn.execute("INSERT INTO pay_variables(period_id,employee_id,primes_imposables,avance) VALUES(?,?,?,?)", (pid, ids["M007"], 60000, 25000))
        pp = conn.execute("SELECT * FROM pay_periods WHERE id=?", (pid,)).fetchone()
        calculer(conn, pp)
        if i < 2:
            conn.execute("UPDATE pay_periods SET statut='cloturee', cloture_le=?, cloture_par='admin' WHERE id=?", (now_iso(), pid))
    audit(conn, "système", "CHARGEMENT_DEMO", "base", "", "Données fictives de démonstration")
    conn.commit()
    conn.close()
    print(f"Base de démonstration créée — identifiant : {DEMO_USER} / mot de passe : {DEMO_PWD}")
