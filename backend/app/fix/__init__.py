"""Human-gated fix flow: an agent proposes a code fix in a sandbox, a human approves it by hash.

Current level is propose-only (F1): approval is recorded against the exact diff hash, but nothing
is applied to any real repository. See `app/fix/apply.py` for the reserved, disabled apply step.
"""
