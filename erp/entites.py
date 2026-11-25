# -*- coding: utf-8 -*-
"""Définition des entités RH et moteur générique de saisie (liste / formulaire / suppression), avec audit."""
from .core import (route, page, redirect, e, d, fr, money, num, audit, csrf_field, table, post_btn, csv_resp, Forbidden, params, today)
from . import paie as M


def F(name, label, typ="text", req=False, choices=None, help="", grp=None):
    return dict(name=name, label=label, typ=typ, req=req, choices=choices, help=help, grp=grp)


EMP = F("employee_id", "Employé", "emp", req=True)
STATUTS = ["Cadre", "Agent de maîtrise / technicien", "Employé", "Ouvrier"]
CONTRATS = ["CDI", "CDD", "Contrat à l'essai", "Stage", "Apprentissage", "Travail temporaire", "Saisonnier / journalier"]
CONGES = ["Congé annuel", "Congé de maternité", "Congé de paternité", "Permission exceptionnelle (événement familial)", "Maladie",
          "Accident du travail", "Congé sans solde", "Absence injustifiée", "Mise à pied", "Formation", "Autre absence autorisée"]
NON_PAYES = ("Congé sans solde", "Absence injustifiée", "Mise à pied")
MOTIFS_SORTIE = ["", "Démission", "Licenciement pour motif personnel", "Licenciement pour motif économique", "Licenciement pour faute lourde",
                 "Fin de CDD", "Rupture en période d'essai", "Rupture d'un commun accord", "Retraite", "Décès", "Autre"]

E = {}

E["employes"] = dict(
    table="employees", titre="Employés", un="un employé", order="nom, prenoms", emp_field=None,
    list=[("matricule", "Matricule"), ("nom", "Nom"), ("prenoms", "Prénoms"), ("emploi", "Emploi"), ("departement", "Service"),
          ("statut", "Statut"), ("date_embauche", "Embauche"), ("date_sortie", "Sortie")],
    search=["matricule", "nom", "prenoms", "emploi", "departement", "cnss_no"],
    fields=[
        F("matricule", "Matricule", req=True, grp="Identité"), F("nom", "Nom", req=True), F("prenoms", "Prénoms", req=True),
        F("sexe", "Sexe", "select", choices=["", "F", "M"]), F("date_naissance", "Date de naissance", "date"), F("lieu_naissance", "Lieu de naissance"),
        F("nationalite", "Nationalité", help="Laisser « Burkinabè » pour les nationaux"),
        F("piece_type", "Pièce d'identité", "select", choices=["", "CNIB", "Passeport", "Carte consulaire", "Autre"]), F("piece_numero", "N° de la pièce"),
        F("situation_famille", "Situation de famille", "select", choices=["", "Célibataire", "Marié(e)", "Veuf(ve)", "Divorcé(e)"]),
        F("nb_enfants", "Nombre d'enfants", "int"), F("nb_charges", "Charges fiscales IUTS (0 à 4)", "int", help="Sert à la réduction d'impôt pour charges de famille"),
        F("handicap", "Travailleur en situation de handicap", "select", choices=["", "Non", "Oui"]),
        F("adresse", "Adresse", grp="Coordonnées"), F("telephone", "Téléphone"), F("email", "E-mail"), F("contact_urgence", "Personne à prévenir (nom, tél.)"),
        F("date_embauche", "Date d'embauche", "date", req=True, grp="Emploi"), F("emploi", "Emploi occupé"), F("departement", "Service / département"),
        F("categorie", "Catégorie / échelon (classification)"), F("statut", "Statut professionnel", "select", choices=STATUTS, req=True),
        F("cnss_no", "N° d'immatriculation CNSS"),
        F("mode_remuneration", "Mode de rémunération", "select", choices=["Mensuel", "Horaire / journalier"], grp="Rémunération mensuelle (FCFA)"),
        F("salaire_base", "Salaire de base", "money"), F("sursalaire", "Sursalaire", "money"), F("ind_logement", "Indemnité de logement", "money"),
        F("ind_transport", "Indemnité de transport", "money"), F("ind_fonction", "Indemnité de fonction", "money"),
        F("primes_fixes", "Autres primes fixes imposables", "money"),
        F("mode_paiement", "Mode de paiement", "select", choices=["Virement bancaire", "Mobile money", "Chèque", "Espèces"]),
        F("banque", "Banque / opérateur"), F("compte", "N° de compte / téléphone"),
        F("conge_solde_initial", "Solde de congés repris (jours)", "num", grp="Reprise des congés", help="Solde à la date de référence ci-contre (migration)"),
        F("conge_date_reference", "Date de référence du solde", "date", help="Vide = calcul depuis l'embauche"),
        F("date_sortie", "Date de sortie", "date", grp="Sortie"), F("motif_sortie", "Motif de sortie", "select", choices=MOTIFS_SORTIE),
        F("notes", "Observations", "textarea"),
    ])

