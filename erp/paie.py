# -*- coding: utf-8 -*-
"""Règles métier : ancienneté, congés, bulletin de paie (CNSS, IUTS, TPA), fin de contrat.
Fonctions pures : tous les taux viennent du référentiel paramétrable."""
import calendar, math
import datetime as dt
from .core import d, num

CADRES = ("Cadre", "Agent de maîtrise / technicien")


def mois_entre(a, b):
    """Nombre de mois (décimal) entre deux dates."""
    if not a or not b or b < a:
        return 0.0
    m = (b.year - a.year) * 12 + (b.month - a.month)
    if b.day < a.day:
        m -= 1
        prev = (b.replace(day=1) - dt.timedelta(days=1))
        frac = (b.day + max(0, prev.day - a.day)) / 30.0
    else:
        frac = (b.day - a.day) / 30.0
    return max(0.0, m + min(frac, 0.99))


def anciennete_ans(emp, at):
    fin = d(emp["date_sortie"]) or at
    return mois_entre(d(emp["date_embauche"]), min(fin, at)) / 12.0


def taux_anciennete(ans, p):
    seuil = p.n("anc_seuil", 3)
    if ans < seuil:
        return 0.0
    return min(p.n("anc_max", 25), p.n("anc_taux", 3) + (math.floor(ans) - seuil) * p.n("anc_increment", 1))


def conge_solde(conn, emp, p, at=None):
    """Droits acquis depuis la date de référence (ou l'embauche) – congés annuels pris."""
    at = at or dt.date.today()
    fin = min(d(emp["date_sortie"]) or at, at)
    ref = d(emp["conge_date_reference"]) or d(emp["date_embauche"])
    acquis = mois_entre(ref, fin) * p.n("conge_jours_mois", 2.5)
    ans = anciennete_ans(emp, at)
    bonus_an = p.n("conge_bonus_30", 6) if ans >= 30 else p.n("conge_bonus_25", 4) if ans >= 25 else p.n("conge_bonus_20", 2) if ans >= 20 else 0
    acquis += bonus_an * mois_entre(ref, fin) / 12.0 if bonus_an else 0
    pris = conn.execute("SELECT COALESCE(SUM(jours),0) FROM leaves WHERE employee_id=? AND type='Congé annuel' AND statut='Approuvé' AND date_debut>=?",
                        (emp["id"], ref.isoformat() if ref else "")).fetchone()[0]
    init = num(emp["conge_solde_initial"])
    return {"acquis": round(acquis + init, 2), "pris": round(pris, 2), "solde": round(acquis + init - pris, 2)}


def jours_presence_30(emp, annee, mois):
    """Jours rémunérables sur une base de 30 (prorata entrée/sortie en cours de mois)."""
    nb = calendar.monthrange(annee, mois)[1]
    debut, fin = dt.date(annee, mois, 1), dt.date(annee, mois, nb)
    emb, sor = d(emp["date_embauche"]), d(emp["date_sortie"])
    a = max(debut, emb) if emb else debut
    b = min(fin, sor) if sor else fin
    if b < a:
        return 0.0
    if a == debut and b == fin:
        return 30.0
    return round(((b - a).days + 1) / nb * 30, 2)


def iuts_bareme(base, bareme):
    """Barème progressif par tranches. bareme : [(borne_inf, borne_sup|None, taux%)]."""
    total = 0.0
    for inf, sup, taux in bareme:
        if base <= inf:
            break
        haut = base if sup is None else min(base, sup)
        total += (haut - inf) * taux / 100.0
    return total


