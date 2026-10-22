"""Sistema simples de gestão de almoxarifado - Flask + SQLite.
Rodar:  pip install flask   |   python app.py   |   abrir http://localhost:5000
"""
import csv, io, sqlite3
from datetime import date
from flask import Flask, g, redirect, render_template_string, request, Response, flash, url_for

DB = "almoxarifado.db"
DIAS_PARADO = 180  # item sem movimento há mais que isso aparece como "parado"
POR_PAGINA = 100

app = Flask(__name__)
app.secret_key = "troque-esta-chave"

SCHEMA = """
CREATE TABLE IF NOT EXISTS itens(
  id INTEGER PRIMARY KEY, codigo TEXT UNIQUE NOT NULL, descricao TEXT NOT NULL,
  categoria TEXT DEFAULT '', unidade TEXT DEFAULT 'un', localizacao TEXT DEFAULT '',
  estoque_minimo REAL DEFAULT 0, cor TEXT DEFAULT '#00A859', ativo INTEGER DEFAULT 1);
CREATE TABLE IF NOT EXISTS movimentos(
  id INTEGER PRIMARY KEY, item_id INTEGER NOT NULL REFERENCES itens(id),
  tipo TEXT NOT NULL CHECK(tipo IN ('ENTRADA','SAIDA','AJUSTE')),
  quantidade REAL NOT NULL, data TEXT NOT NULL, responsavel TEXT DEFAULT '',
  referencia TEXT DEFAULT '', obs TEXT DEFAULT '');
CREATE INDEX IF NOT EXISTS ix_mov_item ON movimentos(item_id, data);
CREATE INDEX IF NOT EXISTS ix_itens_desc ON itens(descricao);
"""
SALDO = "COALESCE(SUM(CASE m.tipo WHEN 'SAIDA' THEN -m.quantidade ELSE m.quantidade END),0)"


def db():
    if "db" not in g:
        g.db = sqlite3.connect(DB)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys=ON")
    return g.db


@app.teardown_appcontext
def close(_):
    d = g.pop("db", None)
    if d:
        d.close()


def init():
    c = sqlite3.connect(DB)
    c.execute("PRAGMA journal_mode=WAL")
    c.executescript(SCHEMA)
    # Adiciona a coluna 'cor' caso o banco já existisse antes
    try:
        c.execute("ALTER TABLE itens ADD COLUMN cor TEXT DEFAULT '#00A859'")
    except sqlite3.OperationalError:
        pass  # Coluna já existe
    c.commit()
    c.close()


BASE = """<!doctype html><html lang="pt-br"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Maxmill - Almoxarifado</title>
<style>
:root {
  --primary-color: #00A859;
  --primary-dark: #007A40;
  --bg-color: #f0f2f5;
  --text-color: #333333;
}
body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 0; background: var(--bg-color); color: var(--text-color); }
nav { background: #ffffff; border-bottom: 3px solid var(--primary-color); padding: 12px 24px; display: flex; align-items: center; justify-content: space-between; box-shadow: 0 2px 5px rgba(0,0,0,0.05); }
.nav-brand { display: flex; align-items: center; gap: 12px; text-decoration: none; color: var(--primary-dark); font-weight: bold; font-size: 18px; }
.nav-brand img { height: 42px; object-fit: contain; }
.nav-links { display: flex; gap: 15px; flex-wrap: wrap; }
.nav-links a { color: #444; text-decoration: none; font-weight: 600; padding: 8px 12px; border-radius: 4px; transition: all 0.2s; }
.nav-links a:hover { background: #e8f5e9; color: var(--primary-dark); }
main { max-width: 1200px; margin: 25px auto; padding: 0 16px; }
h2, h3 { color: var(--primary-dark); margin-top: 0; }
table { width: 100%; border-collapse: collapse; background: #fff; border-radius: 6px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
th, td { padding: 10px 12px; border-bottom: 1px solid #eef0f2; text-align: left; font-size: 14px; }
th { background: #f8faf9; color: var(--primary-dark); font-weight: 600; }
input, select, textarea { padding: 9px 12px; margin: 4px 0 12px 0; width: 100%; box-sizing: border-box; border: 1px solid #ccc; border-radius: 4px; font-size: 14px; }
input[type="color"] { padding: 2px; height: 38px; cursor: pointer; }
input:focus, select:focus, textarea:focus { border-color: var(--primary-color); outline: none; box-shadow: 0 0 0 2px rgba(0,168,89,0.2); }
label { font-size: 13px; font-weight: 600; color: #555; }
.row { display: flex; gap: 12px; flex-wrap: wrap; }
.row > * { flex: 1; min-width: 160px; }
button, .btn { background: var(--primary-color); color: #fff; border: 0; padding: 10px 18px; border-radius: 4px; cursor: pointer; text-decoration: none; display: inline-block; font-size: 14px; font-weight: 600; transition: background 0.2s, transform 0.1s; }
button:hover, .btn:hover { background: var(--primary-dark); }
.card { background: #fff; padding: 20px; border-radius: 8px; margin-bottom: 18px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); border-top: 3px solid var(--primary-color); }
.baixo { background: #ffebee; }
.parado { background: #fff8e1; }
.badge-cat { display: inline-block; padding: 4px 10px; border-radius: 12px; color: #fff; font-weight: 600; font-size: 12px; text-shadow: 0 1px 1px rgba(0,0,0,0.2); }
.msg { background: #e8f5e9; color: var(--primary-dark); padding: 12px; border-radius: 4px; margin-bottom: 15px; border-left: 4px solid var(--primary-color); }
.err { background: #ffebee; color: #c62828; border-left-color: #d32f2f; }
.muted { color: #666; font-size: 13px; }
</style></head><body>
<nav>
  <a href="/" class="nav-brand">
    <img src="/static/logo.png" alt="Maxmill" onerror="this.style.display='none'">
    <span>MAXMILL - Gestão de Almoxarifado</span>
  </a>
  <div class="nav-links">
    <a href="/">Estoque</a>
    <a href="/mov">Nova Movimentação</a>
    <a href="/item/novo">Novo Item</a>
    <a href="/historico">Histórico</a>
    <a href="/exportar.csv">Exportar CSV</a>
  </div>
</nav>
<main>{% for cat,m in msgs %}<div class="msg {{'err' if cat=='erro'}}">{{m}}</div>{% endfor %}{{ body|safe }}</main>
</body></html>"""