E["contrats"] = dict(
    table="contracts", titre="Contrats de travail", un="un contrat", order="date_debut DESC",
    list=[("employee_id", "Employé"), ("type", "Type"), ("date_debut", "Début"), ("date_fin", "Fin"), ("essai_fin", "Fin d'essai"),
          ("visa_inspection", "Visa inspection"), ("statut", "Statut")],
    fields=[EMP, F("type", "Type de contrat", "select", choices=CONTRATS, req=True), F("reference", "Référence du contrat"),
            F("date_debut", "Date de début", "date", req=True), F("date_fin", "Date de fin (CDD, stage…)", "date"),
            F("essai_fin", "Fin de la période d'essai", "date"), F("essai_renouvele", "Essai renouvelé", "select", choices=["", "Non", "Oui"]),
            F("motif", "Motif du recours au CDD / temporaire", "textarea"),
            F("visa_inspection", "N° de visa de l'inspection du travail", help="Obligatoire pour les travailleurs non nationaux"),
            F("visa_date", "Date du visa", "date"), F("permis_travail", "N° du permis de travail (non-nationaux)"), F("permis_expire", "Expiration du permis", "date"),
            F("statut", "Statut", "select", choices=["En cours", "Terminé", "Renouvelé", "Rompu"], req=True), F("notes", "Observations", "textarea")])

E["conges"] = dict(
    table="leaves", titre="Congés et absences", un="un congé / une absence", order="date_debut DESC",
    list=[("employee_id", "Employé"), ("type", "Type"), ("date_debut", "Du"), ("date_fin", "Au"), ("jours", "Jours"), ("statut", "Statut"), ("valide_par", "Validé par")],
    fields=[EMP, F("type", "Type", "select", choices=CONGES, req=True), F("date_debut", "Du", "date", req=True), F("date_fin", "Au (inclus)", "date", req=True),
            F("jours", "Nombre de jours", "num", help="Vide = jours calendaires calculés automatiquement"),
            F("statut", "Statut", "select", choices=["Demandé", "Approuvé", "Refusé", "Annulé"], req=True), F("motif", "Motif / justificatif"),
            F("notes", "Observations", "textarea")])

E["sanctions"] = dict(
    table="sanctions", titre="Registre des sanctions disciplinaires", un="une sanction", order="date DESC", roles_r=("admin", "rh", "lecture"),
    list=[("employee_id", "Employé"), ("date", "Date"), ("type", "Sanction"), ("motif", "Motif"), ("duree_jours", "Durée (j)"), ("date_notification", "Notifiée le")],
    fields=[EMP, F("date", "Date des faits / de la décision", "date", req=True),
            F("type", "Sanction", "select", req=True, choices=["Avertissement écrit", "Blâme", "Mise à pied de 1 à 3 jours", "Mise à pied de 4 à 8 jours", "Licenciement"]),
            F("motif", "Faits reprochés", "textarea", req=True), F("duree_jours", "Durée de la mise à pied (jours)", "num"),
            F("date_explication", "Demande d'explication / audition le", "date", help="Le travailleur doit pouvoir s'expliquer avant toute sanction"),
            F("date_notification", "Notification écrite le", "date", help="Ampliation à l'inspection du travail"), F("notes", "Observations", "textarea")])

