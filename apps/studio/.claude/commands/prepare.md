# Prepare for Task

You are about to work on the Junjo AI Studio codebase. Follow these steps to prepare:

1. Review the @README.md
2. Review the @AGENTS.md (architectural overview)
3. ARD documents
   1. `ingestion/adr/001-segmented-wal-architecture.md`
4. Review detailed documentation as needed:
   1. @TESTING.md - Contract testing, MSW integration tests, test fixtures
   2. @backend/app/database/README.md - Database architecture, Alembic migrations, autouse fixtures
5. Check the @docker-compose.yml along with each service's Dockerfile
   1. @ingestion/Dockerfile
   2. @frontend/Dockerfile
   3. @backend/Dockerfile
6. Review the github workflows inside @.github/workflows
7. Once you have thoroughly reviewed the documents, confirm your readiness outputting that you are ready to proceed with a task with a very simple explanation for how the data flow works.

NOTES: Do not include simulated keys that could be detected by Gitleaks inside any planning docs or comments.
