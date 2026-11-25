# -*- coding: utf-8 -*-
"""Tests automatiques : python -m unittest discover -s tests -v"""
import os, sys, tempfile, unittest, datetime as dt, re, threading, urllib.request, urllib.parse, http.cookiejar

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ["ERP_RH_DATA"] = tempfile.mkdtemp(prefix="erp_rh_test_")

from erp import core, schema, entites, rapports, vues, demo  # noqa: E402
from erp import paie as M  # noqa: E402

schema.init_db()
demo.charger()


def P():
    c = core.connect()
    p = core.params(c)
    bar = vues.bareme(c)
    c.close()
    return p, bar


def emp(**k):
    base = dict(id=0, date_embauche="2025-01-01", date_sortie=None, salaire_base=200000, sursalaire=0, ind_logement=30000, ind_transport=15000, ind_fonction=0,
                primes_fixes=0, statut="Employé", nb_charges=2, mode_remuneration="Mensuel")
    base.update(k)
    return base


class Paie(unittest.TestCase):
    def test_bareme_iuts(self):
        _, bar = P()
        self.assertEqual(M.iuts_bareme(30000, bar), 0)
        self.assertAlmostEqual(M.iuts_bareme(50000, bar), 2420)
        self.assertAlmostEqual(M.iuts_bareme(139200, bar), 2420 + 4170 + 6280 + 19200 * 0.184)
        self.assertAlmostEqual(M.iuts_bareme(300000, bar), 2420 + 4170 + 6280 + 9200 + 17360 + 12500)

    def test_bulletin_non_cadre(self):
        p, bar = P()
        b = M.calc_bulletin(emp(), {}, p, bar, 2026, 6)
        self.assertEqual(b["brut"], 245000)
        self.assertEqual(b["cnss_sal"], 13475)             # 5,5 % de 245 000
        self.assertEqual(b["exonerations"], 42250)         # logement 30 000 + transport plafonné à 5 % du brut
        self.assertEqual(b["abattement"], 50000)           # 25 % du salaire de base
        self.assertEqual(b["base_iuts"], 139200)           # arrondi à la centaine inférieure
        self.assertEqual(b["iuts"], 14763)                 # 16 402,8 × (1 – 10 %)
        self.assertEqual(b["net"], 245000 - 13475 - 14763)
        self.assertEqual(b["cnss_pat"], round(245000 * .055) + round(245000 * .07) + round(245000 * .035))
        self.assertEqual(b["tpa"], round((245000 - 42250) * .03))

    def test_plafond_cnss_et_cadre(self):
        p, bar = P()
        b = M.calc_bulletin(emp(salaire_base=1500000, statut="Cadre", nb_charges=0), {}, p, bar, 2026, 6)
        self.assertEqual(b["base_cnss"], p.n("cnss_plafond"))
        self.assertEqual(b["taux_abatt"], 20)

    def test_anciennete_heures_sup_prorata(self):
        p, bar = P()
        e1 = emp(date_embauche="2020-06-01", ind_logement=0, ind_transport=0)
        b = M.calc_bulletin(e1, {"hs15": 10}, p, bar, 2026, 6)     # 6 ans -> 3 % + 3 × 1 % = 6 %
        self.assertEqual(b["taux_anc"], 6)
        th = 200000 / 173.33
        self.assertEqual(b["brut"], round(200000 + 12000 + 10 * th * 1.15))
        b2 = M.calc_bulletin(emp(date_embauche="2026-06-16", ind_logement=0, ind_transport=0), {}, p, bar, 2026, 6)
        self.assertEqual(b2["jours"], 15)
        self.assertEqual(b2["brut"], 100000)
        b3 = M.calc_bulletin(emp(ind_logement=0, ind_transport=0), {"jours_non_payes": 3}, p, bar, 2026, 6)
        self.assertEqual(b3["brut"], 180000)

    def test_indemnite_licenciement(self):
        p, _ = P()
        self.assertEqual(M.indemnite_licenciement(0.5, 100000, p), 0)
        self.assertEqual(M.indemnite_licenciement(12, 100000, p), 25000 * 5 + 30000 * 5 + 40000 * 2)

    def test_conges(self):
        p, _ = P()
        c = core.connect()
        e1 = emp(id=-1, date_embauche="2025-06-01", conge_solde_initial=0, conge_date_reference=None)
        s = M.conge_solde(c, e1, p, dt.date(2026, 6, 1))
        self.assertAlmostEqual(s["acquis"], 30, places=1)   # 12 mois × 2,5 jours
        c.close()


