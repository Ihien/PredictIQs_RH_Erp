# -*- coding: utf-8 -*-
"""Écrans : connexion, tableau de bord, fiche employé, documents, paie, administration."""
import json, time, calendar, os, glob
import datetime as dt
from .core import (route, page, redirect, Resp, e, d, fr, money, num, audit, audit_verify, csrf_field, table, post_btn, params, get_params, today, now_iso,
                   hash_pwd, check_pwd, pwd_policy, session_create, cookie_header, backup, ROLES, MOIS, Forbidden, BACKUP_DIR, csv_resp)
from . import paie as M
from .entites import E, fmap, show, emp_name, emp_map, NON_PAYES, MOTIFS_SORTIE
from .rapports import controles, actifs, contrat_courant, entete

RH = ("admin", "rh")
PAIE = ("admin", "rh", "paie")


# ================================================================== authentification
@route("/setup", methods=("GET", "POST"), public=True)
def setup(req):
    conn = req.db
    if conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]:
        return redirect("/login")
    if req.ip not in ("127.0.0.1", "::1"):
        return Resp("La configuration initiale doit être faite depuis le poste serveur.", 403)
    err = ""
    if req.method == "POST":
        u, n, p1, p2 = req.f("username").lower(), req.f("fullname"), req.form.get("pwd", ""), req.form.get("pwd2", "")
        err = pwd_policy(p1) or ("Les mots de passe ne correspondent pas." if p1 != p2 else "") or ("Identifiant et nom obligatoires." if not (u and n) else "")
        if not err:
            h, s = hash_pwd(p1)
            conn.execute("INSERT INTO users(username,fullname,role,pwd_hash,pwd_salt,created_at) VALUES(?,?,?,?,?,?)", (u, n, "admin", h, s, now_iso()))
            audit(conn, u, "CREATION_ADMIN", "users", u)
            return redirect("/login", msg="Compte administrateur créé. Connectez-vous.")
    return page(req, "Première configuration", f'<h2>ERP RH Burkina</h2><p>Création du compte administrateur.</p>{f"<div class=err>{e(err)}</div>" if err else ""}'
                '<form method="post"><label>Identifiant</label><input name="username" required><label>Nom complet</label><input name="fullname" required>'
                '<label>Mot de passe (10 caractères min., lettres et chiffres)</label><input type="password" name="pwd" required>'
                '<label>Confirmation</label><input type="password" name="pwd2" required><p><button>Créer le compte</button></p></form>')


@route("/login", methods=("GET", "POST"), public=True)
def login(req):
    conn = req.db
    err = ""
    if req.method == "POST":
        sec = params(conn)
        u = conn.execute("SELECT * FROM users WHERE username=?", (req.f("username").lower(),)).fetchone()
        pwd = req.form.get("pwd", "")
        if u and u["locked_until"] > time.time():
            err = "Compte temporairement verrouillé après plusieurs échecs. Réessayez plus tard."
            audit(conn, u["username"], "CONNEXION_REFUSEE", "users", u["id"], "compte verrouillé " + req.ip)
        elif u and u["active"] and check_pwd(pwd, u["pwd_hash"], u["pwd_salt"]):
            conn.execute("UPDATE users SET failed=0, locked_until=0 WHERE id=?", (u["id"],))
            conn.execute("DELETE FROM sessions WHERE last_seen<?", (time.time() - 86400,))
            tok = session_create(conn, u["id"], req.ip)
            audit(conn, u["username"], "CONNEXION", "users", u["id"], req.ip)
            r = redirect("/")
            r.headers.append(cookie_header(tok))
            return r
        else:
            if not u:
                hash_pwd(pwd, "00" * 16)  # temps constant
            else:
                failed = u["failed"] + 1
                lock = time.time() + sec.n("verrou_minutes", 15) * 60 if failed >= sec.n("max_echecs", 5) else 0
                conn.execute("UPDATE users SET failed=?, locked_until=? WHERE id=?", (0 if lock else failed, lock, u["id"]))
            audit(conn, req.f("username")[:40], "ECHEC_CONNEXION", "users", "", req.ip)
            err = err or "Identifiant ou mot de passe incorrect."
    return page(req, "Connexion", f'<h2>ERP RH Burkina</h2>{f"<div class=err>{e(err)}</div>" if err else ""}'
                '<form method="post"><label>Identifiant</label><input name="username" autofocus required>'
                '<label style="margin-top:8px">Mot de passe</label><input type="password" name="pwd" required><p><button>Se connecter</button></p></form>'
                '<p class="muted sm">Accès réservé aux personnes habilitées. Toutes les opérations sont journalisées.</p>')


@route("/logout", methods=("POST",))
def logout(req):
    req.db.execute("DELETE FROM sessions WHERE token_hash=?", (req.session_hash,))
    audit(req.db, req.uname, "DECONNEXION", "users", req.user["id"])
    r = redirect("/login")
    r.headers.append(cookie_header("", clear=True))
    return r


@route("/compte", methods=("GET", "POST"))
def compte(req):
    conn, err = req.db, ""
    if req.method == "POST":
        old, p1, p2 = req.form.get("old", ""), req.form.get("pwd", ""), req.form.get("pwd2", "")
        if not check_pwd(old, req.user["pwd_hash"], req.user["pwd_salt"]):
            err = "Mot de passe actuel incorrect."
        else:
            err = pwd_policy(p1) or ("Les mots de passe ne correspondent pas." if p1 != p2 else "") or ("Le nouveau mot de passe doit être différent." if p1 == old else "")
        if not err:
            h, s = hash_pwd(p1)
            conn.execute("UPDATE users SET pwd_hash=?, pwd_salt=?, must_change=0 WHERE id=?", (h, s, req.user["id"]))
            conn.execute("DELETE FROM sessions WHERE user_id=? AND token_hash<>?", (req.user["id"], req.session_hash))
            audit(conn, req.uname, "CHANGEMENT_MOT_DE_PASSE", "users", req.user["id"])
            return redirect("/", msg="Mot de passe modifié.")
    return page(req, "Mon compte", f'{f"<div class=err>{e(err)}</div>" if err else ""}<div class="card" style="max-width:420px"><p>Identifiant : <b>{e(req.uname)}</b> — profil : {e(ROLES[req.role])}</p>'
                f'<form method="post">{csrf_field(req)}<label>Mot de passe actuel</label><input type="password" name="old" required>'
                '<label>Nouveau mot de passe (10 caractères min., lettres et chiffres)</label><input type="password" name="pwd" required>'
                '<label>Confirmation</label><input type="password" name="pwd2" required><p><button>Changer le mot de passe</button></p></form></div>')


