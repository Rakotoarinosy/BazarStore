"""Types Pydantic réutilisables (email normalisé, mot de passe conforme à la politique)."""

from typing import Annotated

from pydantic import AfterValidator, EmailStr

from src.domain.user.rules import normalize_email, validate_password_strength

Email = Annotated[EmailStr, AfterValidator(normalize_email)]
Password = Annotated[str, AfterValidator(validate_password_strength)]
