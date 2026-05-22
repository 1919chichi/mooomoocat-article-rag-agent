from __future__ import annotations

import pytest

from mooomoocatrag.utils import estimate_tokens, is_retryable, retry_with_backoff


class TestEstimateTokens:
    def test_empty_string(self):
        assert estimate_tokens("") == 0

    def test_fifteen_chars(self):
        assert estimate_tokens("a" * 15) == 10  # ceil(15 / 1.5)

    def test_chinese_text(self):
        assert estimate_tokens("好" * 3) == 2  # ceil(3 / 1.5)


class TestIsRetryable:
    def test_429(self):
        assert is_retryable(Exception("rate limit 429")) is True

    def test_500(self):
        assert is_retryable(Exception("server error 500")) is True

    def test_502(self):
        assert is_retryable(Exception("bad gateway 502")) is True

    def test_503(self):
        assert is_retryable(Exception("service unavailable 503")) is True

    def test_504(self):
        assert is_retryable(Exception("gateway timeout 504")) is True

    def test_400_not_retryable(self):
        assert is_retryable(Exception("bad request 400")) is False

    def test_connection_error_not_retryable(self):
        assert is_retryable(Exception("connection refused")) is False


class TestRetryWithBackoff:
    def test_succeeds_first_try(self):
        calls = []

        def fn():
            calls.append(1)
            return "ok"

        result = retry_with_backoff(fn)
        assert result == "ok"
        assert len(calls) == 1

    def test_retries_on_429(self, monkeypatch):
        monkeypatch.setattr("mooomoocatrag.utils.time.sleep", lambda _: None)
        calls = []

        def fn():
            calls.append(1)
            if len(calls) < 3:
                raise Exception("429 Too Many Requests")
            return "ok"

        result = retry_with_backoff(fn)
        assert result == "ok"
        assert len(calls) == 3

    def test_does_not_retry_non_retryable(self):
        def fn():
            raise ValueError("invalid input")

        with pytest.raises(ValueError, match="invalid input"):
            retry_with_backoff(fn)

    def test_raises_after_max_attempts(self, monkeypatch):
        monkeypatch.setattr("mooomoocatrag.utils.time.sleep", lambda _: None)

        def fn():
            raise Exception("503 Service Unavailable")

        with pytest.raises(Exception, match="503"):
            retry_with_backoff(fn)

    def test_custom_max_attempts(self, monkeypatch):
        monkeypatch.setattr("mooomoocatrag.utils.time.sleep", lambda _: None)
        calls = []

        def fn():
            calls.append(1)
            raise Exception("503")

        with pytest.raises(Exception):
            retry_with_backoff(fn, max_attempts=2)

        assert len(calls) == 2
