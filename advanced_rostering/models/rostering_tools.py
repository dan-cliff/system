# -*- coding: utf-8 -*-
"""Rostering cycles and time-of-day helpers shared by the Rostering models."""
from datetime import date, datetime, time, timedelta

import pytz
from dateutil.relativedelta import relativedelta

# How often rosters are published. Code works out each period's dates from
# these values, so they stay a fixed selection (see CLAUDE.md > Choice fields).
CYCLES = [
    ('weekly', 'Weekly'),
    ('fortnightly', 'Fortnightly'),
    ('monthly', 'Monthly'),
    ('quarterly', 'Quarterly'),
]
CYCLE_LENGTHS = {'weekly': 7, 'fortnightly': 14}
# Weeks a Roster Template holds for each cycle: enough 7-day blocks to cover
# the longest period (a 31-day month, a 92-day quarter).
CYCLE_WEEKS = {'weekly': 1, 'fortnightly': 2, 'monthly': 5, 'quarterly': 14}
# Weekly and fortnightly periods count from this date unless Settings say otherwise.
DEFAULT_PERIOD_START = date(2024, 1, 1)  # a Monday

# Weekdays as date.weekday() numbers; templates match roster days on them.
WEEKDAYS = [
    ('0', 'Monday'),
    ('1', 'Tuesday'),
    ('2', 'Wednesday'),
    ('3', 'Thursday'),
    ('4', 'Friday'),
    ('5', 'Saturday'),
    ('6', 'Sunday'),
]


def get_cycle(env):
    value = env['ir.config_parameter'].sudo().get_param('advanced_rostering.cycle')
    return value if value in dict(CYCLES) else 'weekly'


def get_period_anchor(env):
    value = env['ir.config_parameter'].sudo().get_param('advanced_rostering.period_start')
    try:
        return date.fromisoformat(value) if value else DEFAULT_PERIOD_START
    except ValueError:
        return DEFAULT_PERIOD_START


def period_bounds(env, day, cycle=None):
    """First and last day of the roster period (of ``cycle``, by default the
    one in Settings) containing ``day``."""
    cycle = cycle or get_cycle(env)
    if cycle == 'monthly':
        start = day.replace(day=1)
        return start, start + relativedelta(months=1, days=-1)
    if cycle == 'quarterly':
        start = day.replace(month=(day.month - 1) // 3 * 3 + 1, day=1)
        return start, start + relativedelta(months=3, days=-1)
    length = CYCLE_LENGTHS[cycle]
    anchor = get_period_anchor(env)
    start = anchor + timedelta(days=(day - anchor).days // length * length)
    return start, start + timedelta(days=length - 1)


def span(start, end):
    """Hours from ``start`` to ``end`` (hours of the day, e.g. 17.5 for
    17:30), running past midnight when ``end`` is not after ``start``."""
    return (end - start) % 24.0


def float_to_hhmm(value):
    minutes = int(round((value or 0.0) * 60))
    return '%02d:%02d' % divmod(minutes % (24 * 60), 60)


def local_to_utc(day, hours, tz_name):
    """Naive UTC datetime of ``hours`` (e.g. 9.5) after midnight of ``day`` in
    time zone ``tz_name``."""
    tz = pytz.timezone(tz_name or 'UTC')
    local = datetime.combine(day, time()) + timedelta(hours=hours)
    return tz.localize(local).astimezone(pytz.utc).replace(tzinfo=None)


def search_positive(operator, value):
    """Whether a search on a computed boolean field asks for True records
    (Odoo 19 hands search methods ``in [True]`` / ``not in [True]``), or
    None for an operator it cannot handle."""
    if operator in ('in', 'not in'):
        values = value if isinstance(value, (list, tuple, set, frozenset)) else [value]
        return (True in values) == (operator == 'in')
    if operator in ('=', '!='):
        return bool(value) == (operator == '=')
    return None
