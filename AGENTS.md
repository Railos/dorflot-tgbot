# AGENTS.md

## Purpose
Provide consistent project guidance for building and maintaining a professional Telegram bot in this repository.

## Project Overview
- Goal: A reliable, secure Telegram bot with clear workflows, solid error handling, and maintainable code.
- Runtime: Python (see `requirements.txt`).
- Structure: Application code lives in `app/`, templates in `templates/`, persistent data in `storage/`.

## Behavior Guidelines
- Treat user inputs as untrusted; validate and sanitize early.
- Prefer explicit, user-friendly errors over silent failures.
- Keep responses concise; guide users with clear next steps.
- Avoid leaking secrets; never echo tokens or private config.

## Architecture Notes
- Handlers:
  - Keep Telegram update handlers small and focused.
  - Offload heavy logic to `app/utils.py` or new service modules.
- State:
  - Use a single source of truth for user/session state.
  - Document any state transitions and expected inputs.
- Templates:
  - Reuse templates for long or repetitive messages.

## Reliability and Error Handling
- Wrap all handler entry points with try/except and log exceptions.
- Return a safe fallback message on unexpected errors.
- Validate API responses before using them.

## Security
- Load secrets from environment variables; never hardcode tokens.
- Do not log sensitive data (tokens, user PII).
- Rate-limit or debounce user-triggered heavy operations.

## Logging
- Log handler start/end with user and update identifiers.
- Log failures with enough context to reproduce (no secrets).
- Use consistent log levels: INFO for normal flow, WARNING for recoverable issues, ERROR for failures.

## Testing
- Add unit tests for parsing/validation and utility functions.
- Add integration tests for handler flows when feasible.
- Mock Telegram API calls in tests.

## Coding Standards
- Keep functions short; prefer small, composable helpers.
- Use type hints in new or refactored code.
- Prefer pure functions in utilities when practical.
- Document non-obvious logic with brief comments.

## Release Checklist
- Verify `.env` includes required variables and sample docs exist.
- Run tests locally.
- Smoke-test bot commands in a Telegram chat.

