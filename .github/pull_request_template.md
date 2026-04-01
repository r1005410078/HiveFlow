## Summary

- What changed?
- Why this change?

## Architecture Checklist (Required)

- [ ] I read `AGENTS.md` before coding.
- [ ] I did not put business logic in `quant/src/interfaces/http`.
- [ ] Dependency direction remains `interfaces -> application -> domain`.
- [ ] `application` does not import FastAPI/framework concerns.
- [ ] Rust CLI layering remains valid (`cmd -> application -> domain`, no `cmd -> infrastructure`).
- [ ] I added/updated tests for changed behavior.
- [ ] Commit messages follow `type: description` (`feat|fix|refactor|test|docs|chore`).
- [ ] I ran `make architecture-check` and `make check`.

## Risk & Rollback

- Main risks:
- Rollback plan:
