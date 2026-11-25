# -*- coding: utf-8 -*-
"""Contrôles automatiques de conformité, rapports réglementaires et dossier pour l'inspection du travail."""
import json, calendar
import datetime as dt
from .core import route, page, e, d, fr, money, num, table, csv_resp, params, today, MOIS, get_params, logo_img
from . import paie as M
from .entites import emp_name, NON_PAYES


def actifs(conn, at=None):
    at = (at or today()).isoformat()
    return conn.execute("SELECT * FROM employees WHERE date_embauche<=? AND (date_sortie IS NULL OR date_sortie='' OR date_sortie>=?) ORDER BY nom,prenoms",
                        (at, at)).fetchall()


def est_etranger(emp):
    n = (emp["nationalite"] or "").strip().lower()
    return bool(n) and not n.startswith("burkinab")


def contrat_courant(conn, emp_id):
    return conn.execute("SELECT * FROM contracts WHERE employee_id=? ORDER BY date_debut DESC, id DESC LIMIT 1", (emp_id,)).fetchone()


# ------------------------------------------------------------------ contrôles de conformité
def controles(conn):
    """Retourne [(niveau, thème, message, lien)] ; niveau ∈ critique / important / info."""
    p = params(conn)
    t = today()
    out = []
    add = lambda niv, theme, msg, lien="": out.append((niv, theme, msg, lien))
    emps = actifs(conn)
    eff = len(emps)
    for emp in emps:
        nom, lien = emp_name(emp), f'/employes/{emp["id"]}'
        if not (emp["cnss_no"] or "").strip():
            add("critique", "CNSS", f"{nom} : aucun numéro d'immatriculation CNSS.", lien)
        if (emp["mode_remuneration"] or "Mensuel") == "Mensuel" and 0 < num(emp["salaire_base"]) < p.n("smig_mensuel"):
            add("critique", "Salaire", f"{nom} : salaire de base ({money(emp['salaire_base'])}) inférieur au SMIG ({money(p.n('smig_mensuel'))}).", lien)
        if not num(emp["salaire_base"]):
            add("important", "Salaire", f"{nom} : salaire de base non renseigné.", lien)
        dn = d(emp["date_naissance"])
        if not dn:
            add("info", "Dossier", f"{nom} : date de naissance non renseignée.", lien)
        elif (t - dn).days / 365.25 < 18:
            add("important", "Jeunes travailleurs", f"{nom} : travailleur de moins de 18 ans (travaux interdits, travail de nuit, visite médicale renforcée).", lien)
        cs = conn.execute("SELECT * FROM contracts WHERE employee_id=? ORDER BY date_debut", (emp["id"],)).fetchall()
        if not cs:
            add("critique", "Contrats", f"{nom} : aucun contrat de travail enregistré.", lien)
        else:
            c = cs[-1]
            cdds = [x for x in cs if x["type"] == "CDD"]
            if c["type"] == "CDD":
                fin = d(c["date_fin"])
                if fin and fin < t and c["statut"] == "En cours":
                    add("critique", "Contrats", f"{nom} : CDD échu le {fr(fin)} et relation poursuivie — risque de requalification en CDI.", lien)
                elif fin and (fin - t).days <= 30 and c["statut"] == "En cours":
                    add("important", "Contrats", f"{nom} : CDD arrivant à terme le {fr(fin)} (décision à prendre et à notifier).", lien)
                if len(cdds) > p.n("cdd_max_contrats", 3):
                    add("critique", "Contrats", f"{nom} : {len(cdds)} CDD conclus (maximum {p.n('cdd_max_contrats'):g}).", lien)
                elif len(cdds) - 1 > p.n("cdd_max_renouv", 2):
                    add("critique", "Contrats", f"{nom} : plus de {p.n('cdd_max_renouv'):g} renouvellements de CDD.", lien)
                duree = sum(M.mois_entre(d(x["date_debut"]), d(x["date_fin"]) or t) for x in cdds)
                if duree > p.n("cdd_duree_max_mois", 24) + 0.1:
                    add("critique", "Contrats", f"{nom} : durée cumulée des CDD de {duree:.0f} mois (maximum {p.n('cdd_duree_max_mois'):g}).", lien)
            ef = d(c["essai_fin"])
            if ef and 0 <= (ef - t).days <= 15:
                add("important", "Contrats", f"{nom} : fin de période d'essai le {fr(ef)} (confirmer ou rompre avant cette date).", lien)
            if est_etranger(emp):
                if not (c["visa_inspection"] or "").strip():
                    add("critique", "Travailleurs non nationaux", f"{nom} : contrat non visé par l'inspection du travail.", lien)
                if not (c["permis_travail"] or "").strip():
                    add("critique", "Travailleurs non nationaux", f"{nom} : permis de travail non renseigné.", lien)
                pe = d(c["permis_expire"])
                if pe and (pe - t).days <= 60:
                    add("important", "Travailleurs non nationaux", f"{nom} : permis de travail expirant le {fr(pe)}.", lien)
        vm = conn.execute("SELECT * FROM medical WHERE employee_id=? ORDER BY date DESC", (emp["id"],)).fetchall()
        if not any(v["type"] == "Embauche" for v in vm):
            add("important", "Santé au travail", f"{nom} : visite médicale d'embauche non enregistrée.", lien)
        if vm:
            der = d(vm[0]["date"])
            if M.mois_entre(der, t) > p.n("visite_med_mois", 12):
                add("important", "Santé au travail", f"{nom} : dernière visite médicale le {fr(der)} (périodicité dépassée).", lien)
        cg = M.conge_solde(conn, emp, p)
        if cg["solde"] > p.n("conge_solde_alerte", 60):
            add("important", "Congés", f"{nom} : solde de congés de {cg['solde']:g} jours — congés non pris à planifier.", lien)
        cont = p.n("hs_contingent_annuel")
        if cont:
            hs = conn.execute("SELECT COALESCE(SUM(heures_sup),0) FROM payslips s JOIN pay_periods pp ON pp.id=s.period_id WHERE employee_id=? AND annee=?",
                              (emp["id"], t.year)).fetchone()[0]
            if hs > cont:
                add("important", "Durée du travail", f"{nom} : {hs:g} heures supplémentaires en {t.year} (contingent {cont:g}).", lien)
    # --- accidents
    for a in conn.execute("SELECT a.*, e.nom, e.prenoms, e.matricule FROM accidents a JOIN employees e ON e.id=a.employee_id"):
        da = d(a["date"])
        delai = dt.timedelta(hours=p.n("at_delai_h", 48))
        for col, org in (("declare_cnss_le", "la CNSS"), ("declare_inspection_le", "l'inspection du travail")):
            dc = d(a[col])
            if not dc:
                add("critique", "Accidents du travail", f"{emp_name(a)} : accident du {fr(da)} non déclaré à {org}.", f'/e/accidents/{a["id"]}')
            elif da and dc - da > delai:
                add("info", "Accidents du travail", f"{emp_name(a)} : accident du {fr(da)} déclaré hors délai à {org} ({fr(dc)}).", f'/e/accidents/{a["id"]}')
    # --- représentation du personnel
    dp = conn.execute("SELECT * FROM representatives WHERE mandat LIKE 'Délégué du personnel%'").fetchall()
    dp_ok = [r for r in dp if not d(r["date_fin_mandat"]) or d(r["date_fin_mandat"]) >= t]
    if eff >= p.n("seuil_dp", 11):
        if not dp:
            add("critique", "Représentation", f"Effectif de {eff} travailleurs : élection de délégués du personnel obligatoire, aucun mandat enregistré.", "/e/representants")
        elif not dp_ok:
            add("critique", "Représentation", "Les mandats des délégués du personnel sont expirés : organiser de nouvelles élections.", "/e/representants")
    if eff >= p.n("seuil_csst", 30) and not conn.execute("SELECT 1 FROM representatives WHERE mandat='Membre du CSST'").fetchone():
        add("critique", "Santé au travail", f"Effectif de {eff} travailleurs : comité de sécurité et santé au travail (CSST) à constituer.", "/e/representants")
    # --- inspection
    for i in conn.execute("SELECT * FROM inspections WHERE statut='En cours de traitement'"):
        dl = d(i["delai"])
        if dl and dl < t:
            add("critique", "Inspection du travail", f"Mise en demeure du {fr(i['date'])} : délai dépassé depuis le {fr(dl)}.", f'/e/inspections/{i["id"]}')
        else:
            add("important", "Inspection du travail", f"Mise en demeure / observation du {fr(i['date'])} en cours de traitement" + (f" (délai : {fr(dl)})." if dl else "."), f'/e/inspections/{i["id"]}')
    # --- obligations
    for o in conn.execute("SELECT * FROM obligations WHERE statut IN ('À faire','En cours')"):
        ech = d(o["echeance"])
        niv = "critique" if ech and ech < t else "important" if o["statut"] == "À faire" else "info"
        add(niv, "Obligations de l'employeur", f"{o['libelle']} — {o['statut'].lower()}" + (f", échéance {fr(ech)}" if ech else "") + ".", f'/e/obligations/{o["id"]}')
    for o in conn.execute("SELECT * FROM obligations WHERE statut='Conforme' AND echeance<>'' AND echeance<?", (t.isoformat(),)):
        add("important", "Obligations de l'employeur", f"{o['libelle']} — échéance du {fr(o['echeance'])} dépassée : à renouveler.", f'/e/obligations/{o["id"]}')
    # --- paie
    prev = (t.replace(day=1) - dt.timedelta(days=1))
    if emps and t.day > 8:
        pp = conn.execute("SELECT * FROM pay_periods WHERE annee=? AND mois=?", (prev.year, prev.month)).fetchone()
        if not pp or pp["statut"] != "cloturee":
            add("important", "Paie", f"La paie de {MOIS[prev.month]} {prev.year} n'est pas clôturée (salaire payable au plus tard 8 jours après la fin du mois).", "/paie")
    ent = get_params(conn, "entreprise")
    for k, lbl in (("raison_sociale", "raison sociale"), ("cnss_employeur", "numéro employeur CNSS"), ("ifu", "numéro IFU"), ("inspection_ressort", "inspection du travail du ressort")):
        if not ent.get(k):
            add("info", "Entreprise", f"Paramètre entreprise manquant : {lbl}.", "/admin/params/entreprise")
    ordre = {"critique": 0, "important": 1, "info": 2}
    return sorted(out, key=lambda x: (ordre[x[0]], x[1]))


