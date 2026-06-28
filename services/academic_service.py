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

        # Progreso hacia el grado: las obligatorias cuentan completas, pero las
        # electivas solo cuentan hasta lo que el programa exige (total - obligatorias).
        # Así un estudiante que cursó electivas de más no supera el 100%.
        obligatorias_total = sum(s.credits for s in subjects if s.obligatoria)
        obligatorias_passed = sum(s.credits for s in subjects if s.obligatoria and s.cursada)
        electives_passed = sum(s.credits for s in subjects if not s.obligatoria and s.cursada)
        electives_in_progress = sum(
            s.credits for s in subjects if not s.obligatoria and s.cursando and not s.cursada)
        electives_required = max(0, total_credits - obligatorias_total)
        # ¿Ya se cubrió el requisito de electivas? (cursum no da el cupo por banco,
        # así que usamos el agregado: aprobadas + en curso >= requeridas).
        electives_satisfied = electives_passed + electives_in_progress >= electives_required

        enriched: list[Subject] = []
        for s in subjects:
            if s.cursada:
                status = "passed"
            elif s.cursando:
                status = "in_progress"
            elif all(p in unlocked for p in s.prerequisites):
                # Una electiva solo está "disponible" si aún hacen falta créditos
                # de electivas; si el requisito ya se cubrió, no se necesita.
                if not s.obligatoria and electives_satisfied:
                    status = "not_needed"
                else:
                    status = "available"
            else:
                status = "locked"
            enriched.append(s.model_copy(update={"status": status}))

        completed_credits = sum(s.credits for s in enriched if s.cursada)
        in_progress_credits = sum(s.credits for s in enriched if s.cursando and not s.cursada)
        progress_credits = min(
            total_credits,
            obligatorias_passed + min(electives_passed, electives_required),
        )
        graduated = progress_credits >= total_credits

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
            progress_credits=progress_credits,
            in_progress_credits=in_progress_credits,
            graduated=graduated,
            subjects=enriched,
            elective_banks=elective_banks,
        )
