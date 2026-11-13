"""Read complete attachment groups without silently ignoring later documents."""
import hashlib
import io
from dataclasses import dataclass

import pandas as pd
from fastapi import HTTPException
from fastapi.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile


@dataclass
class DocumentGroup:
    documents: list
    filename: str

    async def read(self):
        return self.documents


def merge_models(documents):
    """Keep source worksheet names (bank identification) and all rows."""
    sheets = {}
    for content, name in documents:
        with pd.ExcelFile(io.BytesIO(content)) as book:
            for sheet in book.sheet_names:
                frame = pd.read_excel(book, sheet_name=sheet, header=None, dtype=object)
                header = next((i for i, row in frame.iterrows()
                               if {'DATA', 'VALOR', 'HISTORICO'} <= {str(v).strip().upper().replace('Ó', 'O') for v in row}), None)
                if header is None:
                    raise ValueError(f'Cabeçalho do Modelo Domínio não encontrado em {name}, aba {sheet}.')
                indices = [i for i, value in enumerate(frame.iloc[header]) if pd.notna(value) and str(value).strip()]
                columns = [str(frame.iloc[header, i]).strip() for i in indices]
                if len(set(columns)) != len(columns):
                    raise ValueError(f'Cabeçalho com colunas repetidas em {name}, aba {sheet}.')
                data = frame.iloc[header + 1:, indices].copy()
                data.columns = columns
                sheets.setdefault(sheet, []).append(data)
    out = io.BytesIO()
    with pd.ExcelWriter(out, engine='openpyxl') as writer:
        for sheet, frames in sheets.items():
            # Write one header per bank and preserve every source movement.
            pd.concat(frames, ignore_index=True).to_excel(writer, sheet_name=sheet, index=False)
    return out.getvalue()


async def upload_group(uploads, *, model=False):
    if not uploads:
        return None
    if isinstance(uploads, UploadFile):
        return uploads
    if len(uploads) == 1:
        return uploads[0]
    if len(uploads) > 40:
        raise HTTPException(422, 'Anexe no máximo 40 arquivos por campo.')
    documents = []
    seen = set()
    size = 0
    for upload in uploads:
        content = await upload.read()
        size += len(content)
        if not content or len(content) > 25_000_000 or size > 100_000_000:
            raise HTTPException(422, 'Limite de 25 MB por arquivo e 100 MB por campo; arquivos vazios não são aceitos.')
        digest = hashlib.sha256(content).digest()
        if digest in seen:
            raise HTTPException(422, f'Arquivo repetido: {upload.filename}. Remova a cópia para evitar valores duplicados.')
        seen.add(digest)
        documents.append((content, upload.filename or 'documento.xlsx'))
    if model:
        try:
            merged = await run_in_threadpool(merge_models, documents)
        except Exception as exc:
            raise HTTPException(422, f'Não foi possível reunir os modelos: {exc}') from exc
        return UploadFile(io.BytesIO(merged), filename='modelos.xlsx')
    return DocumentGroup(documents, 'documentos.xlsx')