# ================================================================== tableau de bord
@route("/")
def dashboard(req):
    conn = req.db
    emps = actifs(conn)
    f = sum(1 for x in emps if x["sexe"] == "F")
    types = {}
    for x in emps:
        c = contrat_courant(conn, x["id"])
        types[c["type"] if c else "Sans contrat"] = types.get(c["type"] if c else "Sans contrat", 0) + 1
    last = conn.execute("SELECT pp.annee, pp.mois, pp.statut, SUM(brut) b, SUM(net) n, SUM(cnss_pat+tpa) ch FROM payslips s JOIN pay_periods pp ON pp.id=s.period_id "
                        "GROUP BY pp.id ORDER BY annee DESC, mois DESC LIMIT 1").fetchone()
    cs = controles(conn)
    crit = [c for c in cs if c[0] == "critique"]
    kp = (f'<div class="kpis"><div class="kpi"><b>{len(emps)}</b><span>travailleurs en poste</span></div>'
          f'<div class="kpi"><b>{f} F / {len(emps) - f} H</b><span>répartition par sexe</span></div>'
          f'<div class="kpi"><b>{" · ".join(f"{v} {k}" for k, v in sorted(types.items())) or "—"}</b><span>contrats</span></div>')
    if last:
        kp += (f'<div class="kpi"><b>{money(last["b"])}</b><span>masse salariale brute {MOIS[last["mois"]]} {last["annee"]}</span></div>'
               f'<div class="kpi"><b>{money(last["b"] + last["ch"])}</b><span>coût employeur du mois</span></div>')
    kp += f'<div class="kpi"><b>{len(crit)}</b><span><a href="/conformite">points critiques de conformité</a></span></div></div>'
    t = today()
    ech = []
    for x in emps:
        c = contrat_courant(conn, x["id"])
        if c:
            for col, lib in (("date_fin", "Fin de contrat"), ("essai_fin", "Fin d'essai"), ("permis_expire", "Expiration du permis de travail")):
                dd = d(c[col])
                if dd and 0 <= (dd - t).days <= 60 and c["statut"] == "En cours":
                    ech.append((dd, lib, x))
    for v in conn.execute("SELECT m.prochaine, e.* FROM medical m JOIN employees e ON e.id=m.employee_id WHERE prochaine BETWEEN ? AND ?", (t.isoformat(), (t + dt.timedelta(days=60)).isoformat())):
        ech.append((d(v["prochaine"]), "Visite médicale", v))
    for fe in conn.execute("SELECT * FROM feries WHERE date BETWEEN ? AND ? ORDER BY date", (t.isoformat(), (t + dt.timedelta(days=45)).isoformat())):
        ech.append((d(fe["date"]), f'{fe["libelle"]} ({fe["type"]})', None))
    ech.sort(key=lambda z: z[0])
    en_conge = conn.execute("SELECT l.*, e.nom, e.prenoms, e.matricule FROM leaves l JOIN employees e ON e.id=l.employee_id WHERE l.statut='Approuvé' AND date_debut<=? AND date_fin>=?",
                            (t.isoformat(), t.isoformat())).fetchall()
    dem = conn.execute("SELECT l.*, e.nom, e.prenoms, e.matricule FROM leaves l JOIN employees e ON e.id=l.employee_id WHERE l.statut='Demandé' ORDER BY date_debut").fetchall()
    body = kp + '<div class="two"><div>'
    body += "<h3>Alertes critiques</h3>" + table(["Thème", "Constat", ""], [[e(c[1]), e(c[2]), f'<a href="{e(c[3])}">Traiter</a>' if c[3] else ""] for c in crit[:12]], raw=(0, 1, 2))
    if len(crit) > 12:
        body += f'<p><a href="/conformite">Voir les {len(crit)} points critiques…</a></p>'
    body += "</div><div><h3>Échéances des 60 prochains jours</h3>" + table(
        ["Date", "Échéance", "Concerné"], [[fr(a), e(b), f'<a href="/employes/{x["id"]}">{e(emp_name(x))}</a>' if x else ""] for a, b, x in ech[:15]], raw=(1, 2))
    body += "<h3>Demandes de congé à traiter</h3>" + table(["Employé", "Type", "Du", "Au", ""], [
        [e(emp_name(l)), e(l["type"]), fr(l["date_debut"]), fr(l["date_fin"]), f'<a href="/e/conges/{l["id"]}">Traiter</a>'] for l in dem], raw=(0, 1, 4))
    body += "<h3>Absents aujourd'hui</h3>" + table(["Employé", "Motif", "Retour le"], [[emp_name(l), l["type"], fr(d(l["date_fin"]) + dt.timedelta(days=1))] for l in en_conge])
    body += "</div></div>"
    return page(req, "Tableau de bord", body)


# ================================================================== fiche employé
SUB = [("contrats", "Contrats"), ("conges", "Congés et absences"), ("visites", "Visites médicales"), ("formations", "Formations"),
       ("sanctions", "Sanctions"), ("accidents", "Accidents du travail"), ("representants", "Mandats"), ("documents", "Pièces du dossier")]


def get_emp(req, eid):
    emp = req.db.execute("SELECT * FROM employees WHERE id=?", (eid,)).fetchone()
    if not emp:
        raise Forbidden()
    return emp


@route(r"/employes/(\d+)")
def fiche(req, eid):
    conn = req.db
    emp = get_emp(req, eid)
    p = params(conn)
    t = today()
    cg = M.conge_solde(conn, emp, p)
    ans = M.anciennete_ans(emp, t)
    c = contrat_courant(conn, eid)
    fm = fmap(E["employes"])
    brut = sum(num(emp[k]) for k in ("salaire_base", "sursalaire", "ind_logement", "ind_transport", "ind_fonction", "primes_fixes"))
    pv, pu = M.preavis(emp, p)

    def bloc(titre, noms):
        return f"<h3>{titre}</h3><table>" + "".join(f'<tr><th style="width:42%">{e(fm[n]["label"])}</th><td>{e(show(fm[n], emp[n]))}</td></tr>' for n in noms) + "</table>"

    voir_sal = req.role in PAIE or req.role == "lecture"
    body = '<div class="noprint">'
    if req.role in RH:
        body += f'<a class="btn" href="/e/employes/{eid}">Modifier la fiche</a>'
    body += (f'<a class="btn g" href="/employes/{eid}/doc/attestation">Attestation de travail</a>'
             f'<a class="btn g" href="/employes/{eid}/doc/certificat">Certificat de travail</a>'
             f'<a class="btn g" href="/employes/{eid}/solde">Simulation de fin de contrat</a></div>')
    sortie = f' <span class="tag critique">Sorti le {fr(emp["date_sortie"])}</span>' if emp["date_sortie"] and d(emp["date_sortie"]) < t else ""
    body += (f'<div class="kpis"><div class="kpi"><b>{ans:.1f} ans</b><span>ancienneté (prime {M.taux_anciennete(ans, p):g} %)</span></div>'
             f'<div class="kpi"><b>{cg["solde"]:g} j</b><span>solde de congés (acquis {cg["acquis"]:g} – pris {cg["pris"]:g})</span></div>'
             f'<div class="kpi"><b>{e(c["type"]) if c else "Aucun"}</b><span>contrat{(" jusqu’au " + fr(c["date_fin"])) if c and c["date_fin"] else ""}</span></div>'
             + (f'<div class="kpi"><b>{money(brut)}</b><span>brut mensuel théorique</span></div>' if voir_sal else "")
             + f'<div class="kpi"><b>{pv:g} {pu}</b><span>préavis applicable</span></div></div>{sortie}')
    body += '<div class="two"><div>' + bloc("Identité", ["matricule", "nom", "prenoms", "sexe", "date_naissance", "lieu_naissance", "nationalite", "piece_type", "piece_numero",
                                                         "situation_famille", "nb_enfants", "nb_charges", "handicap"])
    body += bloc("Coordonnées", ["adresse", "telephone", "email", "contact_urgence"]) + "</div><div>"
    body += bloc("Emploi", ["date_embauche", "emploi", "departement", "categorie", "statut", "cnss_no", "date_sortie", "motif_sortie"])
    if voir_sal:
        body += bloc("Rémunération", ["mode_remuneration", "salaire_base", "sursalaire", "ind_logement", "ind_transport", "ind_fonction", "primes_fixes", "mode_paiement", "banque", "compte"])
    body += "</div></div>"
    emps = emp_map(conn)
    for key, titre in SUB:
        ent = E[key]
        if ent["roles_r"] and req.role not in ent["roles_r"]:
            continue
        f2 = fmap(ent)
        cols = [x for x in ent["list"] if x[0] != "employee_id"]
        rows = conn.execute(f'SELECT * FROM {ent["table"]} WHERE employee_id=? ORDER BY {ent["order"]}', (eid,)).fetchall()
        can = req.role in ent["roles_w"]
        add = f' <a class="btn noprint" style="padding:2px 8px;font-size:12px" href="/e/{key}/new?employee_id={eid}">+ Ajouter</a>' if can else ""
        body += f"<h3>{titre}{add}</h3>" + table([l for _, l in cols] + [""], [[e(show(f2[cn], r[cn], emps)) for cn, _ in cols] +
                                                 [f'<a href="/e/{key}/{r["id"]}">Modifier</a>' if can else ""] for r in rows], raw=tuple(range(len(cols) + 1)))
    if voir_sal:
        ps = conn.execute("SELECT s.*, pp.annee, pp.mois, pp.statut FROM payslips s JOIN pay_periods pp ON pp.id=s.period_id WHERE employee_id=? ORDER BY annee DESC, mois DESC LIMIT 24", (eid,)).fetchall()
        body += "<h3>Bulletins de paie</h3>" + table(["Période", "Brut", "CNSS", "IUTS", "Net", ""], [
            [f'{MOIS[s["mois"]]} {s["annee"]}', money(s["brut"]), money(s["cnss_sal"]), money(s["iuts"]), money(s["net"]),
             f'<a href="/paie/{s["period_id"]}/bulletin/{eid}">Bulletin</a>'] for s in ps], right=(1, 2, 3, 4), raw=(5,))
    return page(req, f'{emp["nom"]} {emp["prenoms"]} — {emp["matricule"]}', body)


