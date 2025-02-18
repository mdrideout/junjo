from tortoise import Tortoise, fields
from tortoise.models import Model


class JunjoDatabase:
    """A class to manage the database of a Junjo project."""

    @staticmethod
    async def init_db(sqlite_url: str):
        """Initialize the database."""
        print("Initializing junjo database connection...")
        await Tortoise.init(
            db_url=sqlite_url,
            modules={'models': ['junjo.database.tortoise']}
        )
        await Tortoise.generate_schemas()

class WorkflowModel(Model):
    id = fields.IntField(pk=True)
    workflow_id = fields.CharField(max_length=255)
    state = fields.JSONField()
    duration = fields.FloatField()

class NodeModel(Model):
    id = fields.IntField(pk=True)
    node_id = fields.CharField(max_length=255)
    state = fields.JSONField()
    duration = fields.FloatField()
