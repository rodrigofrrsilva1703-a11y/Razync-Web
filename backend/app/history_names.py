"""Composição conservadora de históricos sem repetir razão social.

Não altera valores, datas, origem ou sinal das movimentações.
"""
import re
import unicodedata

# Palavras comuns de operação e natureza jurídica não comprovam identidade.
_GENERIC = {
    "pago", "recebido", "pagamento", "pagamentos", "recebimento", "recebimentos",
    "pix", "enviado", "recebida", "recebido", "transferencia", "transf", "ted",
    "boleto", "tit", "titulo", "sispag", "conta", "corrente", "banco",
    "itau", "bradesco", "nubank", "caixa", "inter", "creditado",
    "credito", "debito", "com", "para", "por", "de", "da", "do", "das", "dos",
    "e", "a", "o", "em", "na", "no", "nf", "cnpj", "cpf", "ltda", "sa",
    "eireli", "me", "mei", "epp", "empresa", "comercio", "comercial",
    "servicos", "servico", "industria", "industrial", "sociedade",
}


def _words(value):
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).casefold()
    return re.findall(r"[a-z0-9]+", text)


def _identity_tokens(value):
    return {word for word in _words(value)
            if word not in _GENERIC and len(word) >= 4}


def join_history_description(history, name):
    """Mantém o histórico original quando ele já identifica o favorecido.

    Um token distintivo de quatro ou mais caracteres presente em ambos é
    suficiente para não anexar novamente a razão social (inclusive abreviada).
    Não deduz identidades por similaridade aproximada ou palavras genéricas.
    """
    base = " ".join(str(history or "").split()).strip(" -")
    extra = " ".join(str(name or "").split()).strip(" -")
    if not extra:
        return base
    if not base:
        return extra

    base_words = _words(base)
    name_words = _words(extra)
    if not name_words:
        return base
    # Nome inteiro ou sequência já presente, desconsiderando pontuação e acentos.
    if (len(name_words) <= len(base_words) and
        any(base_words[i:i+len(name_words)] == name_words
            for i in range(len(base_words)-len(name_words)+1))):
        return base
    if _identity_tokens(base) & _identity_tokens(extra):
        return base
    return base + " - " + extra
