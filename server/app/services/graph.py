"""Graph database service using Apache AGE."""

import json
import uuid
from typing import Any

from sqlalchemy import delete, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from server.app.models.graph import EdgeType, GraphEdge, GraphNode, NodeType


class GraphService:
    """Service for managing graph data with Apache AGE."""

    def __init__(self, db: AsyncSession, tenant_id: uuid.UUID):
        self.db = db
        self.tenant_id = tenant_id
        self.graph_name = "neuromemory_graph"

    async def _execute_cypher(self, cypher: str, params: dict[str, Any] = None) -> list[dict]:
        """
        Execute a Cypher query using AGE.

        Args:
            cypher: Cypher query string
            params: Query parameters

        Returns:
            List of result dictionaries
        """
        # Build the AGE query
        # Note: AGE uses ag_catalog.cypher() function
        query = text(f"""
            SELECT * FROM ag_catalog.cypher(
                :graph_name,
                $$ {cypher} $$,
                :params
            ) as (result agtype);
        """)

        params_json = json.dumps(params or {})
        result = await self.db.execute(
            query,
            {"graph_name": self.graph_name, "params": params_json}
        )

        # Parse AGE results
        rows = []
        for row in result:
            # AGE returns agtype, need to parse it
            rows.append(self._parse_agtype(row[0]))

        return rows

    def _parse_agtype(self, agtype_value: Any) -> dict:
        """Parse AGE agtype value to Python dict."""
        if isinstance(agtype_value, str):
            try:
                return json.loads(agtype_value)
            except json.JSONDecodeError:
                return {"value": agtype_value}
        return agtype_value

    async def create_node(
        self,
        node_type: NodeType,
        node_id: str,
        properties: dict[str, Any] = None,
    ) -> GraphNode:
        """
        Create a node in the graph.

        Args:
            node_type: Type of node (User, Memory, etc.)
            node_id: Unique identifier for the node
            properties: Additional node properties

        Returns:
            GraphNode: The created node tracking record
        """
        # Check if node already exists in tracking table
        existing = await self.db.execute(
            select(GraphNode).where(
                GraphNode.tenant_id == self.tenant_id,
                GraphNode.node_type == node_type.value,
                GraphNode.node_id == node_id,
            )
        )
        if existing.scalar_one_or_none():
            raise ValueError(f"Node {node_type.value}:{node_id} already exists")

        # Prepare properties with tenant isolation
        props = properties or {}
        props.update({
            "id": node_id,
            "tenant_id": str(self.tenant_id),
            "node_type": node_type.value,
        })

        # Create node in AGE graph using parameterized query
        # Note: Node labels (node_type.value) are safe as they come from enum
        cypher = f"CREATE (n:{node_type.value} $props) RETURN n"
        await self._execute_cypher(cypher, {"props": props})

        # Create tracking record
        node = GraphNode(
            tenant_id=self.tenant_id,
            node_type=node_type.value,
            node_id=node_id,
            properties=properties,
        )
        self.db.add(node)
        await self.db.flush()

        return node

    async def create_edge(
        self,
        source_type: NodeType,
        source_id: str,
        edge_type: EdgeType,
        target_type: NodeType,
        target_id: str,
        properties: dict[str, Any] = None,
    ) -> GraphEdge:
        """
        Create an edge between two nodes.

        Args:
            source_type: Source node type
            source_id: Source node ID
            edge_type: Type of edge/relationship
            target_type: Target node type
            target_id: Target node ID
            properties: Edge properties

        Returns:
            GraphEdge: The created edge tracking record
        """
        # Verify nodes exist
        for ntype, nid in [(source_type, source_id), (target_type, target_id)]:
            node = await self.db.execute(
                select(GraphNode).where(
                    GraphNode.tenant_id == self.tenant_id,
                    GraphNode.node_type == ntype.value,
                    GraphNode.node_id == nid,
                )
            )
            if not node.scalar_one_or_none():
                raise ValueError(f"Node {ntype.value}:{nid} not found")

        # Create edge in AGE graph using parameterized query
        # Note: Labels and relationship types are safe as they come from enums
        props = properties or {}

        cypher = f"""
        MATCH (a:{source_type.value} {{id: $source_id, tenant_id: $tenant_id}})
        MATCH (b:{target_type.value} {{id: $target_id, tenant_id: $tenant_id}})
        CREATE (a)-[r:{edge_type.value} $props]->(b)
        RETURN r
        """
        params = {
            "source_id": source_id,
            "target_id": target_id,
            "tenant_id": str(self.tenant_id),
            "props": props if props else {}
        }
        await self._execute_cypher(cypher, params)

        # Create tracking record
        edge = GraphEdge(
            tenant_id=self.tenant_id,
            source_type=source_type.value,
            source_id=source_id,
            edge_type=edge_type.value,
            target_type=target_type.value,
            target_id=target_id,
            properties=properties,
        )
        self.db.add(edge)
        await self.db.flush()

        return edge

    async def get_neighbors(
        self,
        node_type: NodeType,
        node_id: str,
        edge_types: list[EdgeType] = None,
        direction: str = "both",  # "in", "out", "both"
        limit: int = 10,
    ) -> list[dict]:
        """
        Get neighboring nodes.

        Args:
            node_type: Node type
            node_id: Node ID
            edge_types: Filter by edge types
            direction: Direction of edges ("in", "out", "both")
            limit: Maximum number of neighbors

        Returns:
            List of neighbor nodes with relationship info
        """
        edge_filter = ""
        if edge_types:
            edge_types_str = "|".join([et.value for et in edge_types])
            edge_filter = f":{edge_types_str}"

        if direction == "out":
            rel = f"-[r{edge_filter}]->"
        elif direction == "in":
            rel = f"<-[r{edge_filter}]-"
        else:  # both
            rel = f"-[r{edge_filter}]-"

        # Use parameterized query to prevent injection
        # Note: node_type and edge_filter are safe as they come from enums
        cypher = f"""
        MATCH (n:{node_type.value} {{id: $node_id, tenant_id: $tenant_id}})
        {rel}(neighbor)
        WHERE neighbor.tenant_id = $tenant_id
        RETURN neighbor, type(r) as rel_type, properties(r) as rel_props
        LIMIT $limit
        """
        params = {
            "node_id": node_id,
            "tenant_id": str(self.tenant_id),
            "limit": limit
        }

        return await self._execute_cypher(cypher, params)

    async def find_path(
        self,
        source_type: NodeType,
        source_id: str,
        target_type: NodeType,
        target_id: str,
        max_depth: int = 3,
    ) -> list[dict]:
        """
        Find shortest path between two nodes.

        Args:
            source_type: Source node type
            source_id: Source node ID
            target_type: Target node type
            target_id: Target node ID
            max_depth: Maximum path length

        Returns:
            List of paths (nodes and edges)
        """
        # Use parameterized query to prevent injection
        # Note: node types are safe as they come from enums
        # max_depth needs to be in the pattern, not parameterizable in AGE
        if not isinstance(max_depth, int) or max_depth < 1 or max_depth > 10:
            raise ValueError("max_depth must be an integer between 1 and 10")

        cypher = f"""
        MATCH path = shortestPath(
            (a:{source_type.value} {{id: $source_id, tenant_id: $tenant_id}})-[*..{max_depth}]-
            (b:{target_type.value} {{id: $target_id, tenant_id: $tenant_id}})
        )
        RETURN nodes(path) as nodes, relationships(path) as rels
        """
        params = {
            "source_id": source_id,
            "target_id": target_id,
            "tenant_id": str(self.tenant_id)
        }

        return await self._execute_cypher(cypher, params)

    async def query(
        self,
        cypher: str,
        params: dict[str, Any] = None,
    ) -> list[dict]:
        """
        Execute a custom Cypher query with tenant isolation.

        Args:
            cypher: Cypher query (must include tenant_id filter)
            params: Query parameters

        Returns:
            Query results

        Raises:
            ValueError: If query doesn't include tenant_id filter
        """
        # Ensure tenant isolation
        if "tenant_id" not in cypher:
            raise ValueError("Cypher query must include tenant_id filter")

        params = params or {}
        params["tenant_id"] = str(self.tenant_id)

        return await self._execute_cypher(cypher, params)

    async def get_node(
        self,
        node_type: NodeType,
        node_id: str,
    ) -> dict | None:
        """
        Get a single node by type and ID.

        Args:
            node_type: Type of node
            node_id: Node ID

        Returns:
            Node data dict or None if not found
        """
        cypher = f"""
        MATCH (n:{node_type.value} {{id: $node_id, tenant_id: $tenant_id}})
        RETURN n
        """
        params = {
            "node_id": node_id,
            "tenant_id": str(self.tenant_id)
        }

        results = await self._execute_cypher(cypher, params)
        return results[0] if results else None

    async def update_node(
        self,
        node_type: NodeType,
        node_id: str,
        properties: dict[str, Any],
    ) -> GraphNode:
        """
        Update node properties.

        Args:
            node_type: Type of node
            node_id: Node ID
            properties: Properties to update (will merge with existing)

        Returns:
            Updated GraphNode tracking record

        Raises:
            ValueError: If node doesn't exist
        """
        # Verify node exists in tracking table
        node_result = await self.db.execute(
            select(GraphNode).where(
                GraphNode.tenant_id == self.tenant_id,
                GraphNode.node_type == node_type.value,
                GraphNode.node_id == node_id,
            )
        )
        node = node_result.scalar_one_or_none()
        if not node:
            raise ValueError(f"Node {node_type.value}:{node_id} not found")

        # Update node in AGE graph
        # Build SET clause from properties
        set_clauses = ", ".join([f"n.{key} = $props.{key}" for key in properties.keys()])
        cypher = f"""
        MATCH (n:{node_type.value} {{id: $node_id, tenant_id: $tenant_id}})
        SET {set_clauses}
        RETURN n
        """
        params = {
            "node_id": node_id,
            "tenant_id": str(self.tenant_id),
            "props": properties
        }
        await self._execute_cypher(cypher, params)

        # Update tracking record
        node.properties = {**(node.properties or {}), **properties}
        await self.db.flush()

        return node

    async def delete_node(
        self,
        node_type: NodeType,
        node_id: str,
    ) -> None:
        """
        Delete a node and all its edges.

        Args:
            node_type: Type of node
            node_id: Node ID

        Raises:
            ValueError: If node doesn't exist
        """
        # Verify node exists in tracking table
        node_result = await self.db.execute(
            select(GraphNode).where(
                GraphNode.tenant_id == self.tenant_id,
                GraphNode.node_type == node_type.value,
                GraphNode.node_id == node_id,
            )
        )
        node = node_result.scalar_one_or_none()
        if not node:
            raise ValueError(f"Node {node_type.value}:{node_id} not found")

        # Delete node and edges in AGE graph
        cypher = f"""
        MATCH (n:{node_type.value} {{id: $node_id, tenant_id: $tenant_id}})
        DETACH DELETE n
        """
        params = {
            "node_id": node_id,
            "tenant_id": str(self.tenant_id)
        }
        await self._execute_cypher(cypher, params)

        # Delete tracking records (node and related edges)
        await self.db.delete(node)

        # Delete all edges connected to this node
        await self.db.execute(
            delete(GraphEdge).where(
                GraphEdge.tenant_id == self.tenant_id,
                or_(
                    (GraphEdge.source_type == node_type.value) & (GraphEdge.source_id == node_id),
                    (GraphEdge.target_type == node_type.value) & (GraphEdge.target_id == node_id)
                )
            )
        )
        await self.db.flush()

    async def get_edge(
        self,
        source_type: NodeType,
        source_id: str,
        edge_type: EdgeType,
        target_type: NodeType,
        target_id: str,
    ) -> dict | None:
        """
        Get a single edge.

        Args:
            source_type: Source node type
            source_id: Source node ID
            edge_type: Type of edge
            target_type: Target node type
            target_id: Target node ID

        Returns:
            Edge data dict or None if not found
        """
        cypher = f"""
        MATCH (a:{source_type.value} {{id: $source_id, tenant_id: $tenant_id}})-[r:{edge_type.value}]->(b:{target_type.value} {{id: $target_id, tenant_id: $tenant_id}})
        RETURN r
        """
        params = {
            "source_id": source_id,
            "target_id": target_id,
            "tenant_id": str(self.tenant_id)
        }

        results = await self._execute_cypher(cypher, params)
        return results[0] if results else None

    async def update_edge(
        self,
        source_type: NodeType,
        source_id: str,
        edge_type: EdgeType,
        target_type: NodeType,
        target_id: str,
        properties: dict[str, Any],
    ) -> GraphEdge:
        """
        Update edge properties.

        Args:
            source_type: Source node type
            source_id: Source node ID
            edge_type: Type of edge
            target_type: Target node type
            target_id: Target node ID
            properties: Properties to update (will merge with existing)

        Returns:
            Updated GraphEdge tracking record

        Raises:
            ValueError: If edge doesn't exist
        """
        # Verify edge exists in tracking table
        edge_result = await self.db.execute(
            select(GraphEdge).where(
                GraphEdge.tenant_id == self.tenant_id,
                GraphEdge.source_type == source_type.value,
                GraphEdge.source_id == source_id,
                GraphEdge.edge_type == edge_type.value,
                GraphEdge.target_type == target_type.value,
                GraphEdge.target_id == target_id,
            )
        )
        edge = edge_result.scalar_one_or_none()
        if not edge:
            raise ValueError(f"Edge {source_type.value}:{source_id}-[{edge_type.value}]->{target_type.value}:{target_id} not found")

        # Update edge in AGE graph
        set_clauses = ", ".join([f"r.{key} = $props.{key}" for key in properties.keys()])
        cypher = f"""
        MATCH (a:{source_type.value} {{id: $source_id, tenant_id: $tenant_id}})-[r:{edge_type.value}]->(b:{target_type.value} {{id: $target_id, tenant_id: $tenant_id}})
        SET {set_clauses}
        RETURN r
        """
        params = {
            "source_id": source_id,
            "target_id": target_id,
            "tenant_id": str(self.tenant_id),
            "props": properties
        }
        await self._execute_cypher(cypher, params)

        # Update tracking record
        edge.properties = {**(edge.properties or {}), **properties}
        await self.db.flush()

        return edge

    async def delete_edge(
        self,
        source_type: NodeType,
        source_id: str,
        edge_type: EdgeType,
        target_type: NodeType,
        target_id: str,
    ) -> None:
        """
        Delete an edge.

        Args:
            source_type: Source node type
            source_id: Source node ID
            edge_type: Type of edge
            target_type: Target node type
            target_id: Target node ID

        Raises:
            ValueError: If edge doesn't exist
        """
        # Verify edge exists in tracking table
        edge_result = await self.db.execute(
            select(GraphEdge).where(
                GraphEdge.tenant_id == self.tenant_id,
                GraphEdge.source_type == source_type.value,
                GraphEdge.source_id == source_id,
                GraphEdge.edge_type == edge_type.value,
                GraphEdge.target_type == target_type.value,
                GraphEdge.target_id == target_id,
            )
        )
        edge = edge_result.scalar_one_or_none()
        if not edge:
            raise ValueError(f"Edge {source_type.value}:{source_id}-[{edge_type.value}]->{target_type.value}:{target_id} not found")

        # Delete edge in AGE graph
        cypher = f"""
        MATCH (a:{source_type.value} {{id: $source_id, tenant_id: $tenant_id}})-[r:{edge_type.value}]->(b:{target_type.value} {{id: $target_id, tenant_id: $tenant_id}})
        DELETE r
        """
        params = {
            "source_id": source_id,
            "target_id": target_id,
            "tenant_id": str(self.tenant_id)
        }
        await self._execute_cypher(cypher, params)

        # Delete tracking record
        await self.db.delete(edge)
        await self.db.flush()