E["visites"] = dict(
    table="medical", titre="Visites médicales", un="une visite médicale", order="date DESC",
    list=[("employee_id", "Employé"), ("date", "Date"), ("type", "Type"), ("resultat", "Conclusion"), ("prochaine", "Prochaine visite"), ("medecin", "Médecin / OST")],
    fields=[EMP, F("date", "Date de la visite", "date", req=True), F("type", "Type", "select", choices=["Embauche", "Périodique", "Reprise", "Spontanée"], req=True),
            F("resultat", "Conclusion", "select", choices=["Apte", "Apte avec réserves", "Inapte temporaire", "Inapte"],
              help="Ne saisir que l'aptitude : aucun diagnostic (secret médical)"),
            F("prochaine", "Prochaine visite prévue", "date"), F("medecin", "Médecin / structure (OST)"), F("notes", "Observations (non médicales)", "textarea")])

E["accidents"] = dict(
    table="accidents", titre="Registre des accidents du travail et maladies professionnelles", un="un accident", order="date DESC",
    list=[("employee_id", "Victime"), ("date", "Date"), ("nature", "Nature"), ("lieu", "Lieu"), ("jours_arret", "Arrêt (j)"),
          ("declare_cnss_le", "Déclaré CNSS"), ("declare_inspection_le", "Déclaré inspection")],
    fields=[EMP, F("date", "Date", "date", req=True), F("heure", "Heure"),
            F("nature", "Nature", "select", choices=["Accident du travail", "Accident de trajet", "Maladie professionnelle"], req=True),
            F("lieu", "Lieu"), F("circonstances", "Circonstances", "textarea"), F("lesions", "Siège et nature des lésions"),
            F("jours_arret", "Jours d'arrêt de travail", "num"), F("temoins", "Témoins"),
            F("declare_cnss_le", "Déclaré à la CNSS le", "date"), F("declare_inspection_le", "Déclaré à l'inspection du travail le", "date"),
            F("notes", "Mesures correctives / observations", "textarea")])

E["formations"] = dict(
    table="trainings", titre="Formations", un="une formation", order="date_debut DESC",
    list=[("employee_id", "Employé"), ("intitule", "Intitulé"), ("organisme", "Organisme"), ("date_debut", "Du"), ("date_fin", "Au"), ("heures", "Heures"), ("cout", "Coût")],
    fields=[EMP, F("intitule", "Intitulé", req=True), F("organisme", "Organisme"), F("date_debut", "Du", "date"), F("date_fin", "Au", "date"),
            F("heures", "Durée (heures)", "num"), F("cout", "Coût (FCFA)", "money"), F("notes", "Observations", "textarea")])

E["representants"] = dict(
    table="representatives", titre="Représentants du personnel", un="un mandat", order="date_election DESC",
    list=[("employee_id", "Employé"), ("mandat", "Mandat"), ("college", "Collège"), ("date_election", "Élu / désigné le"), ("date_fin_mandat", "Fin de mandat"), ("pv_reference", "PV")],
    fields=[EMP, F("mandat", "Mandat", "select", req=True, choices=["Délégué du personnel titulaire", "Délégué du personnel suppléant", "Membre du CSST", "Délégué syndical"]),
            F("college", "Collège électoral"), F("date_election", "Date d'élection / désignation", "date", req=True), F("date_fin_mandat", "Fin de mandat", "date"),
            F("pv_reference", "Référence du procès-verbal transmis à l'inspection"), F("notes", "Observations", "textarea")])

E["inspections"] = dict(
    table="inspections", titre="Visites, observations et mises en demeure de l'inspection du travail", un="une visite", order="date DESC", emp_field=None,
    list=[("date", "Date"), ("inspecteur", "Inspecteur / contrôleur"), ("objet", "Objet"), ("mise_en_demeure", "Mise en demeure"), ("delai", "Délai"), ("statut", "Statut")],
    fields=[F("date", "Date", "date", req=True), F("inspecteur", "Inspecteur / contrôleur"), F("objet", "Objet de la visite"),
            F("observations", "Observations formulées", "textarea"), F("mise_en_demeure", "Mise en demeure (contenu)", "textarea"),
            F("delai", "Délai imparti (date limite)", "date"), F("date_levee", "Date de mise en conformité", "date"),
            F("statut", "Statut", "select", choices=["Sans suite", "En cours de traitement", "Levée"], req=True), F("notes", "Actions menées", "textarea")])