@route("/conformite")
def conformite(req):
    cs = controles(req.db)
    if req.q("format") == "csv":
        return csv_resp("conformite", ["Niveau", "Thème", "Constat"], [c[:3] for c in cs])
    n = {k: sum(1 for c in cs if c[0] == k) for k in ("critique", "important", "info")}
    rows = [[f'<span class="tag {c[0]}">{c[0]}</span>', e(c[1]), e(c[2]), f'<a href="{e(c[3])}">Traiter</a>' if c[3] else ""] for c in cs]
    body = (f'<div class="kpis"><div class="kpi"><b>{n["critique"]}</b><span>points critiques</span></div><div class="kpi"><b>{n["important"]}</b><span>points importants</span></div>'
            f'<div class="kpi"><b>{n["info"]}</b><span>informations</span></div></div>'
            '<p class="muted">Contrôles recalculés à chaque affichage à partir des données saisies. Les points « critiques » sont ceux qu\'un inspecteur relèverait en priorité.</p>'
            '<div class="noprint"><a class="btn g" href="/conformite?format=csv">Exporter</a><a class="btn" href="/e/obligations">Suivi des obligations légales</a></div>'
            + table(["Niveau", "Thème", "Constat", ""], rows, raw=(0, 1, 2, 3)))
    return page(req, "Tableau de conformité sociale", body)


