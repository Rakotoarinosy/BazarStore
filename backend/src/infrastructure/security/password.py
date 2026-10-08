"""Hachage des mots de passe avec Argon2id (paramètres par défaut d'argon2-cffi, conformes OWASP)."""

from argon2 import PasswordHasher as Argon2
from argon2.exceptions import InvalidHashError, VerificationError

from src.domain.user.ports import PasswordHasher


class Argon2PasswordHasher(PasswordHasher):
    def __init__(self) -> None:
        self._argon2 = Argon2()

    def hash(self, password: str) -> str:
        return self._argon2.hash(password)

    def verify(self, password: str, password_hash: str) -> bool:
        try:
            return self._argon2.verify(password_hash, password)
        except (VerificationError, InvalidHashError):
            # Hash vide ou invalide (ex. anciens comptes sans mot de passe) : jamais d'accès.
            return False

    def needs_rehash(self, password_hash: str) -> bool:
        try:
            return self._argon2.check_needs_rehash(password_hash)
        except InvalidHashError:
            return False
