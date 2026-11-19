"""Anomaly checks used while reviewing a result sheet.

These checks never declare fraud, reject a result, override the arithmetic
rules or change a value. An alert is a request for a person to look."""

from app.evidence.ai.engine import HEADLINE, Alert, AnalysisResult, analyze

__all__ = ["HEADLINE", "Alert", "AnalysisResult", "analyze"]