# ------------------------------------------------------------------ rapports
def _periode(conn, annee, mois):
    return conn.execute("SELECT * FROM pay_periods WHERE annee=? AND mois=?", (annee, mois)).fetchone()


def r_registre1(conn, annee, mois):
    H = ["N°", "Matricule", "Nom et prénoms", "Sexe", "Date et lieu de naissance", "Nationalité", "Pièce d'identité", "N° CNSS", "Date d'embauche",
         "Emploi", "Catégorie", "Statut", "Contrat", "Visa inspection", "Date de sortie", "Motif de sortie"]
    rows = []
    for i, x in enumerate(conn.execute("SELECT * FROM employees ORDER BY date_embauche, id"), 1):
        c = contrat_courant(conn, x["id"])
        rows.append([i, x["matricule"], f'{x["nom"]} {x["prenoms"]}', x["sexe"], f'{fr(x["date_naissance"])} {x["lieu_naissance"] or ""}'.strip(), x["nationalite"],
                     f'{x["piece_type"] or ""} {x["piece_numero"] or ""}'.strip(), x["cnss_no"], fr(x["date_embauche"]), x["emploi"], x["categorie"], x["statut"],
                     (c["type"] + (f' → {fr(c["date_fin"])}' if c["date_fin"] else "")) if c else "", (c["visa_inspection"] if c else ""), fr(x["date_sortie"]), x["motif_sortie"]])
    return H, rows, "Tous les travailleurs, présents ou sortis, dans l'ordre d'embauche (le registre ne s'efface jamais)."


def r_registre2(conn, annee, mois):
    H = ["Matricule", "Nom et prénoms", "Emploi", "Jours payés", "Heures sup.", "Salaire brut", "Retenue CNSS", "IUTS", "Autres retenues", "Net payé",
         "Congés/absences du mois", "Solde congés (j)"]
    pp = _periode(conn, annee, mois)
    rows = []
    if pp:
        p = params(conn)
        deb, fin = dt.date(annee, mois, 1), dt.date(annee, mois, calendar.monthrange(annee, mois)[1])
        for s in conn.execute("SELECT s.*, e.matricule, e.nom, e.prenoms, e.emploi FROM payslips s JOIN employees e ON e.id=s.employee_id WHERE period_id=? ORDER BY e.nom", (pp["id"],)):
            dj = json.loads(s["data"])
            lv = conn.execute("SELECT type,date_debut,date_fin FROM leaves WHERE employee_id=? AND statut='Approuvé' AND date_debut<=? AND date_fin>=?",
                              (s["employee_id"], fin.isoformat(), deb.isoformat())).fetchall()
            emp = conn.execute("SELECT * FROM employees WHERE id=?", (s["employee_id"],)).fetchone()
            rows.append([s["matricule"], f'{s["nom"]} {s["prenoms"]}', s["emploi"], f'{dj["jours"]:g}', f'{s["heures_sup"]:g}', money(s["brut"]), money(s["cnss_sal"]),
                         money(s["iuts"]), money(dj["avance"] + dj["autres_retenues"]), money(s["net"]),
                         " ; ".join(f'{l["type"]} {fr(l["date_debut"])}–{fr(l["date_fin"])}' for l in lv), f'{M.conge_solde(conn, emp, p, fin)["solde"]:g}'])
    return H, rows, f"Travail effectué, salaires et congés – {MOIS[mois]} {annee}" + ("" if pp else " : aucune paie calculée pour cette période.")


def r_registre3(conn, annee, mois):
    H = ["Date", "Inspecteur / contrôleur", "Objet", "Observations", "Mise en demeure", "Délai", "Mise en conformité", "Statut"]
    rows = [[fr(i["date"]), i["inspecteur"], i["objet"], i["observations"], i["mise_en_demeure"], fr(i["delai"]), fr(i["date_levee"]), i["statut"]]
            for i in conn.execute("SELECT * FROM inspections ORDER BY date")]
    return H, rows, "Visas, mises en demeure et observations de l'inspection du travail."


def r_mouvements(conn, annee, mois):
    H = ["Date", "Mouvement", "Matricule", "Nom et prénoms", "Emploi", "Contrat", "Motif"]
    a, b = f"{annee}-01-01", f"{annee}-12-31"
    rows = []
    for x in conn.execute("SELECT * FROM employees WHERE date_embauche BETWEEN ? AND ?", (a, b)):
        c = contrat_courant(conn, x["id"])
        rows.append([x["date_embauche"], "Entrée", x["matricule"], f'{x["nom"]} {x["prenoms"]}', x["emploi"], c["type"] if c else "", "Embauche"])
    for x in conn.execute("SELECT * FROM employees WHERE date_sortie BETWEEN ? AND ?", (a, b)):
        c = contrat_courant(conn, x["id"])
        rows.append([x["date_sortie"], "Sortie", x["matricule"], f'{x["nom"]} {x["prenoms"]}', x["emploi"], c["type"] if c else "", x["motif_sortie"]])
    rows.sort(key=lambda r: r[0])
    for r in rows:
        r[0] = fr(r[0])
    return H, rows, f"Mouvements du personnel – année {annee}."


