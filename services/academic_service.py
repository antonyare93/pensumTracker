from collections import defaultdict
from models.academic import Subject, ElectiveBank, AcademicRecord


class AcademicRecordBuilder:
    def build(
        self,
        student_name: str,
        program_name: str,
        program_code: str,
        pensum_version: int,
        version_actual: int,
        versiones: list[int],
        total_credits: int,
        subjects: list[Subject],
    ) -> AcademicRecord:
        unlocked = {s.code for s in subjects if s.cursada or s.cursando}
        enriched: list[Subject] = []
        for s in subjects:
            if s.cursada:
                status = "passed"
            elif s.cursando:
                status = "in_progress"
            elif all(p in unlocked for p in s.prerequisites):
                status = "available"
            else:
                status = "locked"
            enriched.append(s.model_copy(update={"status": status}))

        completed_credits = sum(s.credits for s in enriched if s.cursada)
        in_progress_credits = sum(s.credits for s in enriched if s.cursando and not s.cursada)

        bank_subjects: dict[str, list[Subject]] = defaultdict(list)
        for s in enriched:
            if s.elective_bank:
                bank_subjects[s.elective_bank].append(s)

        elective_banks: list[ElectiveBank] = [
            ElectiveBank(
                name=bank_name,
                credits_required=sum(s.credits for s in group),
                credits_approved=sum(s.credits for s in group if s.cursada),
                subject_codes=[s.code for s in group],
            )
            for bank_name, group in sorted(bank_subjects.items())
        ]

        return AcademicRecord(
            student_name=student_name,
            program_name=program_name,
            program_code=program_code,
            pensum_version=pensum_version,
            version_actual=version_actual,
            versiones=versiones,
            total_credits=total_credits,
            completed_credits=completed_credits,
            in_progress_credits=in_progress_credits,
            subjects=enriched,
            elective_banks=elective_banks,
        )