E["documents"] = dict(
    table="documents", titre="Pièces des dossiers individuels", un="une pièce", order="date DESC",
    list=[("employee_id", "Employé"), ("type", "Pièce"), ("reference", "Référence"), ("date", "Date"), ("expire", "Expire le"), ("emplacement", "Emplacement")],
    fields=[EMP, F("type", "Type de pièce", "select", req=True, choices=["Contrat signé", "Copie pièce d'identité", "Diplômes / CV", "Certificat médical d'embauche", "Casier judiciaire",
            "Attestation CNSS", "Fiche de poste", "Avenant", "Décision de congé", "Lettre de sanction", "Permis de travail", "Autre"]),
            F("reference", "Référence"), F("date", "Date", "date"), F("expire", "Date d'expiration", "date"),
            F("emplacement", "Emplacement (classeur physique / dossier numérique)"), F("notes", "Observations", "textarea")])

E["obligations"] = dict(
    table="obligations", titre="Obligations légales de l'employeur", un="une obligation", order="id", emp_field=None,
    list=[("libelle", "Obligation"), ("reference", "Texte"), ("frequence", "Périodicité"), ("statut", "Statut"), ("echeance", "Échéance"), ("preuve", "Preuve")],
    fields=[F("libelle", "Obligation", "textarea", req=True), F("reference", "Texte de référence"), F("frequence", "Périodicité"),
            F("statut", "Statut", "select", choices=["À faire", "En cours", "Conforme", "Non applicable"], req=True),
            F("echeance", "Prochaine échéance", "date"), F("preuve", "Preuve (référence, date, emplacement du document)"), F("notes", "Observations", "textarea")])

E["feries"] = dict(
    table="feries", titre="Jours fériés et commémorations", un="un jour", order="date", emp_field=None, roles_w=("admin",),
    list=[("date", "Date"), ("libelle", "Libellé"), ("type", "Régime")],
    fields=[F("date", "Date", "date", req=True), F("libelle", "Libellé", req=True),
            F("type", "Régime", "select", choices=["Chômé et payé", "Commémoration (travaillée)", "Chômé par communiqué"], req=True), F("notes", "Observations")])

for _k, _v in E.items():
    _v.setdefault("emp_field", "employee_id")
    _v.setdefault("roles_w", ("admin", "rh"))
    _v.setdefault("roles_r", None)
    _v["key"] = _k


# ------------------------------------------------------------------ helpers
def emp_name(r):
    return f'{r["nom"]} {r["prenoms"]} ({r["matricule"]})'


def emp_map(conn):
    return {r["id"]: r for r in conn.execute("SELECT id,matricule,nom,prenoms,date_sortie FROM employees")}


def show(f, v, emps=None):
    if v in (None, ""):
        return ""
    t = f["typ"]
    if t == "date":
        return fr(v)
    if t == "money":
        return money(v)
    if t in ("num", "int"):
        return f"{num(v):g}"
    if t == "emp" and emps is not None:
        r = emps.get(v)
        return emp_name(r) if r else "?"
    return str(v)


def get_ent(req, key):
    ent = E.get(key)
    if not ent:
        raise Forbidden()
    if ent["roles_r"] and req.role not in ent["roles_r"]:
        raise Forbidden()
    return ent


class _FM(dict):
    def __missing__(self, k):
        return F(k, k)


def fmap(ent):
    return _FM({f["name"]: f for f in ent["fields"]})


