from typing import Optional

from pandasai.agent.base_judge import BaseJudge
from pandasai.helpers.query_exec_tracker import QueryExecTracker
from pandasai.pipelines.chat.chat_pipeline_input import (
    ChatPipelineInput,
)
from pandasai.pipelines.chat.code_execution_pipeline_input import (
    CodeExecutionPipelineInput,
)
from pandasai.pipelines.chat.error_correction_pipeline.error_correction_pipeline import (
    ErrorCorrectionPipeline,
)
from pandasai.pipelines.chat.error_correction_pipeline.error_correction_pipeline_input import (
    ErrorCorrectionPipelineInput,
)
from pandasai.pipelines.chat.validate_pipeline_input import (
    ValidatePipelineInput,
)

from ...helpers.logger import Logger
from ..pipeline import Pipeline
from ..pipeline_context import PipelineContext
from .cache_lookup import CacheLookup
from .cache_population import CachePopulation
from .code_cleaning import CodeCleaning
from .code_execution import CodeExecution
from .code_generator import CodeGenerator
from .prompt_generation import PromptGeneration
from .result_parsing import ResultParsing
from .result_validation import ResultValidation


class GenerateChatPipeline:
    code_generation_pipeline = Pipeline
    code_execution_pipeline = Pipeline
    context: PipelineContext
    _logger: Logger
    last_error: str

    def __init__(
        self,
        context: Optional[PipelineContext] = None,
        logger: Optional[Logger] = None,
        judge: BaseJudge = None,
        on_prompt_generation=None,
        on_code_generation=None,
        before_code_execution=None,
        on_result=None,
    ):
        self.query_exec_tracker = QueryExecTracker(
            server_config=context.config.log_server
        )

        self.code_generation_pipeline = Pipeline(
            context=context,
            logger=logger,
            query_exec_tracker=self.query_exec_tracker,
            steps=[
                ValidatePipelineInput(),
                CacheLookup(),
                PromptGeneration(
                    skip_if=self.is_cached,
                    on_execution=on_prompt_generation,
                ),
                CodeGenerator(
                    skip_if=self.is_cached,
                    on_execution=on_code_generation,
                ),
                CachePopulation(skip_if=self.is_cached),
                CodeCleaning(
                    skip_if=self.no_code,
                    on_failure=self.on_code_cleaning_failure,
                    on_retry=self.on_code_retry,
                ),
            ],
        )

        self.code_execution_pipeline = Pipeline(
            context=context,
            logger=logger,
            query_exec_tracker=self.query_exec_tracker,
            steps=[
                CodeExecution(
                    before_execution=before_code_execution,
                    on_failure=self.on_code_execution_failure,
                    on_retry=self.on_code_retry,
                ),
                ResultValidation(),
                ResultParsing(
                    before_execution=on_result,
                ),
            ],
        )

        self.code_exec_error_pipeline = ErrorCorrectionPipeline(
            context=context,
            logger=logger,
            query_exec_tracker=self.query_exec_tracker,
            on_code_generation=on_code_generation,
            on_prompt_generation=on_prompt_generation,
        )

        self.judge = judge

        if self.judge:
            if self.judge.pipeline.pipeline.context:
                self.judge.pipeline.pipeline.context.memory = context.memory
            else:
                self.judge.pipeline.pipeline.context = context

            self.judge.pipeline.pipeline.logger = logger
            self.judge.pipeline.pipeline.query_exec_tracker = self.query_exec_tracker

        self.context = context
        self._logger = logger
        self.last_error = None

    def on_code_execution_failure(self, code: str, errors: Exception) -> str:
        """
        Executes on code execution failure
        Args:
            code (str): code that is ran
            exception (Exception): exception that is raised during code execution

        Returns:
            str: returns the updated code with the fixes
        """
        # Add information about the code failure in the query tracker for debug
        self.query_exec_tracker.add_step(
            {
                "type": "CodeExecution",
                "success": False,
                "message": "Failed to execute code",
                "execution_time": None,
                "data": {
                    "content_type": "code",
                    "value": code,
                    "exception": errors,
                },
            }
        )

    def on_code_cleaning_failure(self, code, errors):
        # Add information about the code failure in the query tracker for debug
        self.query_exec_tracker.add_step(
            {
                "type": "CodeCleaning",
                "success": False,
                "message": "Failed to clean code",
                "execution_time": None,
                "data": {
                    "content_type": "code",
                    "value": code,
                    "exception": errors,
                },
            }
        )

    def on_code_retry(self, code: str, exception: Exception):
        correction_input = ErrorCorrectionPipelineInput(code, exception)
        return self.code_exec_error_pipeline.run(correction_input)

    def no_code(self, context: PipelineContext):
        return context.get("last_code_generated") is None

    def is_cached(self, context: PipelineContext):
        return context.get("found_in_cache")

    def get_last_track_log_id(self):
        return self.query_exec_tracker.last_log_id

    def run_generate_code(self, input: ChatPipelineInput) -> dict:
        """
        Executes the code generation pipeline with user input and return the result
        Args:
            input (ChatPipelineInput): _description_

        Returns:
            The `output` dictionary is expected to have the following keys:
            - 'type': The type of the output.
            - 'value': The value of the output.
        """
        self._logger.log(f"Executing Pipeline: {self.__class__.__name__}")
        print(f"Executing Pipeline: {self.__class__.__name__}")
        # Reset intermediate values
        self.context.reset_intermediate_values()

        # Start New Tracking for Query
        self.query_exec_tracker.start_new_track(input)

        self.query_exec_tracker.add_skills(self.context)

        self.query_exec_tracker.add_dataframes(self.context.dfs)

        # Add Query to memory
        self.context.memory.add(input.query, True)

        self.context.add_many(
            {
                "output_type": input.output_type,
                "last_prompt_id": input.prompt_id,
            }
        )
        print("Intermediate values after adding to context:", self.context.intermediate_values)

        try:
            output = self.code_generation_pipeline.run(input)

            self.query_exec_tracker.success = True

            self.query_exec_tracker.publish()
            print(f"Pipeline generate code output: {output}")
            return output

        except Exception as e:
            # Show the full traceback
            import traceback

            traceback.print_exc()

            self.last_error = str(e)
            self.query_exec_tracker.success = False
            self.query_exec_tracker.publish()

            return (
                "Unfortunately, I was not able to answer your question, "
                "because of the following error:\n"
                f"\n{e}\n"
            )

    def run_execute_code(self, input: CodeExecutionPipelineInput) -> dict:
        """
        Executes the chat pipeline with user input and return the result
        Args:
            input (CodeExecutionPipelineInput): _description_

        Returns:
            The `output` dictionary is expected to have the following keys:
            - 'type': The type of the output.
            - 'value': The value of the output.
        """
        self._logger.log(f"Executing Pipeline: {self.__class__.__name__}")
        print(f"run_execute_code Executing Pipeline: {self.__class__.__name__}")
        # Reset intermediate values
        self.context.reset_intermediate_values()

        # Start New Tracking for Query
        self.query_exec_tracker.start_new_track(input)

        self.query_exec_tracker.add_skills(self.context)

        self.query_exec_tracker.add_dataframes(self.context.dfs)

        # Add Query to memory
        self.context.memory.add(input.code, True)

        self.context.add_many(
            {
                "output_type": input.output_type,
                "last_prompt_id": input.prompt_id,
            }
        )
        try:
            output = self.code_execution_pipeline.run(input.code)

            self.query_exec_tracker.success = True

            self.query_exec_tracker.publish()

            return output

        except Exception as e:
            # Show the full traceback
            import traceback

            traceback.print_exc()

            self.last_error = str(e)
            self.query_exec_tracker.success = False
            self.query_exec_tracker.publish()

            return (
                "Unfortunately, I was not able to answer your question, "
                "because of the following error:\n"
                f"\n{e}\n"
            )

    def run(self, input: ChatPipelineInput) -> dict:
        """
        Executes the chat pipeline with user input and return the result
        Args:
            input (ChatPipelineInput): _description_

        Returns:
            The `output` dictionary is expected to have the following keys:
            - 'type': The type of the output.
            - 'value': The value of the output.
        """
        self._logger.log(f"Executing Pipeline: {self.__class__.__name__}")
        print(f"run Executing Pipeline: {self.__class__.__name__}")

        print(f"run Executing Pipeline DATA: {self.context.dfs}")
        

        # Reset intermediate values
        self.context.reset_intermediate_values()

        # Start New Tracking for Query
        self.query_exec_tracker.start_new_track(input)

        self.query_exec_tracker.add_skills(self.context)

        self.query_exec_tracker.add_dataframes(self.context.dfs)

        # Log the DataFrame shapes before running the pipeline
        for df in self.context.dfs:
            print(f"Connector: {df}")
            if hasattr(df, 'pandas_df'):
                pandas_df = df.pandas_df
                print(f"DataFrame shape: {pandas_df.shape}")
                print(f"DataFrame columns: {pandas_df.columns.tolist()}")
                print(f"DataFrame data types:\n{pandas_df.dtypes}")
                print(f"First few rows of the DataFrame:\n{pandas_df.head()}")
                print(f"Summary statistics of the DataFrame:\n{pandas_df.describe(include='all')}")
                print(f"Summary statistics of the DataFrame:\n{pandas_df.head(20)}")
            else:
                print("No DataFrame found in this connector.")

        # Add Query to memory
        self.context.memory.add(input.query, True)

        self.context.add_many(
            {
                "output_type": input.output_type,
                "last_prompt_id": input.prompt_id,
            }
        )
        print("Intermediate values after adding to context:", self.context.intermediate_values)

        try:
            if self.judge:
                code = self.code_generation_pipeline.run(input)
                print("code_generation_pipeline pipeline run:")
                if 'rows' in code['value']:
                    print(f"code_generation_pipeline rows count: {len(code['value']['rows'])}")
                else:
                    print("No rows found in code generation output")
                retry_count = 0
                while retry_count < self.context.config.max_retries:
                    if self.judge.evaluate(query=input.query, code=code):
                        break
                    code = self.code_generation_pipeline.run(input)
                    retry_count += 1

                output = self.code_execution_pipeline.run(code)

            elif self.code_execution_pipeline:
                print(f"FULL code_execution_pipeline: {self.code_execution_pipeline}")
                
                output = (
                    self.code_generation_pipeline | self.code_execution_pipeline
                ).run(input)


                print("code_execution_pipeline  run:")

                if 'rows' in output['value']:
                    print(f"code_execution_pipeline pipeline rows count: {len(output['value']['rows'])}")
                else:
                    print("No rows found in combined pipeline output")
            else:
                output = self.code_generation_pipeline.run(input)
                print("code_generation_pipeline pipeline run (no execution):")
                if 'rows' in output['value']:
                    print(f"Code generation rows count: {len(output['value']['rows'])}")
                else:
                    print("No rows found in code generation output (no execution)")

            self.query_exec_tracker.success = True

            self.query_exec_tracker.publish()
            print(output)
            if output['type'] == 'dataframe':
                rows = output['value']['rows']
                self._logger.log(f"Number of rows in run response: {len(rows)}")
                print(f"Number of rows in run response: {len(rows)}")
                for row in rows:
                    self._logger.log(f"Row: {row}")
                    print(f"Row: {row}")

            return output

        except Exception as e:
            # Show the full traceback
            import traceback

            traceback.print_exc()

            self.last_error = str(e)
            self.query_exec_tracker.success = False
            self.query_exec_tracker.publish()

            return (
                "Unfortunately, I was not able to answer your question, "
                "because of the following error:\n"
                f"\n{e}\n"
            )
