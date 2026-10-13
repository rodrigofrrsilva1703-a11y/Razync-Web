"""Janela diária de funcionamento do Razync no horário de São Paulo.

A regra de expediente limita novas requisições da API, mas não substitui
a suspensão automática de recursos do Railway Serverless.
"""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

TIMEZONE = ZoneInfo("America/Sao_Paulo")
OPEN_HOUR = 7
CLOSE_HOUR = 0


def current_time(now=None):
    if now is None:
        return datetime.now(TIMEZONE)
    if now.tzinfo is None:
        raise ValueError("O horário deve conter fuso horário.")
    return now.astimezone(TIMEZONE)


def is_open(now=None):
    return current_time(now).hour >= OPEN_HOUR


def seconds_until_open(now=None):
    clock = current_time(now)
    if is_open(clock):
        return 0
    opening = clock.replace(hour=OPEN_HOUR, minute=0, second=0, microsecond=0)
    return max(1, int((opening - clock).total_seconds() + 0.999))
