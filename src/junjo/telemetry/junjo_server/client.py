from enum import StrEnum

import grpc
from google.protobuf.empty_pb2 import Empty

from .proto_gen import workflow_log_pb2, workflow_log_pb2_grpc, workflow_metadata_pb2, workflow_metadata_pb2_grpc


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
        self.workflow_log_stub = workflow_log_pb2_grpc.WorkflowLogServiceStub(self.channel)
        self.workflow_metadata_stub = workflow_metadata_pb2_grpc.WorkflowMetadataServiceStub(self.channel)

    def create_workflow_log(self,
            exec_id: str,
            type: WorkflowLogType,
            event_time_nano: int,
            state: str
        ) -> None:
        """
        Make a CreateWorkflow gRPC call.

        Args:
            exec_id: The id of the workflow execution (same for start and end)
            type: The type of the workflow log ("start" or "end")
            event_time_nano: The time of the event in nanoseconds
            state: The state of the workflow execution

        """
        print("Sending grpc request to create workflow with id:", exec_id)
        request = workflow_log_pb2.CreateWorkflowLogRequest(
            exec_id=exec_id,
            type=type,
            event_time_nano=event_time_nano,
            state=state
        )

        response: Empty = self.workflow_log_stub.CreateWorkflowLog(request)
        print("CreateWorkflow RPC succeeded. Response is:", response)

    def create_workflow_metadata(self,
            exec_id: str,
            app_name: str,
            workflow_name: str,
            structure: str
        ) -> None:
        """
        Make a CreateWorkflowMetadata gRPC call.

        Args:
            exec_id: The id of the workflow execution
            app_name: The name of the application
            workflow_name: The name of the workflow
            structure: The workflow structure as a JSON string

        """
        print("Sending grpc request to create workflow metadata with id:", exec_id)
        request = workflow_metadata_pb2.CreateWorkflowMetadataRequest(
            exec_id=exec_id,
            app_name=app_name,
            workflow_name=workflow_name,
            structure=structure
        )

        response: Empty = self.workflow_metadata_stub.CreateWorkflowMetadata(request)
        print("CreateWorkflowMetadata RPC succeeded. Response is:", response)
