from candidate_transformer.core.normalize import (
    company_identity_key,
    normalize_company,
    normalize_email,
    normalize_github_url,
    normalize_name,
    normalize_phone,
    normalize_skill,
    normalize_url,
)


def test_normalize_email():
    assert normalize_email(" ALEX.CHEN@Example.com ") == "alex.chen@example.com"
    assert normalize_email("alex+jobs@example-domain.com") == (
        "alex+jobs@example-domain.com"
    )
    assert normalize_email("o'connor@example.com") == "o'connor@example.com"
    assert normalize_email("not-an-email") is None
    assert normalize_email("theo.martin@example..com") is None
    assert normalize_email("theo..martin@example.com") is None
    assert normalize_email(".theo@example.com") is None
    assert normalize_email("theo.@example.com") is None
    assert normalize_email("theo@-example.com") is None
    assert normalize_email("theo@example-.com") is None
    assert normalize_email("theo@exam_ple.com") is None
    assert normalize_email("") is None
    assert normalize_email(None) is None


def test_normalize_name():
    assert normalize_name("  Alex   Chen  ") == "Alex Chen"
    assert normalize_name("") is None
    assert normalize_name(None) is None


def test_normalize_company_removes_only_superficial_legal_variants():
    assert normalize_company(" Google LLC ") == "Google"
    assert normalize_company("Google, L.L.C.") == "Google"
    assert normalize_company("Acme Pvt. Ltd.") == "Acme"
    assert normalize_company("Alphabet") == "Alphabet"
    assert company_identity_key("GOOGLE L.L.C.") == "google"
    assert company_identity_key("Google") == "google"
    assert company_identity_key("Alphabet") == "alphabet"
    assert company_identity_key("München GmbH") == "münchen"
    assert normalize_company("The Honest Company") == "The Honest Company"
    assert normalize_company("") is None


def test_normalize_phone():
    assert normalize_phone("9876543210", default_region="IN") == "+919876543210"
    assert normalize_phone("09876543210", default_region="IN") == "+919876543210"
    assert normalize_phone("+91 98765 43210", default_region="IN") == "+919876543210"
    assert normalize_phone("6502530000", default_region="US") == "+16502530000"
    assert normalize_phone("6502530000") is None
    assert normalize_phone("+1 650 253 0000") == "+16502530000"
    assert normalize_phone("12345", default_region="IN") is None
    assert normalize_phone(None) is None


def test_normalize_url():
    assert normalize_url("github.com/AlexChen/") == "https://github.com/AlexChen"
    assert normalize_url("https://www.example.com/path/") == "https://example.com/path"
    assert normalize_url("") is None


def test_normalize_github_url():
    assert normalize_github_url("github.com/alexchen") == "https://github.com/alexchen"
    assert normalize_github_url("https://www.github.com/alexchen/") == "https://github.com/alexchen"
    assert normalize_github_url("https://github.com/alexchen/project") == "https://github.com/alexchen"
    assert normalize_github_url("https://linkedin.com/in/alexchen") is None


def test_normalize_skill():
    assert normalize_skill("py") == "Python"
    assert normalize_skill("k8s") == "Kubernetes"
    assert normalize_skill("javascript") == "JavaScript"
    assert normalize_skill("Distributed Systems") == "Distributed Systems"
    assert normalize_skill("") is None
