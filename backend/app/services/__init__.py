"""
MediGenius — services/__init__.py
Exports service singletons.
"""

from app.services.chat_service import ChatService, chat_service
from app.services.database_service import DatabaseService, db_service
from app.services.ecg_monitor_service import ECGMonitorService, ecg_monitor_service
from app.services.ecg_report_service import ECGReportService, ecg_report_service

__all__ = [
    "DatabaseService",
    "db_service",
    "ChatService",
    "chat_service",
    "ECGMonitorService",
    "ecg_monitor_service",
    "ECGReportService",
    "ecg_report_service",
]