def r_main_oeuvre(conn, annee, mois):
    at = dt.date(annee, 12, 31)
    emps = actifs(conn, min(at, today()))
    H = ["Rubrique", "Modalité", "Hommes", "Femmes", "Total"]
    rows = []

    def bloc(titre, keyf, ordre=None):
        cats = {}
        for x in emps:
            k = keyf(x) or "Non renseigné"
            c = cats.setdefault(k, [0, 0])
            c[1 if x["sexe"] == "F" else 0] += 1
        for k in (ordre or sorted(cats)):
            if k in cats:
                rows.append([titre, k, cats[k][0], cats[k][1], sum(cats[k])])

    def age(x):
        dn = d(x["date_naissance"])
        if not dn:
            return None
        a = (at - dn).days / 365.25
        return "Moins de 18 ans" if a < 18 else "18–24 ans" if a < 25 else "25–34 ans" if a < 35 else "35–44 ans" if a < 45 else "45–54 ans" if a < 55 else "55 ans et plus"

    bloc("Effectif total", lambda x: "Ensemble")
    bloc("Statut professionnel", lambda x: x["statut"])
    bloc("Type de contrat", lambda x: (contrat_courant(conn, x["id"]) or {"type": None})["type"])
    bloc("Nationalité", lambda x: "Non nationaux" if est_etranger(x) else "Nationaux")
    bloc("Tranche d'âge", age, ["Moins de 18 ans", "18–24 ans", "25–34 ans", "35–44 ans", "45–54 ans", "55 ans et plus", "Non renseigné"])
    bloc("Handicap", lambda x: "En situation de handicap" if x["handicap"] == "Oui" else "Sans handicap déclaré")
    bloc("Service", lambda x: x["departement"])
    ms = conn.execute("SELECT COALESCE(SUM(brut),0) b, COALESCE(SUM(cnss_pat),0) c, COALESCE(SUM(tpa),0) t, COALESCE(SUM(heures_sup),0) h FROM payslips s JOIN pay_periods pp ON pp.id=s.period_id WHERE annee=?", (annee,)).fetchone()
    ent = conn.execute("SELECT COUNT(*) FROM employees WHERE date_embauche BETWEEN ? AND ?", (f"{annee}-01-01", f"{annee}-12-31")).fetchone()[0]
    sor = conn.execute("SELECT COUNT(*) FROM employees WHERE date_sortie BETWEEN ? AND ?", (f"{annee}-01-01", f"{annee}-12-31")).fetchone()[0]
    at_ = conn.execute("SELECT COUNT(*), COALESCE(SUM(jours_arret),0) FROM accidents WHERE date BETWEEN ? AND ?", (f"{annee}-01-01", f"{annee}-12-31")).fetchone()
    fo = conn.execute("SELECT COUNT(DISTINCT employee_id), COALESCE(SUM(heures),0), COALESCE(SUM(cout),0) FROM trainings WHERE date_debut BETWEEN ? AND ?", (f"{annee}-01-01", f"{annee}-12-31")).fetchone()
    for lib, val in (("Masse salariale brute annuelle (FCFA)", money(ms["b"])), ("Charges patronales CNSS (FCFA)", money(ms["c"])), ("TPA (FCFA)", money(ms["t"])),
                     ("Heures supplémentaires", f'{ms["h"]:g}'), ("Embauches de l'année", ent), ("Départs de l'année", sor),
                     ("Accidents du travail / jours d'arrêt", f"{at_[0]} / {at_[1]:g}"), ("Salariés formés / heures / coût", f"{fo[0]} / {fo[1]:g} / {money(fo[2])}")):
        rows.append(["Indicateurs annuels", lib, "", "", val])
    return H, rows, f"Situation de la main-d'œuvre au 31 décembre {annee} (base de la déclaration annuelle à l'inspection du travail)."


def r_cdd(conn, annee, mois):
    p = params(conn)
    H = ["Matricule", "Nom et prénoms", "Nb de CDD", "Premier CDD", "Fin du CDD en cours", "Durée cumulée (mois)", "Motif", "Situation"]
    rows = []
    for x in actifs(conn):
        cdds = conn.execute("SELECT * FROM contracts WHERE employee_id=? AND type='CDD' ORDER BY date_debut", (x["id"],)).fetchall()
        cur = contrat_courant(conn, x["id"])
        if not cdds or not cur or cur["type"] != "CDD":
            continue
        duree = sum(M.mois_entre(d(c["date_debut"]), d(c["date_fin"]) or today()) for c in cdds)
        pb = []
        if len(cdds) > p.n("cdd_max_contrats", 3) or len(cdds) - 1 > p.n("cdd_max_renouv", 2):
            pb.append("nombre de CDD dépassé")
        if duree > p.n("cdd_duree_max_mois", 24) + 0.1:
            pb.append("durée maximale dépassée")
        if d(cur["date_fin"]) and d(cur["date_fin"]) < today():
            pb.append("terme échu")
        rows.append([x["matricule"], f'{x["nom"]} {x["prenoms"]}', len(cdds), fr(cdds[0]["date_debut"]), fr(cur["date_fin"]), f"{duree:.1f}", cur["motif"],
                     "NON CONFORME : " + ", ".join(pb) if pb else "Conforme"])
    return H, rows, f"Maximum {p.n('cdd_max_renouv'):g} renouvellements, {p.n('cdd_max_contrats'):g} CDD et {p.n('cdd_duree_max_mois'):g} mois cumulés avec le même travailleur."