def page(tpl, **ctx):
    from flask import get_flashed_messages
    body = render_template_string(tpl, **ctx)
    return render_template_string(BASE, body=body, msgs=get_flashed_messages(with_categories=True))


def num(v):
    return float(str(v).replace(",", ".") or 0)


@app.route("/")
def estoque():
    q = request.args.get("q", "").strip()
    f = request.args.get("f", "")
    pg = max(int(request.args.get("p", 1)), 1)
    like = f"%{q}%"
    having = {"baixo": "HAVING i.estoque_minimo>0 AND saldo<i.estoque_minimo",
              "parado": f"HAVING ultima IS NULL OR ultima < date('now','-{DIAS_PARADO} days')",
              "zerado": "HAVING saldo<=0"}.get(f, "")
    sql = f"""SELECT i.*, {SALDO} saldo, MAX(m.data) ultima FROM itens i
      LEFT JOIN movimentos m ON m.item_id=i.id WHERE i.ativo=1 AND
      (i.codigo LIKE ? OR i.descricao LIKE ? OR i.categoria LIKE ? OR i.localizacao LIKE ?)
      GROUP BY i.id {having} ORDER BY i.descricao LIMIT {POR_PAGINA+1} OFFSET {(pg-1)*POR_PAGINA}"""
    rows = db().execute(sql, (like,) * 4).fetchall()
    mais = len(rows) > POR_PAGINA
    return page("""
<div class="card"><form class="row" method="get" style="align-items: flex-end;">
<div style="flex:3"><label>Buscar</label><input name="q" value="{{q}}" placeholder="Buscar código, descrição, categoria ou local"></div>
<div><label>Filtro</label><select name="f"><option value="">Todos</option>
<option value="baixo" {{'selected' if f=='baixo'}}>Abaixo do mínimo</option>
<option value="parado" {{'selected' if f=='parado'}}>Parados (+{{dias}} dias)</option>
<option value="zerado" {{'selected' if f=='zerado'}}>Zerados</option></select></div>
<div style="flex:0"><button style="margin-bottom:12px;">Filtrar</button></div></form></div>
<table><tr><th>Código</th><th>Descrição</th><th>Categoria</th><th>Local</th><th>Saldo</th><th>Mín.</th><th>Últ. mov.</th><th>Ações</th></tr>
{% for r in rows[:per] %}
<tr class="{{'baixo' if r.estoque_minimo>0 and r.saldo<r.estoque_minimo else ('parado' if (not r.ultima or r.ultima < limite) else '')}}">
<td><b>{{r.codigo}}</b></td><td>{{r.descricao}}</td>
<td>{% if r.categoria %}<span class="badge-cat" style="background-color: {{r.cor or '#00A859'}};">{{r.categoria}}</span>{% else %}—{% endif %}</td>
<td>{{r.localizacao}}</td>
<td><b>{{'%g'|format(r.saldo)}}</b> {{r.unidade}}</td><td>{{'%g'|format(r.estoque_minimo)}}</td>
<td>{{r.ultima or '—'}}</td><td><a href="/item/{{r.id}}">Abrir</a> · <a href="/mov?codigo={{r.codigo}}">Movimentar</a></td></tr>
{% else %}<tr><td colspan=8>Nenhum item encontrado.</td></tr>{% endfor %}</table>
<p class="muted">Vermelho suave = abaixo do mínimo · Amarelo suave = sem movimento há mais de {{dias}} dias.</p>
{% if pg>1 %}<a class="btn" href="?q={{q}}&f={{f}}&p={{pg-1}}">← Anterior</a>{% endif %}
{% if mais %}<a class="btn" href="?q={{q}}&f={{f}}&p={{pg+1}}">Próxima →</a>{% endif %}""",
        rows=rows, q=q, f=f, pg=pg, mais=mais, per=POR_PAGINA, dias=DIAS_PARADO,
        limite=db().execute(f"SELECT date('now','-{DIAS_PARADO} days')").fetchone()[0])


