# -*- coding: utf-8 -*-
"""Noyau technique : serveur HTTP, routage, sessions, sécurité, audit, sauvegardes.
Aucune dépendance externe (bibliothèque standard Python uniquement)."""
import os, re, io, csv, json, hmac, html, time, glob, hashlib, secrets, sqlite3, threading, traceback
import datetime as dt
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, quote

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.environ.get("ERP_RH_DATA", os.path.join(BASE, "data"))
DB_PATH = os.path.join(DATA_DIR, "erp_rh.db")
BACKUP_DIR = os.path.join(DATA_DIR, "sauvegardes")
WRITE_LOCK = threading.RLock()
PBKDF2_ITER = 310_000
TLS = {"on": False}

ROLES = {
    "admin": "Administrateur (tout, y compris utilisateurs et paramètres)",
    "rh": "Gestionnaire RH (personnel, contrats, congés, paie)",
    "paie": "Gestionnaire de paie (paie + consultation)",
    "lecture": "Consultation seule (direction, auditeur, inspecteur)",
}


# ------------------------------------------------------------------ utilitaires
def e(v):
    return html.escape("" if v is None else str(v), quote=True)


def today():
    return dt.date.today()


def now_iso():
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def d(s):
    """Chaîne ISO -> date (None si vide/invalide)."""
    if not s:
        return None
    if isinstance(s, dt.date):
        return s
    try:
        return dt.date.fromisoformat(str(s)[:10])
    except ValueError:
        return None


def fr(s):
    x = d(s)
    return x.strftime("%d/%m/%Y") if x else ""


def money(n):
    try:
        return f"{round(float(n or 0)):,}".replace(",", " ")
    except (TypeError, ValueError):
        return ""


def num(v, default=0.0):
    try:
        return float(str(v).replace(" ", "").replace(" ", "").replace(",", ".")) if v not in (None, "") else default
    except ValueError:
        return default


MOIS = ["", "janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
        "septembre", "octobre", "novembre", "décembre"]


# ------------------------------------------------------------------ base de données
def connect():
    os.makedirs(DATA_DIR, exist_ok=True)
    c = sqlite3.connect(DB_PATH, timeout=20)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    return c


def get_params(conn, grp=None):
    q = "SELECT key,value FROM params" + (" WHERE grp=?" if grp else "")
    return {r["key"]: r["value"] for r in conn.execute(q, (grp,) if grp else ())}


class P(dict):
    """Paramètres avec accès numérique : p.n('smig_mensuel')."""
    def n(self, k, default=0.0):
        return num(self.get(k), default)


def params(conn):
    return P(get_params(conn))


# ------------------------------------------------------------------ mots de passe
def hash_pwd(pwd, salt=None):
    salt = salt or secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", pwd.encode(), bytes.fromhex(salt), PBKDF2_ITER).hex()
    return h, salt


def check_pwd(pwd, h, salt):
    return hmac.compare_digest(hash_pwd(pwd, salt)[0], h)


def pwd_policy(pwd):
    if len(pwd) < 10:
        return "Le mot de passe doit contenir au moins 10 caractères."
    if not (re.search(r"[A-Za-z]", pwd) and re.search(r"\d", pwd)):
        return "Le mot de passe doit contenir des lettres et des chiffres."
    return None


# ------------------------------------------------------------------ piste d'audit (chaînée)
def audit(conn, user, action, entity="", entity_id="", details=""):
    """Journal inviolable : chaque ligne contient l'empreinte de la précédente."""
    row = conn.execute("SELECT hash FROM audit ORDER BY id DESC LIMIT 1").fetchone()
    prev = row["hash"] if row else "GENESIS"
    ts = now_iso()
    if not isinstance(details, str):
        details = json.dumps(details, ensure_ascii=False, default=str)
    payload = "|".join([prev, ts, str(user), action, entity, str(entity_id), details])
    h = hashlib.sha256(payload.encode()).hexdigest()
    conn.execute("INSERT INTO audit(ts,user,action,entity,entity_id,details,prev_hash,hash) VALUES(?,?,?,?,?,?,?,?)",
                 (ts, str(user), action, entity, str(entity_id), details, prev, h))


