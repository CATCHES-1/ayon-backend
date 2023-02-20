from typing import Annotated

from strawberry.types import Info

from ayon_server.graphql.connections import VersionsConnection
from ayon_server.graphql.edges import VersionEdge
from ayon_server.graphql.nodes.version import VersionNode
from ayon_server.graphql.resolvers.common import (
    ARGAfter,
    ARGBefore,
    ARGFirst,
    ARGHasLinks,
    ARGIds,
    ARGLast,
    FieldInfo,
    argdesc,
    create_folder_access_list,
    create_pagination,
    get_has_links_conds,
    resolve,
    sortdesc,
)
from ayon_server.types import validate_name_list, validate_status_list
from ayon_server.utils import SQLTool

SORT_OPTIONS = {
    "version": "versions.version",
    "status": "versions.status",
    "createdAt": "versions.created_at",
    "updatedAt": "versions.updated_at",
}


async def get_versions(
    root,
    info: Info,
    first: ARGFirst = None,
    after: ARGAfter = None,
    last: ARGLast = None,
    before: ARGBefore = None,
    ids: ARGIds = None,
    version: int | None = None,
    versions: list[int] | None = None,
    statuses: Annotated[
        list[str] | None, argdesc("List of statuses to filter by")
    ] = None,
    tags: Annotated[list[str] | None, argdesc("List of tags to filter by")] = None,
    subset_ids: Annotated[
        list[str] | None,
        argdesc("List of parent subsets IDs"),
    ] = None,
    task_ids: Annotated[
        list[str] | None,
        argdesc("List of parent task IDs"),
    ] = None,
    authors: Annotated[
        list[str] | None,
        argdesc("List of version author user names to filter by."),
    ] = None,
    latestOnly: Annotated[
        bool,
        argdesc("List only latest versions"),
    ] = False,
    heroOnly: Annotated[
        bool,
        argdesc("List only hero versions"),
    ] = False,
    heroOrLatestOnly: Annotated[
        bool,
        argdesc("List hero versions. If hero does not exist, list latest"),
    ] = False,
    has_links: ARGHasLinks = None,
    sort_by: Annotated[str | None, sortdesc(SORT_OPTIONS)] = None,
) -> VersionsConnection:
    """Return a list of versions."""

    project_name = root.project_name

    #
    # SQL
    #

    sql_columns = [
        "versions.id AS id",
        "versions.version AS version",
        "versions.subset_id AS subset_id",
        "versions.task_id AS task_id",
        "versions.thumbnail_id AS thumbnail_id",
        "versions.author AS author",
        "versions.attrib AS attrib",
        "versions.data AS data",
        "versions.status AS status",
        "versions.tags AS tags",
        "versions.active AS active",
        "versions.created_at AS created_at",
        "versions.updated_at AS updated_at",
        "versions.creation_order AS creation_order",
    ]

    # sql_joins = []
    sql_conditions = []
    sql_joins = []

    # Empty overrides. Skip querying
    if ids == ["0" * 32]:
        return VersionsConnection(edges=[])

    if ids:
        sql_conditions.append(f"id IN {SQLTool.id_array(ids)}")
    if version:
        sql_conditions.append(f"version = {version}")
    if versions:
        sql_conditions.append(f"version IN {SQLTool.array(versions)}")
    if authors:
        validate_name_list(authors)
        sql_conditions.append(f"author IN {SQLTool.array(authors)}")
    if statuses:
        validate_status_list(statuses)
        sql_conditions.append(f"status IN {SQLTool.array(statuses)}")
    if tags:
        validate_name_list(tags)
        sql_conditions.append(f"tags @> {SQLTool.array(tags, curly=True)}")

    if subset_ids:
        sql_conditions.append(f"subset_id IN {SQLTool.id_array(subset_ids)}")
    elif root.__class__.__name__ == "SubsetNode":
        sql_conditions.append(f"subset_id = '{root.id}'")
    if task_ids:
        sql_conditions.append(f"task_id IN {SQLTool.id_array(task_ids)}")
    elif root.__class__.__name__ == "TaskNode":
        sql_conditions.append(f"task_id = '{root.id}'")

    if latestOnly:
        sql_conditions.append(
            f"""
            versions.id IN (
            SELECT l.ids[array_upper(l.ids, 1)]
            FROM project_{project_name}.version_list as l
            )
            """
        )
    elif heroOnly:
        sql_conditions.append("versions.version < 0")

    elif heroOrLatestOnly:
        sql_conditions.append(
            f"""
            (versions.version < 0
            OR versions.id IN (
                SELECT l.ids[array_upper(l.ids, 1)]
                FROM project_{project_name}.version_list as l
                WHERE l.versions[1] >= 0
            )
            )
            """
        )

    if has_links is not None:
        sql_conditions.extend(
            get_has_links_conds(project_name, "versions.id", has_links)
        )

    access_list = await create_folder_access_list(root, info)
    if access_list is not None:
        sql_conditions.append(
            f"hierarchy.path like ANY ('{{ {','.join(access_list)} }}')"
        )

        sql_joins.extend(
            [
                f"""
                INNER JOIN project_{project_name}.subsets AS subsets
                ON subsets.id = versions.subset_id
                """,
                f"""
                INNER JOIN project_{project_name}.hierarchy AS hierarchy
                ON hierarchy.id = subsets.folder_id
                """,
            ]
        )

    #
    # Pagination
    #

    order_by = ["versions.creation_order"]
    if sort_by is not None:
        if sort_by in SORT_OPTIONS:
            order_by.insert(0, SORT_OPTIONS[sort_by])
        elif sort_by.startswith("attrib."):
            order_by.insert(0, f"versions.attrib->>'{sort_by[7:]}'")
        else:
            raise ValueError(f"Invalid sort_by value: {sort_by}")

    paging_fields = FieldInfo(info, "versions")
    need_cursor = paging_fields.has_any(
        "versions.pageInfo.startCursor",
        "versions.pageInfo.endCursor",
        "versions.edges.cursor",
    )

    pagination, paging_conds, cursor = create_pagination(
        order_by,
        first,
        after,
        last,
        before,
        need_cursor=need_cursor,
    )
    sql_conditions.extend(paging_conds)

    #
    # Query
    #

    query = f"""
        SELECT {cursor}, {", ".join(sql_columns)}
        FROM project_{project_name}.versions AS versions
        {" ".join(sql_joins)}
        {SQLTool.conditions(sql_conditions)}
        {pagination}
    """

    return await resolve(
        VersionsConnection,
        VersionEdge,
        VersionNode,
        project_name,
        query,
        first,
        last,
        context=info.context,
    )


async def get_version(root, info: Info, id: str) -> VersionNode | None:
    """Return a task node based on its ID"""
    if not id:
        return None
    connection = await get_versions(root, info, ids=[id])
    if not connection.edges:
        return None
    return connection.edges[0].node
