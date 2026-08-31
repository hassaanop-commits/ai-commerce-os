from app.core.security import hash_password, verify_password


def test_valid_password_verification():
    hashed = hash_password("correct horse battery staple")
    assert verify_password("correct horse battery staple", hashed) is True


def test_invalid_password_verification():
    hashed = hash_password("correct horse battery staple")
    assert verify_password("wrong password", hashed) is False


def test_hash_never_contains_plaintext():
    password = "correct horse battery staple"
    hashed = hash_password(password)
    assert password not in hashed
    assert hashed.startswith("$argon2id$")
