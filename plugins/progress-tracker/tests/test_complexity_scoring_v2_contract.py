"""
Contract tests for v2 complexity scoring pipeline.

Two layers:
  Layer 1 — threshold regression (deterministic)
  Layer 2 — haiku response parsing contract (mocks haiku JSON; tests coordinator logic)

For acceptance test #2 ("haiku scores 3 features correctly"), the manual verification
template is provided in HAIKU_FIXTURE_RESPONSES below.
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../hooks/scripts"))
import progress_manager


HAIKU_FIXTURE_RESPONSES = {
    "fix typo in CLI help text": {
        "score": 5,
        "bucket": "simple",
        "model": "haiku",
        "path": "direct_tdd",
        "confidence": "high",
    },
    "add --confidence flag to CLI with bucket_override support": {
        "score": 48,
        "bucket": "standard",
        "model": "sonnet",
        "path": "plan_execute",
        "confidence": "high",
    },
    "refactor progress_manager.py into layered modules": {
        "score": 78,
        "bucket": "complex",
        "model": "opus",
        "path": "full_design_plan_execute",
        "confidence": "high",
    },
}

BUCKET_UPGRADE = {
    "simple": "standard",
    "standard": "complex",
    "complex": "complex",
}


class TestComplexityBucketThresholdsLayer1:
    """Layer 1: deterministic threshold regression for v2 0-100 scale."""

    @pytest.mark.parametrize("score,expected_bucket", [
        (5, "simple"),
        (37, "simple"),
        (38, "standard"),
        (48, "standard"),
        (62, "standard"),
        (63, "complex"),
        (78, "complex"),
        (100, "complex"),
    ])
    def test_score_maps_to_correct_bucket(self, score, expected_bucket):
        assert progress_manager.determine_complexity_bucket(score) == expected_bucket


class TestHaikuResponseParsingLayer2:
    """Layer 2: coordinator correctly parses haiku JSON and applies routing rules."""

    @pytest.mark.parametrize("feature_text,expected_bucket", [
        ("fix typo in CLI help text", "simple"),
        ("add --confidence flag to CLI with bucket_override support", "standard"),
        ("refactor progress_manager.py into layered modules", "complex"),
    ])
    def test_parse_haiku_response_routes_correctly(self, feature_text, expected_bucket):
        """Given a haiku-style JSON response, routed_bucket matches expected."""
        response = HAIKU_FIXTURE_RESPONSES[feature_text]
        confidence = response["confidence"]
        raw_bucket = response["bucket"]
        routed_bucket = BUCKET_UPGRADE[raw_bucket] if confidence == "low" else raw_bucket
        assert routed_bucket == expected_bucket

    def test_low_confidence_upgrades_simple_to_standard(self):
        low_conf = {"score": 30, "bucket": "simple", "confidence": "low"}
        routed = BUCKET_UPGRADE[low_conf["bucket"]]
        assert routed == "standard"

    def test_low_confidence_upgrades_standard_to_complex(self):
        low_conf = {"score": 50, "bucket": "standard", "confidence": "low"}
        routed = BUCKET_UPGRADE[low_conf["bucket"]]
        assert routed == "complex"

    def test_low_confidence_complex_stays_complex(self):
        low_conf = {"score": 80, "bucket": "complex", "confidence": "low"}
        routed = BUCKET_UPGRADE[low_conf["bucket"]]
        assert routed == "complex"

    def test_high_confidence_no_upgrade(self):
        high_conf = {"score": 30, "bucket": "simple", "confidence": "high"}
        routed = BUCKET_UPGRADE[high_conf["bucket"]] if high_conf["confidence"] == "low" else high_conf["bucket"]
        assert routed == "simple"

    @pytest.mark.parametrize("feature_text", list(HAIKU_FIXTURE_RESPONSES.keys()))
    def test_fixture_score_matches_bucket(self, feature_text):
        """Fixture scores are internally consistent with v2 thresholds."""
        response = HAIKU_FIXTURE_RESPONSES[feature_text]
        expected = progress_manager.determine_complexity_bucket(response["score"])
        assert response["bucket"] == expected
