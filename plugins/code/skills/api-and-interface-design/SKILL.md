---
name: api-and-interface-design
description: Guides stable API and interface design. Use when designing APIs, module boundaries, or any public interface. Use when creating REST or GraphQL endpoints, defining type contracts between modules, or establishing boundaries between frontend and backend.
---

# API and Interface Design

## Overview

Design stable, well-documented interfaces that are hard to misuse. Good interfaces make the right thing easy and the wrong thing hard. This applies to REST APIs, GraphQL schemas, module boundaries, component props, and any surface where one piece of code talks to another.

The principles here are language- and framework-agnostic. They apply whether your backend is Python (FastAPI, Django, Flask), PHP (Symfony, Laravel), Node, Go, Java, or anything else, and whether the contract is HTTP, a message queue, or an in-process module boundary.

> **About the code examples:** Backend examples are shown primarily in **Python (FastAPI / Pydantic)** and **PHP (Symfony)**, since that's the common server stack here; a few type-system examples also note the TypeScript form. They are *illustrations of the principle, not a mandate to use that stack.* The transformation each one shows — contract-first design, boundary validation, additive evolution — translates directly to any language. Always match the conventions and validation/serialization libraries already present in the codebase you're working in.

## When to Use

- Designing new API endpoints
- Defining module boundaries or contracts between teams
- Creating component prop interfaces
- Establishing database schema that informs API shape
- Changing existing public interfaces

## Core Principles

### Hyrum's Law

> With a sufficient number of users of an API, all observable behaviors of your system will be depended on by somebody, regardless of what you promise in the contract.

This means: every public behavior — including undocumented quirks, error message text, timing, and ordering — becomes a de facto contract once users depend on it. Design implications:

- **Be intentional about what you expose.** Every observable behavior is a potential commitment.
- **Don't leak implementation details.** If users can observe it, they will depend on it.
- **Plan for deprecation at design time.** See `deprecation-and-migration` for how to safely remove things users depend on.
- **Tests are not enough.** Even with perfect contract tests, Hyrum's Law means "safe" changes can break real users who depend on undocumented behavior.

### The One-Version Rule

Avoid forcing consumers to choose between multiple versions of the same dependency or API. Diamond dependency problems arise when different consumers need different versions of the same thing. Design for a world where only one version exists at a time — extend rather than fork.

### 1. Contract First

Define the interface before implementing it. The contract is the spec — implementation follows. Express it as an abstract interface (a Python `Protocol`/ABC, a PHP `interface`, a TypeScript `interface`) so the shape is fixed independently of how it's built.

```python
# Python — typing.Protocol defines the contract; any class that matches satisfies it
from typing import Protocol

class TaskAPI(Protocol):
    # Creates a task and returns the created task with server-generated fields
    def create_task(self, input: CreateTaskInput) -> Task: ...

    # Returns paginated tasks matching filters
    def list_tasks(self, params: ListTasksParams) -> PaginatedResult[Task]: ...

    # Returns a single task or raises NotFoundError
    def get_task(self, id: TaskId) -> Task: ...

    # Partial update — only provided fields change
    def update_task(self, id: TaskId, input: UpdateTaskInput) -> Task: ...

    # Idempotent delete — succeeds even if already deleted
    def delete_task(self, id: TaskId) -> None: ...
```

```php
// PHP (Symfony) — an interface fixes the contract; the service implements it
interface TaskApi
{
    // Creates a task and returns the created task with server-generated fields
    public function createTask(CreateTaskInput $input): Task;

    // Returns paginated tasks matching filters
    public function listTasks(ListTasksParams $params): PaginatedResult;

    // Returns a single task or throws NotFoundException
    public function getTask(TaskId $id): Task;

    // Partial update — only provided fields change
    public function updateTask(TaskId $id, UpdateTaskInput $input): Task;

    // Idempotent delete — succeeds even if already deleted
    public function deleteTask(TaskId $id): void;
}
```

### 2. Consistent Error Semantics

