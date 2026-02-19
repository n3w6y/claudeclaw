# Security Rules

- NEVER display, echo, or print private keys, API keys, passwords, or secrets
- When asked to verify a key exists, only confirm "yes it's set" - never show the value
- Mask sensitive values: show only first 4 and last 4 characters with *** in between
- Treat any environment variable containing KEY, SECRET, TOKEN, PASSWORD, or PRIVATE as sensitive
