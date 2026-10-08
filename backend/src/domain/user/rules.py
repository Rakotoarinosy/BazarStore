"""Règles métier pures : politique de mot de passe, normalisation d'email."""

import re

PASSWORD_MIN_LENGTH = 10
PASSWORD_MAX_LENGTH = 128  # borne haute : évite de faire hacher des payloads géants


def validate_password_strength(value: str) -> str:
    if not PASSWORD_MIN_LENGTH <= len(value) <= PASSWORD_MAX_LENGTH:
        raise ValueError(
            f"Password must be between {PASSWORD_MIN_LENGTH} and {PASSWORD_MAX_LENGTH} characters"
        )
    if not (re.search(r"[a-z]", value) and re.search(r"[A-Z]", value) and re.search(r"\d", value)):
        raise ValueError("Password must contain a lowercase letter, an uppercase letter and a digit")

    return value


def normalize_email(value: str) -> str:
    return value.strip().lower()
