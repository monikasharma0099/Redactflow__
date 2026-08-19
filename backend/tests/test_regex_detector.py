"""Regex layer tests: every PII type positive + false-positive guards."""

import pytest

from app.services.pii_detector import (PIIDetector, luhn_validate,
                                       valid_date_string, valid_ip,
                                       verhoeff_check_digit,
                                       verhoeff_validate)


@pytest.fixture()
def detector():
    return PIIDetector(enable_spacy=False, enable_llm=False)


def _types(detector, text):
    return {d.pii_type for d in detector.detect(text)}


def _valid_aadhaar(body: str) -> str:
    return body + str(verhoeff_check_digit(body))


# -- positives ---------------------------------------------------------------

def test_email_positive(detector):
    assert "email" in _types(detector, "Reach me at priya.patel@example.co.in today")


def test_phone_indian_positive(detector):
    assert "phone" in _types(detector, "Call +91 9876543210 now")


def test_phone_plain_positive(detector):
    assert "phone" in _types(detector, "Mobile: 9123456789.")


def test_aadhaar_verhoeff_positive(detector):
    aadhaar = _valid_aadhaar("23411234567")
    text = f"Aadhaar: {aadhaar[:4]} {aadhaar[4:8]} {aadhaar[8:]}"
    assert "aadhaar" in _types(detector, text)


def test_pan_positive(detector):
    assert "pan" in _types(detector, "PAN number ABCDE1234F here")


def test_credit_card_luhn_positive(detector):
    assert "credit_card" in _types(detector, "Card 4539-5787-6362-1486 charged")


def test_ip_positive(detector):
    assert "ip" in _types(detector, "Server at 192.168.1.100 down")


def test_dob_positive(detector):
    assert "dob" in _types(detector, "Born on 15/08/1990 in Pune")


def test_ssn_positive(detector):
    assert "ssn" in _types(detector, "SSN 123-45-6789 recorded")


def test_url_positive(detector):
    assert "url" in _types(detector, "Portal https://example.gov.in/login here")


# -- false-positive guards -----------------------------------------------------

def test_aadhaar_bad_checksum_rejected(detector):
    assert "aadhaar" not in _types(detector, "ID 1234 5678 9012 here")


def test_credit_card_bad_luhn_rejected(detector):
    assert "credit_card" not in _types(detector, "Card 1234-5678-9012-3456 nope")


def test_credit_card_not_misread_as_aadhaar(detector):
    # The first 12 digits of a 16-digit card must not match AADHAAR.
    assert "aadhaar" not in _types(detector, "Card 4539-5787-6362-1486 charged")


def test_ip_octet_999_rejected(detector):
    assert "ip" not in _types(detector, "Host 999.999.999.999 invalid")


def test_dob_invalid_date_rejected(detector):
    assert "dob" not in _types(detector, "Date 31/02/2020 impossible")
    assert "dob" not in _types(detector, "Date 13/13/2020 impossible")


# -- validator units -------------------------------------------------------------

def test_verhoeff_roundtrip():
    body = "23411234567"
    assert verhoeff_validate(body + str(verhoeff_check_digit(body)))
    assert not verhoeff_validate(body + "0")


def test_luhn_known_numbers():
    assert luhn_validate("4539578763621486")
    assert not luhn_validate("4539578763621487")


def test_valid_ip_bounds():
    assert valid_ip("0.0.0.0") and valid_ip("255.255.255.255")
    assert not valid_ip("256.1.1.1")


def test_valid_date_string_ranges():
    assert valid_date_string("29/02/2020")  # leap day
    assert not valid_date_string("29/02/2021")
    assert not valid_date_string("01/01/1800")
    assert valid_date_string("2024-01-31")
