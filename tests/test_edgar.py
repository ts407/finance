"""Offline unit tests for EDGAR point selection / growth helpers."""

from __future__ import annotations

from datetime import date

from standing.providers.edgar.client import FactPoint, latest_as_of, ttm_sum_quarters, yoy_growth


def _fp(end: str, filed: str, val: float, *, form="10-Q", fp="Q1", frame=None) -> FactPoint:
    return FactPoint(
        end=date.fromisoformat(end),
        filed=date.fromisoformat(filed),
        val=val,
        form=form,
        fp=fp,
        frame=frame,
    )


def test_latest_as_of_respects_filed_cutoff():
    points = [
        _fp("2024-12-31", "2025-02-01", 1.0, form="10-K", fp="FY", frame="CY2024"),
        _fp("2025-12-31", "2026-02-01", 2.0, form="10-K", fp="FY", frame="CY2025"),
    ]
    assert latest_as_of(points, date(2025, 6, 1)).val == 1.0
    assert latest_as_of(points, date(2026, 7, 22)).val == 2.0


def test_ttm_sum_quarters():
    points = [
        _fp("2025-03-31", "2025-05-01", 1.0, frame="CY2025Q1"),
        _fp("2025-06-30", "2025-08-01", 2.0, frame="CY2025Q2"),
        _fp("2025-09-30", "2025-11-01", 3.0, frame="CY2025Q3"),
        _fp("2025-12-31", "2026-02-01", 4.0, frame="CY2025Q4"),
    ]
    assert ttm_sum_quarters(points, date(2026, 7, 22)) == 10.0


def test_yoy_growth():
    points = [
        _fp("2024-12-31", "2025-02-01", 100.0, form="10-K", fp="FY", frame="CY2024"),
        _fp("2025-12-31", "2026-02-01", 120.0, form="10-K", fp="FY", frame="CY2025"),
    ]
    g = yoy_growth(points, date(2026, 7, 22))
    assert abs(g - 0.2) < 1e-9
