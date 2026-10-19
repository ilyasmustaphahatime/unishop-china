"""Domain failures shared by the two independent personal lists."""


class PersonalizationError(Exception):
    def __init__(self, message: str, status: int = 409):
        super().__init__(message)
        self.status = status
