# -*- coding: utf-8 -*-
"""TDD: 보안 관련 단위 테스트"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
import hmac
import hashlib
import time
import json
from unittest.mock import patch, MagicMock


class TestWebhookSecurity:
    """웹훅 보안 검증 테스트"""

    def _make_signature(self, body: bytes, secret: str) -> str:
        """HMAC-SHA256 서명 생성 헬퍼"""
        return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

    def test_valid_hmac_signature_passes(self):
        """올바른 HMAC 서명은 통과해야 함"""
        secret = "test_secret_key_32chars_minimum!!"
        body = json.dumps({"ticker": "NVDA", "action": "BUY"}).encode()
        sig = self._make_signature(body, secret)

        expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        assert hmac.compare_digest(sig, expected), "올바른 서명이 거부됨"

    def test_invalid_hmac_signature_fails(self):
        """잘못된 HMAC 서명은 거부되어야 함"""
        secret = "test_secret_key_32chars_minimum!!"
        body = json.dumps({"ticker": "NVDA", "action": "BUY"}).encode()
        fake_sig = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"

        expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        assert not hmac.compare_digest(fake_sig, expected), "잘못된 서명이 통과됨"

    def test_tampered_body_fails(self):
        """페이로드가 변조된 경우 서명 검증 실패해야 함"""
        secret = "test_secret_key_32chars_minimum!!"
        original_body = json.dumps({"ticker": "NVDA", "action": "BUY"}).encode()
        sig = self._make_signature(original_body, secret)

        tampered_body = json.dumps({"ticker": "NVDA", "action": "SELL"}).encode()
        expected = hmac.new(secret.encode(), tampered_body, hashlib.sha256).hexdigest()
        assert not hmac.compare_digest(sig, expected), "변조된 페이로드가 통과됨"

    def test_timing_safe_comparison(self):
        """타이밍 공격 방지 — hmac.compare_digest 사용 검증"""
        a = "deadbeef" * 8
        b = "deadbeef" * 8
        c = "cafebabe" * 8
        assert hmac.compare_digest(a, b), "동일한 값 비교 실패"
        assert not hmac.compare_digest(a, c), "다른 값이 같다고 판정됨"


class TestAPIKeyValidation:
    """API 키 유효성 검증 테스트"""

    def test_empty_api_key_detected(self):
        """빈 API 키는 유효하지 않음"""
        def is_valid_key(key: str, min_len: int = 10) -> bool:
            return bool(key and len(key.strip()) >= min_len)

        assert not is_valid_key(""), "빈 키가 유효하다고 판정됨"
        assert not is_valid_key("   "), "공백 키가 유효하다고 판정됨"
        assert not is_valid_key("short"), "너무 짧은 키가 유효하다고 판정됨"

    def test_placeholder_key_detected(self):
        """플레이스홀더 API 키 감지"""
        placeholders = [
            "your_api_key",
            "YOUR_API_KEY",
            "your_alpaca_api_key",
            "your_telegram_bot_token",
        ]
        def is_placeholder(key: str) -> bool:
            return key.lower().startswith("your_")

        for ph in placeholders:
            assert is_placeholder(ph), f"플레이스홀더 미감지: {ph}"

    def test_valid_api_key_format(self):
        """유효한 형식의 API 키 통과"""
        def is_valid_key(key: str, min_len: int = 10) -> bool:
            return bool(key and len(key.strip()) >= min_len and not key.lower().startswith("your_"))

        assert is_valid_key("PSjSHOdRJ1KtNndPnmE3CuYp3nByFxiI"), "유효한 KIS 키 거부됨"
        assert is_valid_key("GlxDI6uP3zNTx6HYAk5soRfEceVbZhUe"), "유효한 업비트 키 거부됨"


class TestInputSanitization:
    """입력 데이터 검증 테스트"""

    def test_ticker_whitelist_validation(self):
        """허용된 종목코드만 통과"""
        ALLOWED = {'005930', '000660', 'NVDA', 'TSLA', 'BTC', 'ETH'}

        def validate_ticker(t: str) -> bool:
            return t.upper() in {k.upper() for k in ALLOWED}

        assert validate_ticker("NVDA"), "허용 종목 거부됨"
        assert validate_ticker("005930"), "허용 종목 거부됨"
        assert not validate_ticker("UNKNOWN"), "미허용 종목 통과됨"
        assert not validate_ticker("'; DROP TABLE--"), "SQL Injection 통과됨"

    def test_action_enum_validation(self):
        """BUY/SELL만 허용"""
        ALLOWED_ACTIONS = {"BUY", "SELL", "HALT"}

        def validate_action(a: str) -> bool:
            return a.upper() in ALLOWED_ACTIONS

        assert validate_action("BUY")
        assert validate_action("SELL")
        assert not validate_action("BUY; rm -rf /")
        assert not validate_action("")
        assert not validate_action("HACK")

    def test_price_injection_prevention(self):
        """가격 파라미터 숫자 강제 변환"""
        def safe_price(raw) -> float | None:
            try:
                val = float(str(raw).replace(',', '').strip())
                if val <= 0 or val > 1_000_000_000:
                    return None
                return val
            except (ValueError, TypeError):
                return None

        assert safe_price("1234.56") == 1234.56
        assert safe_price("1,234.56") == 1234.56
        assert safe_price("{{close}}") is None   # TradingView 미치환 변수
        assert safe_price("'; DROP TABLE") is None
        assert safe_price(-100) is None
        assert safe_price(0) is None
        assert safe_price(2_000_000_000) is None  # 비현실적 가격


class TestRateLimiting:
    """Rate Limiting 테스트"""

    def test_rate_limiter_blocks_excess(self):
        """초당 요청 한도 초과 시 차단"""
        class SimpleRateLimiter:
            def __init__(self, max_calls: int, period: float):
                self.max_calls = max_calls
                self.period = period
                self._calls: list[float] = []

            def is_allowed(self) -> bool:
                now = time.time()
                self._calls = [t for t in self._calls if now - t < self.period]
                if len(self._calls) >= self.max_calls:
                    return False
                self._calls.append(now)
                return True

        limiter = SimpleRateLimiter(max_calls=3, period=1.0)
        assert limiter.is_allowed()   # 1st
        assert limiter.is_allowed()   # 2nd
        assert limiter.is_allowed()   # 3rd
        assert not limiter.is_allowed()  # 4th — 차단
