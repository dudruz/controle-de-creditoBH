from flask import Flask, render_template, request, redirect, send_file
import sqlite3
import os
import openpyxl
from io import BytesIO
from datetime import datetime

app = Flask(__name__)
DATABASE = "controle.db"

def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    if not os.path.exists(DATABASE):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.executescript('''
            CREATE TABLE config (creditos INTEGER, alerta INTEGER);
            INSERT INTO config (creditos, alerta) VALUES (1000, 100);

            CREATE TABLE lancamentos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                data TEXT,
                quantidade INTEGER,
                responsavel TEXT,
                observacoes TEXT,
                empresa TEXT
            );

            CREATE TABLE creditos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                empresa TEXT,
                quantidade INTEGER,
                data TEXT
            );
        ''')
        conn.commit()
        conn.close()

@app.route("/")
def home():
    return redirect("/lancamentos")

@app.route("/lancamentos", methods=["GET", "POST"])
def lancamentos():
    conn = get_db_connection()
    empresas = conn.execute("SELECT DISTINCT empresa FROM creditos").fetchall()
    empresa_selecionada = request.args.get("empresa")

    if request.method == "POST":
        data = request.form["data"]
        quantidade = int(request.form["quantidade"])
        responsavel = request.form["responsavel"]
        observacoes = request.form["observacoes"]
        empresa = request.form["empresa"]
        conn.execute(
            "INSERT INTO lancamentos (data, quantidade, responsavel, observacoes, empresa) VALUES (?, ?, ?, ?, ?)",
            (data, quantidade, responsavel, observacoes, empresa)
        )
        conn.commit()
        return redirect(f"/lancamentos?empresa={empresa}")

    lancamentos = []
    dashboard = None

    if empresa_selecionada:
        total_creditos = conn.execute("SELECT COALESCE(SUM(quantidade), 0) FROM creditos WHERE empresa = ?", (empresa_selecionada,)).fetchone()[0]
        total_utilizados = conn.execute("SELECT COALESCE(SUM(quantidade), 0) FROM lancamentos WHERE empresa = ?", (empresa_selecionada,)).fetchone()[0]
        saldo = total_creditos - total_utilizados
        alerta = saldo < 100
        dashboard = {
            "empresa": empresa_selecionada,
            "creditos": total_creditos,
            "utilizados": total_utilizados,
            "saldo": saldo,
            "alerta": alerta
        }
        lancamentos = conn.execute("SELECT * FROM lancamentos WHERE empresa = ? ORDER BY data DESC", (empresa_selecionada,)).fetchall()

    conn.close()
    return render_template("lancamentos.html", empresas=empresas, empresa_selecionada=empresa_selecionada, dashboard=dashboard, lancamentos=lancamentos)

@app.route("/creditos", methods=["GET", "POST"])
def creditos():
    conn = get_db_connection()

    if request.method == "POST":
        empresa = request.form.get("empresa")
        quantidade = request.form.get("quantidade")

        if not empresa or not quantidade:
            conn.close()
            return "Empresa e quantidade são obrigatórios.", 400

        try:
            quantidade = int(quantidade)
        except ValueError:
            conn.close()
            return "Quantidade deve ser um número inteiro.", 400

        conn.execute("INSERT INTO creditos (empresa, quantidade, data) VALUES (?, ?, DATE('now'))", (empresa, quantidade))
        conn.commit()
        return redirect("/creditos")

    creditos = conn.execute("SELECT empresa, SUM(quantidade) as quantidade FROM creditos GROUP BY empresa").fetchall()
    conn.close()
    return render_template("creditos.html", creditos=creditos)

@app.route("/configuracoes", methods=["GET", "POST"])
def configuracoes():
    conn = get_db_connection()
    if request.method == "POST":
        creditos = int(request.form["creditos"])
        alerta = int(request.form["alerta"])
        conn.execute("DELETE FROM config")
        conn.execute("INSERT INTO config (creditos, alerta) VALUES (?, ?)", (creditos, alerta))
        conn.commit()
    config = conn.execute("SELECT creditos, alerta FROM config").fetchone()
    conn.close()
    return render_template("configuracoes.html", config=config)

@app.route("/exportar_creditos/<empresa>")
def exportar_creditos(empresa):
    conn = get_db_connection()
    lancamentos = conn.execute(
        "SELECT data, quantidade, responsavel, observacoes FROM lancamentos WHERE empresa = ? ORDER BY data ASC",
        (empresa,)
    ).fetchall()

    total_comprado = conn.execute(
        "SELECT COALESCE(SUM(quantidade),0) FROM creditos WHERE empresa = ?",
        (empresa,)
    ).fetchone()[0]

    total_utilizado = conn.execute(
        "SELECT COALESCE(SUM(quantidade),0) FROM lancamentos WHERE empresa = ?",
        (empresa,)
    ).fetchone()[0]

    saldo = total_comprado - total_utilizado

    conn.close()

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Resumo Créditos"

    # Cabeçalhos da planilha
    ws.append([f"Empresa: {empresa}"])
    ws.append([f"Total Comprado", total_comprado])
    ws.append([f"Total Utilizado", total_utilizado])
    ws.append([f"Saldo Atual", saldo])

    # Calcular tempo entre primeiro lançamento e último
    if lancamentos:
        data_inicio = datetime.strptime(lancamentos[0]["data"], "%Y-%m-%d")
        data_fim = datetime.strptime(lancamentos[-1]["data"], "%Y-%m-%d")
        dias_para_finalizar = (data_fim - data_inicio).days
    else:
        dias_para_finalizar = 0
    ws.append([f"Dias entre 1º lançamento e último", dias_para_finalizar])

    # Espaço
    ws.append([])
    ws.append(["Detalhes dos Lançamentos"])
    ws.append(["Data", "Quantidade Usada", "Responsável", "Observações"])

    # Ajustar largura colunas
    ws.column_dimensions['A'].width = 15
    ws.column_dimensions['B'].width = 18
    ws.column_dimensions['C'].width = 25
    ws.column_dimensions['D'].width = 40

    for row in lancamentos:
        ws.append([row["data"], row["quantidade"], row["responsavel"], row["observacoes"]])

    output = BytesIO()
    wb.save(output)
    output.seek(0)

    filename = f"lancamentos_{empresa}.xlsx"

    return send_file(
        output,
        as_attachment=True,
        download_name=filename,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

if __name__ == "__main__":
    init_db()
    app.run(debug=True)