def audit_verify(conn):
    prev = "GENESIS"
    n = 0
    for r in conn.execute("SELECT * FROM audit ORDER BY id"):
        payload = "|".join([prev, r["ts"], r["user"], r["action"], r["entity"], r["entity_id"], r["details"]])
        if r["prev_hash"] != prev or hashlib.sha256(payload.encode()).hexdigest() != r["hash"]:
            return False, n, r["id"]
        prev = r["hash"]
        n += 1
    return True, n, None


# ------------------------------------------------------------------ sauvegardes
def backup(reason="manuel"):
    os.makedirs(BACKUP_DIR, exist_ok=True)
    name = os.path.join(BACKUP_DIR, f"erp_rh_{dt.datetime.now():%Y%m%d_%H%M%S}.db")
    src = connect()
    dst = sqlite3.connect(name)
    with dst:
        src.backup(dst)
    dst.close()
    keep = int(num(get_params(src).get("backups_conserves"), 60))
    src.close()
    files = sorted(glob.glob(os.path.join(BACKUP_DIR, "erp_rh_*.db")))
    for f in files[:-keep]:
        os.remove(f)
    return name


def backup_if_needed():
    stamp = f"erp_rh_{dt.date.today():%Y%m%d}_"
    if not glob.glob(os.path.join(BACKUP_DIR, stamp + "*.db")):
        backup("automatique")


# ------------------------------------------------------------------ requête / réponse
class Resp:
    def __init__(self, body="", status=200, ctype="text/html; charset=utf-8", headers=None):
        self.body = body.encode("utf-8") if isinstance(body, str) else body
        self.status, self.ctype, self.headers = status, ctype, headers or []


def redirect(url, msg=None, err=None):
    if msg:
        url += ("&" if "?" in url else "?") + "msg=" + quote(msg)
    if err:
        url += ("&" if "?" in url else "?") + "err=" + quote(err)
    return Resp("", 303, headers=[("Location", url)])


def csv_resp(name, headers, rows):
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";", lineterminator="\r\n")
    w.writerow(headers)
    for r in rows:
        # neutralise les injections de formules dans Excel
        w.writerow([("'" + x) if isinstance(x, str) and x[:1] in "=+-@" and not re.fullmatch(r"-?[\d\s.,]+", x) else x for x in r])
    return Resp(("﻿" + buf.getvalue()).encode("utf-8"), ctype="text/csv; charset=utf-8",
                headers=[("Content-Disposition", f'attachment; filename="{name}.csv"')])


class Req:
    def __init__(self, method, path, query, form, cookies, ip):
        self.method, self.path, self.query, self.form, self.cookies, self.ip = method, path, query, form, cookies, ip
        self.user = None
        self.csrf = ""
        self.db = None

    def q(self, k, default=""):
        return self.query.get(k, default)

    def f(self, k, default=""):
        return self.form.get(k, default).strip()

    @property
    def role(self):
        return self.user["role"] if self.user else None

    def can(self, *roles):
        return self.role in roles

    @property
    def uname(self):
        return self.user["username"] if self.user else "-"


ROUTES = []


def route(pattern, methods=("GET",), roles=None, public=False):
    def deco(fn):
        ROUTES.append((re.compile("^" + pattern + "$"), methods, roles, public, fn))
        return fn
    return deco


class Forbidden(Exception):
    pass


# ------------------------------------------------------------------ sessions
def session_create(conn, user_id, ip):
    token = secrets.token_urlsafe(32)
    csrf = secrets.token_urlsafe(24)
    conn.execute("INSERT INTO sessions(token_hash,user_id,csrf,created_at,last_seen,ip) VALUES(?,?,?,?,?,?)",
                 (hashlib.sha256(token.encode()).hexdigest(), user_id, csrf, time.time(), time.time(), ip))
    return token