def signature(ent):
    return (f'<p style="margin-top:30px">Fait à {e(ent.get("ville") or "…")}, le {fr(today())}</p>'
            f'<p style="margin-top:10px"><b>{e(ent.get("qualite_representant") or "Le représentant légal")}</b><br><br><br><br>{e(ent.get("representant_legal"))}</p>')


@route(r"/employes/(\d+)/doc/(attestation|certificat)")
def doc(req, eid, kind):
    conn = req.db
    emp = get_emp(req, eid)
    ent = get_params(conn, "entreprise")
    civ = "Madame" if emp["sexe"] == "F" else "Monsieur"
    qui = (f'Je soussigné(e), <b>{e(ent.get("representant_legal") or "…")}</b>, {e(ent.get("qualite_representant"))} de <b>{e(ent.get("raison_sociale") or "…")}</b>, '
           f'{e(ent.get("adresse"))} {e(ent.get("ville"))}, immatriculée à la CNSS sous le n° {e(ent.get("cnss_employeur") or "…")},')
    ident = (f'{civ} <b>{e(emp["nom"])} {e(emp["prenoms"])}</b>, né(e) le {fr(emp["date_naissance"]) or "…"} à {e(emp["lieu_naissance"] or "…")}, '
             f'immatriculé(e) à la CNSS sous le n° {e(emp["cnss_no"] or "…")},')
    if kind == "attestation":
        titre = "ATTESTATION DE TRAVAIL"
        c = contrat_courant(conn, eid)
        txt = (f'<p>{qui} atteste que {ident} est employé(e) dans notre entreprise depuis le <b>{fr(emp["date_embauche"])}</b> en qualité de <b>{e(emp["emploi"] or "…")}</b>'
               f'{(", sous contrat " + e(c["type"])) if c else ""}.</p><p>La présente attestation lui est délivrée pour servir et valoir ce que de droit.</p>')
    else:
        titre = "CERTIFICAT DE TRAVAIL"
        if not emp["date_sortie"]:
            return redirect(f"/employes/{eid}", err="Le certificat de travail se délivre à la fin du contrat : renseignez d'abord la date de sortie.")
        emplois = e(emp["emploi"] or "…") + (f', catégorie {e(emp["categorie"])}' if emp["categorie"] else "")
        txt = (f'<p>{qui} certifie que {ident} a été employé(e) dans notre entreprise du <b>{fr(emp["date_embauche"])}</b> au <b>{fr(emp["date_sortie"])}</b> '
               f'en qualité de <b>{emplois}</b>.</p><p>{civ} {e(emp["nom"])} nous quitte libre de tout engagement.</p>'
               '<p>En foi de quoi, le présent certificat lui est délivré pour servir et valoir ce que de droit.</p>')
    audit(conn, req.uname, "EDITION_DOCUMENT", "employees", eid, titre)
    return page(req, titre.capitalize(), f'<div class="doc">{entete(conn)}<h2 style="margin:40px 0">{titre}</h2><div style="font-size:15px;line-height:1.8">{txt}</div>{signature(ent)}</div>'
                f'<p class="noprint muted">Impression / PDF : Ctrl+P. <a href="/employes/{eid}">Retour à la fiche</a></p>')


@route(r"/employes/(\d+)/solde")
def solde(req, eid):
    conn = req.db
    emp = get_emp(req, eid)
    p = params(conn)
    ds = d(req.q("date")) or d(emp["date_sortie"]) or today()
    motif = req.q("motif") or emp["motif_sortie"] or "Démission"
    s = M.solde_tout_compte(conn, emp, p, ds, motif)
    lic_txt = "Due (licenciement, ancienneté ≥ 1 an)" if s["ind_licenciement"] else "Non due pour ce motif ou ancienneté < 1 an"
    rows = [["Ancienneté à la date de sortie", f'{s["anciennete"]:.2f} ans', ""],
            ["Salaire global mensuel moyen", money(s["salaire_moyen"]), f'Moyenne des {s["nb_bulletins"]} derniers bulletins' if s["nb_bulletins"] else "Rémunération théorique (aucun bulletin)"],
            ["Indemnité compensatrice de congés payés", money(s["ind_conge"]), f'Solde de {s["conge"]["solde"]:g} jours × salaire moyen / 30'],
            ["Indemnité de licenciement", money(s["ind_licenciement"]), lic_txt + f' — {p.n("lic_taux_1"):g} % / {p.n("lic_taux_2"):g} % / {p.n("lic_taux_3"):g} % par année'],
            ["Préavis applicable", f'{s["preavis"][0]:g} {s["preavis"][1]}', f'Indemnité compensatrice si préavis non exécuté : {money(s["ind_preavis"])}'],
            ["Total hors préavis (brut)", money(s["ind_conge"] + s["ind_licenciement"]), "À ajouter au salaire du dernier mois (bulletin de paie)"]]
    opts = "".join(f'<option{" selected" if m == motif else ""}>{e(m)}</option>' for m in MOTIFS_SORTIE if m)
    body = (f'<form method="get" class="card noprint"><div class="grid"><div><label>Date de sortie</label><input type="date" name="date" value="{ds.isoformat()}"></div>'
            f'<div><label>Motif</label><select name="motif">{opts}</select></div><div><label>&nbsp;</label><button>Recalculer</button></div></div></form>'
            + f'<div class="doc">{entete(conn)}<h2>Simulation du solde de tout compte</h2><p><b>{e(emp_name(emp))}</b> — {e(emp["emploi"])} — sortie le {fr(ds)} — motif : {e(motif)}</p>'
            + table(["Élément", "Montant / valeur", "Base de calcul"], rows, right=(1,))
            + f'<p class="sm muted">Simulation indicative fondée sur le référentiel paramétré (convention collective interprofessionnelle). En cas de licenciement abusif, les dommages-intérêts '
              f'peuvent atteindre {p.n("dommages_max_mois"):g} mois de salaire. Le régime fiscal et social des indemnités est à valider avec votre conseil. '
              f'Le reçu pour solde de tout compte peut être dénoncé par le travailleur.</p></div>')
    return page(req, "Fin de contrat", body)


