"""detect_market 单元测试。"""
import pytest
from hiveflow.domain.market import CN_A_SHARE, CRYPTO, ANNUALIZATION_FACTOR, detect_market


def test_detect_market_cn_sh() -> None:
    assert detect_market("600000.SH") == CN_A_SHARE


def test_detect_market_cn_sz() -> None:
    assert detect_market("000001.SZ") == CN_A_SHARE


def test_detect_market_cn_bj() -> None:
    assert detect_market("830017.BJ") == CN_A_SHARE


def test_detect_market_case_insensitive() -> None:
    assert detect_market("600000.sh") == CN_A_SHARE


def test_detect_market_cn_with_whitespace() -> None:
    assert detect_market("  000001.SZ  ") == CN_A_SHARE


def test_detect_market_crypto_btc() -> None:
    assert detect_market("BTC") == CRYPTO


def test_detect_market_crypto_eth() -> None:
    assert detect_market("ETH") == CRYPTO


def test_detect_market_no_suffix() -> None:
    """6 位数字但没有 .SH/.SZ/.BJ 后缀 → crypto（不是 A 股）"""
    assert detect_market("000001") == CRYPTO


def test_detect_market_empty_string() -> None:
    assert detect_market("") == CRYPTO


def test_detect_market_does_not_raise_on_garbage() -> None:
    assert detect_market("!@#$%") == CRYPTO


def test_annualization_factor_crypto() -> None:
    assert ANNUALIZATION_FACTOR[CRYPTO] == 365


def test_annualization_factor_cn() -> None:
    assert ANNUALIZATION_FACTOR[CN_A_SHARE] == 252
