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
        subjects: list[Subject],
        elective_banks: list[ElectiveBank],
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
        subjects = enriched

        bank_codes          = {code for b in elective_banks for code in b.subject_codes}
        mandatory_total     = sum(s.credits for s in subjects if s.obligatoria and s.code not in bank_codes)
        mandatory_completed = sum(s.credits for s in subjects if s.obligatoria and s.cursada and s.code not in bank_codes)
        mandatory_in_progress = sum(s.credits for s in subjects if s.obligatoria and s.cursando and not s.cursada and s.code not in bank_codes)
        elective_total      = sum({b.credits_required for b in elective_banks})
        elective_completed  = sum(b.credits_approved for b in elective_banks)
        elective_in_progress = sum(
            s.credits for s in subjects if s.cursando and not s.cursada and s.code in bank_codes
        )

        return AcademicRecord(
            student_name=student_name,
            program_name=program_name,
            program_code=program_code,
            pensum_version=pensum_version,
            version_actual=version_actual,
            versiones=versiones,
            total_credits=mandatory_total + elective_total,
            completed_credits=mandatory_completed + elective_completed,
            in_progress_credits=mandatory_in_progress + elective_in_progress,
            elective_banks=elective_banks,
            subjects=subjects,
        )
