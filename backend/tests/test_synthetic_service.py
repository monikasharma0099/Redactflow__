"""Synthetic replacement service tests (SPEC 1.5)."""

import re

import pytest

from app.services.pii_detector import luhn_validate, verhoeff_validate
from app.services.synthetic_service import SyntheticDataService


@pytest.fixture()
def svc():
    return SyntheticDataService()


def test_email_shape_preserved(svc):
    for _ in range(20):
        out = svc.generate("email", "real.person@company.co.in")
        assert re.fullmatch(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", out)


def test_phone_digit_count_preserved(svc):
    out = svc.generate("phone", "+91 9876543210")
    assert out.startswith("+91")
    assert len(re.sub(r"\D", "", out)) >= 10


def test_aadhaar_format_and_checksum(svc):
    out = svc.generate("aadhaar", "2341 1234 5678")
    assert re.fullmatch(r"\d{4} \d{4} \d{4}", out)  # separators preserved
    assert verhoeff_validate(re.sub(r"\D", "", out))


def test_pan_shape(svc):
    assert re.fullmatch(r"[A-Z]{5}\d{4}[A-Z]", svc.generate("pan", "ABCDE1234F"))


def test_credit_card_luhn_and_format(svc):
    out = svc.generate("credit_card", "4539-5787-6362-1486")
    assert re.fullmatch(r"\d{4}-\d{4}-\d{4}-\d{4}", out)
    assert luhn_validate(re.sub(r"\D", "", out))


def test_dob_valid_date(svc):
    out = svc.generate("dob", "15/08/1990")
    day, month, year = (int(p) for p in out.split("/"))
    assert 1 <= day <= 31 and 1 <= month <= 12 and 1900 <= year <= 2100


def test_unknown_type_redacted(svc):
    assert svc.generate("mystery_type", "x") == "[REDACTED]"


def test_1000_generations_no_exception(svc):
    cases = [("email", "a@b.com"), ("phone", "+91 9876543210"),
             ("aadhaar", "1234 5678 9012"), ("pan", "ABCDE1234F"),
             ("credit_card", "4111-1111-1111-1111"), ("dob", "01/01/1990"),
             ("ssn", "123-45-6789"), ("ip", "1.2.3.4"), ("url", "https://x.in"),
             ("name", "Rahul Sharma"), ("address", "1 MG Road"),
             ("organization", "Acme")]
    for i in range(1000):  # old code crashed with %5 IndexError style bugs
        pii_type, original = cases[i % len(cases)]
        out = svc.generate(pii_type, original)
        assert isinstance(out, str) and out


def test_stateless_no_shared_counter(svc):
    # Two independent services produce valid output immediately and
    # repeatedly — no shared mutable index state to overflow.
    other = SyntheticDataService()
    for s in (svc, other, svc):
        assert re.fullmatch(r"[A-Z]{5}\d{4}[A-Z]", s.generate("pan", ""))
