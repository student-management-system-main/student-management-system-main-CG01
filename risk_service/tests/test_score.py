"""
risk_service/tests/test_score.py
---------------------------------
Placeholder test module for the risk scoring service.

Full tests are implemented in task 8.7.  This file establishes the test
module structure and includes a basic smoke test for :func:`score.classify_risk`
so the test suite is runnable from day one.

Requirements: 4.1, 4.4, 4.7
"""

import pytest

from score import classify_risk


# ---------------------------------------------------------------------------
# classify_risk – boundary value tests
# ---------------------------------------------------------------------------

class TestClassifyRisk:
    """Unit tests for the classify_risk threshold logic."""

    def test_score_zero_is_low(self):
        assert classify_risk(0) == "low"

    def test_score_39_is_low(self):
        assert classify_risk(39) == "low"

    def test_score_40_is_medium(self):
        assert classify_risk(40) == "medium"

    def test_score_69_is_medium(self):
        assert classify_risk(69) == "medium"

    def test_score_70_is_high(self):
        assert classify_risk(70) == "high"

    def test_score_100_is_high(self):
        assert classify_risk(100) == "high"

    def test_score_below_zero_raises(self):
        with pytest.raises(ValueError):
            classify_risk(-1)

    def test_score_above_100_raises(self):
        with pytest.raises(ValueError):
            classify_risk(101)