def session_load(req):
    tok = req.cookies.get("sid")
    if not tok:
        return
    th = hashlib.sha256(tok.encode()).hexdigest()
    conn = req.db
    s = conn.execute("SELECT * FROM sessions WHERE token_hash=?", (th,)).fetchone()
    if not s:
        return
    idle = num(get_params(conn, "securite").get("session_minutes"), 30) * 60
    if time.time() - s["last_seen"] > idle:
        conn.execute("DELETE FROM sessions WHERE token_hash=?", (th,))
        return
    u = conn.execute("SELECT * FROM users WHERE id=? AND active=1", (s["user_id"],)).fetchone()
    if not u:
        return
    if time.time() - s["last_seen"] > 60:
        conn.execute("UPDATE sessions SET last_seen=? WHERE token_hash=?", (time.time(), th))
    req.user, req.csrf, req.session_hash = u, s["csrf"], th


def cookie_header(token, clear=False):
    v = f"sid={'' if clear else token}; Path=/; HttpOnly; SameSite=Strict"
    if clear:
        v += "; Max-Age=0"
    if TLS["on"]:
        v += "; Secure"
    return ("Set-Cookie", v)


# ------------------------------------------------------------------ mise en page
NAV = [
    ("Tableau de bord", "/", None),
    ("Employés", "/e/employes", None),
    ("Contrats", "/e/contrats", None),
    ("Congés & absences", "/e/conges", None),
    ("Paie", "/paie", None),
    ("Discipline", "/e/sanctions", ("admin", "rh", "lecture")),
    ("Santé & sécurité", "/sst", None),
    ("Formation", "/e/formations", None),
    ("Représentants du personnel", "/e/representants", None),
    ("Conformité", "/conformite", None),
    ("Dossier Inspection", "/inspection", None),
    ("Rapports", "/rapports", None),
    ("Paramètres", "/admin", ("admin",)),
]

CSS = """
*{box-sizing:border-box}body{margin:0;font:14px/1.45 system-ui,'Segoe UI',Roboto,Arial,sans-serif;color:#1c2530;background:#f3f5f7}
a{color:#0b5c8a;text-decoration:none}a:hover{text-decoration:underline}
.side{position:fixed;top:0;left:0;bottom:0;width:230px;background:#12303f;color:#dfe9ee;overflow:auto;padding:14px 0}
.side h1{font-size:16px;margin:0 16px 4px;color:#fff}.side small{display:block;margin:0 16px 12px;color:#9db7c4}
.side a{display:block;padding:8px 16px;color:#dfe9ee}.side a:hover,.side a.on{background:#1d4a61;text-decoration:none;color:#fff}
.main{margin-left:230px;padding:18px 26px 60px}.top{display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;color:#566}
h2{margin:4px 0 14px;font-size:22px}h3{margin:22px 0 8px;font-size:16px;border-bottom:2px solid #d6dde3;padding-bottom:4px}
table{border-collapse:collapse;width:100%;background:#fff;margin:6px 0 14px}th,td{border:1px solid #d6dde3;padding:5px 8px;text-align:left;vertical-align:top}
th{background:#e8eef2;font-weight:600;font-size:13px}td.r,th.r{text-align:right;white-space:nowrap}tr:nth-child(even) td{background:#fafbfc}
.card{background:#fff;border:1px solid #d6dde3;border-radius:6px;padding:14px 16px;margin-bottom:14px}
.kpis{display:flex;flex-wrap:wrap;gap:12px;margin-bottom:14px}.kpi{background:#fff;border:1px solid #d6dde3;border-radius:6px;padding:10px 16px;min-width:150px}
.kpi b{display:block;font-size:22px}.kpi span{color:#566;font-size:12px}
.btn,button{display:inline-block;background:#0b5c8a;color:#fff;border:0;border-radius:4px;padding:7px 13px;font-size:14px;cursor:pointer;margin:2px 4px 2px 0}
.btn:hover,button:hover{background:#094a70;text-decoration:none}.btn.g{background:#5d6b76}.btn.d,button.d{background:#a32828}.btn.ok,button.ok{background:#1f7a45}
form.inline{display:inline}label{display:block;font-weight:600;font-size:13px;margin-bottom:2px}
input,select,textarea{width:100%;padding:6px 8px;border:1px solid #b9c4cc;border-radius:4px;font:inherit;background:#fff}
textarea{min-height:70px}.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:10px 16px}
.help{font-size:12px;color:#667;font-weight:400}.msg{background:#e3f4e8;border:1px solid #9fd2af;padding:8px 12px;border-radius:4px;margin-bottom:12px}
.err{background:#fbe6e6;border:1px solid #e0a3a3;padding:8px 12px;border-radius:4px;margin-bottom:12px}
.tag{display:inline-block;padding:1px 8px;border-radius:10px;font-size:12px;font-weight:600;white-space:nowrap}
.tag.critique{background:#f6d0d0;color:#7c1414}.tag.important{background:#fde7c2;color:#7a4a00}.tag.info{background:#dbe9f5;color:#184a73}.tag.ok{background:#d3efdc;color:#145c30}
.muted{color:#667}.login{max-width:380px;margin:9vh auto;background:#fff;padding:26px;border-radius:8px;border:1px solid #d6dde3}
.doc{background:#fff;padding:26px 34px;border:1px solid #d6dde3;max-width:900px}.doc h2{text-align:center}.pb{page-break-after:always}
.two{display:grid;grid-template-columns:1fr 1fr;gap:16px}.sm{font-size:12px}
@media print{.side,.top,.noprint,.msg,.err{display:none!important}.main{margin:0;padding:0}body{background:#fff;font-size:11.5px}
.doc,.card{border:0;padding:0;max-width:none}th,td{padding:3px 5px}a{color:inherit}}
@media(max-width:800px){.side{position:static;width:auto}.main{margin:0;padding:12px}.two{grid-template-columns:1fr}}
"""


