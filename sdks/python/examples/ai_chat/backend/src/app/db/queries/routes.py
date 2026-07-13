from fastapi import APIRouter

queries_router = APIRouter(prefix="/api")

# This should probably be only accessed through the workflow
# @queries_router.post("/create-setup-contact")
# async def post_create_setup_contact(request: ContactCreate) -> ChatWithMembersRead:
#     """
#     Create a new contact directly.
#     """

#     logger.info(f"Creating new contact with request: {request}")

#     # Call the repository service to create the contact
#     result = await CreateSetupContactRepository.create_setup_contact(request)

#     return result
