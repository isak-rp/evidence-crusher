# Dataset curado mínimo (techsheet_v1)

Cada carpeta `case_XX` contiene un `expected_fields.json` con:

- `case_id`: UUID del expediente en tu base.
- `expected_fields`: campos esperados para validación.

Campos base usados por el evaluador:

- `start_date_real`
- `salary_sd`
- `termination_cause`
- `claimed_amount`
- `closure_offer`

Si `value` es `null`, el evaluador espera estado `MISSING`.
