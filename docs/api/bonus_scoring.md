# Bonus scoring API

`bonus_scoring.py` contains the canonical, deterministic scoring policy used by all CSV serializers.

## Public helpers

- `number(value)`: parse a finite number or return `None`.
- `score_bonus(...)`: calculate effective withdrawal minimum, observed/imputed maximum withdrawal and rollover, legacy and current weighted scores, rollover burden, confidence, and status/source metadata.

Unknown rollover is not silently treated as zero. Missing inputs are either imputed from supplied site/dataset context or left provisional, with the source and confidence recorded in the result.

See [bonus_scoring.py](../../bonus_scoring.py).
