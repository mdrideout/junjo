import grpc
from google.protobuf.empty_pb2 import Empty

from .proto_gen import workflow_pb2, workflow_pb2_grpc


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
        self.stub = workflow_pb2_grpc.WorkflowServiceStub(self.channel)

    def create_workflow(self, workflow_id: str, workflow_name: str) -> None:
        """
        Make a CreateWorkflow gRPC call using workflow_id and workflow_name.
        """
        print("Sending grpc request to create workflow with id:", workflow_id)
        request = workflow_pb2.CreateWorkflowRequest(
            id=workflow_id,
            name=workflow_name
        )

        # stub.CreateWorkflow returns an Empty object.
        response: Empty = self.stub.CreateWorkflow(request)
        print("CreateWorkflow RPC succeeded. Response is:", response)