def r_etrangers(conn, annee, mois):
    H = ["Matricule", "Nom et prénoms", "Nationalité", "Emploi", "Contrat", "Visa inspection", "Date du visa", "Permis de travail", "Expiration"]
    rows = []
    for x in actifs(conn):
        if est_etranger(x):
            c = contrat_courant(conn, x["id"])
            rows.append([x["matricule"], f'{x["nom"]} {x["prenoms"]}', x["nationalite"], x["emploi"]] +
                        ([c["type"], c["visa_inspection"], fr(c["visa_date"]), c["permis_travail"], fr(c["permis_expire"])] if c else ["", "", "", "", ""]))
    return H, rows, "Travailleurs non nationaux : contrat visé par l'inspection du travail et permis de travail."


def r_hs(conn, annee, mois):
    H = ["Matricule", "Nom et prénoms"] + [MOIS[m][:4] for m in range(1, 13)] + ["Total heures", "Montant payé"]
    rows = []
    data = {}
    for s in conn.execute("SELECT s.employee_id, pp.mois, s.heures_sup, s.data FROM payslips s JOIN pay_periods pp ON pp.id=s.period_id WHERE annee=? AND heures_sup>0", (annee,)):
        x = data.setdefault(s["employee_id"], [[0] * 13, 0])
        x[0][s["mois"]] += s["heures_sup"]
        x[1] += json.loads(s["data"]).get("hs_montant", 0)
    for eid, (hm, mt) in data.items():
        x = conn.execute("SELECT * FROM employees WHERE id=?", (eid,)).fetchone()
        rows.append([x["matricule"], f'{x["nom"]} {x["prenoms"]}'] + [f"{h:g}" if h else "" for h in hm[1:]] + [f"{sum(hm):g}", money(mt)])
    return H, rows, f"Heures supplémentaires effectuées et payées – année {annee} (issues des bulletins de paie)."


def r_livre_paie(conn, annee, mois):
    H = ["Matricule", "Nom et prénoms", "Jours", "Brut", "Base CNSS", "CNSS salarié", "Base IUTS", "IUTS", "Avances et retenues", "Net à payer",
         "CNSS patronale", "TPA", "Coût employeur"]
    pp = _periode(conn, annee, mois)
    rows, tot = [], [0] * 10
    if pp:
        for s in conn.execute("SELECT s.*, e.matricule, e.nom, e.prenoms FROM payslips s JOIN employees e ON e.id=s.employee_id WHERE period_id=? ORDER BY e.nom", (pp["id"],)):
            dj = json.loads(s["data"])
            vals = [s["brut"], s["base_cnss"], s["cnss_sal"], dj["base_iuts"], s["iuts"], dj["avance"] + dj["autres_retenues"], s["net"], s["cnss_pat"], s["tpa"], dj["cout_employeur"]]
            tot = [a + b for a, b in zip(tot, vals)]
            rows.append([s["matricule"], f'{s["nom"]} {s["prenoms"]}', f'{dj["jours"]:g}'] + [money(v) for v in vals])
        rows.append(["", "TOTAUX", ""] + [money(v) for v in tot])
    st = f" (période {'clôturée' if pp['statut'] == 'cloturee' else 'NON clôturée – provisoire'})" if pp else " : aucune paie calculée."
    return H, rows, f"Livre de paie – {MOIS[mois]} {annee}{st}"


def r_cnss(conn, annee, mois):
    H = ["N° CNSS", "Matricule", "Nom et prénoms"] + [] + ["Mois", "Salaire soumis à cotisation", "Part salariale", "Part patronale", "Total cotisations"]
    tr = (mois - 1) // 3
    ms = [tr * 3 + 1, tr * 3 + 2, tr * 3 + 3]
    rows, tot = [], [0, 0, 0, 0]
    for s in conn.execute(f"SELECT s.*, pp.mois, e.cnss_no, e.matricule, e.nom, e.prenoms FROM payslips s JOIN pay_periods pp ON pp.id=s.period_id JOIN employees e ON e.id=s.employee_id "
                          f"WHERE annee=? AND mois IN ({ms[0]},{ms[1]},{ms[2]}) ORDER BY e.nom, pp.mois", (annee,)):
        vals = [s["base_cnss"], s["cnss_sal"], s["cnss_pat"], s["cnss_sal"] + s["cnss_pat"]]
        tot = [a + b for a, b in zip(tot, vals)]
        rows.append([s["cnss_no"], s["matricule"], f'{s["nom"]} {s["prenoms"]}', MOIS[s["mois"]]] + [money(v) for v in vals])
    if rows:
        rows.append(["", "", "TOTAL DU TRIMESTRE", ""] + [money(v) for v in tot])
    return H, rows, f"État de préparation de la déclaration CNSS – {tr + 1}ᵉ trimestre {annee} ({MOIS[ms[0]]} à {MOIS[ms[2]]})."


def r_fiscal(conn, annee, mois):
    H = ["Mois", "Effectif payé", "Brut", "IUTS retenu", "TPA due", "Total à verser aux impôts"]
    rows, tot = [], [0, 0, 0, 0]
    for r in conn.execute("SELECT pp.mois, COUNT(*) n, SUM(brut) b, SUM(iuts) i, SUM(tpa) t FROM payslips s JOIN pay_periods pp ON pp.id=s.period_id WHERE annee=? GROUP BY pp.mois ORDER BY pp.mois", (annee,)):
        vals = [r["b"], r["i"], r["t"], r["i"] + r["t"]]
        tot = [a + b for a, b in zip(tot, vals)]
        rows.append([MOIS[r["mois"]], r["n"]] + [money(v) for v in vals])
    if rows:
        rows.append(["TOTAL " + str(annee), ""] + [money(v) for v in tot])
    return H, rows, f"IUTS et TPA – récapitulatif {annee} (base des déclarations mensuelles et de l'état annuel des salaires)."


