"""Synthetic evaluation dataset generator (SPEC 1.6).

Generates N=60 synthetic text documents (invoice, resume, medical note,
bank statement, ID form, complaint letter) with Faker (en_IN), embedding
known PII spans. Writes backend/evaluation/dataset.json with ground truth
{doc_id, text, entities: [{start, end, type, text}]}.

Usage: python -m app.evaluation.dataset_generator
"""

import json
import random
import string
from pathlib import Path
from typing import Dict, List, Tuple

from faker import Faker

from app.services.pii_detector import luhn_check_digit, verhoeff_check_digit

N_DOCUMENTS = 60
TEMPLATE_KINDS = ["invoice", "resume", "medical", "bank", "idform", "complaint"]

DATASET_PATH = Path(__file__).resolve().parents[2] / "evaluation" / "dataset.json"


class _Builder:
    """Accumulates document text while recording ground-truth spans."""

    def __init__(self):
        self.parts: List[str] = []
        self.entities: List[Dict] = []

    def text(self, s: str) -> "_Builder":
        self.parts.append(s)
        return self

    def pii(self, pii_type: str, value: str) -> "_Builder":
        start = sum(len(p) for p in self.parts)
        self.parts.append(value)
        self.entities.append({"start": start, "end": start + len(value),
                              "type": pii_type, "text": value})
        return self

    def build(self) -> Tuple[str, List[Dict]]:
        return "".join(self.parts), self.entities


def _valid_aadhaar(rng: random.Random) -> str:
    body = "".join(rng.choice(string.digits) for _ in range(11))
    digits = body + str(verhoeff_check_digit(body))
    return f"{digits[:4]} {digits[4:8]} {digits[8:]}"


def _valid_card(rng: random.Random) -> str:
    body = "".join(rng.choice(string.digits) for _ in range(15))
    digits = body + str(luhn_check_digit(body))
    return f"{digits[:4]}-{digits[4:8]}-{digits[8:12]}-{digits[12:]}"


def _pan(rng: random.Random) -> str:
    letters = "".join(rng.choice(string.ascii_uppercase) for _ in range(5))
    return f"{letters}{rng.randint(1000, 9999)}{rng.choice(string.ascii_uppercase)}"


def _phone(fake: Faker, rng: random.Random) -> str:
    return f"+91 {rng.choice('6789')}{rng.randint(100000000, 999999999)}"


def _dob(fake: Faker) -> str:
    d = fake.date_of_birth(minimum_age=18, maximum_age=85)
    return d.strftime("%d/%m/%Y")


def _pii_set(fake: Faker, rng: random.Random) -> Dict[str, str]:
    return {
        "name": fake.name(),
        "email": fake.email(),
        "phone": _phone(fake, rng),
        "aadhaar": _valid_aadhaar(rng),
        "pan": _pan(rng),
        "credit_card": _valid_card(rng),
        "dob": _dob(fake),
        "address": fake.address().replace("\n", ", "),
        "organization": fake.company(),
        "ip": fake.ipv4(),
    }


def _invoice(fake: Faker, rng: random.Random, p: Dict[str, str]) -> Tuple[str, List[Dict]]:
    b = _Builder()
    b.text("TAX INVOICE\nInvoice No: INV-").text(str(rng.randint(1000, 9999)))
    b.text("\nBilled To: ").pii("name", p["name"])
    b.text("\nCompany: ").pii("organization", p["organization"])
    b.text("\nAddress: ").pii("address", p["address"])
    b.text("\nEmail: ").pii("email", p["email"])
    b.text("\nPhone: ").pii("phone", p["phone"])
    b.text("\nPAN: ").pii("pan", p["pan"])
    b.text(f"\nAmount Due: Rs. {rng.randint(500, 99999)}\nThank you for your business.\n")
    return b.build()


def _resume(fake: Faker, rng: random.Random, p: Dict[str, str]) -> Tuple[str, List[Dict]]:
    b = _Builder()
    b.text("CURRICULUM VITAE\nName: ").pii("name", p["name"])
    b.text("\nDate of Birth: ").pii("dob", p["dob"])
    b.text("\nEmail: ").pii("email", p["email"])
    b.text("\nMobile: ").pii("phone", p["phone"])
    b.text("\nAddress: ").pii("address", p["address"])
    b.text("\nCurrent Employer: ").pii("organization", p["organization"])
    b.text(f"\nExperience: {rng.randint(1, 20)} years in software engineering.\n")
    return b.build()