FORM_ITEM = """
<div class="card"><h2>{{titulo}}</h2><form method="post">
<div class="row"><label>Código*<input name="codigo" required value="{{i.codigo}}"></label>
<label>Unidade<input name="unidade" value="{{i.unidade}}"></label>
<label>Estoque mínimo<input name="estoque_minimo" value="{{'%g'|format(i.estoque_minimo)}}"></label></div>
<label>Descrição*<input name="descricao" required value="{{i.descricao}}"></label>
<div class="row">
<label style="flex: 3;">Categoria<input name="categoria" value="{{i.categoria}}" list="cats"></label>
<label style="flex: 1;">Cor da Categoria<input type="color" name="cor" value="{{i.cor or '#00A859'}}"></label>
<label style="flex: 3;">Localização (corredor/prateleira)<input name="localizacao" value="{{i.localizacao}}"></label>
</div>
<datalist id="cats">{% for c in cats %}<option value="{{c}}">{% endfor %}</datalist>
<button>Salvar</button></form></div>"""


def cats():
    return [r[0] for r in db().execute("SELECT DISTINCT categoria FROM itens WHERE categoria<>'' ORDER BY 1")]


def ler_item(f):
    return (f["codigo"].strip(), f["descricao"].strip(), f["categoria"].strip(),
            f["unidade"].strip() or "un", f["localizacao"].strip(), num(f["estoque_minimo"]),
            f.get("cor", "#00A859").strip())


@app.route("/item/novo", methods=["GET", "POST"])
def item_novo():
    if request.method == "POST":
        try:
            db().execute("INSERT INTO itens(codigo,descricao,categoria,unidade,localizacao,estoque_minimo,cor) VALUES(?,?,?,?,?,?,?)",
                         ler_item(request.form))
            db().commit()
            flash("Item cadastrado.")
            return redirect("/")
        except sqlite3.IntegrityError:
            flash("Já existe um item com esse código.", "erro")
    vazio = dict(codigo="", descricao="", categoria="", unidade="un", localizacao="", estoque_minimo=0, cor="#00A859")
    return page(FORM_ITEM, titulo="Novo Item", i=vazio, cats=cats())


@app.route("/item/<int:id>", methods=["GET", "POST"])
def item(id):
    i = db().execute("SELECT * FROM itens WHERE id=?", (id,)).fetchone()
    if not i:
        return redirect("/")
    if request.method == "POST":
        try:
            db().execute("UPDATE itens SET codigo=?,descricao=?,categoria=?,unidade=?,localizacao=?,estoque_minimo=?,cor=? WHERE id=?",
                         ler_item(request.form) + (id,))
            db().commit()
            flash("Item atualizado.")
            return redirect(f"/item/{id}")
        except sqlite3.IntegrityError:
            flash("Já existe outro item com esse código.", "erro")
    hist = db().execute("SELECT * FROM movimentos WHERE item_id=? ORDER BY data DESC, id DESC LIMIT 200", (id,)).fetchall()
    saldo = db().execute(f"SELECT {SALDO} FROM movimentos m WHERE item_id=?", (id,)).fetchone()[0]
    return page(FORM_ITEM + """<div class="card"><h3>Saldo atual: {{'%g'|format(saldo)}} {{i.unidade}}</h3>
<a class="btn" href="/mov?codigo={{i.codigo}}">Movimentar</a></div>
<table><tr><th>Data</th><th>Tipo</th><th>Qtd</th><th>Responsável</th><th>OS / Projeto</th><th>Obs.</th></tr>
{% for m in hist %}<tr><td>{{m.data}}</td><td>{{m.tipo}}</td><td>{{'%g'|format(m.quantidade)}}</td>
<td>{{m.responsavel}}</td><td>{{m.referencia}}</td><td>{{m.obs}}</td></tr>{% endfor %}</table>""",
                titulo=f"Item {i['codigo']}", i=i, cats=cats(), hist=hist, saldo=saldo)