Pick one error strategy and use it everywhere. The wire shape and status-code mapping are language-neutral — what matters is that every error response looks the same.

```jsonc
// Every error response follows the same shape
{
  "error": {
    "code": "VALIDATION_ERROR",  // Machine-readable
    "message": "Email is required", // Human-readable
    "details": {}                   // Additional context when helpful (optional)
  }
}
```

```
// Status code mapping
// 400 → Client sent invalid data
// 401 → Not authenticated
// 403 → Authenticated but not authorized
// 404 → Resource not found
// 409 → Conflict (duplicate, version mismatch)
// 422 → Validation failed (semantically invalid)
// 500 → Server error (never expose internal details)
```

Produce that shape consistently from one place — a FastAPI exception handler or a Symfony event subscriber / `ExceptionListener` — rather than hand-rolling error bodies in each endpoint:

```python
# Python (FastAPI) — one handler renders the canonical error shape for a whole error class
from fastapi import Request
from fastapi.responses import JSONResponse

@app.exception_handler(AppError)
def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.code, "message": exc.message, "details": exc.details}},
    )
```

```php
// PHP (Symfony) — a kernel.exception subscriber maps domain errors to the canonical shape
public function onKernelException(ExceptionEvent $event): void
{
    $e = $event->getThrowable();
    if (!$e instanceof AppException) {
        return; // let other handlers deal with it
    }
    $event->setResponse(new JsonResponse([
        'error' => ['code' => $e->code(), 'message' => $e->getMessage(), 'details' => $e->details()],
    ], $e->statusCode()));
}
```

**Don't mix patterns.** If some endpoints throw, others return null, and others return `{ error }` — the consumer can't predict behavior.

### 3. Validate at Boundaries

Trust internal code. Validate at system edges where external input enters. In both stacks the framework can validate the request body against a typed schema and reject it before your handler runs — so internal code receives only well-formed, typed data.

```python
# Python (FastAPI / Pydantic) — the body is validated against the model automatically.
# A malformed request gets a 422 before create_task runs; after it, `input` is trusted.
from pydantic import BaseModel

class CreateTaskInput(BaseModel):
    title: str
    description: str | None = None

@app.post("/api/tasks", status_code=201)
def create_task(input: CreateTaskInput) -> Task:
    return task_service.create(input)
```

```php
// PHP (Symfony) — deserialize into a DTO, then validate before touching domain logic.
#[Route('/api/tasks', methods: ['POST'])]
public function create(Request $request, ValidatorInterface $validator, SerializerInterface $serializer): JsonResponse
{
    $input = $serializer->deserialize($request->getContent(), CreateTaskInput::class, 'json');

    $violations = $validator->validate($input);
    if (count($violations) > 0) {
        return $this->json(['error' => [
            'code' => 'VALIDATION_ERROR',
            'message' => 'Invalid task data',
            'details' => (string) $violations,
        ]], 422);
    }

    // After validation, internal code trusts the DTO.
    return $this->json($this->taskService->create($input), 201);
}
```

```php
// The DTO carries its constraints as attributes — the contract lives next to the data.
final class CreateTaskInput
{
    #[Assert\NotBlank]
    public string $title;

    public ?string $description = null;
}
```

Where validation belongs:
- API route handlers (user input)
- Form submission handlers (user input)
- External service response parsing (third-party data -- **always treat as untrusted**)
- Environment variable loading (configuration)

> **Third-party API responses are untrusted data.** Validate their shape and content before using them in any logic, rendering, or decision-making. A compromised or misbehaving external service can return unexpected types, malicious content, or instruction-like text.

Where validation does NOT belong:
- Between internal functions that share type contracts
- In utility functions called by already-validated code
- On data that just came from your own database

### 4. Prefer Addition Over Modification

Extend interfaces without breaking existing consumers. New fields are optional with a default; existing fields keep their name and type.