# ------------------------------------------------------------------ liste
@route(r"/e/(\w+)")
def ent_list(req, key):
    ent = get_ent(req, key)
    conn, fm = req.db, fmap(ent)
    where, args = [], []
    emp_id = req.q("employee_id")
    if emp_id and ent["emp_field"]:
        where.append("employee_id=?")
        args.append(emp_id)
    q = req.q("q").strip()
    if q and ent.get("search"):
        where.append("(" + " OR ".join(f"{c} LIKE ?" for c in ent["search"]) + ")")
        args += [f"%{q}%"] * len(ent["search"])
    if key == "employes" and req.q("tous") != "1":
        where.append("(date_sortie IS NULL OR date_sortie='' OR date_sortie>=?)")
        args.append(today().isoformat())
    sql = f'SELECT * FROM {ent["table"]}' + (" WHERE " + " AND ".join(where) if where else "") + f' ORDER BY {ent["order"]} LIMIT 2000'
    rows = conn.execute(sql, args).fetchall()
    emps = emp_map(conn)
    heads = [lbl for _, lbl in ent["list"]]
    if req.q("format") == "csv":
        return csv_resp(key, heads, [[show(fm[c], r[c], emps) for c, _ in ent["list"]] for r in rows])
    can_w = req.role in ent["roles_w"]
    out = []
    for r in rows:
        cells = [e(show(fm[c], r[c], emps)) for c, _ in ent["list"]]
        if key == "employes":
            cells[1] = f'<a href="/employes/{r["id"]}"><b>{cells[1]}</b></a>'
            act = f'<a href="/employes/{r["id"]}">Fiche</a>'
        else:
            act = ""
            if ent["emp_field"]:
                cells[0] = f'<a href="/employes/{r["employee_id"]}">{cells[0]}</a>'
        if can_w:
            act += f' <a href="/e/{key}/{r["id"]}">Modifier</a>'
        out.append(cells + [act])
    n = len(heads)
    bar = '<div class="noprint">'
    if can_w:
        bar += f'<a class="btn" href="/e/{key}/new{("?employee_id=" + e(emp_id)) if emp_id else ""}">+ Ajouter {e(ent["un"])}</a>'
    bar += f'<a class="btn g" href="/e/{key}?format=csv{("&employee_id=" + e(emp_id)) if emp_id else ""}{"&tous=1" if req.q("tous") == "1" else ""}">Exporter (Excel/CSV)</a>'
    if ent.get("search"):
        bar += (f'<form class="inline" method="get"><input name="q" value="{e(q)}" placeholder="Rechercher…" style="width:220px"> '
                f'<button class="g">Chercher</button></form>')
    if key == "employes":
        bar += ' <a href="/e/employes?tous=1">Inclure les sortis</a>' if req.q("tous") != "1" else ' <a href="/e/employes">Actifs seulement</a>'
    bar += "</div>"
    body = bar + table(heads + [""], out, raw=tuple(range(n + 1))) + f'<p class="muted sm">{len(rows)} enregistrement(s).</p>'
    return page(req, ent["titre"], body)


# ------------------------------------------------------------------ formulaire
def render_form(req, ent, values, errors, rid):
    conn = req.db
    html_ = [f'<div class="err">{"<br>".join(e(x) for x in errors)}</div>' if errors else "",
             f'<form method="post" action="/e/{ent["key"]}/{rid}">{csrf_field(req)}<div class="card">']
    opened = False
    for f in ent["fields"]:
        if f["grp"] or not opened:
            if opened:
                html_.append("</div>")
            if f["grp"]:
                html_.append(f'<h3>{e(f["grp"])}</h3>')
            html_.append('<div class="grid">')
            opened = True
        v = values.get(f["name"])
        v = "" if v is None else v
        n, t = f["name"], f["typ"]
        star = " *" if f["req"] else ""
        if t == "emp":
            opts = "".join(f'<option value="{r["id"]}"{" selected" if str(r["id"]) == str(v) else ""}>{e(emp_name(r))}</option>'
                           for r in conn.execute("SELECT id,matricule,nom,prenoms FROM employees ORDER BY nom,prenoms"))
            inp = f'<select name="{n}"><option value=""></option>{opts}</select>'
        elif t == "select":
            ch = list(f["choices"])
            if v and v not in ch:
                ch.append(v)
            inp = f'<select name="{n}">' + "".join(f'<option{" selected" if str(c) == str(v) else ""}>{e(c)}</option>' for c in ch) + "</select>"
        elif t == "textarea":
            inp = f'<textarea name="{n}">{e(v)}</textarea>'
        elif t == "date":
            inp = f'<input type="date" name="{n}" value="{e(v)}">'
        elif t in ("int", "num", "money"):
            vv = f"{num(v):g}" if v != "" else ""
            inp = f'<input type="number" step="{"1" if t == "int" else "any"}" name="{n}" value="{e(vv)}">'
        else:
            inp = f'<input name="{n}" value="{e(v)}" maxlength="300">'
        hlp = f'<span class="help">{e(f["help"])}</span>' if f["help"] else ""
        html_.append(f'<div><label>{e(f["label"])}{star}</label>{inp}{hlp}</div>')
    html_.append("</div></div><button>Enregistrer</button> "
                 f'<a class="btn g" href="{e(back_url(ent, values))}">Annuler</a></form>')
    if rid != "new" and req.role in ent["roles_w"]:
        html_.append(f'<p class="noprint" style="margin-top:24px"><a class="btn d" href="/e/{ent["key"]}/{rid}/supprimer">Supprimer…</a></p>')
    return "".join(html_)


