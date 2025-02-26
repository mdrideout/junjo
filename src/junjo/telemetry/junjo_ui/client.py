from enum import StrEnum

import grpc
from google.protobuf.empty_pb2 import Empty

from .proto_gen import workflow_log_pb2, workflow_log_pb2_grpc


class WorkflowLogType(StrEnum):
    START = "start"
    END = "end"

class JunjoUiClient:
    """
    A gRPC client that connects to the WorkflowService 
    and provides a convenience method to call CreateWorkflow.
    """

    def __init__(self, host: str = "localhost", port: int = 50051):
        """
        Initialize a gRPC channel and stub for the given host/port.
        """
        self.channel = grpc.insecure_channel(f"{host}:{port}")
        self.stub = workflow_log_pb2_grpc.WorkflowLogServiceStub(self.channel)

    def create_workflow_log(self, exec_id: str, name: str, type: WorkflowLogType, event_time_nano: int) -> None:
        """
        Make a CreateWorkflow gRPC call.

        Args:
            exec_id: The id of the workflow execution (same for start and end)
            name: The name of the workflow (human readable)
            type: The type of the workflow log ("start" or "end")
            event_time_nano: The time of the event in nanoseconds

        """
        print("Sending grpc request to create workflow with id:", exec_id)
        request = workflow_log_pb2.CreateWorkflowLogRequest(
            exec_id=exec_id,
            name=name,
            type=type,
            event_time_nano=event_time_nano
        )

        # stub.CreateWorkflow returns an Empty object.
        response: Empty = self.stub.CreateWorkflowLog(request)
        print("CreateWorkflow RPC succeeded. Response is:", response)