def r_smig(conn, annee, mois):
    p = params(conn)
    H = ["Matricule", "Nom et prénoms", "Emploi", "Catégorie", "Sexe", "Salaire de base", "Brut théorique", "Écart au SMIG", "Situation"]
    rows = []
    for x in actifs(conn):
        brut = sum(num(x[k]) for k in ("salaire_base", "sursalaire", "ind_logement", "ind_transport", "ind_fonction", "primes_fixes"))
        ec = num(x["salaire_base"]) - p.n("smig_mensuel")
        rows.append([x["matricule"], f'{x["nom"]} {x["prenoms"]}', x["emploi"], x["categorie"], x["sexe"], money(x["salaire_base"]), money(brut), money(ec),
                     "Conforme" if ec >= 0 or (x["mode_remuneration"] or "Mensuel") != "Mensuel" else "INFÉRIEUR AU SMIG"])
    return H, rows, f"Contrôle du respect du SMIG ({money(p.n('smig_mensuel'))} FCFA/mois) et grille des salaires (égalité de rémunération)."


def r_conges(conn, annee, mois):
    p = params(conn)
    H = ["Matricule", "Nom et prénoms", "Date d'embauche", "Ancienneté (ans)", "Droits acquis (j)", "Congés pris (j)", "Solde (j)", "Dernier congé annuel"]
    rows = []
    for x in actifs(conn):
        cg = M.conge_solde(conn, x, p)
        der = conn.execute("SELECT MAX(date_fin) FROM leaves WHERE employee_id=? AND type='Congé annuel' AND statut='Approuvé'", (x["id"],)).fetchone()[0]
        rows.append([x["matricule"], f'{x["nom"]} {x["prenoms"]}', fr(x["date_embauche"]), f"{M.anciennete_ans(x, today()):.1f}", f'{cg["acquis"]:g}', f'{cg["pris"]:g}', f'{cg["solde"]:g}', fr(der)])
    return H, rows, f"Situation des congés payés au {fr(today())} ({p.n('conge_jours_mois'):g} jours calendaires par mois de service)."


def _simple(sql, H, fmt, note):
    def f(conn, annee, mois):
        return H, [fmt(r) for r in conn.execute(sql, (f"{annee}-01-01", f"{annee}-12-31"))], note.format(annee=annee)
    return f


J = " t JOIN employees e ON e.id=t.employee_id WHERE t.date BETWEEN ? AND ? ORDER BY t.date"
r_accidents = _simple("SELECT t.*, e.matricule, e.nom, e.prenoms FROM accidents" + J,
                      ["Date", "Heure", "Victime", "Nature", "Lieu", "Circonstances", "Lésions", "Arrêt (j)", "Déclaré CNSS", "Déclaré inspection"],
                      lambda r: [fr(r["date"]), r["heure"], emp_name(r), r["nature"], r["lieu"], r["circonstances"], r["lesions"], r["jours_arret"], fr(r["declare_cnss_le"]), fr(r["declare_inspection_le"])],
                      "Registre des accidents du travail et maladies professionnelles – {annee}.")
r_sanctions = _simple("SELECT t.*, e.matricule, e.nom, e.prenoms FROM sanctions" + J,
                      ["Date", "Travailleur", "Sanction", "Motif", "Durée (j)", "Explications demandées le", "Notifiée le"],
                      lambda r: [fr(r["date"]), emp_name(r), r["type"], r["motif"], r["duree_jours"], fr(r["date_explication"]), fr(r["date_notification"])],
                      "Registre des sanctions disciplinaires – {annee}.")
r_visites = _simple("SELECT t.*, e.matricule, e.nom, e.prenoms FROM medical" + J,
                    ["Date", "Travailleur", "Type", "Conclusion", "Prochaine visite", "Médecin / structure"],
                    lambda r: [fr(r["date"]), emp_name(r), r["type"], r["resultat"], fr(r["prochaine"]), r["medecin"]],
                    "Suivi des visites médicales – {annee}.")


def r_representants(conn, annee, mois):
    H = ["Mandat", "Nom et prénoms", "Collège", "Élu / désigné le", "Fin de mandat", "PV transmis", "État"]
    rows = [[r["mandat"], emp_name(r), r["college"], fr(r["date_election"]), fr(r["date_fin_mandat"]), r["pv_reference"],
             "Expiré" if d(r["date_fin_mandat"]) and d(r["date_fin_mandat"]) < today() else "En cours"]
            for r in conn.execute("SELECT t.*, e.matricule, e.nom, e.prenoms FROM representatives t JOIN employees e ON e.id=t.employee_id ORDER BY mandat, date_election DESC")]
    return H, rows, f"Délégués du personnel, CSST et délégués syndicaux. Effectif actuel : {len(actifs(conn))} travailleur(s)."


def r_feries(conn, annee, mois):
    H = ["Date", "Libellé", "Régime"]
    return H, [[fr(r["date"]), r["libelle"], r["type"]] for r in conn.execute("SELECT * FROM feries WHERE date BETWEEN ? AND ? ORDER BY date", (f"{annee}-01-01", f"{annee}-12-31"))], \
        f"Jours chômés et payés et journées de commémoration – {annee} (loi de janvier 2026 ; fêtes mobiles à confirmer par communiqué)."