def back_url(ent, values):
    if ent["key"] == "employes":
        return f'/employes/{values["id"]}' if values.get("id") else "/e/employes"
    if ent["emp_field"] and values.get("employee_id"):
        return f'/employes/{values["employee_id"]}'
    return f'/e/{ent["key"]}'


def validate(req, ent, data, rid):
    conn, errs = req.db, []
    for f in ent["fields"]:
        v = data[f["name"]]
        if f["req"] and v in (None, ""):
            errs.append(f'« {f["label"]} » est obligatoire.')
        if f["typ"] == "date" and v and not d(v):
            errs.append(f'« {f["label"]} » : date invalide.')
        if f["typ"] in ("num", "money", "int") and v is not None and v < 0:
            errs.append(f'« {f["label"]} » ne peut pas être négatif.')
    k = ent["key"]
    dd, df = d(data.get("date_debut")), d(data.get("date_fin"))
    if dd and df and df < dd:
        errs.append("La date de fin précède la date de début.")
    if errs:
        return errs
    p = params(conn)
    if k == "employes":
        dup = conn.execute("SELECT id FROM employees WHERE matricule=? AND id<>?", (data["matricule"], rid if rid != "new" else 0)).fetchone()
        if dup:
            errs.append("Ce matricule est déjà utilisé.")
        dn, de = d(data["date_naissance"]), d(data["date_embauche"])
        if dn and de and (de - dn).days / 365.25 < p.n("age_min", 16):
            errs.append(f'Âge à l\'embauche inférieur à l\'âge minimum légal ({p.n("age_min"):g} ans).')
        if data["date_sortie"] and not data["motif_sortie"]:
            errs.append("Indiquez le motif de sortie.")
        if (data["nb_charges"] or 0) > 4:
            errs.append("Les charges fiscales IUTS sont plafonnées à 4.")
        if rid == "new" and not data["nationalite"]:
            data["nationalite"] = "Burkinabè"
    if k == "contrats":
        if data["type"] in ("CDD", "Stage", "Travail temporaire") and not df:
            errs.append("La date de fin est obligatoire pour ce type de contrat.")
    if k == "conges":
        if not data["jours"]:
            data["jours"] = (df - dd).days + 1
        clash = conn.execute("SELECT id FROM leaves WHERE employee_id=? AND id<>? AND statut IN ('Demandé','Approuvé') AND date_debut<=? AND date_fin>=?",
                             (data["employee_id"], rid if rid != "new" else 0, data["date_fin"], data["date_debut"])).fetchone()
        if clash and data["statut"] in ("Demandé", "Approuvé"):
            errs.append("Chevauchement avec un autre congé / une autre absence de cet employé.")
        if data["type"] == "Congé annuel" and data["statut"] == "Approuvé":
            emp = conn.execute("SELECT * FROM employees WHERE id=?", (data["employee_id"],)).fetchone()
            deja = 0
            if rid != "new":
                old = conn.execute("SELECT * FROM leaves WHERE id=?", (rid,)).fetchone()
                deja = old["jours"] if old["type"] == "Congé annuel" and old["statut"] == "Approuvé" else 0
            solde = M.conge_solde(conn, emp, p)["solde"] + deja
            if data["jours"] > solde + 0.01:
                errs.append(f"Solde de congés insuffisant : {solde:g} jour(s) disponible(s) pour {data['jours']:g} demandé(s).")
    return errs


