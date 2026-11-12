"""Empresa 1399 — organização multi-banco Itaú (508) + Bradesco (9)."""
from __future__ import annotations

import pandas as pd

from app.bradesco_1399 import read_statement as read_bradesco
from app.itau_1399 import read_statement as read_itau


def workflow_1399(roles, options):
    from app.excel import gerar_modelo_abas
    from app.migration_services import filter_frame
    inputs=(
        ("itau","Itaú",read_itau),
        ("bradesco","Bradesco",read_bradesco),
    )
    groups={}
    for key,label,parser in inputs:
        uploads=roles.get(key) or []
        if not uploads:
            continue
        periods=set()
        frames=[]
        for filename,content in uploads:
            if not filename.lower().endswith(".pdf"):
                raise ValueError(f"Banco {label}: envie o extrato PDF.")
            frame=parser(content)
            periods_current=set(frame["DATA"].dt.to_period("M"))
            if len(periods_current)!=1 or bool(periods & periods_current):
                raise ValueError(f"Banco {label}: competência repetida ou inconsistente.")
            periods.update(periods_current)
            frames.append(frame)
        filtered=filter_frame(pd.concat(frames,ignore_index=True),options)
        if not filtered.empty:
            groups[label]=filtered.sort_values("DATA",kind="stable")
    if not groups:
        raise ValueError("Envie o extrato Itaú e/ou Bradesco da empresa 1399 para o período escolhido.")
    workbook=gerar_modelo_abas(groups,date_format="dd/mm/yyyy")
    return workbook,"EMPRESA_1399_MODELO_DOMINIO.xlsx"