def r_virements(conn, annee, mois):
    H = ["Matricule", "Nom et prénoms", "Mode de paiement", "Banque / opérateur", "N° de compte / téléphone", "Net à payer"]
    pp = _periode(conn, annee, mois)
    rows, tot = [], 0
    if pp:
        for s in conn.execute("SELECT s.net, e.* FROM payslips s JOIN employees e ON e.id=s.employee_id WHERE period_id=? ORDER BY e.mode_paiement, e.nom", (pp["id"],)):
            rows.append([s["matricule"], f'{s["nom"]} {s["prenoms"]}', s["mode_paiement"], s["banque"], s["compte"], money(s["net"])])
            tot += s["net"]
        rows.append(["", "TOTAL", "", "", "", money(tot)])
    return H, rows, f"État de paiement des salaires – {MOIS[mois]} {annee} (à faire émarger pour les paiements en espèces)."


RAPPORTS = {
    "registre1": ("Registre d'employeur – Fascicule 1 : personnel et contrats", r_registre1, ""),
    "registre2": ("Registre d'employeur – Fascicule 2 : travail, salaires et congés", r_registre2, "m"),
    "registre3": ("Registre d'employeur – Fascicule 3 : visas et mises en demeure de l'inspection", r_registre3, ""),
    "mouvements": ("Mouvements du personnel (entrées / sorties)", r_mouvements, "a"),
    "main_oeuvre": ("Situation annuelle de la main-d'œuvre", r_main_oeuvre, "a"),
    "livre_paie": ("Livre de paie mensuel", r_livre_paie, "m"),
    "virements": ("État de paiement / ordre de virement", r_virements, "m"),
    "cnss": ("État des cotisations CNSS (trimestre)", r_cnss, "m"),
    "fiscal": ("IUTS et TPA – récapitulatif annuel", r_fiscal, "a"),
    "smig": ("Contrôle du SMIG et grille des salaires", r_smig, ""),
    "hs": ("Heures supplémentaires", r_hs, "a"),
    "conges": ("Situation des congés payés", r_conges, ""),
    "cdd": ("Suivi des CDD", r_cdd, ""),
    "etrangers": ("Travailleurs non nationaux", r_etrangers, ""),
    "accidents": ("Registre des accidents du travail", r_accidents, "a"),
    "sanctions": ("Registre des sanctions disciplinaires", r_sanctions, "a"),
    "visites": ("Suivi des visites médicales", r_visites, "a"),
    "representants": ("Représentants du personnel", r_representants, ""),
    "feries": ("Jours fériés de l'année", r_feries, "a"),
}


def _am(req):
    t = today()
    a = int(num(req.q("annee"), t.year))
    m = int(num(req.q("mois"), t.month))
    return max(2000, min(2100, a)), max(1, min(12, m))


def entete(conn):
    ent = get_params(conn, "entreprise")
    lg = logo_img(conn, 60, "float:left;margin:0 14px 6px 0")
    return (f'<div class="sm" style="overflow:hidden">{lg}<b>{e(ent.get("raison_sociale") or "Raison sociale à renseigner")}</b> — {e(ent.get("adresse"))} {e(ent.get("ville"))}<br>'
            f'IFU : {e(ent.get("ifu"))} · RCCM : {e(ent.get("rccm"))} · N° employeur CNSS : {e(ent.get("cnss_employeur"))}</div>')


def selecteur(code, a, m, mode):
    if not mode:
        return ""
    ms = ""
    if mode == "m":
        ms = '<select name="mois" style="width:auto">' + "".join(f'<option value="{i}"{" selected" if i == m else ""}>{MOIS[i]}</option>' for i in range(1, 13)) + "</select> "
    return f'<form class="inline noprint" method="get">{ms}<input type="number" name="annee" value="{a}" style="width:90px"> <button class="g">Afficher</button></form>'


@route(r"/rapports/(\w+)")
def rapport(req, code):
    if code not in RAPPORTS:
        return page(req, "Rapport inconnu", "")
    if code == "sanctions" and req.role == "paie":
        from .core import Forbidden
        raise Forbidden()
    titre, fn, mode = RAPPORTS[code]
    a, m = _am(req)
    H, rows, note = fn(req.db, a, m)
    if req.q("format") == "csv":
        return csv_resp(f"{code}_{a}_{m:02d}", H, rows)
    body = (entete(req.db) + f'<p>{e(note)}</p><div class="noprint">{selecteur(code, a, m, mode)}'
            f'<a class="btn g" href="/rapports/{code}?format=csv&annee={a}&mois={m}">Exporter (Excel/CSV)</a> <span class="muted">Impression / PDF : Ctrl+P</span></div>'
            + table(H, rows) + f'<p class="muted sm">Édité le {fr(today())} par {e(req.user["fullname"])}.</p>')
    return page(req, titre, body)


@route("/rapports")
def rapports_index(req):
    rows = [[f'<a href="/rapports/{k}">{e(v[0])}</a>', {"m": "Mensuel", "a": "Annuel", "": "Situation à date"}[v[2]]] for k, v in RAPPORTS.items()]
    return page(req, "Rapports et états réglementaires", table(["Rapport", "Périodicité"], rows, raw=(0,)))


