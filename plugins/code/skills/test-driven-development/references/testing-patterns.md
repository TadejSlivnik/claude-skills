# Testing Patterns Reference

Quick reference for common testing patterns across the stack. Use alongside the `test-driven-development` skill.

The *patterns* here — Arrange-Act-Assert, behavior-focused naming, mocking only at boundaries, the anti-patterns — are universal and apply in any language or test runner. The *snippets* use a JavaScript toolchain (Jest/Vitest matchers, Testing Library, supertest, Playwright) because it's compact and widely readable. Each section notes the equivalent elsewhere: matcher APIs map to pytest/JUnit/RSpec/Go's `testing`; Testing Library ships for React, Vue, Svelte, and Angular with the same query-by-accessible-role philosophy; E2E concepts carry over to Cypress, Selenium, etc. Use whatever your stack provides — the structure stays the same.

## Table of Contents

- [Testing Patterns Reference](#testing-patterns-reference)
  - [Table of Contents](#table-of-contents)
  - [Test Structure (Arrange-Act-Assert)](#test-structure-arrange-act-assert)
  - [Test Naming Conventions](#test-naming-conventions)
  - [Common Assertions](#common-assertions)
  - [Mocking Patterns](#mocking-patterns)
    - [Mock Functions](#mock-functions)
    - [Mock Modules](#mock-modules)
    - [Mock at Boundaries Only](#mock-at-boundaries-only)
  - [Component Testing](#component-testing)
  - [API / Integration Testing](#api--integration-testing)
  - [E2E Testing](#e2e-testing)
  - [Test Anti-Patterns](#test-anti-patterns)

## Test Structure (Arrange-Act-Assert)

```typescript
it('describes expected behavior', () => {
  // Arrange: Set up test data and preconditions
  const input = { title: 'Test Task', priority: 'high' };

  // Act: Perform the action being tested
  const result = createTask(input);

  // Assert: Verify the outcome
  expect(result.title).toBe('Test Task');
  expect(result.priority).toBe('high');
  expect(result.status).toBe('pending');
});
```

## Test Naming Conventions

```typescript
// Pattern: [unit] [expected behavior] [condition]
describe('TaskService.createTask', () => {
  it('creates a task with default pending status', () => {});
  it('throws ValidationError when title is empty', () => {});
  it('trims whitespace from title', () => {});
  it('generates a unique ID for each task', () => {});
});
```

## Common Assertions

Jest/Vitest matchers shown — the *kinds* of assertion (equality, truthiness, numeric, string, collection, error, async) exist in every framework; only the spelling differs (pytest `assert`, JUnit `assertEquals`/AssertJ, RSpec `expect().to eq`, Go `if got != want`).

```typescript
// Equality
expect(result).toBe(expected);           // Strict equality (===)
expect(result).toEqual(expected);        // Deep equality (objects/arrays)
expect(result).toStrictEqual(expected);  // Deep equality + type matching

// Truthiness
expect(result).toBeTruthy();
expect(result).toBeFalsy();
expect(result).toBeNull();
expect(result).toBeDefined();
expect(result).toBeUndefined();

// Numbers
expect(result).toBeGreaterThan(5);
expect(result).toBeLessThanOrEqual(10);
expect(result).toBeCloseTo(0.3, 5);      // Floating point

// Strings
expect(result).toMatch(/pattern/);
expect(result).toContain('substring');

// Arrays / Objects
expect(array).toContain(item);
expect(array).toHaveLength(3);
expect(object).toHaveProperty('key', 'value');

// Errors
expect(() => fn()).toThrow();
expect(() => fn()).toThrow(ValidationError);
expect(() => fn()).toThrow('specific message');

// Async
await expect(asyncFn()).resolves.toBe(value);
await expect(asyncFn()).rejects.toThrow(Error);
```

## Mocking Patterns

Jest API shown (`jest.*`); Vitest is identical with `vi.*`, and other ecosystems have direct analogues (Python `unittest.mock`/`pytest-mock`, Java Mockito, Ruby RSpec mocks, Go testify/mock or hand-written interfaces). The principle — fake the dependency, assert on the interaction — is the same everywhere.

### Mock Functions

```typescript
const mockFn = jest.fn();
mockFn.mockReturnValue(42);
mockFn.mockResolvedValue({ data: 'test' });
mockFn.mockImplementation((x) => x * 2);

expect(mockFn).toHaveBeenCalled();
expect(mockFn).toHaveBeenCalledWith('arg1', 'arg2');
expect(mockFn).toHaveBeenCalledTimes(3);
```

### Mock Modules

```typescript
// Mock an entire module
jest.mock('./database', () => ({
  query: jest.fn().mockResolvedValue([{ id: 1, title: 'Test' }]),
}));

// Mock specific exports
jest.mock('./utils', () => ({
  ...jest.requireActual('./utils'),
  generateId: jest.fn().mockReturnValue('test-id'),
}));
```

### Mock at Boundaries Only

```
Mock these:                    Don't mock these:
├── Database calls             ├── Internal utility functions
├── HTTP requests              ├── Business logic
├── File system operations     ├── Data transformations
├── External API calls         ├── Validation functions
└── Time/Date (when needed)    └── Pure functions
```

## Component Testing

Testing Library shown for React (`@testing-library/react`); the same API and philosophy ship as `@testing-library/vue`, `-svelte`, and `-angular`. The golden rule is framework-independent: **query by accessible role/label, not by test IDs or CSS selectors** — your test then exercises the UI the way a user (and assistive tech) does.

```tsx
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

describe('TaskForm', () => {
  it('submits the form with entered data', async () => {
    const onSubmit = jest.fn();
    render(<TaskForm onSubmit={onSubmit} />);

    // Find elements by accessible role/label (not test IDs)
    await screen.findByRole('textbox', { name: /title/i });
    fireEvent.change(screen.getByRole('textbox', { name: /title/i }), {
      target: { value: 'New Task' },
    });
    fireEvent.click(screen.getByRole('button', { name: /create/i }));

    await waitFor(() => {
      expect(onSubmit).toHaveBeenCalledWith({ title: 'New Task' });
    });
  });

  it('shows validation error for empty title', async () => {
    render(<TaskForm onSubmit={jest.fn()} />);

    fireEvent.click(screen.getByRole('button', { name: /create/i }));

    expect(await screen.findByText(/title is required/i)).toBeInTheDocument();
  });
});
```

## API / Integration Testing

Drive the app through real HTTP and assert on status + body (supertest against an Express app shown). The pattern is server-framework-agnostic — use any in-process test client or HTTP library (FastAPI `TestClient`, Spring `MockMvc`, Rails integration tests, Go `httptest`, or a plain HTTP client against a running instance).

```typescript
import request from 'supertest';
import { app } from '../src/app';

describe('POST /api/tasks', () => {
  it('creates a task and returns 201', async () => {
    const response = await request(app)
      .post('/api/tasks')
      .send({ title: 'Test Task' })
      .set('Authorization', `Bearer ${testToken}`)
      .expect(201);

    expect(response.body).toMatchObject({
      id: expect.any(String),
      title: 'Test Task',
      status: 'pending',
    });
  });

  it('returns 422 for invalid input', async () => {
    const response = await request(app)
      .post('/api/tasks')
      .send({ title: '' })
      .set('Authorization', `Bearer ${testToken}`)
      .expect(422);

    expect(response.body.error.code).toBe('VALIDATION_ERROR');
  });

  it('returns 401 without authentication', async () => {
    await request(app)
      .post('/api/tasks')
      .send({ title: 'Test' })
      .expect(401);
  });
});
```

## E2E Testing

Playwright shown; Cypress, Selenium/WebDriver, and others express the same flow. Whatever the tool, the principle holds: **drive the real browser and locate elements by user-visible text / accessible attributes, not brittle CSS or XPath.**

```typescript
import { test, expect } from '@playwright/test';

test('user can create and complete a task', async ({ page }) => {
  // Navigate and authenticate
  await page.goto('/');
  await page.fill('[name="email"]', 'test@example.com');
  await page.fill('[name="password"]', 'testpass123');
  await page.click('button:has-text("Log in")');

  // Create a task
  await page.click('button:has-text("New Task")');
  await page.fill('[name="title"]', 'Buy groceries');
  await page.click('button:has-text("Create")');

  // Verify task appears
  await expect(page.locator('text=Buy groceries')).toBeVisible();

  // Complete the task
  await page.click('[aria-label="Complete Buy groceries"]');
  await expect(page.locator('text=Buy groceries')).toHaveCSS(
    'text-decoration-line', 'line-through'
  );
});
```

## Test Anti-Patterns

| Anti-Pattern                   | Problem                        | Better Approach            |
| ------------------------------ | ------------------------------ | -------------------------- |
| Testing implementation details | Breaks on refactor             | Test inputs/outputs        |
| Snapshot everything            | No one reviews snapshot diffs  | Assert specific values     |
| Shared mutable state           | Tests pollute each other       | Setup/teardown per test    |
| Testing third-party code       | Wastes time, not your bug      | Mock the boundary          |
| Skipping tests to pass CI      | Hides real bugs                | Fix or delete the test     |
| Using `test.skip` permanently  | Dead code                      | Remove or fix it           |
| Overly broad assertions        | Doesn't catch regressions      | Be specific                |
| No async error handling        | Swallowed errors, false passes | Always `await` async tests |