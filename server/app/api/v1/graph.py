"""Graph API endpoints for managing graph data with Apache AGE."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from server.app.api.v1.schemas import (
    EdgeCreate,
    EdgeResponse,
    EdgeUpdate,
    GraphQueryRequest,
    GraphQueryResponse,
    NeighborsRequest,
    NodeCreate,
    NodeResponse,
    NodeUpdate,
    PathRequest,
)
from server.app.core.logging import get_logger
from server.app.db.session import get_db
from server.app.models.graph import EdgeType, NodeType
from server.app.services.auth import AuthContext, get_auth_context
from server.app.services.graph import GraphService

router = APIRouter(prefix="/graph", tags=["graph"])
logger = get_logger(__name__)


@router.post("/nodes", response_model=NodeResponse)
async def create_node(
    body: NodeCreate,
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    """
    Create a node in the graph.

    Creates a node of specified type with properties. Nodes are automatically
    isolated by tenant.

    Returns:
        NodeResponse: The created node

    Raises:
        HTTPException 400: Invalid node type
        HTTPException 409: Node already exists
        HTTPException 500: Database error
    """
    try:
        # Validate node type
        try:
            node_type = NodeType(body.node_type)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid node_type. Must be one of: {', '.join([t.value for t in NodeType])}"
            )

        graph_service = GraphService(db, auth.tenant_id)
        node = await graph_service.create_node(
            node_type=node_type,
            node_id=body.node_id,
            properties=body.properties,
        )

        await db.commit()

        logger.info(
            f"Node created: {node_type.value}:{body.node_id}",
            extra={"tenant_id": str(auth.tenant_id), "node_type": node_type.value}
        )

        return NodeResponse(
            id=str(node.id),
            tenant_id=str(node.tenant_id),
            node_type=node.node_type,
            node_id=node.node_id,
            properties=node.properties,
            created_at=node.created_at,
        )

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to create node: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to create node: {str(e)}")


@router.post("/edges", response_model=EdgeResponse)
async def create_edge(
    body: EdgeCreate,
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    """
    Create an edge between two nodes.

    Creates a directed edge from source to target node with optional properties.

    Returns:
        EdgeResponse: The created edge

    Raises:
        HTTPException 400: Invalid node/edge type
        HTTPException 404: Source or target node not found
        HTTPException 500: Database error
    """
    try:
        # Validate types
        try:
            source_type = NodeType(body.source_type)
            target_type = NodeType(body.target_type)
            edge_type = EdgeType(body.edge_type)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Invalid type: {str(e)}")

        graph_service = GraphService(db, auth.tenant_id)
        edge = await graph_service.create_edge(
            source_type=source_type,
            source_id=body.source_id,
            edge_type=edge_type,
            target_type=target_type,
            target_id=body.target_id,
            properties=body.properties,
        )

        await db.commit()

        logger.info(
            f"Edge created: {source_type.value}:{body.source_id} -{edge_type.value}-> {target_type.value}:{body.target_id}",
            extra={"tenant_id": str(auth.tenant_id)}
        )

        return EdgeResponse(
            id=str(edge.id),
            tenant_id=str(edge.tenant_id),
            source_type=edge.source_type,
            source_id=edge.source_id,
            edge_type=edge.edge_type,
            target_type=edge.target_type,
            target_id=edge.target_id,
            properties=edge.properties,
            created_at=edge.created_at,
        )

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to create edge: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to create edge: {str(e)}")


@router.post("/neighbors", response_model=GraphQueryResponse)
async def get_neighbors(
    body: NeighborsRequest,
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    """
    Get neighboring nodes.

    Retrieves nodes connected to the specified node via edges, optionally
    filtered by edge type and direction.

    Returns:
        GraphQueryResponse: List of neighbor nodes with relationship info

    Raises:
        HTTPException 400: Invalid node type
        HTTPException 500: Query error
    """
    try:
        try:
            node_type = NodeType(body.node_type)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid node_type. Must be one of: {', '.join([t.value for t in NodeType])}"
            )

        edge_types = None
        if body.edge_types:
            try:
                edge_types = [EdgeType(et) for et in body.edge_types]
            except ValueError as e:
                raise HTTPException(status_code=400, detail=f"Invalid edge_type: {str(e)}")

        graph_service = GraphService(db, auth.tenant_id)
        results = await graph_service.get_neighbors(
            node_type=node_type,
            node_id=body.node_id,
            edge_types=edge_types,
            direction=body.direction,
            limit=body.limit,
        )

        return GraphQueryResponse(results=results, count=len(results))

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get neighbors: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Query failed: {str(e)}")


@router.post("/paths", response_model=GraphQueryResponse)
async def find_path(
    body: PathRequest,
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    """
    Find shortest path between two nodes.

    Finds the shortest path connecting source and target nodes within the
    specified maximum depth.

    Returns:
        GraphQueryResponse: Path information (nodes and edges)

    Raises:
        HTTPException 400: Invalid node types
        HTTPException 404: Path not found
        HTTPException 500: Query error
    """
    try:
        try:
            source_type = NodeType(body.source_type)
            target_type = NodeType(body.target_type)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Invalid type: {str(e)}")

        graph_service = GraphService(db, auth.tenant_id)
        results = await graph_service.find_path(
            source_type=source_type,
            source_id=body.source_id,
            target_type=target_type,
            target_id=body.target_id,
            max_depth=body.max_depth,
        )

        if not results:
            raise HTTPException(
                status_code=404,
                detail=f"No path found between {body.source_type}:{body.source_id} and {body.target_type}:{body.target_id}"
            )

        return GraphQueryResponse(results=results, count=len(results))

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to find path: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Query failed: {str(e)}")


@router.post("/query", response_model=GraphQueryResponse)
async def execute_query(
    body: GraphQueryRequest,
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    """
    Execute a custom Cypher query.

    Executes a custom Cypher query with automatic tenant isolation.
    The query MUST include a tenant_id filter for security.

    Returns:
        GraphQueryResponse: Query results

    Raises:
        HTTPException 400: Query missing tenant_id filter
        HTTPException 500: Query execution error
    """
    try:
        graph_service = GraphService(db, auth.tenant_id)
        results = await graph_service.query(
            cypher=body.cypher,
            params=body.params,
        )

        logger.info(
            f"Custom query executed: {len(results)} results",
            extra={"tenant_id": str(auth.tenant_id)}
        )

        return GraphQueryResponse(results=results, count=len(results))

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Query failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Query execution failed: {str(e)}")


@router.get("/nodes/{node_type}/{node_id}", response_model=NodeResponse)
async def get_node(
    node_type: str,
    node_id: str,
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    """
    Get a node by type and ID.

    Retrieves a single node from the graph.

    Returns:
        NodeResponse: The requested node

    Raises:
        HTTPException 400: Invalid node type
        HTTPException 404: Node not found
        HTTPException 500: Database error
    """
    try:
        # Validate node type
        try:
            node_type_enum = NodeType(node_type)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid node_type. Must be one of: {', '.join([t.value for t in NodeType])}"
            )

        graph_service = GraphService(db, auth.tenant_id)
        result = await graph_service.get_node(
            node_type=node_type_enum,
            node_id=node_id,
        )

        if not result:
            raise HTTPException(
                status_code=404,
                detail=f"Node {node_type}:{node_id} not found"
            )

        # Get tracking record for metadata
        from sqlalchemy import select
        from server.app.models.graph import GraphNode
        node_result = await db.execute(
            select(GraphNode).where(
                GraphNode.tenant_id == auth.tenant_id,
                GraphNode.node_type == node_type,
                GraphNode.node_id == node_id,
            )
        )
        node = node_result.scalar_one()

        return NodeResponse(
            id=str(node.id),
            tenant_id=str(node.tenant_id),
            node_type=node.node_type,
            node_id=node.node_id,
            properties=node.properties,
            created_at=node.created_at,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get node: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get node: {str(e)}")


@router.put("/nodes/{node_type}/{node_id}", response_model=NodeResponse)
async def update_node(
    node_type: str,
    node_id: str,
    body: NodeUpdate,
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    """
    Update a node's properties.

    Updates the properties of an existing node. Properties are merged with existing values.

    Returns:
        NodeResponse: The updated node

    Raises:
        HTTPException 400: Invalid node type
        HTTPException 404: Node not found
        HTTPException 500: Database error
    """
    try:
        # Validate node type
        try:
            node_type_enum = NodeType(node_type)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid node_type. Must be one of: {', '.join([t.value for t in NodeType])}"
            )

        graph_service = GraphService(db, auth.tenant_id)
        node = await graph_service.update_node(
            node_type=node_type_enum,
            node_id=node_id,
            properties=body.properties,
        )

        await db.commit()

        logger.info(
            f"Node updated: {node_type}:{node_id}",
            extra={"tenant_id": str(auth.tenant_id)}
        )

        return NodeResponse(
            id=str(node.id),
            tenant_id=str(node.tenant_id),
            node_type=node.node_type,
            node_id=node.node_id,
            properties=node.properties,
            created_at=node.created_at,
        )

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to update node: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to update node: {str(e)}")


@router.delete("/nodes/{node_type}/{node_id}", status_code=204)
async def delete_node(
    node_type: str,
    node_id: str,
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    """
    Delete a node and all its edges.

    Deletes a node from the graph along with all edges connected to it.

    Returns:
        No content (204)

    Raises:
        HTTPException 400: Invalid node type
        HTTPException 404: Node not found
        HTTPException 500: Database error
    """
    try:
        # Validate node type
        try:
            node_type_enum = NodeType(node_type)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid node_type. Must be one of: {', '.join([t.value for t in NodeType])}"
            )

        graph_service = GraphService(db, auth.tenant_id)
        await graph_service.delete_node(
            node_type=node_type_enum,
            node_id=node_id,
        )

        await db.commit()

        logger.info(
            f"Node deleted: {node_type}:{node_id}",
            extra={"tenant_id": str(auth.tenant_id)}
        )

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to delete node: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to delete node: {str(e)}")


@router.get("/edges/{source_type}/{source_id}/{edge_type}/{target_type}/{target_id}", response_model=EdgeResponse)
async def get_edge(
    source_type: str,
    source_id: str,
    edge_type: str,
    target_type: str,
    target_id: str,
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    """
    Get an edge by source, target, and type.

    Retrieves a single edge from the graph.

    Returns:
        EdgeResponse: The requested edge

    Raises:
        HTTPException 400: Invalid node/edge type
        HTTPException 404: Edge not found
        HTTPException 500: Database error
    """
    try:
        # Validate types
        try:
            source_type_enum = NodeType(source_type)
            target_type_enum = NodeType(target_type)
            edge_type_enum = EdgeType(edge_type)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Invalid type: {str(e)}")

        graph_service = GraphService(db, auth.tenant_id)
        result = await graph_service.get_edge(
            source_type=source_type_enum,
            source_id=source_id,
            edge_type=edge_type_enum,
            target_type=target_type_enum,
            target_id=target_id,
        )

        if not result:
            raise HTTPException(
                status_code=404,
                detail=f"Edge {source_type}:{source_id}-[{edge_type}]->{target_type}:{target_id} not found"
            )

        # Get tracking record for metadata
        from sqlalchemy import select
        from server.app.models.graph import GraphEdge
        edge_result = await db.execute(
            select(GraphEdge).where(
                GraphEdge.tenant_id == auth.tenant_id,
                GraphEdge.source_type == source_type,
                GraphEdge.source_id == source_id,
                GraphEdge.edge_type == edge_type,
                GraphEdge.target_type == target_type,
                GraphEdge.target_id == target_id,
            )
        )
        edge = edge_result.scalar_one()

        return EdgeResponse(
            id=str(edge.id),
            tenant_id=str(edge.tenant_id),
            source_type=edge.source_type,
            source_id=edge.source_id,
            edge_type=edge.edge_type,
            target_type=edge.target_type,
            target_id=edge.target_id,
            properties=edge.properties,
            created_at=edge.created_at,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get edge: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get edge: {str(e)}")


@router.put("/edges/{source_type}/{source_id}/{edge_type}/{target_type}/{target_id}", response_model=EdgeResponse)
async def update_edge(
    source_type: str,
    source_id: str,
    edge_type: str,
    target_type: str,
    target_id: str,
    body: EdgeUpdate,
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    """
    Update an edge's properties.

    Updates the properties of an existing edge. Properties are merged with existing values.

    Returns:
        EdgeResponse: The updated edge

    Raises:
        HTTPException 400: Invalid node/edge type
        HTTPException 404: Edge not found
        HTTPException 500: Database error
    """
    try:
        # Validate types
        try:
            source_type_enum = NodeType(source_type)
            target_type_enum = NodeType(target_type)
            edge_type_enum = EdgeType(edge_type)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Invalid type: {str(e)}")

        graph_service = GraphService(db, auth.tenant_id)
        edge = await graph_service.update_edge(
            source_type=source_type_enum,
            source_id=source_id,
            edge_type=edge_type_enum,
            target_type=target_type_enum,
            target_id=target_id,
            properties=body.properties,
        )

        await db.commit()

        logger.info(
            f"Edge updated: {source_type}:{source_id}-[{edge_type}]->{target_type}:{target_id}",
            extra={"tenant_id": str(auth.tenant_id)}
        )

        return EdgeResponse(
            id=str(edge.id),
            tenant_id=str(edge.tenant_id),
            source_type=edge.source_type,
            source_id=edge.source_id,
            edge_type=edge.edge_type,
            target_type=edge.target_type,
            target_id=edge.target_id,
            properties=edge.properties,
            created_at=edge.created_at,
        )

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to update edge: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to update edge: {str(e)}")


@router.delete("/edges/{source_type}/{source_id}/{edge_type}/{target_type}/{target_id}", status_code=204)
async def delete_edge(
    source_type: str,
    source_id: str,
    edge_type: str,
    target_type: str,
    target_id: str,
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    """
    Delete an edge.

    Deletes an edge from the graph.

    Returns:
        No content (204)

    Raises:
        HTTPException 400: Invalid node/edge type
        HTTPException 404: Edge not found
        HTTPException 500: Database error
    """
    try:
        # Validate types
        try:
            source_type_enum = NodeType(source_type)
            target_type_enum = NodeType(target_type)
            edge_type_enum = EdgeType(edge_type)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Invalid type: {str(e)}")

        graph_service = GraphService(db, auth.tenant_id)
        await graph_service.delete_edge(
            source_type=source_type_enum,
            source_id=source_id,
            edge_type=edge_type_enum,
            target_type=target_type_enum,
            target_id=target_id,
        )

        await db.commit()

        logger.info(
            f"Edge deleted: {source_type}:{source_id}-[{edge_type}]->{target_type}:{target_id}",
            extra={"tenant_id": str(auth.tenant_id)}
        )

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to delete edge: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to delete edge: {str(e)}")
