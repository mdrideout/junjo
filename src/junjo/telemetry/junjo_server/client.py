from enum import StrEnum

import grpc
from google.protobuf.empty_pb2 import Empty

from junjo.telemetry.junjo_server.proto_gen import node_log_pb2, node_log_pb2_grpc

from .proto_gen import workflow_log_pb2, workflow_log_pb2_grpc, workflow_metadata_pb2, workflow_metadata_pb2_grpc


class JunjoLogType(StrEnum):
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
        self.node_log_stub = node_log_pb2_grpc.NodeLogServiceStub(self.channel)
        self.workflow_log_stub = workflow_log_pb2_grpc.WorkflowLogServiceStub(self.channel)
        self.workflow_metadata_stub = workflow_metadata_pb2_grpc.WorkflowMetadataServiceStub(self.channel)

    def create_node_log(self,
            exec_id: str,
            type: JunjoLogType,
            event_time_nano: int,
            state: str
        ) -> None:
        """
        Make a CreateNodeLog gRPC call.

        Args:
            exec_id: The id of the workflow execution (same for start and end)
            type: The type of the workflow log ("start" or "end")
            event_time_nano: The time of the event in nanoseconds
            state: The state of the workflow execution

        """
        print("Sending grpc request to create workflow with id:", exec_id)
        request = node_log_pb2.CreateNodeLogRequest(
            exec_id=exec_id,
            type=type,
            event_time_nano=event_time_nano,
            state=state
        )

        response: Empty = self.node_log_stub.CreateNodeLog(request)
        print("CreateNodeLog RPC succeeded. Response is:", response)

    def create_workflow_log(self,
            exec_id: str,
            type: JunjoLogType,
            event_time_nano: int,
            state: str
        ) -> None:
        """
        Make a CreateWorkflowLog gRPC call.

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
        print("CreateWorkflowLog RPC succeeded. Response is:", response)

    def create_workflow_metadata(self,
            exec_id: str,
            app_name: str,
            workflow_name: str,
            event_time_nano: int,
            structure: str
        ) -> None:
        """
        Make a CreateWorkflowMetadata gRPC call.

        Args:
            exec_id: The id of the workflow execution
            app_name: The name of the application
            workflow_name: The name of the workflow
            event_time_nano: The time of the event in nanoseconds
            structure: The workflow structure as a JSON string

        """
        print("Sending grpc request to create workflow metadata with id:", exec_id)
        request = workflow_metadata_pb2.CreateWorkflowMetadataRequest(
            exec_id=exec_id,
            app_name=app_name,
            workflow_name=workflow_name,
            event_time_nano=event_time_nano,
            structure=structure
        )

        response: Empty = self.workflow_metadata_stub.CreateWorkflowMetadata(request)
        print("CreateWorkflowMetadata RPC succeeded. Response is:", response)

