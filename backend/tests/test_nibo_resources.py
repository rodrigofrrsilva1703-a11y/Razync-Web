import fitz
import pandas as pd
import pytest
from razync import nibo


def fixture():
    doc=fitz.open()
    doc.new_page()
    content=doc.tobytes()
    doc.close()
    return content


def test_nibo_libera_documento_e_imagem_quando_ocr_falha(monkeypatch):
    images=[]
    documents=[]
    real_open=nibo.fitz.open
    def open_document(*args,**kwargs):
        doc=real_open(*args,**kwargs)
        documents.append(doc)
        return doc
    def ocr(image, **kwargs):
        images.append(image)
        assert kwargs['timeout']==90
        raise RuntimeError('Tesseract process timeout')
    content=fixture()
    monkeypatch.setattr(nibo.fitz,'open',open_document)
    monkeypatch.setattr(nibo.pytesseract,'image_to_data',ocr)
    with pytest.raises(ValueError,match='página 1'):
        nibo.processar_extrato_nibo_pdf(content)
    assert documents[0].is_closed
    with pytest.raises(ValueError):
        images[0].getpixel((0,0))