@app.route("/mov", methods=["GET", "POST"])
def mov():
    if request.method == "POST":
        f = request.form
        it = db().execute("SELECT id FROM itens WHERE codigo=? AND ativo=1", (f["codigo"].strip(),)).fetchone()
        q = num(f["quantidade"])
        if not it:
            flash("Código não encontrado.", "erro")
        elif q == 0 or (f["tipo"] != "AJUSTE" and q < 0):
            flash("Quantidade inválida.", "erro")
        else:
            saldo = db().execute(f"SELECT {SALDO} FROM movimentos m WHERE item_id=?", (it["id"],)).fetchone()[0]
            if f["tipo"] == "SAIDA" and q > saldo:
                flash(f"Saldo insuficiente (disponível: {saldo:g}).", "erro")
            else:
                db().execute("INSERT INTO movimentos(item_id,tipo,quantidade,data,responsavel,referencia,obs) VALUES(?,?,?,?,?,?,?)",
                             (it["id"], f["tipo"], q, f["data"] or str(date.today()), f["responsavel"].strip(),
                              f["referencia"].strip(), f["obs"].strip()))
                db().commit()
                flash("Movimentação registrada.")
                return redirect("/mov")
    codigos = db().execute("SELECT codigo, descricao FROM itens WHERE ativo=1 ORDER BY codigo").fetchall()
    return page("""<div class="card"><h2>Nova Movimentação</h2><form method="post">
<div class="row"><label>Código do item*<input name="codigo" list="cods" required value="{{cod}}" autofocus></label>
<label>Tipo<select name="tipo"><option value="SAIDA">Saída</option><option value="ENTRADA">Entrada</option>
<option value="AJUSTE">Ajuste de inventário (+/-)</option></select></label>
<label>Quantidade*<input name="quantidade" required></label>
<label>Data<input type="date" name="data" value="{{hoje}}"></label></div>
<div class="row"><label>Responsável<input name="responsavel"></label>
<label>OS / Projeto / NF<input name="referencia"></label></div>
<label>Observação<input name="obs"></label>
<datalist id="cods">{% for c in codigos %}<option value="{{c.codigo}}">{{c.descricao}}</option>{% endfor %}</datalist>
<button>Registrar</button></form></div>""",
                cod=request.args.get("codigo", ""), hoje=date.today(), codigos=codigos)


@app.route("/historico")
def historico():
    rows = db().execute("""SELECT m.*, i.codigo, i.descricao FROM movimentos m JOIN itens i ON i.id=m.item_id
                           ORDER BY m.data DESC, m.id DESC LIMIT 300""").fetchall()
    return page("""<h2>Últimas Movimentações</h2><table><tr><th>Data</th><th>Item</th><th>Tipo</th><th>Qtd</th>
<th>Responsável</th><th>OS / Projeto</th></tr>{% for m in rows %}<tr><td>{{m.data}}</td>
<td><b>{{m.codigo}}</b> - {{m.descricao}}</td><td>{{m.tipo}}</td><td>{{'%g'|format(m.quantidade)}}</td>
<td>{{m.responsavel}}</td><td>{{m.referencia}}</td></tr>{% endfor %}</table>""", rows=rows)


@app.route("/exportar.csv")
def exportar():
    rows = db().execute(f"""SELECT i.codigo,i.descricao,i.categoria,i.unidade,i.localizacao,i.estoque_minimo,
        {SALDO} saldo, MAX(m.data) ultima FROM itens i LEFT JOIN movimentos m ON m.item_id=i.id
        WHERE i.ativo=1 GROUP BY i.id ORDER BY i.descricao""").fetchall()
    out = io.StringIO()
    w = csv.writer(out, delimiter=";")
    w.writerow(["Código", "Descrição", "Categoria", "Unidade", "Localização", "Estoque mínimo", "Saldo", "Última movimentação"])
    w.writerows([list(r) for r in rows])
    return Response("\ufeff" + out.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=estoque.csv"})


if __name__ == "__main__":
    init()
    app.run(host="0.0.0.0", port=5000, threaded=True)
