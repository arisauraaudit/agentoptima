#!/usr/bin/env python3
"""
Phase 5 Test Suite — Conservative Semantic Cache
Tests: similarity scoring, real-time detection, false positive prevention
"""
import sys
sys.path.insert(0, '/root/.openclaw/workspace/AgentOptima')

from api.semantic_cache import (
    _cosine_similarity, _is_realtime_query, SEMANTIC_THRESHOLD
)


def test_cosine_similarity():
    print("=== Test: Cosine similarity ===")
    # Identical vectors → 1.0
    v = [1.0, 0.0, 0.0]
    assert abs(_cosine_similarity(v, v) - 1.0) < 0.0001, "Identical should be 1.0"
    # Orthogonal → 0.0
    a, b = [1.0, 0.0], [0.0, 1.0]
    assert abs(_cosine_similarity(a, b)) < 0.0001, "Orthogonal should be 0.0"
    # Zero vector → 0.0 (no crash)
    z = [0.0, 0.0, 0.0]
    assert _cosine_similarity(z, v) == 0.0, "Zero vector should return 0.0"
    print("  ✅ Cosine similarity math correct")


def test_realtime_detection():
    print("=== Test: Real-time query detection ===")
    should_skip = [
        "what is bitcoin price today",
        "current weather in Paris",
        "latest news about OpenAI",
        "what is eth price right now",
        "stock market this week",
    ]
    should_cache = [
        "what is 2 + 2",
        "explain recursion",
        "write a python function to sort a list",
        "what is the capital of France",
        "how does TCP/IP work",
    ]
    for q in should_skip:
        assert _is_realtime_query(q), f"Should detect as real-time: {q}"
        print(f"  ✅ Correctly skipped: '{q}'")
    for q in should_cache:
        assert not _is_realtime_query(q), f"Should allow caching: {q}"
        print(f"  ✅ Correctly allowed: '{q}'")


def test_threshold():
    print(f"=== Test: Threshold check ===")
    print(f"  Semantic threshold: {SEMANTIC_THRESHOLD}")
    assert SEMANTIC_THRESHOLD >= 0.95, "Threshold must be at least 0.95 for safety"
    assert SEMANTIC_THRESHOLD >= 0.97, "Threshold must be at least 0.97 per spec"
    print(f"  ✅ Conservative threshold confirmed: {SEMANTIC_THRESHOLD}")


def test_cosine_near_match():
    print("=== Test: Near-match scoring ===")
    # Two vectors pointing same direction but different magnitude → 1.0
    a = [2.0, 0.0, 0.0]
    b = [5.0, 0.0, 0.0]
    assert abs(_cosine_similarity(a, b) - 1.0) < 0.0001, "Same direction → 1.0"
    # Partial overlap
    c = [1.0, 1.0, 0.0]
    d = [1.0, 0.0, 0.0]
    sim = _cosine_similarity(c, d)
    assert 0.5 < sim < 1.0, f"Partial overlap should be between 0.5 and 1.0, got {sim}"
    print(f"  ✅ Partial overlap sim={sim:.4f} (expected 0.707)")
    # Opposite vectors → -1.0
    e = [1.0, 0.0]
    f = [-1.0, 0.0]
    assert abs(_cosine_similarity(e, f) + 1.0) < 0.0001, "Opposite vectors → -1.0"
    print("  ✅ Near-match scoring correct")


if __name__ == "__main__":
    test_cosine_similarity()
    test_realtime_detection()
    test_threshold()
    test_cosine_near_match()
    print("\n✅ All Phase 5 unit tests passed")
    print("Note: Live embedding tests require deployed environment")