# ================================================================== santé-sécurité (page d'accueil)
@route("/sst")
def sst(req):
    body = ('<div class="card"><a class="btn" href="/e/visites">Visites médicales</a><a class="btn" href="/e/accidents">Accidents du travail</a>'
            '<a class="btn g" href="/rapports/visites">État des visites</a><a class="btn g" href="/rapports/accidents">Registre des accidents</a>'
            '<p class="muted">Seule l\'aptitude est enregistrée ; aucun diagnostic médical ne doit être saisi (secret médical, protection des données).</p></div>')
    cs = [c for c in controles(req.db) if c[1] in ("Santé au travail", "Accidents du travail")]
    body += "<h3>Points d'attention</h3>" + table(["Niveau", "Constat", ""], [[f'<span class="tag {c[0]}">{c[0]}</span>', e(c[2]), f'<a href="{e(c[3])}">Traiter</a>'] for c in cs], raw=(0, 1, 2))
    return page(req, "Santé et sécurité au travail", body)


# ================================================================== paie
def bareme(conn):
    return [(r["borne_inf"], r["borne_sup"], r["taux"]) for r in conn.execute("SELECT * FROM iuts_bareme ORDER BY borne_inf")]


def eligibles(conn, annee, mois):
    deb, fin = dt.date(annee, mois, 1), dt.date(annee, mois, calendar.monthrange(annee, mois)[1])
    return conn.execute("SELECT * FROM employees WHERE date_embauche<=? AND (date_sortie IS NULL OR date_sortie='' OR date_sortie>=?) ORDER BY nom,prenoms",
                        (fin.isoformat(), deb.isoformat())).fetchall()


def jours_non_payes_auto(conn, eid, annee, mois):
    deb, fin = dt.date(annee, mois, 1), dt.date(annee, mois, calendar.monthrange(annee, mois)[1])
    n = 0
    for l in conn.execute(f"SELECT * FROM leaves WHERE employee_id=? AND statut='Approuvé' AND type IN ({','.join('?' * len(NON_PAYES))}) AND date_debut<=? AND date_fin>=?",
                          (eid, *NON_PAYES, fin.isoformat(), deb.isoformat())):
        a, b = max(deb, d(l["date_debut"])), min(fin, d(l["date_fin"]))
        n += (b - a).days + 1
    return n


def get_period(req, pid):
    pp = req.db.execute("SELECT * FROM pay_periods WHERE id=?", (pid,)).fetchone()
    if not pp:
        raise Forbidden()
    return pp


def calculer(conn, pp):
    p, bar = params(conn), bareme(conn)
    conn.execute("DELETE FROM payslips WHERE period_id=?", (pp["id"],))
    n = 0
    for emp in eligibles(conn, pp["annee"], pp["mois"]):
        var = conn.execute("SELECT * FROM pay_variables WHERE period_id=? AND employee_id=?", (pp["id"], emp["id"])).fetchone()
        var = dict(var) if var else {"jours_non_payes": jours_non_payes_auto(conn, emp["id"], pp["annee"], pp["mois"])}
        b = M.calc_bulletin(emp, var, p, bar, pp["annee"], pp["mois"])
        b["employe"] = {k: emp[k] for k in ("matricule", "nom", "prenoms", "emploi", "categorie", "statut", "cnss_no", "date_embauche", "departement", "mode_paiement", "banque", "compte", "nb_charges", "situation_famille")}
        b["conge"] = M.conge_solde(conn, emp, p, dt.date(pp["annee"], pp["mois"], calendar.monthrange(pp["annee"], pp["mois"])[1]))
        conn.execute("INSERT INTO payslips(period_id,employee_id,brut,base_cnss,cnss_sal,iuts,retenues,net,cnss_pat,tpa,heures_sup,data,calcule_le) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                     (pp["id"], emp["id"], b["brut"], b["base_cnss"], b["cnss_sal"], b["iuts"], b["retenues"], b["net"], b["cnss_pat"], b["tpa"], b["heures_sup"],
                      json.dumps(b, ensure_ascii=False), now_iso()))
        n += 1
    return n


@route("/paie", methods=("GET", "POST"))
def paie_index(req):
    conn = req.db
    if req.method == "POST":
        if req.role not in PAIE:
            raise Forbidden()
        a, m = int(num(req.f("annee"))), int(num(req.f("mois")))
        if not (2000 <= a <= 2100 and 1 <= m <= 12):
            return redirect("/paie", err="Période invalide.")
        if conn.execute("SELECT 1 FROM pay_periods WHERE annee=? AND mois=?", (a, m)).fetchone():
            return redirect("/paie", err="Cette période existe déjà.")
        cur = conn.execute("INSERT INTO pay_periods(annee,mois) VALUES(?,?)", (a, m))
        audit(conn, req.uname, "OUVERTURE_PERIODE", "pay_periods", cur.lastrowid, f"{m:02d}/{a}")
        return redirect(f"/paie/{cur.lastrowid}", msg="Période ouverte.")
    rows = []
    for pp in conn.execute("SELECT pp.*, (SELECT COUNT(*) FROM payslips WHERE period_id=pp.id) n, (SELECT SUM(brut) FROM payslips WHERE period_id=pp.id) b, "
                           "(SELECT SUM(net) FROM payslips WHERE period_id=pp.id) net FROM pay_periods pp ORDER BY annee DESC, mois DESC"):
        st = '<span class="tag ok">Clôturée</span>' if pp["statut"] == "cloturee" else '<span class="tag important">Ouverte</span>'
        rows.append([f'<a href="/paie/{pp["id"]}"><b>{MOIS[pp["mois"]].capitalize()} {pp["annee"]}</b></a>', st, pp["n"], money(pp["b"]), money(pp["net"]),
                     f'{fr(pp["cloture_le"])} {e(pp["cloture_par"] or "")}'])
    t = today()
    form = ""
    if req.role in PAIE:
        ms = "".join(f'<option value="{i}"{" selected" if i == t.month else ""}>{MOIS[i]}</option>' for i in range(1, 13))
        form = (f'<form method="post" class="card noprint">{csrf_field(req)}<b>Ouvrir une période de paie :</b> <select name="mois" style="width:auto">{ms}</select> '
                f'<input type="number" name="annee" value="{t.year}" style="width:90px"> <button>Ouvrir</button></form>')
    return page(req, "Paie", form + table(["Période", "Statut", "Bulletins", "Brut", "Net", "Clôture"], rows, right=(2, 3, 4), raw=(0, 1, 5)))


