# Prepare for Task

You are about to work on the Junjo AI Studio codebase to refactor from the existing architecture to "V4".

Follow these steps to prepare:

For the existing codebase:
1. Review the @README.md
2. Review the @AGENTS.md (architectural overview)
3. Review detailed documentation as needed:
   1. @TESTING.md - Contract testing, MSW integration tests, test fixtures
   2. @backend/app/database/README.md - Database architecture, Alembic migrations, autouse fixtures
4. Check the @docker-compose.yml along with each service's Dockerfile
   1. @ingestion/Dockerfile
   2. @frontend/Dockerfile
   3. @backend/Dockerfile
5. Review the github workflows inside @.github/workflows

For the refactor:
1. Review @REFACTOR_V4_ARCHITECTURE.md
2. Review @REFACTOR_V4_PLAN.md

Once you have thoroughly reviewed the documents, confirm your readiness outputting that you are ready to proceed with refactoring. You do not need to summarize or explain your understanding.

NOTES: Do not include simulated keys that could be detected by Gitleaks inside any planning docs or comments.
