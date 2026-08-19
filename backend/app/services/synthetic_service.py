"""Format-preserving synthetic PII replacement (SPEC 1.5).

Faker-based (en_IN locale). Stateless: no shared mutable counters, no
modulo-indexed hardcoded lists — every call draws from Faker's RNG and
only depends on (pii_type, original) plus randomness.
"""

import random
import re
import string
from typing import Optional

from faker import Faker

from app.services.pii_detector import luhn_check_digit, verhoeff_check_digit


class SyntheticDataService:
    """Generates realistic, format-preserving synthetic replacements."""

    def __init__(self, locale: str = "en_IN", seed: Optional[int] = None):
        self._faker = Faker(locale)
        self._rng = random.Random(seed)  # local RNG, never a shared counter
        if seed is not None:
            self._faker.seed_instance(seed)

    # -- helpers -------------------------------------------------------------
    def _rand_digits(self, n: int) -> str:
        return "".join(self._rng.choice(string.digits) for _ in range(n))

    def _reformat_like(self, digits: str, original: str) -> str:
        """Re-apply the separator pattern of `original` to new digits."""
        out, i = [], 0
        for ch in original:
            if ch.isdigit():
                if i < len(digits):
                    out.append(digits[i])
                    i += 1
            else:
                out.append(ch)
        while i < len(digits):
            out.append(digits[i])
            i += 1
        return "".join(out)

    # -- per-type generators ---------------------------------------------------
    def _email(self) -> str:
        return self._faker.email()  # always a valid email shape

    def _phone(self, original: str) -> str:
        n = len(re.sub(r"\D", "", original))
        n = max(10, min(n, 12))
        digits = self._rng.choice("6789") + self._rand_digits(n - 1)
        if original.strip().startswith("+"):
            return "+91 " + digits[-10:] if n >= 10 else "+" + digits
        return digits

    def _aadhaar(self, original: str) -> str:
        body = self._rand_digits(11)
        digits = body + str(verhoeff_check_digit(body))
        return self._reformat_like(digits, original)

    def _pan(self) -> str:
        letters = "".join(self._rng.choice(string.ascii_uppercase) for _ in range(5))
        return f"{letters}{self._rand_digits(4)}{self._rng.choice(string.ascii_uppercase)}"

    def _credit_card(self, original: str) -> str:
        body = self._rand_digits(15)
        digits = body + str(luhn_check_digit(body))
        return self._reformat_like(digits, original)

    def _ip(self) -> str:
        return self._faker.ipv4()

    def _dob(self, original: str) -> str:
        d = self._faker.date_of_birth(minimum_age=18, maximum_age=90)
        m = re.match(r"^(\d{1,4})([-/.])(\d{1,2})[-/.](\d{1,4})$", original.strip())
        if m and int(m.group(1)) > 31:
            return f"{d.year:04d}{m.group(2)}{d.month:02d}{m.group(2)}{d.day:02d}"
        sep = m.group(2) if m else "/"
        return f"{d.day:02d}{sep}{d.month:02d}{sep}{d.year:04d}"

    def _ssn(self, original: str) -> str:
        digits = self._rand_digits(9)
        return self._reformat_like(digits, original)

    def _url(self) -> str:
        return self._faker.url()

    def _name(self) -> str:
        return self._faker.name()

    def _address(self) -> str:
        return self._faker.address().replace("\n", ", ")

    def _organization(self) -> str:
        return self._faker.company()

    # -- public API -------------------------------------------------------------
    def generate(self, pii_type: str, original: str = "") -> str:
        """Return a synthetic replacement for the given PII type, preserving
        the original's format (email shape, digit counts, separators)."""
        generators = {
            "email": lambda: self._email(),
            "phone": lambda: self._phone(original),
            "aadhaar": lambda: self._aadhaar(original or "0000 0000 0000"),
            "pan": self._pan,
            "credit_card": lambda: self._credit_card(original or "0000000000000000"),
            "ip": self._ip,
            "dob": lambda: self._dob(original),
            "ssn": lambda: self._ssn(original or "000-00-0000"),
            "url": self._url,
            "name": self._name,
            "address": self._address,
            "organization": self._organization,
        }
        gen = generators.get(pii_type)
        return gen() if gen else "[REDACTED]"


_service: Optional[SyntheticDataService] = None


def get_synthetic_service() -> SyntheticDataService:
    """Lazy singleton factory."""
    global _service
    if _service is None:
        from app.core.config import settings

        _service = SyntheticDataService(locale=settings.SYNTHETIC_LOCALE)
    return _service
