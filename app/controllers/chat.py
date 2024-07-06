import os
import shutil
from typing import List

import pandas as pd
from pandasai import Agent
from pandasai.connectors.pandas import PandasConnector
from pandasai.helpers.path import find_project_root
from pandasai.llm.openai import OpenAI
  # Import the function
from app.models import Dataset, User
from app.repositories import UserRepository
from app.repositories.conversation import ConversationRepository
from app.repositories.workspace import WorkspaceRepository
from app.schemas.requests.chat import ChatRequest
from app.schemas.responses.chat import ChatResponse
from app.schemas.responses.users import UserInfo
from app.utils.memory import prepare_conv_memory
from core.constants import CHAT_FALLBACK_MESSAGE
from core.controller import BaseController
from core.utils.database_utils import load_data_from_db
from core.database.transactional import Propagation, Transactional
from core.utils.dataframe import load_df
from core.utils.json_encoder import jsonable_encoder
from core.utils.response_parser import JsonResponseParser
from core.config import config as env_config
from core.database.session import session
from sqlalchemy.sql import text

class ChatController(BaseController[User]):
    def __init__(
        self,
        user_repository: UserRepository,
        space_repository: WorkspaceRepository,
        conversation_repository: ConversationRepository,
    ):
        super().__init__(model=User, repository=user_repository)
        self.user_repository = user_repository
        self.space_repository = space_repository
        self.conversation_repository = conversation_repository

    @Transactional(propagation=Propagation.REQUIRED)
    async def start_new_conversation(self, user: UserInfo, chat_request: ChatRequest):
        return await self.conversation_repository.create(
            {
                "workspace_id": chat_request.workspace_id,
                "user_id": user.id,
            }
        )

    @Transactional(propagation=Propagation.REQUIRED)
    async def chat(self, user: UserInfo, chat_request: ChatRequest) -> ChatResponse:
        datasets: List[Dataset] = await self.space_repository.get_space_datasets(
            chat_request.workspace_id
        )
        conversation_id = chat_request.conversation_id
        conversation_messages = []
        memory = None

        if not chat_request.conversation_id:
            user_conversation = await self.start_new_conversation(user, chat_request)
            conversation_id = user_conversation.id

        else:
            conversation_messages = (
                await self.conversation_repository.get_conversation_messages(
                    conversation_id
                )
            )
            memory = prepare_conv_memory(conversation_messages)

        #if the init_database in server.js uses the CSV method then use this connector
        #connectors = []
        #for dataset in datasets:
        #    config = dataset.connector.config
        #    df = pd.read_csv(config["file_path"])
        #    connector = PandasConnector(
        #        {"original_df": df},
        #        name=dataset.name,
        #        description=dataset.description,
        #        custom_head=(load_df(dataset.head) if dataset.head else None),
        #        field_descriptions=dataset.field_descriptions,
        #    )
        #    connectors.append(connector)

        #if the init_database in server.js uses the POSTGRES method then use this connector
        connectors = []
        for dataset in datasets:
            print("running chat dataset query")
            query = f"SELECT * FROM {dataset.table_name}"
            print(query)
            try:
                df = await load_data_from_db(query)
                print(f"DataFrame shape: {df.shape}")
                print(f"DataFrame head: {df.head()}")
                connector = PandasConnector(
                    {"original_df": df},
                    name=dataset.name,
                    description=dataset.description,
                    custom_head=(load_df(dataset.head) if dataset.head else None),
                    field_descriptions=dataset.field_descriptions,
                )
                print(f"Creating PandasConnector for dataset: {dataset.name}")
                print(f"Connector name: {connector.name}")
                print(f"Connector description: {connector.description}")
                print(f"Connector custom head: {connector.custom_head}")
                print(f"Connector field descriptions: {connector.field_descriptions}")
                connectors.append(connector)
            except Exception as e:
                print(f"Failed to load data for table {dataset.table_name}: {e}")

        path_plot_directory = find_project_root() + "/exports/" + str(conversation_id)

        config = {
            "enable_cache": False,
            "response_parser": JsonResponseParser,
            "save_charts": True,
            "save_charts_path": path_plot_directory,
        }

        if env_config.OPENAI_API_KEY:
            llm = OpenAI(env_config.OPENAI_API_KEY)
            config["llm"] = llm

        agent = Agent(connectors, config=config)
        if memory:
            agent.context.memory = memory

        response = agent.chat(chat_request.query)

        if os.path.exists(path_plot_directory):
            shutil.rmtree(path_plot_directory)

        if isinstance(response, str) and (
            response.startswith("Unfortunately, I was not able to")
        ):
            return [
                {
                    "type": "string",
                    "message": CHAT_FALLBACK_MESSAGE,
                    "value": CHAT_FALLBACK_MESSAGE,
                }
            ]

        response = jsonable_encoder([response])
        conversation_message = await self.conversation_repository.add_conversation_message(
            conversation_id=conversation_id,
            query=chat_request.query,
            response=response,
            code_generated=agent.last_code_executed,
        )

        return ChatResponse(
            response=response,
            conversation_id=str(conversation_id),
            message_id = str(conversation_message.id),
            query = str(conversation_message.query)
        )