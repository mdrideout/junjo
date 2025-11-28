# Prepare for Task

You are about to work on the Junjo AI Studio codebase to refactor from the existing architecture to "V4". Follow these steps to prepare:

## For the existing codebase:
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

## For the refactor:
1. Review @REFACTOR_V4_ARCHITECTURE.md
2. Review @REFACTOR_V4_PLAN.md

## Methodology:
We will not boil the ocean. We will focus on a specific part of this plan, from top to bottom, implementing this plan in a piece-by-piece methodical way with the ability to test and validate each stage of the flow.

## Planning:
- Do not include extensive code examples inside plans. Planning isn't for coding.
- Keep plans strategic, higher level, and process / step / dependency focused
- Keep track of decisions made and rationale for important context
- You can use todo lists to help us keep track of what is done and what is next

## Code Opinions and Arhitecture:
We prefer "grug" principles when coding. Single responsibility principle, YAGNI, KISS, avoiding abstractions, WET better than DRY, etc. Seek clarification if you are unsure of what architecture or code patterns and opinions to use when planning. 

## Notes:
- Do not include keys that could be detected by Gitleaks inside any planning docs or comments
- When adding dependencies or installing libraries, use CLI commands to install instead of editing the go.mod, pyproject.toml, package.json, etc. Do not include versions. Allow the CLI command to fetch and install  the latest version.
  - Ex: `go get modernc.org/sqlite` or `uv add junjo`

# When You Are Ready
- Once you have thoroughly reviewed the documents, confirm your readiness outputting that you are ready to proceed with refactoring. You do not need to summarize or explain your understanding, or creating leading ideas of what should be next.