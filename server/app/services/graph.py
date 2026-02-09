"""Graph database service using Apache AGE."""

import json
import uuid
from typing import Any

from sqlalchemy import select, text
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

        # Create node in AGE graph
        props_str = json.dumps(props)
        cypher = f"CREATE (n:{node_type.value} {props_str}) RETURN n"
        await self._execute_cypher(cypher)

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

        # Create edge in AGE graph
        props = properties or {}
        props_str = json.dumps(props) if props else ""

        cypher = f"""
        MATCH (a:{source_type.value} {{id: '{source_id}', tenant_id: '{self.tenant_id}'}})
        MATCH (b:{target_type.value} {{id: '{target_id}', tenant_id: '{self.tenant_id}'}})
        CREATE (a)-[r:{edge_type.value} {props_str}]->(b)
        RETURN r
        """
        await self._execute_cypher(cypher)

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

        cypher = f"""
        MATCH (n:{node_type.value} {{id: '{node_id}', tenant_id: '{self.tenant_id}'}})
        {rel}(neighbor)
        WHERE neighbor.tenant_id = '{self.tenant_id}'
        RETURN neighbor, type(r) as rel_type, properties(r) as rel_props
        LIMIT {limit}
        """

        return await self._execute_cypher(cypher)

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
        cypher = f"""
        MATCH path = shortestPath(
            (a:{source_type.value} {{id: '{source_id}', tenant_id: '{self.tenant_id}'}})-[*..{max_depth}]-
            (b:{target_type.value} {{id: '{target_id}', tenant_id: '{self.tenant_id}'}})
        )
        RETURN nodes(path) as nodes, relationships(path) as rels
        """

        return await self._execute_cypher(cypher)

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