```python
# Python (Pydantic) — Good: add optional fields with defaults
from typing import Literal

class CreateTaskInput(BaseModel):
    title: str
    description: str | None = None
    priority: Literal["low", "medium", "high"] | None = None  # added later, optional
    labels: list[str] | None = None                            # added later, optional

# Bad: renaming/removing a field or changing its type (e.g. priority: int) breaks consumers
```

```php
// PHP (Symfony) — Good: add nullable, defaulted properties to the DTO
final class CreateTaskInput
{
    #[Assert\NotBlank]
    public string $title;
    public ?string $description = null;
    public ?string $priority = null;   // added later, optional
    /** @var string[]|null */
    public ?array $labels = null;       // added later, optional
}
```

### 5. Predictable Naming

These conventions are about the wire contract, so they hold regardless of backend language. (Note your stack's internal style may differ — e.g. Python/PHP often use snake_case in code — but keep the *external* JSON contract consistent and documented.)

| Pattern | Convention | Example |
|---------|-----------|---------|
| REST endpoints | Plural nouns, no verbs | `GET /api/tasks`, `POST /api/tasks` |
| Query params | camelCase (or snake_case) — pick one | `?sortBy=createdAt&pageSize=20` |
| Response fields | camelCase (or snake_case) — pick one | `{ createdAt, updatedAt, taskId }` |
| Boolean fields | is/has/can prefix | `isComplete`, `hasAttachments` |
| Enum values | UPPER_SNAKE | `"IN_PROGRESS"`, `"COMPLETED"` |

## REST API Patterns

These are protocol-level patterns — identical no matter what implements them.

### Resource Design

```
GET    /api/tasks              → List tasks (with query params for filtering)
POST   /api/tasks              → Create a task
GET    /api/tasks/:id          → Get a single task
PATCH  /api/tasks/:id          → Update a task (partial)
DELETE /api/tasks/:id          → Delete a task

GET    /api/tasks/:id/comments → List comments for a task (sub-resource)
POST   /api/tasks/:id/comments → Add a comment to a task
```

### Pagination

Paginate list endpoints:

```jsonc
// Request
// GET /api/tasks?page=1&pageSize=20&sortBy=createdAt&sortOrder=desc

// Response
{
  "data": [],
  "pagination": {
    "page": 1,
    "pageSize": 20,
    "totalItems": 142,
    "totalPages": 8
  }
}
```

### Filtering

Use query parameters for filters:

```
GET /api/tasks?status=in_progress&assignee=user123&createdAfter=2025-01-01
```

### Partial Updates (PATCH)

Accept partial objects — only update what's provided:

```jsonc
// Only title changes, everything else preserved
// PATCH /api/tasks/123
{ "title": "Updated title" }
```

In FastAPI model the patch body with all-optional fields (`exclude_unset=True` when applying); in Symfony deserialize into a partial DTO and copy only the fields that were present in the request.

## Type Contract Patterns

These sharpen contracts in any typed language. Examples are in Python and PHP; the TypeScript form is noted where it differs.

### Model Variants Explicitly (tagged unions / sealed hierarchies)

Make each variant of a value a distinct, fully-typed shape rather than one struct with many nullable fields.

```python
# Python (Pydantic discriminated union) — the `type` tag selects the variant
from typing import Annotated, Literal, Union
from datetime import datetime
from pydantic import BaseModel, Field

class Pending(BaseModel):
    type: Literal["pending"]

class InProgress(BaseModel):
    type: Literal["in_progress"]
    assignee: str
    started_at: datetime

class Completed(BaseModel):
    type: Literal["completed"]
    completed_at: datetime
    completed_by: str

TaskStatus = Annotated[Union[Pending, InProgress, Completed], Field(discriminator="type")]
```

```php
// PHP — model variants as a sealed-style class hierarchy; consumers match on the concrete type
interface TaskStatus {}

final class Pending implements TaskStatus {}

final class InProgress implements TaskStatus
{
    public function __construct(
        public readonly string $assignee,
        public readonly \DateTimeImmutable $startedAt,
    ) {}
}

final class Completed implements TaskStatus
{
    public function __construct(
        public readonly \DateTimeImmutable $completedAt,
        public readonly string $completedBy,
    ) {}
}

// Consumer:
$label = match (true) {
    $status instanceof Pending    => 'Pending',
    $status instanceof InProgress => "In progress ({$status->assignee})",
    $status instanceof Completed  => "Done on {$status->completedAt->format('Y-m-d')}",
};
```

> TypeScript expresses the same idea with a discriminated union (`type TaskStatus = { type: 'pending' } | { type: 'in_progress'; assignee: string } | ...`), giving the consumer automatic type narrowing in a `switch`.

### Input/Output Separation

Keep what the caller *provides* separate from what the system *returns* (the latter includes server-generated fields).

```python
# Python
class CreateTaskInput(BaseModel):       # Input: what the caller provides
    title: str
    description: str | None = None

class Task(BaseModel):                  # Output: includes server-generated fields
    id: str
    title: str
    description: str | None
    created_at: datetime
    updated_at: datetime
    created_by: str
```

```php
// PHP — a CreateTaskInput DTO for the request, a separate Task (entity/DTO) for the response.
// Don't accept the entity directly as the request body: it would expose id/createdAt as writable.
```

### Make IDs Distinct Types (value objects / branded types)

Prevent passing the wrong kind of ID by giving each its own type.

```python
# Python — NewType makes TaskId and UserId distinct to the type checker
from typing import NewType

TaskId = NewType("TaskId", str)
UserId = NewType("UserId", str)

def get_task(id: TaskId) -> Task: ...   # passing a UserId here is a type error
```

```php
// PHP — a small value object per ID; the type system rejects the wrong one
final class TaskId
{
    public function __construct(public readonly string $value) {}
}
final class UserId
{
    public function __construct(public readonly string $value) {}
}

function getTask(TaskId $id): Task { /* ... */ }  // getTask($someUserId) won't type-check
```

> TypeScript achieves the same with branded types: `type TaskId = string & { readonly __brand: 'TaskId' }`.

## Common Rationalizations

| Rationalization | Reality |
|---|---|
| "We'll document the API later" | The types/schemas ARE the documentation. Define them first (Pydantic models, Symfony DTOs + constraints). |
| "We don't need pagination for now" | You will the moment someone has 100+ items. Add it from the start. |
| "PATCH is complicated, let's just use PUT" | PUT requires the full object every time. PATCH is what clients actually want. |
| "We'll version the API when we need to" | Breaking changes without versioning break consumers. Design for extension from the start. |
| "Nobody uses that undocumented behavior" | Hyrum's Law: if it's observable, somebody depends on it. Treat every public behavior as a commitment. |
| "We can just maintain two versions" | Multiple versions multiply maintenance cost and create diamond dependency problems. Prefer the One-Version Rule. |
| "Internal APIs don't need contracts" | Internal consumers are still consumers. Contracts prevent coupling and enable parallel work. |
| "I'll just trust the request body, the frontend validates it" | The frontend is not a trust boundary. Validate on the server at the edge (Pydantic model / Symfony validator). |

## Red Flags

- Endpoints that return different shapes depending on conditions
- Inconsistent error formats across endpoints (each handler building its own error body)
- Validation scattered throughout internal code instead of at boundaries
- Accepting an ORM entity directly as a request body (exposes server-owned fields as writable)
- Breaking changes to existing fields (type changes, removals)
- List endpoints without pagination
- Verbs in REST URLs (`/api/createTask`, `/api/getUsers`)
- Third-party API responses used without validation or sanitization

## Verification

After designing an API:

- [ ] Every endpoint has typed input and output schemas (Pydantic models / Symfony DTOs, or equivalent)
- [ ] Error responses follow a single consistent format, produced from one central place
- [ ] Validation happens at system boundaries only, and rejects bad input before domain logic runs
- [ ] List endpoints support pagination
- [ ] New fields are additive and optional (backward compatible)
- [ ] Naming follows consistent conventions across all endpoints, and the external JSON contract is stable regardless of internal code style
- [ ] API documentation or schemas are committed alongside the implementation