class Securite(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = core.serve("127.0.0.1", 0)
        cls.url = f"http://127.0.0.1:{cls.srv.server_address[1]}"
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def client(self):
        return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def post(self, op, path, **data):
        try:
            return op.open(self.url + path, urllib.parse.urlencode(data).encode())
        except urllib.error.HTTPError as ex:
            return ex

    def login(self, user=demo.DEMO_USER, pwd=demo.DEMO_PWD):
        op = self.client()
        r = self.post(op, "/login", username=user, pwd=pwd)
        html = r.read().decode()
        m = re.search(r'name="_csrf" value="([^"]+)"', html)
        return op, (m.group(1) if m else None), html

    def test_acces_sans_connexion(self):
        r = self.client().open(self.url + "/e/employes")
        self.assertIn("/login", r.geturl())

    def test_mauvais_mot_de_passe(self):
        _, csrf, html = self.login(pwd="mauvais")
        self.assertIsNone(csrf)
        self.assertIn("incorrect", html)

    def test_parcours_et_csrf(self):
        op, csrf, html = self.login()
        self.assertIn("Tableau de bord", html)
        for path in ["/e/employes", "/e/contrats", "/e/conges", "/paie", "/paie/1", "/paie/1/bulletins", "/conformite", "/inspection", "/inspection/dossier",
                     "/rapports", "/employes/1", "/employes/1/solde", "/employes/1/doc/attestation", "/sst", "/admin", "/admin/audit", "/admin/users",
                     "/admin/params/paie", "/admin/bareme", "/e/employes/1", "/e/employes/new", "/e/obligations", "/e/feries"] + [f"/rapports/{k}" for k in rapports.RAPPORTS]:
            self.assertEqual(op.open(self.url + path).status, 200, path)
            self.assertEqual(op.open(self.url + path + "?format=csv").status, 200, path)
        self.assertEqual(self.post(op, "/paie/3/calculer", _csrf="faux").code, 403)          # jeton CSRF invalide
        self.assertEqual(self.post(op, "/paie/3/calculer", _csrf=csrf).status, 200)
        self.assertIn("cl%C3%B4tur", self.post(op, "/paie/1/calculer", _csrf=csrf).geturl())  # période clôturée : refus

    def test_profil_lecture_et_audit(self):
        op, csrf, _ = self.login()
        self.post(op, "/admin/users", _csrf=csrf, action="create", username="insp", fullname="Inspecteur", role="lecture", pwd="Provisoire2026x")
        op2, c2, _ = self.login("insp", "Provisoire2026x")
        r = self.post(op2, "/compte", _csrf=c2, old="Provisoire2026x", pwd="Definitif2026xy", pwd2="Definitif2026xy")
        self.assertEqual(r.status, 200)
        self.assertEqual(op2.open(self.url + "/rapports/registre1").status, 200)
        self.assertEqual(self.post(op2, "/e/employes/1", _csrf=c2, nom="PIRATE").code, 403)   # écriture interdite
        try:
            op2.open(self.url + "/admin/users")
            self.fail("accès admin autorisé à un profil lecture")
        except urllib.error.HTTPError as ex:
            self.assertEqual(ex.code, 403)
        c = core.connect()
        self.assertTrue(core.audit_verify(c)[0])
        c.execute("UPDATE audit SET details='falsifié' WHERE id=3")
        self.assertFalse(core.audit_verify(c)[0])                                             # toute altération est détectée
        c.rollback()
        c.close()

    def test_verrouillage(self):
        op, csrf, _ = self.login()
        self.post(op, "/admin/users", _csrf=csrf, action="create", username="cible", fullname="Cible", role="paie", pwd="Provisoire2026x")
        for _ in range(5):
            self.login("cible", "faux")
        _, _, html = self.login("cible", "Provisoire2026x")
        self.assertIn("verrouillé", html)

    def upload(self, op, csrf, filename, data):
        b = "----frontiereTest"
        body = (f'--{b}\r\nContent-Disposition: form-data; name="_csrf"\r\n\r\n{csrf}\r\n'
                f'--{b}\r\nContent-Disposition: form-data; name="logo"; filename="{filename}"\r\nContent-Type: application/octet-stream\r\n\r\n').encode() + data + f"\r\n--{b}--\r\n".encode()
        rq = urllib.request.Request(self.url + "/admin/logo", body, {"Content-Type": f"multipart/form-data; boundary={b}"})
        return op.open(rq)

    def test_logo(self):
        import base64
        op, csrf, _ = self.login()
        png = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")
        r = self.upload(op, csrf, "logo.png", png)
        self.assertIn("Logo%20enregistr", r.geturl())
        for path in ("/", "/rapports/registre1", "/paie/1/bulletin/1", "/employes/1/doc/attestation"):
            self.assertIn('src="data:image/png;base64,', op.open(self.url + path).read().decode(), path)
        r = self.upload(op, csrf, "faux.png", b"<svg onload=alert(1)></svg>")       # contenu non image refusé
        self.assertIn("Format%20refus", r.geturl())
        r = self.upload(op, csrf, "gros.png", png + b"0" * 600_000)                 # trop lourd refusé
        self.assertIn("trop%20lourd", r.geturl())
        self.assertIn('src="data:image/png;base64,', op.open(self.url + "/admin/logo").read().decode())   # l'ancien logo est conservé
        self.post(op, "/admin/logo", _csrf=csrf, action="supprimer")
        self.assertNotIn('alt="Logo"', op.open(self.url + "/rapports/registre1").read().decode())

    def test_conformite_detecte(self):
        c = core.connect()
        msgs = " | ".join(x[2] for x in rapports.controles(c))
        c.close()
        for attendu in ["aucun numéro d'immatriculation CNSS", "inférieur au SMIG", "aucun contrat de travail", "risque de requalification",
                        "contrat non visé par l'inspection", "permis de travail non renseigné", "fin de période d'essai"]:
            self.assertIn(attendu, msgs)


if __name__ == "__main__":
    unittest.main(verbosity=2)
