# Conventions for this repository

These rules apply to every change, however small.

- Every public function in `textutils.py` has a docstring.
- Every public function is listed in `__all__` in `textutils.py`, kept in alphabetical order.
- Every user-visible change gets a bullet under `## Unreleased` in `CHANGES.md`.
  Mention the function name in backticks. Never edit released sections.