@route(r"/e/(\w+)/(new|\d+)", methods=("GET", "POST"))
def ent_form(req, key, rid):
    ent = get_ent(req, key)
    if req.role not in ent["roles_w"]:
        raise Forbidden()
    conn = req.db
    old = None
    if rid != "new":
        old = conn.execute(f'SELECT * FROM {ent["table"]} WHERE id=?', (rid,)).fetchone()
        if not old:
            return redirect(f"/e/{key}", err="Enregistrement introuvable.")
    titre = ("Ajouter " if rid == "new" else "Modifier ") + ent["un"]
    if req.method == "GET":
        values = dict(old) if old else {f["name"]: "" for f in ent["fields"]}
        if not old and req.q("employee_id"):
            values["employee_id"] = req.q("employee_id")
        if not old:
            for f in ent["fields"]:
                if f["name"] == "statut" and f["typ"] == "select" and key != "employes":
                    values["statut"] = f["choices"][0]
        return page(req, titre, render_form(req, ent, values, [], rid))
    data = {}
    for f in ent["fields"]:
        raw = req.f(f["name"])
        if f["typ"] in ("num", "money"):
            data[f["name"]] = num(raw) if raw != "" else None
        elif f["typ"] in ("int", "emp"):
            data[f["name"]] = int(num(raw)) if raw != "" else None
        else:
            data[f["name"]] = raw[:5000]
    errs = validate(req, ent, data, rid)
    if key == "conges" and data.get("statut") == "Approuvé":
        data_extra = {"valide_par": req.uname}
    else:
        data_extra = {}
    if errs:
        v = dict(data)
        v["id"] = old["id"] if old else None
        return page(req, titre, render_form(req, ent, v, errs, rid))
    data.update(data_extra)
    cols = list(data.keys())
    if rid == "new":
        cur = conn.execute(f'INSERT INTO {ent["table"]}({",".join(cols)}) VALUES({",".join("?" * len(cols))})', [data[c] for c in cols])
        new_id = cur.lastrowid
        audit(conn, req.uname, "CREATION", ent["table"], new_id, data)
    else:
        diff = {c: [old[c], data[c]] for c in cols if (old[c] if old[c] is not None else "") != (data[c] if data[c] is not None else "")}
        conn.execute(f'UPDATE {ent["table"]} SET {",".join(c + "=?" for c in cols)} WHERE id=?', [data[c] for c in cols] + [rid])
        new_id = int(rid)
        if diff:
            audit(conn, req.uname, "MODIFICATION", ent["table"], rid, diff)
    data["id"] = new_id
    return redirect(back_url(ent, data), msg="Enregistrement effectué.")


@route(r"/e/(\w+)/(\d+)/supprimer", methods=("GET", "POST"))
def ent_delete(req, key, rid):
    ent = get_ent(req, key)
    if req.role not in ent["roles_w"]:
        raise Forbidden()
    conn = req.db
    old = conn.execute(f'SELECT * FROM {ent["table"]} WHERE id=?', (rid,)).fetchone()
    if not old:
        return redirect(f"/e/{key}", err="Enregistrement introuvable.")
    if key == "employes":
        for t in ("payslips", "contracts", "leaves", "sanctions", "medical", "accidents", "trainings", "representatives", "documents", "pay_variables"):
            if conn.execute(f"SELECT 1 FROM {t} WHERE employee_id=? LIMIT 1", (rid,)).fetchone():
                return redirect(f"/employes/{rid}", err="Suppression impossible : cet employé possède un historique (le registre d'employeur doit être conservé). "
                                                        "Renseignez plutôt sa date et son motif de sortie.")
    if req.method == "GET":
        fm = fmap(ent)
        emps = emp_map(conn)
        recap = "".join(f"<tr><th>{e(lbl)}</th><td>{e(show(fm[c], old[c], emps))}</td></tr>" for c, lbl in ent["list"])
        return page(req, "Confirmer la suppression", f'<div class="card"><table>{recap}</table><p>Cette suppression est définitive et sera inscrite au journal d\'audit.</p>'
                    + post_btn(req, f"/e/{key}/{rid}/supprimer", "Supprimer définitivement", "d") + f'<a class="btn g" href="/e/{key}/{rid}">Annuler</a></div>')
    conn.execute(f'DELETE FROM {ent["table"]} WHERE id=?', (rid,))
    audit(conn, req.uname, "SUPPRESSION", ent["table"], rid, dict(old))
    return redirect(back_url(ent, {"employee_id": old["employee_id"]} if ent["emp_field"] else {}), msg="Enregistrement supprimé.")
