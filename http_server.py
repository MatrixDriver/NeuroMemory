"""
NeuroMemory HTTP Server

基于 FastAPI 的 HTTP 服务端，供 DIFY 等 HTTP 客户端调用。

启动方式:
    uvicorn http_server:app --host 0.0.0.0 --port 8765

开发模式（自动重载）:
    uvicorn http_server:app --host 0.0.0.0 --port 8765 --reload

生产模式:
    uvicorn http_server:app --host 0.0.0.0 --port 8765 --workers 4
"""
import logging
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s - %(name)s - %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("neuro_memory.http")

from config import HTTP_SERVER_CONFIG
from health_checks import check_llm_config, check_neo4j, check_qdrant
from private_brain import get_brain
from session_manager import get_session_manager

# =============================================================================
# Lifespan：启动时启动 Session 超时检查
# =============================================================================


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动时启动 Session 超时检查任务（需在已有 event loop 中）"""
    get_session_manager().start_timeout_checker()
    yield
    # shutdown：可选清理


# =============================================================================
# FastAPI 应用初始化
# =============================================================================

app = FastAPI(
    title="NeuroMemory API",
    description="私有化外挂大脑服务 - Memory-as-a-Service",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# 配置 CORS（支持 DIFY 等跨域调用）
app.add_middleware(
    CORSMiddleware,
    allow_origins=HTTP_SERVER_CONFIG.get("cors_origins", ["*"]),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =============================================================================
# 请求/响应模型
# =============================================================================

class ProcessRequest(BaseModel):
    """处理记忆请求"""
    input: str
    user_id: str

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "input": "小朱的女儿叫什么？",
                    "user_id": "user_001"
                }
            ]
        }
    }


class DebugResponse(BaseModel):
    """调试模式响应"""
    report: str


class EndSessionRequest(BaseModel):
    """结束会话请求"""
    user_id: str


class EndSessionResponse(BaseModel):
    """结束会话响应"""
    status: str
    message: str
    session_info: dict | None = None


class AskRequest(BaseModel):
    """基于记忆问答请求"""
    question: str
    user_id: str = "default"


class AskResponse(BaseModel):
    """基于记忆问答响应"""
    answer: str
    sources: list


class HealthResponse(BaseModel):
    """健康检查响应（含 components）"""
    status: str
    service: str = "neuro-memory"
    components: dict  # {"neo4j": bool, "qdrant": bool, "llm": bool}


# =============================================================================
# API 端点
# =============================================================================


@app.get("/", summary="根路由")
def read_root() -> dict:
    """
    根路径，用于 Railway 等平台的存活探测及直接访问。
    避免未定义根路由时返回 404，被网关误判为 502。
    """
    return {
        "service": "neuro-memory",
        "docs": "/docs",
        "health": "/health",
    }


@app.post("/process", summary="处理记忆（生产模式）")
async def process_memory(request: ProcessRequest) -> dict:
    """
    处理用户输入，检索相关记忆并异步存储（Session 管理）。
    
    返回结构化 JSON，包含：
    - resolved_query: 指代消解后的查询
    - memories: 语义相关的记忆片段
    - relations: 知识图谱中的关系
    - metadata: 检索耗时、是否有记忆等信息
    
    适用于：将记忆上下文注入到 LLM prompt 中
    """
    logger.info(f"[/process] user_id={request.user_id}, input={request.input[:50]}...")
    
    try:
        brain = get_brain()
        result = await brain.process_async(request.input, request.user_id)
        return result
    except Exception as e:
        logger.error(f"[/process] 处理失败: {e}")
        # 静默降级：返回空结果
        return {
            "status": "error",
            "resolved_query": request.input,
            "memories": [],
            "relations": [],
            "metadata": {
                "retrieval_time_ms": 0,
                "has_memory": False,
                "error": str(e),
            }
        }


@app.post("/debug", summary="处理记忆（调试模式）")
async def debug_process_memory(request: ProcessRequest) -> DebugResponse:
    """
    调试模式：处理用户输入并返回详细的处理过程（旧版流程）。
    
    不写 Session、不做指代消解，仅演示检索 + 隐私分类 + 存储决策；适用于观察
    分类与存储行为。生产级流程（Session、指代消解）请使用 POST /process。
    
    报告包含：检索过程、存储决策、性能统计、原始数据。
    """
    logger.info(f"[/debug] user_id={request.user_id}, input={request.input[:50]}...")
    
    try:
        brain = get_brain()
        report = brain.process_debug(request.input, request.user_id)
        return DebugResponse(report=report)
    except Exception as e:
        logger.error(f"[/debug] 处理失败: {e}")
        return DebugResponse(report=f"=== 错误 ===\n处理失败: {e}")


@app.get("/graph/{user_id}", summary="获取用户知识图谱")
async def get_user_graph(user_id: str) -> dict:
    """
    获取用户的完整知识图谱。
    
    返回用户存储的所有记忆和实体关系。
    
    适用于：查看用户记忆状态、调试图谱结构
    """
    logger.info(f"[/graph] user_id={user_id}")
    
    try:
        brain = get_brain()
        result = brain.get_user_graph(user_id)
        return result
    except Exception as e:
        logger.error(f"[/graph] 获取失败: {e}")
        return {
            "status": "error",
            "user_id": user_id,
            "error": str(e),
        }


@app.post("/end-session", summary="结束会话")
async def end_session(request: EndSessionRequest) -> EndSessionResponse:
    """
    显式结束用户的当前会话。
    
    后台触发长期记忆整合流程：
    1. 对 Session 事件执行隐私过滤
    2. 存储私有数据到长期记忆
    3. 清理短期存储
    
    注意：接口立即返回，整合过程在后台异步执行。
    """
    logger.info(f"[/end-session] user_id={request.user_id}")
    
    try:
        brain = get_brain()
        result = await brain.end_session_async(request.user_id)
        return EndSessionResponse(**result)
    except Exception as e:
        logger.error(f"[/end-session] 处理失败: {e}")
        return EndSessionResponse(
            status="error",
            message=f"处理失败: {str(e)}",
            session_info=None,
        )


@app.get("/session-status/{user_id}", summary="获取会话状态")
async def get_session_status(user_id: str) -> dict:
    """
    获取用户当前会话状态（调试用）。
    
    返回 Session 的事件数、创建时间、最后活跃时间等信息。
    """
    logger.info(f"[/session-status] user_id={user_id}")
    
    try:
        status = get_session_manager().get_session_status(user_id)
        
        if status is None:
            return {
                "status": "success",
                "has_active_session": False,
                "session_info": None,
            }
        
        return {
            "status": "success",
            "has_active_session": True,
            "session_info": status,
        }
    except Exception as e:
        logger.error(f"[/session-status] 获取失败: {e}")
        return {
            "status": "error",
            "error": str(e),
        }


@app.get("/health", summary="健康检查")
async def health_check() -> HealthResponse:
    """
    健康检查 - 检查所有关键服务状态。

    返回：
    - status: healthy（所有必需服务可用）或 unhealthy
    - components: {neo4j, qdrant, llm} 各组件状态
    """
    neo4j_ok = check_neo4j()
    qdrant_ok = check_qdrant()
    llm_ok = check_llm_config()
    status = "healthy" if (neo4j_ok and qdrant_ok) else "unhealthy"
    return HealthResponse(
        status=status,
        service="neuro-memory",
        components={"neo4j": neo4j_ok, "qdrant": qdrant_ok, "llm": llm_ok},
    )


@app.get("/search", summary="纯检索", tags=["检索"])
async def search_memories(
    query: str = Query(..., description="查询文本"),
    user_id: str = Query("default", description="用户标识"),
    limit: int = Query(10, description="返回数量上限"),
) -> dict:
    """
    纯检索：混合检索相关记忆，不写 Session。

    返回 memories、relations、metadata，适用于只读查询场景。
    """
    logger.info(f"[/search] user_id={user_id}, query_len={len(query)}, limit={limit}")
    brain = get_brain()
    return brain.search(query, user_id=user_id, limit=limit)


@app.post("/ask", summary="基于记忆问答", tags=["问答"])
async def ask_with_memory(request: AskRequest) -> AskResponse:
    """
    基于记忆检索 + LLM 生成回答。

    返回 answer（LLM 生成的答案）和 sources（参考的记忆来源）。
    """
    logger.info(f"[/ask] user_id={request.user_id}, question_len={len(request.question)}")
    brain = get_brain()
    result = brain.ask(request.question, request.user_id)
    if result.get("error"):
        raise HTTPException(status_code=500, detail=result.get("error", "问答失败"))
    return AskResponse(answer=result["answer"], sources=result["sources"])


# =============================================================================
# 启动入口
# =============================================================================

if __name__ == "__main__":
    import uvicorn
    
    host = HTTP_SERVER_CONFIG.get("host", "0.0.0.0")
    port = HTTP_SERVER_CONFIG.get("port", 8765)
    
    logger.info(f"启动 NeuroMemory HTTP Server: http://{host}:{port}")
    logger.info(f"API 文档: http://{host}:{port}/docs")
    
    uvicorn.run(
        "http_server:app",
        host=host,
        port=port,
        reload=False,
    )
