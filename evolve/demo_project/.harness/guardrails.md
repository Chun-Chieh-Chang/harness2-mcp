# Guardrails
- Only touch files inside this project.
- Never modify .harness/ (the evolution system manages it).
- read_file target file before write_file if extending existing code, to preserve unrelated content and reduce regressions.
- Before write_file to an existing test/source file, read the target file to confirm whether the required symbols already exist; if they do, skip writing and just run tests to verify.
- - For numeric assertions on floating-point results, use assertAlmostEqual or a tolerance check instead of ==.
