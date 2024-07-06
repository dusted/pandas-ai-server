from fastapi import status, HTTPException
from typing import List
from app.models import ConnectorType, Workspace, User
from app.repositories.dataset import DatasetRepository
from app.repositories.workspace import WorkspaceRepository
from core.controller import BaseController
from core.database.transactional import Propagation, Transactional
from app.schemas.responses.users import WorkspaceUsersResponse
from app.schemas.responses.datasets import WorkspaceDatasetsResponseModel

class WorkspaceController(BaseController[Workspace]):
    def __init__(
        self,
        space_repository: WorkspaceRepository,
        dataset_repository: DatasetRepository,
    ):
        super().__init__(model=User, repository=space_repository)
        self.space_repository = space_repository
        self.dataset_repository = dataset_repository

    @Transactional(propagation=Propagation.REQUIRED_NEW)
    async def reset_space_datasets(self, workspace_id: str) -> bool:
        await self.space_repository.delete_space_datasets(workspace_id)
        return True

    @Transactional(propagation=Propagation.REQUIRED_NEW)
    async def add_csv_datasets(
        self, datasets: List[dict], user: User, workspace_id: str
    ):
        for dataset in datasets:
            dataset = await self.dataset_repository.create_dataset(
                user_id=user.id,
                organization_id=user.memberships[0].organization_id,
                name=dataset["file_name"],
                connector_type=ConnectorType.CSV,
                config={
                    "file_path": dataset["file_path"],
                    "file_name": dataset["file_name"],
                },
                head=dataset["head"],
            )
            await self.space_repository.add_dataset_to_space(
                dataset_id=dataset.id, workspace_id=workspace_id
            )

    @Transactional(propagation=Propagation.REQUIRED_NEW)
    async def add_datasets_from_db(self, datasets: List[dict], user: User, workspace_id: str):
        if datasets:
            # Extract headers and rows for the head of the dataset
            headers = list(datasets[0].keys())
            rows = [list(dataset.values()) for dataset in datasets[:5]]  # Only take the first 5 rows for the head

            head = {
                "headers": headers,
                "rows": rows
            }
            config = {
                "query": "SELECT * FROM loan_payments_data"  # Adjust the query or config as needed
            }
            dataset_obj = await self.dataset_repository.create_dataset(
                user_id=user.id,
                organization_id=user.memberships[0].organization_id,
                name="loan_payments_data",  # or another appropriate name
                table_name="loan_payments_data",
                description="Dataset from PostgreSQL",
                connector_type=ConnectorType.POSTGRES,
                config=config,
                head=head,
            )
            await self.space_repository.add_dataset_to_space(
                dataset_id=dataset_obj.id, workspace_id=workspace_id
            )



    async def get_workspace_by_id(self, workspace_id: str):
        workspace = await self.space_repository.get_by_id(id=workspace_id)
        if not workspace:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Workspace with id: {workspace_id} was not found"
            )
        return workspace

    async def get_workspace_users(
            self, workspace_id: str,
    ):
        await self.get_workspace_by_id(workspace_id)
        users = await self.space_repository.get_users_by_workspace_id(workspace_id)
        return WorkspaceUsersResponse(users=users)
    
    
    async def get_workspace_datasets(self, workspace_id) -> WorkspaceDatasetsResponseModel:
        await self.get_workspace_by_id(workspace_id)        
        datasets = await self.dataset_repository.get_all_by_workspace_id(workspace_id)
        if not datasets:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No dataset found. Please restart the server and try again"
            )
        return WorkspaceDatasetsResponseModel(datasets=datasets)