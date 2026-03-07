# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | :white_check_mark: |

## Reporting a Vulnerability

If you discover a security vulnerability, please report it responsibly:

1. **Do not** open a public issue.
2. Send an email describing the vulnerability to the repository maintainer.
3. Include steps to reproduce the issue if possible.
4. You will receive a response within 48 hours acknowledging receipt.

## Security Measures

- Passwords are hashed with bcrypt
- Sensitive configuration values are encrypted at rest (Fernet)
- CSRF protection on all form submissions
- Input validation via Pydantic
- File upload validation (type, size)
- SSRF protection for URL-based imports
- Audit logging for administrative actions
- Non-root container execution
- No debug mode in production