@route(r"/paie/(\d+)")
def paie_period(req, pid):
    conn = req.db
    pp = get_period(req, pid)
    a, m = pp["annee"], pp["mois"]
    ouverte = pp["statut"] != "cloturee"
    slips = {s["employee_id"]: s for s in conn.execute("SELECT * FROM payslips WHERE period_id=?", (pid,))}
    rows, tot = [], [0] * 6
    for emp in eligibles(conn, a, m):
        s = slips.get(emp["id"])
        var = conn.execute("SELECT 1 FROM pay_variables WHERE period_id=? AND employee_id=?", (pid, emp["id"])).fetchone()
        lien_var = f'<a href="/paie/{pid}/var/{emp["id"]}">{"Variables ✓" if var else "Variables"}</a>' if ouverte and req.role in PAIE else ""
        if s:
            dj = json.loads(s["data"])
            vals = [s["brut"], s["cnss_sal"], s["iuts"], dj["avance"] + dj["autres_retenues"], s["net"], dj["cout_employeur"]]
            tot = [x + y for x, y in zip(tot, vals)]
            al = " ".join(f'<span class="tag critique">{e(x)}</span>' for x in dj["alertes"])
            rows.append([e(emp["matricule"]), f'{e(emp["nom"])} {e(emp["prenoms"])} {al}', f'{dj["jours"]:g}'] + [money(v) for v in vals] +
                        [f'{lien_var} <a href="/paie/{pid}/bulletin/{emp["id"]}">Bulletin</a>'])
        else:
            rows.append([e(emp["matricule"]), f'{e(emp["nom"])} {e(emp["prenoms"])}', "", "", "", "", "", "", "", lien_var + ' <span class="muted">non calculé</span>'])
    if slips:
        rows.append(["", "<b>TOTAUX</b>", ""] + [f"<b>{money(v)}</b>" for v in tot] + [""])
    q = f"annee={a}&mois={m}"
    bar = '<div class="noprint">'
    if ouverte and req.role in PAIE:
        bar += post_btn(req, f"/paie/{pid}/calculer", "Calculer / recalculer la paie", "ok")
    if ouverte and req.role in RH and slips:
        bar += f'<a class="btn d" href="/paie/{pid}/cloturer">Clôturer la période…</a>'
    if not ouverte and req.role == "admin":
        bar += f'<a class="btn d" href="/paie/{pid}/rouvrir">Rouvrir (exceptionnel)…</a>'
    if slips:
        bar += (f'<a class="btn g" href="/paie/{pid}/bulletins">Tous les bulletins</a><a class="btn g" href="/rapports/livre_paie?{q}">Livre de paie</a>'
                f'<a class="btn g" href="/rapports/virements?{q}">État de paiement</a><a class="btn g" href="/rapports/cnss?{q}">CNSS</a><a class="btn g" href="/rapports/fiscal?{q}">IUTS / TPA</a>')
    bar += "</div>"
    info = ('<p class="muted">Période ouverte : saisissez les variables (absences, heures sup., primes, avances), calculez, vérifiez puis clôturez. '
            'La clôture fige définitivement les bulletins.</p>' if ouverte else f'<p><span class="tag ok">Clôturée</span> le {fr(pp["cloture_le"])} par {e(pp["cloture_par"])} — bulletins figés.</p>')
    return page(req, f"Paie de {MOIS[m]} {a}", info + bar + table(["Matricule", "Nom et prénoms", "Jours", "Brut", "CNSS", "IUTS", "Avances/retenues", "Net à payer", "Coût employeur", ""],
                                                                 rows, right=(2, 3, 4, 5, 6, 7, 8), raw=tuple(range(10))))


VARS = [("jours_non_payes", "Jours non payés (absence injustifiée, sans solde, mise à pied) – base 30"), ("hs15", "Heures sup. 41e–48e h (+15 %)"), ("hs35", "Heures sup. au-delà de 48 h (+35 %)"),
        ("hs50", "Heures sup. de nuit, jours ouvrables (+50 %)"), ("hs60", "Heures sup. de jour, dimanche/férié (+60 %)"), ("hs120", "Heures sup. de nuit, dimanche/férié (+120 %)"),
        ("primes_imposables", "Primes et gratifications du mois (imposables)"), ("avantages_nature", "Avantages en nature (évaluation, imposable, non versé)"),
        ("remboursements", "Remboursements de frais (non imposables)"), ("avance", "Avances / acomptes à retenir"), ("autres_retenues", "Autres retenues (prêt, saisie, cotisation syndicale…)")]


@route(r"/paie/(\d+)/var/(\d+)", methods=("GET", "POST"), roles=PAIE)
def paie_var(req, pid, eid):
    conn = req.db
    pp = get_period(req, pid)
    emp = get_emp(req, eid)
    if pp["statut"] == "cloturee":
        return redirect(f"/paie/{pid}", err="Période clôturée : aucune modification possible.")
    old = conn.execute("SELECT * FROM pay_variables WHERE period_id=? AND employee_id=?", (pid, eid)).fetchone()
    if req.method == "POST":
        vals = {k: max(0.0, num(req.f(k))) for k, _ in VARS}
        note = req.f("note")[:500]
        if vals["jours_non_payes"] > 30:
            return redirect(f"/paie/{pid}/var/{eid}", err="Les jours non payés ne peuvent pas dépasser 30.")
        conn.execute("DELETE FROM pay_variables WHERE period_id=? AND employee_id=?", (pid, eid))
        conn.execute(f"INSERT INTO pay_variables(period_id,employee_id,{','.join(vals)},note) VALUES(?,?,{','.join('?' * len(vals))},?)", (pid, eid, *vals.values(), note))
        audit(conn, req.uname, "VARIABLES_PAIE", "pay_variables", f"{pid}/{eid}", {"avant": dict(old) if old else None, "apres": vals, "note": note})
        return redirect(f"/paie/{pid}", msg=f"Variables enregistrées pour {emp['nom']}. Pensez à recalculer la paie.")
    auto = jours_non_payes_auto(conn, eid, pp["annee"], pp["mois"])
    inputs = ""
    for k, lbl in VARS:
        v = old[k] if old else (auto if k == "jours_non_payes" else 0)
        inputs += f'<div><label>{e(lbl)}</label><input type="number" step="any" min="0" name="{k}" value="{v:g}"></div>'
    body = (f'<p class="muted">Absences non payées approuvées ce mois selon le module Congés : <b>{auto:g} jour(s)</b>.</p>'
            f'<form method="post">{csrf_field(req)}<div class="card"><div class="grid">{inputs}</div><div style="margin-top:10px"><label>Note / justification</label>'
            f'<input name="note" value="{e(old["note"] if old else "")}"></div></div><button>Enregistrer</button> <a class="btn g" href="/paie/{pid}">Annuler</a></form>')
    return page(req, f'Variables de paie – {emp_name(emp)} – {MOIS[pp["mois"]]} {pp["annee"]}', body)