def page(req, title, body, wide=False):
    msg = f'<div class="msg">{e(req.q("msg"))}</div>' if req.q("msg") else ""
    err = f'<div class="err">{e(req.q("err"))}</div>' if req.q("err") else ""
    if not req.user:
        return Resp(f'<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
                    f'<title>{e(title)} – ERP RH</title><style>{CSS}</style></head><body><div class="login">{msg}{err}{body}</div></body></html>')
    ent = get_params(req.db, "entreprise").get("raison_sociale") or "Mon entreprise"
    nav = ""
    for label, href, roles in NAV:
        if roles and req.role not in roles:
            continue
        on = req.path == href or (href != "/" and req.path.startswith(href))
        nav += f'<a href="{href}"{" class=on" if on else ""}>{e(label)}</a>'
    return Resp(
        f'<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<title>{e(title)} – ERP RH</title><style>{CSS}</style></head><body>'
        f'<div class="side"><h1>ERP RH Burkina</h1><small>{e(ent)}</small>{nav}</div>'
        f'<div class="main"><div class="top"><span>{e(req.user["fullname"])} · <span class="tag info">{e(req.role)}</span></span>'
        f'<span><a href="/compte">Mon compte</a> &nbsp; <form class="inline" method="post" action="/logout">{csrf_field(req)}'
        f'<button class="g" style="padding:3px 9px">Déconnexion</button></form></span></div>'
        f'{msg}{err}<h2>{e(title)}</h2>{body}</div></body></html>')


def csrf_field(req):
    return f'<input type="hidden" name="_csrf" value="{e(req.csrf)}">'


def table(headers, rows, right=(), raw=()):
    """rows : listes de valeurs. `right` : index alignés à droite ; `raw` : index HTML non échappé."""
    h = "".join(f'<th class="{"r" if i in right else ""}">{e(x)}</th>' for i, x in enumerate(headers))
    out = [f"<table><tr>{h}</tr>"]
    for r in rows:
        out.append("<tr>" + "".join(
            f'<td class="{"r" if i in right else ""}">{(x if i in raw else e(x))}</td>' for i, x in enumerate(r)) + "</tr>")
    if not rows:
        out.append(f'<tr><td colspan="{len(headers)}" class="muted">Aucun enregistrement.</td></tr>')
    out.append("</table>")
    return "".join(out)


