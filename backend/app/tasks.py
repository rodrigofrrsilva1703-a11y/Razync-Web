from __future__ import annotations

import os
import sqlite3
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

from razync.company_catalog import EMPRESAS
from razync.task_center import classificar_tarefa, ordenar_tarefas, resumir_tarefas
from razync.task_deadlines import calcular_prioridade_empresa, obter_competencia_operacional

DB_PATH = Path(os.getenv("RAZYNC_DB_PATH", "/data/razync.db"))


def _db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.executescript("""
    CREATE TABLE IF NOT EXISTS manual_tasks(
      id TEXT PRIMARY KEY,
      titulo TEXT NOT NULL,
      descricao TEXT,
      codigo_empresa TEXT,
      categoria TEXT,
      prioridade TEXT,
      prazo TEXT,
      status TEXT NOT NULL DEFAULT 'Pendente',
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS company_task_status(
      codigo_empresa TEXT NOT NULL,
      competencia TEXT NOT NULL,
      concluida INTEGER NOT NULL DEFAULT 0,
      updated_at TEXT NOT NULL,
      PRIMARY KEY(codigo_empresa, competencia)
    );
    """)
    return con


def _manual_rows():
    con = _db()
    try:
        rows = [dict(r) for r in con.execute("SELECT * FROM manual_tasks").fetchall()]
        return rows
    finally:
        con.close()


def _statuses(competencia: str):
    con = _db()
    try:
        rows = con.execute(
            "SELECT codigo_empresa, concluida FROM company_task_status WHERE competencia=?",
            (competencia,),
        ).fetchall()
        return {str(r["codigo_empresa"]): {"concluida": bool(r["concluida"])} for r in rows}
    finally:
        con.close()


def dashboard():
    hoje, competencia = obter_competencia_operacional()
    comp = competencia.isoformat()
    status = _statuses(comp)
    manual = _manual_rows()
    manual_ordered = ordenar_tarefas(manual, hoje)
    manual_summary = resumir_tarefas(manual, hoje)

    auto = []
    for empresa in EMPRESAS:
        p = calcular_prioridade_empresa(empresa, status, hoje, competencia)
        auto.append({
            "codigo": empresa["codigo"],
            "nome": empresa["nome"],
            "regime": empresa["regime"],
            **{
                **p,
                "vencimento": p["vencimento"].isoformat(),
            },
        })
    auto.sort(key=lambda x: (x["ordem"], x["vencimento"], int(x["codigo"])))
    auto_abertas = sum(1 for x in auto if not x["concluida"])
    auto_atrasadas = sum(1 for x in auto if x["status"] == "Atrasada")
    auto_urgentes = sum(1 for x in auto if x["status"] == "Urgente")
    auto_concluidas = sum(1 for x in auto if x["concluida"])
    total = len(auto) + manual_summary["total"]
    concluidas = auto_concluidas + manual_summary["concluidas"]

    return {
        "hoje": hoje.isoformat(),
        "competencia": comp,
        "resumo": {
            "pendentes": auto_abertas + manual_summary["abertas"],
            "atrasadas": auto_atrasadas + manual_summary["atrasadas"],
            "urgentes_hoje": auto_urgentes + manual_summary["hoje"],
            "concluidas": concluidas,
            "total": total,
            "progresso": round((concluidas / total) * 100) if total else 0,
        },
        "empresas": auto,
        "manuais": [
            {**t, "classificacao": classificar_tarefa(t, hoje)}
            for t in manual_ordered
        ],
    }


def set_company_status(codigo: str, competencia: str, concluida: bool):
    now = datetime.utcnow().isoformat()
    con = _db()
    try:
        con.execute("""
          INSERT INTO company_task_status(codigo_empresa,competencia,concluida,updated_at)
          VALUES(?,?,?,?)
          ON CONFLICT(codigo_empresa,competencia)
          DO UPDATE SET concluida=excluded.concluida, updated_at=excluded.updated_at
        """, (str(codigo), str(competencia), int(bool(concluida)), now))
        con.commit()
    finally:
        con.close()


def import_company_statuses(rows):
    allowed = {str(e['codigo']) for e in EMPRESAS}
    normalized = []
    for row in rows:
        code = str(row['codigo_empresa'])
        if code not in allowed or not isinstance(row['concluida'], bool):
            raise ValueError('Status de tarefa inválido.')
        period = date.fromisoformat(row['competencia'])
        if period.day != 1:
            raise ValueError('Competência inválida.')
        timestamp = datetime.fromisoformat(row['atualizado_em'].replace('Z','+00:00'))
        if timestamp.tzinfo:
            timestamp = timestamp.astimezone(timezone.utc).replace(tzinfo=None)
        normalized.append((code,period.isoformat(),int(row['concluida']),timestamp.isoformat()))
    con = _db()
    try:
        con.execute('BEGIN IMMEDIATE')
        imported = 0
        for record in normalized:
            old = con.execute('SELECT updated_at FROM company_task_status WHERE codigo_empresa=? AND competencia=?',record[:2]).fetchone()
            if old and datetime.fromisoformat(old['updated_at']) >= datetime.fromisoformat(record[3]):
                continue
            con.execute('INSERT OR REPLACE INTO company_task_status VALUES(?,?,?,?)',record)
            imported += 1
        con.commit()
        return imported
    finally:
        con.close()


def create_task(data: dict):
    title = str(data.get("titulo") or "").strip()
    if not title:
        raise ValueError("Informe o título da tarefa.")
    now = datetime.utcnow().isoformat()
    task_id = str(uuid.uuid4())
    row = {
        "id": task_id,
        "titulo": title,
        "descricao": str(data.get("descricao") or "").strip(),
        "codigo_empresa": str(data.get("codigo_empresa") or "").strip(),
        "categoria": str(data.get("categoria") or "Geral").strip(),
        "prioridade": str(data.get("prioridade") or "Normal").strip(),
        "prazo": str(data.get("prazo") or "").strip(),
        "status": "Pendente",
        "created_at": now,
        "updated_at": now,
    }
    con = _db()
    try:
        con.execute("""
        INSERT INTO manual_tasks(id,titulo,descricao,codigo_empresa,categoria,prioridade,prazo,status,created_at,updated_at)
        VALUES(:id,:titulo,:descricao,:codigo_empresa,:categoria,:prioridade,:prazo,:status,:created_at,:updated_at)
        """, row)
        con.commit()
    finally:
        con.close()
    return row


def update_task(task_id: str, status: str):
    allowed = {"Pendente", "Em andamento", "Concluída", "Cancelada"}
    if status not in allowed:
        raise ValueError("Status de tarefa inválido.")
    con = _db()
    try:
        cur = con.execute(
            "UPDATE manual_tasks SET status=?, updated_at=? WHERE id=?",
            (status, datetime.utcnow().isoformat(), task_id),
        )
        con.commit()
        if not cur.rowcount:
            raise ValueError("Tarefa não encontrada.")
    finally:
        con.close()


def delete_task(task_id: str):
    con = _db()
    try:
        con.execute("DELETE FROM manual_tasks WHERE id=?", (task_id,))
        con.commit()
    finally:
        con.close()
