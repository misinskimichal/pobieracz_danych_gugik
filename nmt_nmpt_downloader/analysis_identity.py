"""Stable analysis titles, preserving the source and the actual creation instant."""
from datetime import datetime, timezone
from qgis.PyQt.QtCore import QDateTime, QTimeZone, Qt


def initialize_identity(report):
    options = report.get('options', {})
    report.setdefault('analysis_name', 'Widoczność')
    report.setdefault('turbine_layer_name', options.get('turbine_layer_name', ''))
    report.setdefault('turbine_layer_id', options.get('turbine_layer_id', ''))
    report.setdefault('created_at', report.get('started_at') or datetime.now(timezone.utc).isoformat(timespec='seconds'))


def result_title(report):
    options = report.get('options', {})
    name = report.get('analysis_name') or 'Widoczność'
    source = report.get('turbine_layer_name') or options.get('turbine_layer_name') or 'warstwa turbin — nazwa niezapisana'
    instant = report.get('created_at') or report.get('started_at', '')
    stamp = QDateTime.fromString(instant, Qt.ISODate)
    date = stamp.toTimeZone(QTimeZone(b'Europe/Warsaw')).toString('yyyy-MM-dd HH:mm:ss t') if stamp.isValid() else 'data niezapisana'
    return f'{name} · {source} · {date}'