@route(r"/paie/(\d+)/calculer", methods=("POST",), roles=PAIE)
def paie_calc(req, pid):
    pp = get_period(req, pid)
    if pp["statut"] == "cloturee":
        return redirect(f"/paie/{pid}", err="Période clôturée.")
    n = calculer(req.db, pp)
    audit(req.db, req.uname, "CALCUL_PAIE", "pay_periods", pid, f"{n} bulletins")
    return redirect(f"/paie/{pid}", msg=f"{n} bulletin(s) calculé(s).")


@route(r"/paie/(\d+)/(cloturer|rouvrir)", methods=("GET", "POST"), roles=RH)
def paie_close(req, pid, action):
    conn = req.db
    pp = get_period(req, pid)
    lib = f'{MOIS[pp["mois"]]} {pp["annee"]}'
    if action == "rouvrir" and req.role != "admin":
        raise Forbidden()
    if req.method == "GET":
        if action == "cloturer":
            txt = (f"<p>La clôture de <b>{lib}</b> fige définitivement les bulletins : ils ne pourront plus être recalculés ni modifiés. "
                   "Vérifiez le livre de paie avant de confirmer.</p>")
            extra = ""
        else:
            txt = f"<p>Rouvrir <b>{lib}</b> permet de recalculer des bulletins déjà remis. Opération exceptionnelle, tracée au journal d'audit.</p>"
            extra = '<label>Motif (obligatoire)</label><input name="motif" required>'
        return page(req, "Confirmation", f'<div class="card">{txt}<form method="post">{csrf_field(req)}{extra}<p><button class="d">Confirmer</button> '
                                         f'<a class="btn g" href="/paie/{pid}">Annuler</a></p></form></div>')
    if action == "cloturer":
        if pp["statut"] == "cloturee":
            return redirect(f"/paie/{pid}")
        calculer(conn, pp)
        conn.execute("UPDATE pay_periods SET statut='cloturee', cloture_le=?, cloture_par=? WHERE id=?", (now_iso(), req.uname, pid))
        tot = conn.execute("SELECT COUNT(*), SUM(brut), SUM(net) FROM payslips WHERE period_id=?", (pid,)).fetchone()
        audit(conn, req.uname, "CLOTURE_PAIE", "pay_periods", pid, f"{lib} : {tot[0]} bulletins, brut {tot[1]:.0f}, net {tot[2]:.0f}")
        return redirect(f"/paie/{pid}", msg="Période clôturée.")
    if not req.f("motif"):
        return redirect(f"/paie/{pid}/rouvrir", err="Motif obligatoire.")
    conn.execute("UPDATE pay_periods SET statut='ouverte', cloture_le=NULL, cloture_par=NULL WHERE id=?", (pid,))
    audit(conn, req.uname, "REOUVERTURE_PAIE", "pay_periods", pid, f"{lib} — motif : {req.f('motif')}")
    return redirect(f"/paie/{pid}", msg="Période rouverte.")


def bulletin_html(conn, pp, s):
    b = json.loads(s["data"])
    em = b["employe"]
    ent = get_params(conn, "entreprise")
    g = "".join(f'<tr><td>{e(x["lib"])}</td><td class="r">{(format(x["nb"], "g")) if x.get("nb") else ""}</td><td class="r">{money(x["taux"]) if x.get("taux") else ""}</td>'
                f'<td class="r">{money(x["montant"])}</td><td></td></tr>' for x in b["gains"])
    ret = [(f'CNSS – part salariale ({b.get("taux_cnss_sal", 0):g} % de {money(b["base_cnss"])})', b["cnss_sal"]),
           (f'IUTS (base {money(b["base_iuts"])} ; {b["nb_charges"]} charge(s), réduction {b["taux_reduction"]:g} %)', b["iuts"]),
           ("Avances et acomptes", b["avance"]), ("Autres retenues", b["autres_retenues"]), ("Avantages en nature (déjà perçus)", b["avantages_nature"])]
    r = "".join(f'<tr><td>{e(l)}</td><td></td><td></td><td></td><td class="r">{money(v)}</td></tr>' for l, v in ret if v)
    if b["remboursements"]:
        g += f'<tr><td>Remboursements de frais (hors brut)</td><td></td><td></td><td class="r">{money(b["remboursements"])}</td><td></td></tr>'
    pat = " · ".join(f"{k} {money(v)}" for k, v in b["cnss_pat_detail"].items())
    prov = "" if pp["statut"] == "cloturee" else '<p class="tag important">PROVISOIRE – période non clôturée</p>'
    return (f'<div class="doc pb"><div class="two"><div><b>{e(ent.get("raison_sociale") or "Employeur à renseigner")}</b><br>{e(ent.get("adresse"))} {e(ent.get("ville"))}<br>'
            f'IFU : {e(ent.get("ifu"))} — N° employeur CNSS : {e(ent.get("cnss_employeur"))}<br>{e(ent.get("convention_collective"))}</div>'
            f'<div><h2 style="text-align:right;margin:0">BULLETIN DE PAIE</h2><p style="text-align:right">Période : <b>{MOIS[pp["mois"]]} {pp["annee"]}</b></p>{prov}</div></div>'
            f'<table><tr><th>Matricule</th><td>{e(em["matricule"])}</td><th>Nom et prénoms</th><td><b>{e(em["nom"])} {e(em["prenoms"])}</b></td></tr>'
            f'<tr><th>Emploi</th><td>{e(em["emploi"])}</td><th>Catégorie / statut</th><td>{e(em["categorie"])} {e(em["statut"])}</td></tr>'
            f'<tr><th>N° CNSS</th><td>{e(em["cnss_no"])}</td><th>Date d\'embauche</th><td>{fr(em["date_embauche"])} (ancienneté {b["anciennete_ans"]:g} ans)</td></tr>'
            f'<tr><th>Situation de famille</th><td>{e(em["situation_famille"])} – {b["nb_charges"]} charge(s)</td><th>Jours payés</th><td>{b["jours"]:g} / 30</td></tr></table>'
            f'<table><tr><th>Rubrique</th><th class="r">Nombre</th><th class="r">Base / taux</th><th class="r">Gains</th><th class="r">Retenues</th></tr>{g}'
            f'<tr><th>SALAIRE BRUT</th><th></th><th></th><th class="r">{money(b["brut"])}</th><th></th></tr>{r}'
            f'<tr><th>TOTAL DES RETENUES</th><th></th><th></th><th></th><th class="r">{money(b["retenues"] + b["avantages_nature"])}</th></tr>'
            f'<tr><th style="font-size:15px">NET À PAYER (FCFA)</th><th></th><th></th><th class="r" style="font-size:15px" colspan="2">{money(b["net"])}</th></tr></table>'
            f'<p class="sm">IUTS : exonérations {money(b["exonerations"])} · abattement {b["taux_abatt"]:g} % = {money(b["abattement"])} · base imposable {money(b["base_iuts"])}<br>'
            f'Charges patronales : CNSS {money(b["cnss_pat"])} ({pat}) · TPA {money(b["tpa"])} — Coût total employeur : {money(b["cout_employeur"])}<br>'
            f'Congés payés : acquis {b["conge"]["acquis"]:g} j · pris {b["conge"]["pris"]:g} j · <b>solde {b["conge"]["solde"]:g} j</b> — '
            f'Paiement : {e(em["mode_paiement"])} {e(em["banque"])} {e(em["compte"])}</p>'
            '<div class="two sm" style="margin-top:18px"><div>L\'employeur</div><div>Le travailleur (reçu le ……/……/…………, signature)</div></div>'
            '<p class="sm muted" style="margin-top:34px">Bulletin à conserver sans limitation de durée. L\'acceptation sans réserve du bulletin ne vaut pas renonciation aux sommes dues.</p></div>')


