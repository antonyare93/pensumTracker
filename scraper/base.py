from abc import ABC, abstractmethod
from models.academic import Subject, ElectiveBank


class Authenticator(ABC):
    @abstractmethod
    def login(self, username: str, password: str) -> bool: ...

    @abstractmethod
    def logout(self) -> None: ...


class CurriculumFetcher(ABC):
    @abstractmethod
    def fetch_curriculum(self) -> list[Subject]: ...

    @abstractmethod
    def fetch_elective_banks(self) -> list[ElectiveBank]: ...


class AcademicHistoryFetcher(ABC):
    @abstractmethod
    def fetch_passed_subjects(self) -> dict[str, float]: ...

    @abstractmethod
    def fetch_current_subjects(self) -> list[str]: ...

    @abstractmethod
    def fetch_student_info(self) -> tuple[str, str, str]: ...
