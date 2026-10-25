"""Expediente Razync: todos os dias, 07h-00h, horário de São Paulo.

Bloqueia novas requisições da API fora do expediente. A economia real depende
do servidor Railway Serverless suspender após ficar sem atividade.
"""
from datetime import datetime
from zoneinfo import ZoneInfo

TIMEZONE = ZoneInfo("America/Sao_Paulo")
OPEN_HOUR = 7


def current_time(now=None):
    if now is None:
        return datetime.now(TIMEZONE)
    if now.tzinfo is None:
        raise ValueError("O horário deve conter fuso horário.")
    return now.astimezone(TIMEZONE)


def is_open(now=None):
    clock = current_time(now)
    return clock.hour >= OPEN_HOUR


def seconds_until_open(now=None):
    clock = current_time(now)
    if is_open(clock):
        return 0
    opening = clock.replace(hour=OPEN_HOUR, minute=0, second=0, microsecond=0)
    return max(1, int((opening - clock).total_seconds() + 0.999))