@route(r"/paie/(\d+)/bulletin/(\d+)")
def bulletin(req, pid, eid):
    pp = get_period(req, pid)
    s = req.db.execute("SELECT * FROM payslips WHERE period_id=? AND employee_id=?", (pid, eid)).fetchone()
    if not s:
        return redirect(f"/paie/{pid}", err="Bulletin non calculé.")
    return page(req, "Bulletin de paie", f'<p class="noprint"><a href="/paie/{pid}">← Retour à la période</a> · Impression / PDF : Ctrl+P</p>' + bulletin_html(req.db, pp, s))


@route(r"/paie/(\d+)/bulletins")
def bulletins(req, pid):
    pp = get_period(req, pid)
    ss = req.db.execute("SELECT s.* FROM payslips s JOIN employees e ON e.id=s.employee_id WHERE period_id=? ORDER BY e.nom", (pid,)).fetchall()
    return page(req, f'Bulletins de {MOIS[pp["mois"]]} {pp["annee"]}', f'<p class="noprint"><a href="/paie/{pid}">← Retour</a> · Ctrl+P : un bulletin par page</p>'
                + "".join(bulletin_html(req.db, pp, s) for s in ss))


# ================================================================== administration
@route("/admin", roles=("admin",))
def admin(req):
    conn = req.db
    ok, n, bad = audit_verify(conn)
    integ = f'<span class="tag ok">Journal intègre ({n} écritures vérifiées)</span>' if ok else f'<span class="tag critique">ALTÉRATION DÉTECTÉE à l\'écriture n° {bad}</span>'
    bk = sorted(glob.glob(os.path.join(BACKUP_DIR, "erp_rh_*.db")))
    body = ('<div class="card"><h3 style="margin-top:0">Entreprise et référentiel légal</h3>'
            '<a class="btn" href="/admin/params/entreprise">Entreprise</a><a class="btn" href="/admin/params/paie">Paramètres de paie (CNSS, IUTS, TPA, SMIG)</a>'
            '<a class="btn" href="/admin/bareme">Barème IUTS</a><a class="btn" href="/admin/params/travail">Droit du travail</a><a class="btn" href="/e/feries">Jours fériés</a>'
            '<p class="muted sm">Aucun taux n\'est codé en dur : mettez ce référentiel à jour à chaque loi de finances, décret SMIG ou texte d\'application du Code du travail.</p></div>'
            '<div class="card"><h3 style="margin-top:0">Sécurité</h3><a class="btn" href="/admin/users">Utilisateurs et profils</a><a class="btn" href="/admin/params/securite">Règles de sécurité</a>'
            f'<a class="btn g" href="/admin/audit">Journal d\'audit</a> {integ}</div>'
            f'<div class="card"><h3 style="margin-top:0">Sauvegardes</h3><p>{len(bk)} sauvegarde(s) dans <code>{e(BACKUP_DIR)}</code>'
            f'{(" — dernière : " + e(os.path.basename(bk[-1]))) if bk else ""}.</p>' + post_btn(req, "/admin/backup", "Sauvegarder maintenant", "ok")
            + '<p class="muted sm">Une sauvegarde automatique est faite chaque jour au démarrage. Copiez régulièrement ce dossier sur un support externe chiffré, conservé hors des locaux.</p></div>')
    return page(req, "Paramètres et administration", body)


@route("/admin/backup", methods=("POST",), roles=("admin",))
def admin_backup(req):
    req.db.commit()
    name = backup()
    audit(req.db, req.uname, "SAUVEGARDE", "base", "", os.path.basename(name))
    return redirect("/admin", msg=f"Sauvegarde créée : {os.path.basename(name)}")


@route(r"/admin/params/(entreprise|paie|travail|securite)", methods=("GET", "POST"), roles=("admin",))
def admin_params(req, grp):
    conn = req.db
    rows = conn.execute("SELECT * FROM params WHERE grp=? ORDER BY ordre", (grp,)).fetchall()
    if req.method == "POST":
        diff = {}
        for r in rows:
            v = req.f("p_" + r["key"])[:500]
            if grp != "entreprise" and v != "" and num(v, None) is None:
                return redirect(f"/admin/params/{grp}", err=f"Valeur numérique attendue pour « {r['label']} ».")
            if v != (r["value"] or ""):
                diff[r["key"]] = [r["value"], v]
                conn.execute("UPDATE params SET value=? WHERE key=?", (v, r["key"]))
        if diff:
            audit(conn, req.uname, "MODIFICATION_PARAMETRES", "params", grp, diff)
        return redirect(f"/admin/params/{grp}", msg=f"{len(diff)} paramètre(s) modifié(s).")
    titres = {"entreprise": "Entreprise", "paie": "Paramètres de paie", "travail": "Référentiel droit du travail", "securite": "Règles de sécurité"}
    tr = "".join(f'<tr><td>{e(r["label"])}</td><td style="width:260px"><input name="p_{r["key"]}" value="{e(r["value"])}"></td><td class="sm muted">{e(r["source"])}</td></tr>' for r in rows)
    warn = "" if grp in ("entreprise", "securite") else ('<div class="err">Valeurs initiales fournies à titre indicatif. Les lignes marquées « À VÉRIFIER » doivent être confirmées '
                                                         "auprès de la CNSS, de la DGI ou de l'inspection du travail avant la première paie réelle. Toute modification est tracée.</div>")
    return page(req, titres[grp], f'{warn}<form method="post">{csrf_field(req)}<table><tr><th>Paramètre</th><th>Valeur</th><th>Source</th></tr>{tr}</table><button>Enregistrer</button> '
                                  '<a class="btn g" href="/admin">Retour</a></form>')


@route("/admin/bareme", methods=("GET", "POST"), roles=("admin",))
def admin_bareme(req):
    conn = req.db
    rows = conn.execute("SELECT * FROM iuts_bareme ORDER BY borne_inf").fetchall()
    if req.method == "POST":
        new = []
        for i in range(10):
            a, t = req.f(f"inf{i}"), req.f(f"taux{i}")
            if a != "" and t != "":
                new.append((num(a), num(t)))
        new.sort()
        if not new or new[0][0] != 0:
            return redirect("/admin/bareme", err="Le barème doit commencer à 0.")
        conn.execute("DELETE FROM iuts_bareme")
        for i, (a, t) in enumerate(new):
            conn.execute("INSERT INTO iuts_bareme(borne_inf,borne_sup,taux) VALUES(?,?,?)", (a, new[i + 1][0] if i + 1 < len(new) else None, t))
        audit(conn, req.uname, "MODIFICATION_BAREME_IUTS", "iuts_bareme", "", {"avant": [tuple(r)[1:] for r in rows], "apres": new})
        return redirect("/admin/bareme", msg="Barème enregistré.")
    tr = ""
    for i in range(10):
        r = rows[i] if i < len(rows) else None
        tr += (f'<tr><td><input type="number" step="any" name="inf{i}" value="{(format(r["borne_inf"], "g")) if r else ""}"></td>'
               f'<td class="muted">{("à " + money(r["borne_sup"])) if r and r["borne_sup"] else ("et au-delà" if r else "")}</td>'
               f'<td><input type="number" step="any" name="taux{i}" value="{(format(r["taux"], "g")) if r else ""}"></td></tr>')
    return page(req, "Barème mensuel de l'IUTS", '<div class="err">Barème progressif par tranches du Code général des impôts — à vérifier après chaque loi de finances.</div>'
                f'<form method="post" style="max-width:640px">{csrf_field(req)}<table><tr><th>Tranche à partir de (FCFA)</th><th></th><th>Taux (%)</th></tr>{tr}</table>'
                '<button>Enregistrer</button> <a class="btn g" href="/admin">Retour</a></form>')


