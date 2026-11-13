"""Compatibilidade com integrações antigas: o Razync funciona 24 horas."""
from datetime import datetime
from zoneinfo import ZoneInfo

TIMEZONE = ZoneInfo("America/Sao_Paulo")


def current_time(now=None):
    if now is None:
        return datetime.now(TIMEZONE)
    if now.tzinfo is None:
        raise ValueError("O horário deve conter fuso horário.")
    return now.astimezone(TIMEZONE)


def is_open(now=None):
    return True


def seconds_until_open(now=None):
    return 0