# ------------------------------------------------------------------ dossier inspection
QUESTIONS = [
    ("Présentez votre registre d'employeur.", [("registre1", "Fascicule 1"), ("registre2", "Fascicule 2"), ("registre3", "Fascicule 3")]),
    ("Quel est votre effectif ? Sa répartition par sexe, catégorie, contrat, nationalité ?", [("main_oeuvre", "Situation de la main-d'œuvre")]),
    ("Avez-vous déclaré vos mouvements de personnel et votre situation annuelle de main-d'œuvre ?", [("mouvements", "Mouvements"), ("main_oeuvre", "Déclaration annuelle")]),
    ("Tous vos travailleurs ont-ils un contrat écrit ? Vos CDD sont-ils réguliers ?", [("registre1", "Contrats par travailleur"), ("cdd", "Suivi des CDD")]),
    ("Employez-vous des travailleurs non nationaux ? Contrats visés, permis de travail ?", [("etrangers", "Travailleurs non nationaux")]),
    ("Respectez-vous le SMIG et les salaires catégoriels ? L'égalité de rémunération ?", [("smig", "Contrôle SMIG / grille")]),
    ("Montrez les bulletins de paie et le registre des paiements.", [("livre_paie", "Livre de paie"), ("virements", "État de paiement")]),
    ("Les travailleurs sont-ils déclarés à la CNSS ? Les cotisations sont-elles à jour ?", [("cnss", "État CNSS"), ("registre1", "N° CNSS par travailleur")]),
    ("L'IUTS et la TPA sont-ils déclarés ?", [("fiscal", "IUTS / TPA")]),
    ("Quelle est la durée du travail ? Les heures supplémentaires sont-elles payées et majorées ?", [("hs", "Heures supplémentaires"), ("feries", "Jours fériés")]),
    ("Les congés payés sont-ils accordés et pris ?", [("conges", "Situation des congés")]),
    ("Avez-vous des délégués du personnel ? Un comité de sécurité et santé (CSST) ?", [("representants", "Représentants du personnel")]),
    ("Les visites médicales d'embauche et périodiques sont-elles faites ?", [("visites", "Visites médicales")]),
    ("Tenez-vous un registre des accidents du travail ? Ont-ils été déclarés sous 48 h ?", [("accidents", "Accidents du travail")]),
    ("Quelles sanctions disciplinaires avez-vous prononcées, et selon quelle procédure ?", [("sanctions", "Registre des sanctions")]),
]


@route("/inspection")
def inspection(req):
    t = today()
    rows = [[e(q), " · ".join(f'<a href="/rapports/{c}">{e(l)}</a>' for c, l in liens)] for q, liens in QUESTIONS]
    rows.append(["Règlement intérieur, affichages, déclaration d'ouverture, OST, évaluation des risques… : où en êtes-vous ?", '<a href="/e/obligations">Suivi des obligations légales (avec preuves)</a>'])
    rows.append(["Quelles suites avez-vous données à nos précédentes observations et mises en demeure ?", '<a href="/e/inspections">Visites et mises en demeure</a>'])
    rows.append(["Quels sont vos points de non-conformité connus ?", '<a href="/conformite">Tableau de conformité (auto-contrôle)</a>'])
    cs = controles(req.db)
    nc = sum(1 for c in cs if c[0] == "critique")
    body = (f'<div class="card"><b>Avant le contrôle :</b> {nc} point(s) critique(s) au <a href="/conformite">tableau de conformité</a>. '
            f'<a class="btn ok" href="/inspection/dossier?annee={t.year}">Éditer le dossier complet {t.year} (impression / PDF)</a>'
            f'<a class="btn g" href="/inspection/dossier?annee={t.year - 1}">Dossier {t.year - 1}</a>'
            '<p class="muted sm">Créez pour l\'inspecteur un compte de profil « Consultation seule » si vous souhaitez lui donner un accès direct, ou imprimez le dossier.</p></div>'
            '<h3>Questions habituelles de l\'inspecteur → pièce à produire</h3>' + table(["Question", "Réponse dans l'ERP"], rows, raw=(0, 1))
            + f'<p><a class="btn" href="/e/inspections/new">+ Consigner une visite / mise en demeure</a></p>')
    return page(req, "Dossier Inspection du travail", body)


@route("/inspection/dossier")
def dossier(req):
    a, _ = _am(req)
    conn = req.db
    m = 12 if a < today().year else max(1, today().month - 1) if today().day < 28 else today().month
    last = conn.execute("SELECT mois FROM pay_periods WHERE annee=? ORDER BY mois DESC LIMIT 1", (a,)).fetchone()
    if last:
        m = last["mois"]
    parts = [f'<div class="noprint card">Dossier prêt à imprimer : <b>Ctrl+P</b> puis « Enregistrer au format PDF ». Orientation paysage conseillée.</div>',
             entete(conn), f'<p>Dossier social édité le {fr(today())} – exercice {a}. Inspection du ressort : {e(get_params(conn, "entreprise").get("inspection_ressort"))}</p>']
    for code in ("registre1", "registre2", "registre3", "main_oeuvre", "mouvements", "cdd", "etrangers", "smig", "livre_paie", "cnss", "fiscal", "hs", "conges",
                 "representants", "visites", "accidents", "sanctions"):
        titre, fn, mode = RAPPORTS[code]
        H, rows, note = fn(conn, a, m)
        parts.append(f'<h3>{e(titre)}</h3><p class="sm">{e(note)}</p>' + table(H, rows))
    ob = conn.execute("SELECT * FROM obligations ORDER BY id").fetchall()
    parts.append("<h3>Obligations légales de l'employeur</h3>" + table(["Obligation", "Périodicité", "Statut", "Échéance", "Preuve"],
                 [[o["libelle"], o["frequence"], o["statut"], fr(o["echeance"]), o["preuve"]] for o in ob]))
    cs = controles(conn)
    parts.append("<h3>Auto-contrôle de conformité</h3>" + table(["Niveau", "Thème", "Constat"], [c[:3] for c in cs]))
    return page(req, f"Dossier social {a} – Inspection du travail", "".join(parts))
