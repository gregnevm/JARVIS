"""promote_gate eval checks."""
from app.promote_gate import eval_promote_denied


def test_disabled():
    assert eval_promote_denied({"eval_score": 0.1}, 0) is None


def test_pass():
    assert eval_promote_denied({"eval_score": 0.95}, 0.9) is None


def test_fail_low():
    msg = eval_promote_denied({"eval_score": 0.5}, 0.9)
    assert msg and "0.5" in msg


def test_missing_score():
    assert eval_promote_denied({}, 0.8) is not None