def _medical(fake: Faker, rng: random.Random, p: Dict[str, str]) -> Tuple[str, List[Dict]]:
    b = _Builder()
    b.text("MEDICAL NOTE\nPatient: ").pii("name", p["name"])
    b.text("\nDOB: ").pii("dob", p["dob"])
    b.text("\nAadhaar ID: ").pii("aadhaar", p["aadhaar"])
    b.text("\nContact: ").pii("phone", p["phone"])
    b.text("\nEmergency Email: ").pii("email", p["email"])
    b.text(f"\nDiagnosis: {fake.sentence(nb_words=8)}")
    b.text(f"\nAttending facility: ").pii("organization", p["organization"])
    b.text("\n")
    return b.build()


def _bank(fake: Faker, rng: random.Random, p: Dict[str, str]) -> Tuple[str, List[Dict]]:
    b = _Builder()
    b.text("ACCOUNT STATEMENT\nAccount Holder: ").pii("name", p["name"])
    b.text("\nCard Number: ").pii("credit_card", p["credit_card"])
    b.text("\nPAN: ").pii("pan", p["pan"])
    b.text("\nRegistered Phone: ").pii("phone", p["phone"])
    b.text("\nStatement queries: ").pii("email", p["email"])
    b.text(f"\nOpening Balance: Rs. {rng.randint(1000, 500000)}")
    b.text(f"\nServer IP: ").pii("ip", p["ip"])
    b.text("\n")
    return b.build()


def _idform(fake: Faker, rng: random.Random, p: Dict[str, str]) -> Tuple[str, List[Dict]]:
    b = _Builder()
    b.text("GOVERNMENT ID APPLICATION\nFull Name: ").pii("name", p["name"])
    b.text("\nDate of Birth: ").pii("dob", p["dob"])
    b.text("\nAadhaar Number: ").pii("aadhaar", p["aadhaar"])
    b.text("\nPAN: ").pii("pan", p["pan"])
    b.text("\nResidential Address: ").pii("address", p["address"])
    b.text("\nMobile Number: ").pii("phone", p["phone"])
    b.text("\nDeclaration: I certify the above information is true.\n")
    return b.build()


def _complaint(fake: Faker, rng: random.Random, p: Dict[str, str]) -> Tuple[str, List[Dict]]:
    b = _Builder()
    b.text("FORMAL COMPLAINT\nFrom: ").pii("name", p["name"])
    b.text("\nEmail: ").pii("email", p["email"])
    b.text("\nAgainst: ").pii("organization", p["organization"])
    b.text("\nRegarding transaction on card ").pii("credit_card", p["credit_card"])
    b.text(f"\nDetails: {fake.sentence(nb_words=12)}")
    b.text("\nContact me at ").pii("phone", p["phone"])
    b.text(" or visit ").pii("address", p["address"])
    b.text("\nSincerely.\n")
    return b.build()


_BUILDERS = {
    "invoice": _invoice,
    "resume": _resume,
    "medical": _medical,
    "bank": _bank,
    "idform": _idform,
    "complaint": _complaint,
}


def generate_dataset(n: int = N_DOCUMENTS) -> List[Dict]:
    docs = []
    for i in range(n):
        fake = Faker("en_IN")
        fake.seed_instance(1000 + i)
        rng = random.Random(2000 + i)
        kind = TEMPLATE_KINDS[i % len(TEMPLATE_KINDS)]
        text, entities = _BUILDERS[kind](fake, rng, _pii_set(fake, rng))
        docs.append({
            "doc_id": f"{kind}-{i // len(TEMPLATE_KINDS):02d}",
            "template": kind,
            "text": text,
            "entities": entities,
        })
    return docs


def main() -> None:
    docs = generate_dataset()
    DATASET_PATH.parent.mkdir(parents=True, exist_ok=True)
    DATASET_PATH.write_text(json.dumps(docs, indent=2))
    total_entities = sum(len(d["entities"]) for d in docs)
    print(f"Wrote {len(docs)} documents ({total_entities} entities) to {DATASET_PATH}")


if __name__ == "__main__":
    main()
