"""Exception de base de toutes les erreurs métier, commune à tous les domaines."""


class DomainError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message
