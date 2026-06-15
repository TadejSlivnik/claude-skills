---
name: security-and-hardening
description: Hardens code against vulnerabilities. Use when handling user input, authentication, data storage, or external integrations. Use when building any feature that accepts untrusted data, manages user sessions, or interacts with third-party services.
---

# Security and Hardening

## Overview

Security-first development practices for applications and services. Treat every external input as hostile, every secret as sacred, and every authorization check as mandatory. Security isn't a phase — it's a constraint on every line of code that touches user data, authentication, or external systems.

> **About the code examples:** Examples are written as language-neutral pseudocode (with a few illustrative library/tool names). They are *illustrations of the principle, not a mandate to use a particular language, framework, or library.* Each pattern names the underlying concept — parameterized queries, output encoding, schema validation, rate limiting — so you can apply it with your own stack's equivalent. Always match the conventions already present in the codebase you're working in.

## When to Use

- Building anything that accepts user input
- Implementing authentication or authorization
- Storing or transmitting sensitive data
- Integrating with external APIs or services
- Adding file uploads, webhooks, or callbacks
- Handling payment or PII data

## The Three-Tier Boundary System

### Always Do (No Exceptions)

- **Validate all external input** at the system boundary (API routes, form handlers)
- **Parameterize all database queries** — never concatenate user input into SQL
- **Encode output** to prevent XSS (use framework auto-escaping, don't bypass it)
- **Use HTTPS** for all external communication
- **Hash passwords** with bcrypt/scrypt/argon2 (never store plaintext)
- **Set security headers** (CSP, HSTS, X-Frame-Options, X-Content-Type-Options)
- **Use httpOnly, secure, sameSite cookies** for sessions (or the equivalent secure-token mechanism for your platform)
- **Audit dependencies** with your ecosystem's audit tool before every release

### Ask First (Requires Human Approval)

- Adding new authentication flows or changing auth logic
- Storing new categories of sensitive data (PII, payment info)
- Adding new external service integrations
- Changing CORS configuration
- Adding file upload handlers
- Modifying rate limiting or throttling
- Granting elevated permissions or roles

### Never Do

- **Never commit secrets** to version control (API keys, passwords, tokens)
- **Never log sensitive data** (passwords, tokens, full credit card numbers)
- **Never trust client-side validation** as a security boundary
- **Never disable security headers** for convenience
- **Never feed user-provided data to dynamic code execution** (`eval` and friends) or raw markup/HTML sinks
- **Never store sessions in client-accessible storage** (e.g. browser localStorage for auth tokens)
- **Never expose stack traces** or internal error details to users

## OWASP Top 10 Prevention

### 1. Injection (SQL, NoSQL, OS Command)

```
# BAD: SQL injection via string concatenation
query = "SELECT * FROM users WHERE id = '" + userId + "'"

# GOOD: Parameterized query — user input is bound, never interpolated
user = db.query("SELECT * FROM users WHERE id = ?", [userId])

# GOOD: A query builder / ORM that parameterizes input for you
user = users.findUnique(where = { id: userId })
```

### 2. Broken Authentication

```
# Password hashing — use a slow, salted KDF (bcrypt / scrypt / argon2)
SALT_ROUNDS = 12
hashedPassword = hash(plaintext, SALT_ROUNDS)
isValid       = verify(plaintext, hashedPassword)

# Session cookie configuration
configureSession({
    secret: env["SESSION_SECRET"],   # From environment, not code
    cookie: {
        httpOnly: true,    # Not accessible to client-side scripts
        secure:   true,    # Sent over HTTPS only
        sameSite: "lax",   # CSRF protection
        maxAge:   24 hours,
    },
})
```

### 3. Cross-Site Scripting (XSS)

```
# BAD: Rendering user input into a raw markup/HTML sink
element.rawHtml = userInput

# GOOD: Render through the framework's auto-escaping output path
#       (most templating/UI layers escape interpolated values by default)
render(text = userInput)

# If you MUST render user-supplied HTML, sanitize with an allowlist first
clean = htmlSanitizer.sanitize(userInput)
```

### 4. Broken Access Control

```
# Always check authorization, not just authentication.
# Handler runs only after the request is authenticated.
handler updateTask(request):
    task = taskService.findById(request.params.id)

    # Check that the authenticated user owns this resource
    if task.ownerId != request.user.id:
        return respond(403, { error: { code: "FORBIDDEN",
                                       message: "Not authorized to modify this task" } })

    # Proceed with update
    updated = taskService.update(request.params.id, request.body)
    return respond(200, updated)
```

### 5. Security Misconfiguration

```
# Apply standard security response headers
#   (HSTS, X-Frame-Options, X-Content-Type-Options, etc.)
useSecurityHeaders()

# Content Security Policy — allowlist where resources may load from
setContentSecurityPolicy({
    defaultSrc: ["self"],
    scriptSrc:  ["self"],
    styleSrc:   ["self", "unsafe-inline"],   # Tighten if possible
    imgSrc:     ["self", "data:", "https:"],
    connectSrc: ["self"],
})

# CORS — restrict to known origins (never a wildcard with credentials)
setCors({
    origin:      env["ALLOWED_ORIGINS"].split(",") or ["https://app.example.com"],
    credentials: true,
})
```

### 6. Sensitive Data Exposure

```
# Never return sensitive fields in API responses — allowlist what's public
function sanitizeUser(user):
    return pick(user, ["id", "name", "email"])   # omit passwordHash, resetToken, ...

# Use environment/secret store for secrets, never hard-code them
API_KEY = env["PAYMENT_API_KEY"]
if API_KEY is missing:
    fail("PAYMENT_API_KEY not configured")
```

## Input Validation Patterns

### Schema Validation at Boundaries

```
# Declare a schema describing exactly what valid input looks like
CreateTaskSchema = schema({
    title:       string, required, length 1..200, trimmed,
    description: string, optional, max length 2000,
    priority:    one_of("low", "medium", "high"), default "medium",
    dueDate:     timestamp, optional,
})

# Validate at the boundary (the request handler), before any business logic
handler createTask(request):
    result = CreateTaskSchema.validate(request.body)
    if not result.ok:
        return respond(422, { error: { code: "VALIDATION_ERROR",
                                       message: "Invalid input",
                                       details: result.errors } })
    # result.value is now validated and safe to use
    task = taskService.create(result.value)
    return respond(201, task)
```

### File Upload Safety

```
# Restrict file types and sizes
ALLOWED_TYPES = ["image/jpeg", "image/png", "image/webp"]
MAX_SIZE      = 5 MB

function validateUpload(file):
    if file.mimetype not in ALLOWED_TYPES:
        fail("File type not allowed")
    if file.size > MAX_SIZE:
        fail("File too large (max 5MB)")
    # Don't trust the file extension — inspect magic bytes if critical
```

## Triaging Dependency Audit Results

Not all audit findings require immediate action. Use this decision tree:

```
A dependency audit reports a vulnerability
├── Severity: critical or high
│   ├── Is the vulnerable code reachable in your app?
│   │   ├── YES --> Fix immediately (update, patch, or replace the dependency)
│   │   └── NO (dev-only dep, unused code path) --> Fix soon, but not a blocker
│   └── Is a fix available?
│       ├── YES --> Update to the patched version
│       └── NO --> Check for workarounds, consider replacing the dependency, or add to allowlist with a review date
├── Severity: moderate
│   ├── Reachable in production? --> Fix in the next release cycle
│   └── Dev-only? --> Fix when convenient, track in backlog
└── Severity: low
    └── Track and fix during regular dependency updates
```

**Key questions:**
- Is the vulnerable function actually called in your code path?
- Is the dependency a runtime dependency or dev-only?
- Is the vulnerability exploitable given your deployment context (e.g., a server-side vulnerability in a client-only app)?

When you defer a fix, document the reason and set a review date.

## Rate Limiting

```
# General API rate limit
rateLimit(path = "/api/", {
    window: 15 minutes,
    max:    100,            # 100 requests per window per client
})

# Stricter limit for auth endpoints (slows credential-stuffing/brute force)
rateLimit(path = "/api/auth/", {
    window: 15 minutes,
    max:    10,             # 10 attempts per 15 minutes
})
```

## Secrets Management

```
.env files:
  ├── .env.example  → Committed (template with placeholder values)
  ├── .env          → NOT committed (contains real secrets)
  └── .env.local    → NOT committed (local overrides)

.gitignore must include:
  .env
  .env.local
  .env.*.local
  *.pem
  *.key
```

**Always check before committing:**
```bash
# Check for accidentally staged secrets
git diff --cached | grep -i "password\|secret\|api_key\|token"
```

## Security Review Checklist

```markdown
### Authentication
- [ ] Passwords hashed with bcrypt/scrypt/argon2 (salt rounds ≥ 12)
- [ ] Session tokens are httpOnly, secure, sameSite
- [ ] Login has rate limiting
- [ ] Password reset tokens expire

### Authorization
- [ ] Every endpoint checks user permissions
- [ ] Users can only access their own resources
- [ ] Admin actions require admin role verification

### Input
- [ ] All user input validated at the boundary
- [ ] SQL queries are parameterized
- [ ] HTML output is encoded/escaped

### Data
- [ ] No secrets in code or version control
- [ ] Sensitive fields excluded from API responses
- [ ] PII encrypted at rest (if applicable)

### Infrastructure
- [ ] Security headers configured (CSP, HSTS, etc.)
- [ ] CORS restricted to known origins
- [ ] Dependencies audited for vulnerabilities
- [ ] Error messages don't expose internals
```
## See Also

For detailed security checklists and pre-commit verification steps, see `references/security-checklist.md`.

## Common Rationalizations

| Rationalization | Reality |
|---|---|
| "This is an internal tool, security doesn't matter" | Internal tools get compromised. Attackers target the weakest link. |
| "We'll add security later" | Security retrofitting is 10x harder than building it in. Add it now. |
| "No one would try to exploit this" | Automated scanners will find it. Security by obscurity is not security. |
| "The framework handles security" | Frameworks provide tools, not guarantees. You still need to use them correctly. |
| "It's just a prototype" | Prototypes become production. Security habits from day one. |

## Red Flags

- User input passed directly to database queries, shell commands, or HTML rendering
- Secrets in source code or commit history
- API endpoints without authentication or authorization checks
- Missing CORS configuration or wildcard (`*`) origins
- No rate limiting on authentication endpoints
- Stack traces or internal errors exposed to users
- Dependencies with known critical vulnerabilities

## Verification

After implementing security-relevant code:

- [ ] Dependency audit shows no critical or high vulnerabilities
- [ ] No secrets in source code or git history
- [ ] All user input validated at system boundaries
- [ ] Authentication and authorization checked on every protected endpoint
- [ ] Security headers present in response (inspect the response headers)
- [ ] Error responses don't expose internal details
- [ ] Rate limiting active on auth endpoints