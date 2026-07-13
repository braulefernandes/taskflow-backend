from app.core.security import get_password_hash, verify_password


def test_password_hash_differs_from_password() -> None:
    password_hash = get_password_hash("Senha123")

    assert password_hash != "Senha123"
    assert password_hash.startswith("pbkdf2_sha256$")


def test_verify_password_against_hash() -> None:
    password_hash = get_password_hash("Senha123")

    assert verify_password("Senha123", password_hash) is True
    assert verify_password("SenhaErrada123", password_hash) is False
