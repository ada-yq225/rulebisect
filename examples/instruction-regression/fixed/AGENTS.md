Lowercase labels in both modules and preserve internal whitespace.

In `labels.py`, strip surrounding whitespace for modern clients. In
`compatibility.py`, preserve the original leading and trailing whitespace for
legacy clients.