def calc_bulletin(emp, var, p, bareme, annee, mois):
    """Calcule un bulletin. emp/var : dict-like. Retourne un dict détaillé (montants entiers FCFA)."""
    g = lambda k: num(var.get(k)) if var else 0.0
    fin_mois = dt.date(annee, mois, calendar.monthrange(annee, mois)[1])
    presence = jours_presence_30(emp, annee, mois)
    jours = max(0.0, presence - g("jours_non_payes"))
    ratio = jours / 30.0
    base_th = num(emp["salaire_base"])
    base = base_th * ratio
    sursal = num(emp["sursalaire"]) * ratio
    ans = anciennete_ans(emp, fin_mois)
    t_anc = taux_anciennete(ans, p)
    prime_anc = base * t_anc / 100.0
    taux_h = (base_th + num(emp["sursalaire"])) / p.n("heures_mois", 173.33)
    hs_lignes, hs_total, hs_heures = [], 0.0, 0.0
    for k in ("hs15", "hs35", "hs50", "hs60", "hs120"):
        h = g(k)
        if h:
            m = h * taux_h * (1 + p.n(k) / 100.0)
            hs_lignes.append({"lib": f"Heures sup. majorées {p.n(k):g} %", "nb": h, "taux": round(taux_h * (1 + p.n(k) / 100.0), 2), "montant": round(m)})
            hs_total += m
            hs_heures += h
    logement = num(emp["ind_logement"]) * ratio
    transport = num(emp["ind_transport"]) * ratio
    fonction = num(emp["ind_fonction"]) * ratio
    primes_fixes = num(emp["primes_fixes"]) * ratio
    primes_var = g("primes_imposables")
    avn = g("avantages_nature")
    brut = base + sursal + prime_anc + hs_total + logement + transport + fonction + primes_fixes + primes_var + avn

    # --- CNSS
    base_cnss = min(brut, p.n("cnss_plafond"))
    cnss_sal = round(base_cnss * p.n("cnss_taux_sal") / 100.0)
    pat = {"Pensions": round(base_cnss * p.n("cnss_taux_pension_pat") / 100.0),
           "Prestations familiales": round(base_cnss * p.n("cnss_taux_pf") / 100.0),
           "Risques professionnels": round(base_cnss * p.n("cnss_taux_rp") / 100.0)}
    cnss_pat = sum(pat.values())

    # --- IUTS
    exo_log = min(logement, brut * p.n("exo_logement_pct") / 100.0, p.n("exo_logement_plafond"))
    exo_tr = min(transport, brut * p.n("exo_transport_pct") / 100.0, p.n("exo_transport_plafond"))
    exo_fn = min(fonction, brut * p.n("exo_fonction_pct") / 100.0, p.n("exo_fonction_plafond"))
    exo = exo_log + exo_tr + exo_fn
    cadre = (emp["statut"] or "") == "Cadre"
    t_ab = p.n("abatt_cadre") if cadre else p.n("abatt_non_cadre")
    abatt = base * t_ab / 100.0
    imposable = max(0.0, brut - exo - cnss_sal - abatt)
    imposable = math.floor(imposable / 100.0) * 100
    iuts_brut = iuts_bareme(imposable, bareme)
    nch = max(0, min(4, int(num(emp["nb_charges"]))))
    t_red = p.n(f"charges_{nch}") if nch else 0.0
    iuts = round(iuts_brut * (1 - t_red / 100.0))
    tpa = round((brut - exo) * p.n("tpa_taux") / 100.0)

    remb = g("remboursements")
    avance, autres = g("avance"), g("autres_retenues")
    net = round(brut) - avn - cnss_sal - iuts - avance - autres + remb
    gains = [
        {"lib": "Salaire de base", "nb": jours, "taux": round(base_th), "montant": round(base)},
        {"lib": "Sursalaire", "montant": round(sursal)},
        {"lib": f"Prime d'ancienneté ({t_anc:g} %)", "montant": round(prime_anc)},
        *hs_lignes,
        {"lib": "Indemnité de logement", "montant": round(logement)},
        {"lib": "Indemnité de transport", "montant": round(transport)},
        {"lib": "Indemnité de fonction", "montant": round(fonction)},
        {"lib": "Primes fixes", "montant": round(primes_fixes)},
        {"lib": "Primes et gratifications du mois", "montant": round(primes_var)},
        {"lib": "Avantages en nature (évaluation)", "montant": round(avn)},
    ]
    alertes = []
    if base_th and base_th < p.n("smig_mensuel") and (emp["mode_remuneration"] or "Mensuel") == "Mensuel":
        alertes.append("Salaire de base inférieur au SMIG")
    if net < 0:
        alertes.append("Net à payer négatif")
    return {
        "gains": [x for x in gains if x["montant"]],
        "jours": jours, "anciennete_ans": round(ans, 2), "taux_anc": t_anc,
        "brut": round(brut), "base_cnss": round(base_cnss), "taux_cnss_sal": p.n("cnss_taux_sal"), "cnss_sal": cnss_sal, "cnss_pat": cnss_pat, "cnss_pat_detail": pat,
        "exonerations": round(exo), "abattement": round(abatt), "taux_abatt": t_ab, "base_iuts": imposable,
        "iuts_brut": round(iuts_brut), "nb_charges": nch, "taux_reduction": t_red, "iuts": iuts, "tpa": tpa,
        "avantages_nature": round(avn), "remboursements": round(remb), "avance": round(avance), "autres_retenues": round(autres),
        "retenues": cnss_sal + iuts + round(avance) + round(autres), "net": round(net),
        "heures_sup": hs_heures, "hs_montant": round(hs_total), "cout_employeur": round(brut) + cnss_pat + tpa, "alertes": alertes,
    }