@route("/admin/users", methods=("GET", "POST"), roles=("admin",))
def admin_users(req):
    conn = req.db
    if req.method == "POST":
        act = req.f("action")
        if act == "create":
            u, n, role, pw = req.f("username").lower(), req.f("fullname"), req.f("role"), req.form.get("pwd", "")
            err = pwd_policy(pw) or ("Profil invalide." if role not in ROLES else "") or ("Identifiant et nom obligatoires." if not (u and n) else "")
            if not err and conn.execute("SELECT 1 FROM users WHERE username=?", (u,)).fetchone():
                err = "Cet identifiant existe déjà."
            if err:
                return redirect("/admin/users", err=err)
            h, s = hash_pwd(pw)
            conn.execute("INSERT INTO users(username,fullname,role,pwd_hash,pwd_salt,must_change,created_at) VALUES(?,?,?,?,?,1,?)", (u, n, role, h, s, now_iso()))
            audit(conn, req.uname, "CREATION_UTILISATEUR", "users", u, role)
            return redirect("/admin/users", msg="Utilisateur créé. Il devra changer son mot de passe à la première connexion.")
        uid = int(num(req.f("id")))
        u = conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
        if not u:
            return redirect("/admin/users")
        admins = conn.execute("SELECT COUNT(*) FROM users WHERE role='admin' AND active=1").fetchone()[0]
        if act == "toggle":
            if u["active"] and u["role"] == "admin" and admins <= 1:
                return redirect("/admin/users", err="Impossible de désactiver le dernier administrateur.")
            conn.execute("UPDATE users SET active=?, failed=0, locked_until=0 WHERE id=?", (0 if u["active"] else 1, uid))
            conn.execute("DELETE FROM sessions WHERE user_id=?", (uid,))
            audit(conn, req.uname, "DESACTIVATION_UTILISATEUR" if u["active"] else "ACTIVATION_UTILISATEUR", "users", u["username"])
        elif act == "reset":
            pw = req.form.get("pwd", "")
            err = pwd_policy(pw)
            if err:
                return redirect("/admin/users", err=err)
            h, s = hash_pwd(pw)
            conn.execute("UPDATE users SET pwd_hash=?, pwd_salt=?, must_change=1, failed=0, locked_until=0 WHERE id=?", (h, s, uid))
            conn.execute("DELETE FROM sessions WHERE user_id=?", (uid,))
            audit(conn, req.uname, "REINITIALISATION_MOT_DE_PASSE", "users", u["username"])
        elif act == "role" and req.f("role") in ROLES:
            if u["role"] == "admin" and req.f("role") != "admin" and admins <= 1:
                return redirect("/admin/users", err="Il doit rester au moins un administrateur.")
            conn.execute("UPDATE users SET role=? WHERE id=?", (req.f("role"), uid))
            audit(conn, req.uname, "CHANGEMENT_PROFIL", "users", u["username"], f'{u["role"]} → {req.f("role")}')
        return redirect("/admin/users", msg="Modification effectuée.")
    ropts = lambda cur="": "".join(f'<option value="{k}"{" selected" if k == cur else ""}>{e(k)}</option>' for k in ROLES)
    rows = []
    for u in conn.execute("SELECT * FROM users ORDER BY username"):
        rows.append([e(u["username"]), e(u["fullname"]),
                     f'<form class="inline" method="post">{csrf_field(req)}<input type="hidden" name="action" value="role"><input type="hidden" name="id" value="{u["id"]}">'
                     f'<select name="role" style="width:auto">{ropts(u["role"])}</select> <button class="g" style="padding:3px 8px">OK</button></form>',
                     '<span class="tag ok">actif</span>' if u["active"] else '<span class="tag critique">désactivé</span>',
                     post_btn(req, "/admin/users", "Désactiver" if u["active"] else "Réactiver", "g", {"action": "toggle", "id": u["id"]}) +
                     f'<form class="inline" method="post">{csrf_field(req)}<input type="hidden" name="action" value="reset"><input type="hidden" name="id" value="{u["id"]}">'
                     '<input type="password" name="pwd" placeholder="nouveau mot de passe" style="width:170px"> <button class="g">Réinitialiser</button></form>'])
    body = table(["Identifiant", "Nom", "Profil", "État", "Actions"], rows, raw=(0, 1, 2, 3, 4))
    body += (f'<h3>Nouvel utilisateur</h3><form method="post" class="card">{csrf_field(req)}<input type="hidden" name="action" value="create"><div class="grid">'
             f'<div><label>Identifiant</label><input name="username" required></div><div><label>Nom complet</label><input name="fullname" required></div>'
             f'<div><label>Profil</label><select name="role">{ropts("lecture")}</select></div>'
             '<div><label>Mot de passe provisoire</label><input type="password" name="pwd" required></div></div><p><button>Créer</button></p></form>'
             + "<h3>Profils</h3>" + table(["Profil", "Droits"], list(ROLES.items())))
    return page(req, "Utilisateurs et profils", body)


@route("/admin/audit", roles=("admin",))
def admin_audit(req):
    conn = req.db
    q = req.q("q").strip()
    sql, args = "SELECT * FROM audit", []
    if q:
        sql += " WHERE user LIKE ? OR action LIKE ? OR entity LIKE ? OR details LIKE ?"
        args = [f"%{q}%"] * 4
    rows = conn.execute(sql + " ORDER BY id DESC LIMIT 1000", args).fetchall()
    H = ["N°", "Date et heure", "Utilisateur", "Action", "Objet", "Réf.", "Détails"]
    data = [[r["id"], r["ts"], r["user"], r["action"], r["entity"], r["entity_id"], r["details"]] for r in rows]
    if req.q("format") == "csv":
        return csv_resp("journal_audit", H + ["Empreinte"], [x + [r["hash"]] for x, r in zip(data, rows)])
    ok, n, bad = audit_verify(conn)
    integ = f'<span class="tag ok">Chaîne d\'empreintes intègre ({n} écritures)</span>' if ok else f'<span class="tag critique">ALTÉRATION DÉTECTÉE à l\'écriture n° {bad}</span>'
    for x in data:
        x[6] = (x[6][:300] + "…") if len(x[6]) > 300 else x[6]
    body = (f'<p>{integ}</p><form method="get" class="noprint"><input name="q" value="{e(q)}" placeholder="Filtrer…" style="width:240px"> <button class="g">Filtrer</button> '
            f'<a class="btn g" href="/admin/audit?format=csv">Exporter</a></form>' + table(H, data))
    return page(req, "Journal d'audit", body)
