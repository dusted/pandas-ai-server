import uuid
from dataclasses import dataclass


@dataclass
class CodeExecutionPipelineInput:
    """
    Contain all the data needed by the Code Execution pipeline
    """

    code: str
    output_type: str
    instance: str
    conversation_id: uuid.UUID
    prompt_id: uuid.UUID
    query: str

    def __init__(
        self,
        code: str,
        output_type: str,
        conversation_id: uuid.UUID,
        prompt_id: uuid.UUID,
    ) -> None:
        self.code = code
        self.output_type = output_type
        self.conversation_id = conversation_id
        self.prompt_id = prompt_id
        self.query = ""

        self.log_input_details()

    def log_input_details(self):
        print(f"CodeExecutionPipelineInput initialized with code={self.code}, output_type={self.output_type}, conversation_id={self.conversation_id}, prompt_id={self.prompt_id}, query={self.query}")