def preavis(emp, p):
    if (emp["statut"] or "") in CADRES:
        return p.n("preavis_cadre_mois", 3), "mois"
    if (emp["mode_remuneration"] or "Mensuel") == "Mensuel":
        return p.n("preavis_mensuel_mois", 1), "mois"
    return p.n("preavis_horaire_jours", 8), "jours"


def essai(emp, p):
    if (emp["statut"] or "") in CADRES:
        return p.n("essai_cadre_mois", 3), "mois"
    if (emp["mode_remuneration"] or "Mensuel") == "Mensuel":
        return p.n("essai_employe_mois", 1), "mois"
    return p.n("essai_ouvrier_jours", 8), "jours"


def indemnite_licenciement(ans, salaire_moyen, p):
    """% du salaire global mensuel moyen par année de présence, par tranches (prorata des fractions d'année)."""
    if ans < 1:
        return 0
    t1 = min(ans, 5)
    t2 = max(0.0, min(ans, 10) - 5)
    t3 = max(0.0, ans - 10)
    return round(salaire_moyen * (t1 * p.n("lic_taux_1") + t2 * p.n("lic_taux_2") + t3 * p.n("lic_taux_3")) / 100.0)


def solde_tout_compte(conn, emp, p, date_sortie, motif):
    """Simulation des droits de fin de contrat."""
    rows = conn.execute("SELECT brut FROM payslips s JOIN pay_periods pp ON pp.id=s.period_id WHERE employee_id=? ORDER BY annee DESC, mois DESC LIMIT 6",
                        (emp["id"],)).fetchall()
    theorique = sum(num(emp[k]) for k in ("salaire_base", "sursalaire", "ind_logement", "ind_transport", "ind_fonction", "primes_fixes"))
    moyen = sum(r["brut"] for r in rows) / len(rows) if rows else theorique
    e2 = dict(emp)
    e2["date_sortie"] = date_sortie.isoformat()
    ans = anciennete_ans(e2, date_sortie)
    cg = conge_solde(conn, e2, p, date_sortie)
    ind_conge = round(max(0, cg["solde"]) * moyen / 30.0)
    lic = indemnite_licenciement(ans, moyen, p) if motif in ("Licenciement pour motif personnel", "Licenciement pour motif économique") else 0
    dur, unite = preavis(emp, p)
    ind_preavis = round(moyen * dur) if unite == "mois" else round(moyen / 30.0 * dur)
    return {"anciennete": ans, "salaire_moyen": round(moyen), "nb_bulletins": len(rows), "conge": cg, "ind_conge": ind_conge,
            "ind_licenciement": lic, "preavis": (dur, unite), "ind_preavis": ind_preavis}