def post_btn(req, action, label, cls="", fields=None):
    hid = "".join(f'<input type="hidden" name="{e(k)}" value="{e(v)}">' for k, v in (fields or {}).items())
    return f'<form class="inline" method="post" action="{e(action)}">{csrf_field(req)}{hid}<button class="{cls}">{e(label)}</button></form>'


# ------------------------------------------------------------------ serveur
SEC_HEADERS = [
    ("X-Content-Type-Options", "nosniff"), ("X-Frame-Options", "DENY"), ("Referrer-Policy", "no-referrer"),
    ("Cache-Control", "no-store"),
    ("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'; img-src 'self' data:; form-action 'self'; frame-ancestors 'none'; base-uri 'none'"),
]


class Handler(BaseHTTPRequestHandler):
    server_version = "ERPRH"
    sys_version = ""

    def log_message(self, *a):
        pass

    def do_GET(self):
        self.handle_req("GET")

    def do_POST(self):
        self.handle_req("POST")

    def handle_req(self, method):
        try:
            u = urlparse(self.path)
            query = {k: v[-1] for k, v in parse_qs(u.query).items()}
            form = {}
            if method == "POST":
                n = int(self.headers.get("Content-Length") or 0)
                if n > 2_000_000:
                    return self.send(Resp("Requête trop volumineuse", 413))
                form = {k: v[-1] for k, v in parse_qs(self.rfile.read(n).decode("utf-8", "replace"), keep_blank_values=True).items()}
            cookies = {}
            for part in (self.headers.get("Cookie") or "").split(";"):
                if "=" in part:
                    k, v = part.strip().split("=", 1)
                    cookies[k] = v
            req = Req(method, u.path, query, form, cookies, self.client_address[0])
            if method == "POST":
                with WRITE_LOCK:
                    resp = self.dispatch(req)
            else:
                resp = self.dispatch(req)
        except Exception:
            traceback.print_exc()
            resp = Resp("<h1>Erreur interne</h1><p>L'opération a été annulée ; aucune donnée n'a été modifiée. Consultez la console du serveur.</p>", 500)
        self.send(resp)

    def dispatch(self, req):
        req.db = connect()
        try:
            session_load(req)
            nb_users = req.db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            if nb_users == 0 and req.path != "/setup":
                return redirect("/setup")
            for rx, methods, roles, public, fn in ROUTES:
                m = rx.match(req.path)
                if not m or req.method not in methods:
                    continue
                if not public:
                    if not req.user:
                        return redirect("/login")
                    if roles and req.role not in roles:
                        raise Forbidden()
                    if req.method == "POST":
                        if not hmac.compare_digest(req.form.get("_csrf", ""), req.csrf):
                            raise Forbidden()
                        if req.role == "lecture" and req.path not in ("/logout", "/compte"):
                            raise Forbidden()
                    if req.user["must_change"] and req.path not in ("/compte", "/logout"):
                        return redirect("/compte", err="Vous devez définir un nouveau mot de passe.")
                resp = fn(req, *m.groups())
                req.db.commit()
                return resp
            return Resp(page(req, "Page introuvable", "<p>Cette page n'existe pas.</p>").body, 404) if req.user else redirect("/login")
        except Forbidden:
            req.db.rollback()
            if req.user:
                audit(req.db, req.uname, "ACCES_REFUSE", "route", req.path, req.method)
                req.db.commit()
            return Resp("<h1>Accès refusé</h1><p>Votre profil ne permet pas cette opération. <a href='/'>Retour</a></p>", 403)
        except Exception:
            req.db.rollback()
            raise
        finally:
            req.db.close()

    def send(self, resp):
        self.send_response(resp.status)
        self.send_header("Content-Type", resp.ctype)
        self.send_header("Content-Length", str(len(resp.body)))
        for k, v in SEC_HEADERS + resp.headers:
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(resp.body)


def serve(host, port, cert=None, key=None):
    srv = ThreadingHTTPServer((host, port), Handler)
    srv.daemon_threads = True
    if cert and key:
        import ssl
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        ctx.load_cert_chain(cert, key)
        srv.socket = ctx.wrap_socket(srv.socket, server_side=True)
        TLS["on"] = True
    return srv
