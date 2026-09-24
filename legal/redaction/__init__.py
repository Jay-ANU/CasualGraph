"""Local de-identification (脱敏) for uploaded documents.

Nothing in this package may call a remote model or embedding API: detection runs
on the server with rules, contract-structure heuristics and local NLP only.
"""
