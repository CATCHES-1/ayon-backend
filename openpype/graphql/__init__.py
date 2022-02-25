import strawberry

from strawberry.types import Info
from strawberry.fastapi import GraphQLRouter
from strawberry.dataloader import DataLoader

from fastapi import Depends

from openpype.entities import UserEntity
from openpype.api.dependencies import dep_current_user

from .connections import ProjectsConnection, UsersConnection
from .nodes.project import ProjectNode
from .nodes.user import UserNode, UserAttribType
from .nodes.folder import folder_from_record
from .resolvers.projects import get_project, get_projects
from .resolvers.users import get_users, get_user

from .dataloaders import (
    folder_loader,
    latest_version_loader,
    subset_loader,
    version_loader,
    user_loader
)


async def graphql_get_context(
    user: UserEntity = Depends(dep_current_user)
) -> dict:
    """Get the current request context"""
    return {
        "folder_loader": DataLoader(load_fn=folder_loader),
        "subset_loader": DataLoader(load_fn=subset_loader),
        "version_loader": DataLoader(load_fn=version_loader),
        "latest_version_loader": DataLoader(load_fn=latest_version_loader),
        "user_loader": DataLoader(load_fn=user_loader),

        "folder_from_record": folder_from_record,

        "user": user
    }


#
# Query
#


@strawberry.type
class Query:
    """OpenPype GraphQL Query."""

    project: ProjectNode = strawberry.field(
        description="Get a project by name",
        resolver=get_project,
    )

    projects: ProjectsConnection = strawberry.field(
        description="Get a list of projects",
        resolver=get_projects
    )

    users: UsersConnection = strawberry.field(
        description="Get a list of users",
        resolver=get_users
    )

    user: UserNode = strawberry.field(
        description="Get a user by name",
        resolver=get_user
    )

    @strawberry.field(description="Current user")
    def me(self, info: Info) -> UserNode:
        user = info.context["user"]
        return UserNode(
            name=user.name,
            attrib=UserAttribType(**user.attrib)
        )


schema = strawberry.Schema(query=Query)
router = GraphQLRouter(
    schema=schema,
    graphiql=False,
    context_getter=graphql_get_context
)
