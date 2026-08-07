"""API Endpoints for Context Memory Service."""

import uuid
from datetime import UTC, datetime
from typing import Any

import structlog
from fastapi import (
    APIRouter,
    Depends,
    Header,
    HTTPException,
    Query,
    Request,
    Response,
    status,
)
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from context_memory.config.settings import get_settings
from context_memory.embeddings.embedder import DummyEmbedder, Embedder
from context_memory.governance.retention import RetentionPolicy
from context_memory.persistence.audit_repo import AuditRepository
from context_memory.persistence.database import get_session
from context_memory.persistence.memory_repo import MemoryRepository
from context_memory.persistence.session_repo import SessionRepository
from context_memory.security.jwt_auth import (
    JWTAuthenticator,
    TokenExpiredError,
    TokenPayload,
    TokenValidationError,
)
from context_memory.security.rbac_abac import RBACABACEngine
from context_memory.security.tenant_guard import (
    SecurityBoundaryViolation,
    TenantIsolationGuard,
)
from context_memory.services.memory_service import MemoryService
from context_memory.services.session_service import SessionService
from context_memory.session.hydration import SessionHydrator
from context_memory.utils.exceptions import (
    ErrorCode,
    ErrorResponse,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/v1", tags=["Context Memory"])
settings = get_settings()
authenticator = JWTAuthenticator()
tenant_guard = TenantIsolationGuard()
rbac_engine = RBACABACEngine()
embedder: Embedder = DummyEmbedder()
retention = RetentionPolicy(default_ttl_days=settings.default_retention_days)


class MemoryCreateRequest(BaseModel):
    """Request model for creating a memory."""

    tenant_id: str = Field(..., min_length=3, max_length=255, description="Tenant identifier")
    session_id: str = Field(..., min_length=1, max_length=255, description="Session identifier")
    user_id: str = Field(..., min_length=1, max_length=255, description="User identifier")
    content: str = Field(..., min_length=1, max_length=100000, description="Memory content")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")
    importance: float = Field(default=1.0, ge=0.0, le=10.0, description="Memory importance score")
    memory_type: str = Field(default="general", description="Type of memory")
    idempotency_key: str | None = Field(default=None, description="Idempotency key")

    @field_validator("content")
    @classmethod
    def validate_content(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Content cannot be empty or whitespace only")
        return v.strip()


class MemoryUpdateRequest(BaseModel):
    """Request model for updating a memory."""

    content: str | None = Field(default=None, min_length=1, max_length=100000, description="Updated content")
    metadata: dict[str, Any] | None = Field(default=None, description="Updated metadata")
    importance: float | None = Field(default=None, ge=0.0, le=10.0, description="Updated importance")


class MemoryResponse(BaseModel):
    """Response model for memory operations."""

    id: str
    tenant_id: str
    session_id: str
    user_id: str
    content: str
    metadata: dict[str, Any]
    importance: float
    memory_type: str
    created_at: str
    updated_at: str
    expires_at: str | None = None


class PaginatedResponse(BaseModel):
    """Paginated response wrapper."""

    items: list[Any]
    total: int
    page: int
    size: int
    pages: int


class SessionHydrateRequest(BaseModel):
    """Request model for session hydration."""

    tenant_id: str = Field(..., min_length=3, max_length=255)
    session_id: str = Field(..., min_length=1, max_length=255)
    user_id: str = Field(..., min_length=1, max_length=255)
    max_tokens: int = Field(default=4000, ge=100, le=128000)


class SearchRequest(BaseModel):
    """Request model for semantic memory search."""

    tenant_id: str = Field(..., min_length=3, max_length=255)
    query: str = Field(..., min_length=1, max_length=5000)
    top_k: int = Field(default=10, ge=1, le=100)
    memory_type: str | None = Field(default=None)


class BatchCreateRequest(BaseModel):
    """Request model for batch memory creation."""

    memories: list[MemoryCreateRequest] = Field(..., min_length=1, max_length=100, description="Memories to create")


async def get_current_user(
    request: Request,
    authorization: str = Header(..., description="Bearer JWT token"),
    x_tenant_id: str = Header(..., description="Tenant identifier"),
) -> TokenPayload:
    """Extract and validate JWT claims from the request."""
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ErrorResponse(
                error_code=ErrorCode.AUTHENTICATION_FAILED,
                message="Invalid authorization header format",
                correlation_id=getattr(request.state, "correlation_id", None),
            ).model_dump(),
        )

    token = authorization.replace("Bearer ", "")

    try:
        claims = authenticator.decode_and_validate(token)
    except TokenExpiredError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ErrorResponse(
                error_code=ErrorCode.TOKEN_EXPIRED,
                message="Access token has expired",
                correlation_id=getattr(request.state, "correlation_id", None),
            ).model_dump(),
        )
    except TokenValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ErrorResponse(
                error_code=ErrorCode.AUTHENTICATION_FAILED,
                message=str(e),
                correlation_id=getattr(request.state, "correlation_id", None),
            ).model_dump(),
        )

    try:
        tenant_guard.verify_tenant_boundary(x_tenant_id, claims)
    except SecurityBoundaryViolation as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=ErrorResponse(
                error_code=ErrorCode.TENANT_ISOLATION_VIOLATION,
                message=str(e),
                correlation_id=getattr(request.state, "correlation_id", None),
            ).model_dump(),
        )

    return claims


def get_memory_service(db: AsyncSession = Depends(get_session)) -> MemoryService:
    """Create MemoryService instance with dependencies."""
    return MemoryService(MemoryRepository(db), embedder, retention)


def get_session_service(db: AsyncSession = Depends(get_session)) -> SessionService:
    """Create SessionService instance with dependencies."""
    return SessionService(SessionRepository(db))


def get_audit_repo(db: AsyncSession = Depends(get_session)) -> AuditRepository:
    """Create AuditRepository instance."""
    return AuditRepository(db)


@router.get("/health/live", tags=["Health"])
async def liveness_check() -> dict[str, str]:
    """Kubernetes liveness probe endpoint."""
    return {"status": "UP", "timestamp": datetime.now(UTC).isoformat()}


@router.get("/health/ready", tags=["Health"])
async def readiness_check(
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Kubernetes readiness probe endpoint."""
    checks: dict[str, str] = {}
    try:
        await db.execute("SELECT 1")
        checks["database"] = "UP"
    except Exception as e:
        checks["database"] = f"DOWN: {str(e)}"

    try:
        from context_memory.cache.redis_client import get_redis_client

        redis = await get_redis_client()
        if await redis.ping():
            checks["redis"] = "UP"
        else:
            checks["redis"] = "DOWN"
    except Exception as e:
        checks["redis"] = f"DOWN: {str(e)}"

    all_up = all(v == "UP" for v in checks.values())
    return {
        "status": "UP" if all_up else "DEGRADED",
        "checks": checks,
        "timestamp": datetime.now(UTC).isoformat(),
    }


@router.get("/health/startup", tags=["Health"])
async def startup_check() -> dict[str, str]:
    """Kubernetes startup probe endpoint."""
    return {"status": "UP", "timestamp": datetime.now(UTC).isoformat()}


@router.post(
    "/memories",
    response_model=MemoryResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new memory",
)
async def create_memory(
    req: MemoryCreateRequest,
    request: Request,
    claims: TokenPayload = Depends(get_current_user),
    memory_service: MemoryService = Depends(get_memory_service),
    audit_repo: AuditRepository = Depends(get_audit_repo),
) -> MemoryResponse:
    """Create a new context memory with embedding generation."""
    try:
        rbac_engine.authorize_write_request(claims)

        if req.tenant_id != claims.tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ErrorResponse(
                    error_code=ErrorCode.TENANT_ISOLATION_VIOLATION,
                    message="Tenant ID in request does not match authenticated tenant",
                    correlation_id=getattr(request.state, "correlation_id", None),
                ).model_dump(),
            )

        memory = await memory_service.add_memory(
            tenant_id=req.tenant_id,
            session_id=req.session_id,
            user_id=req.user_id,
            content=req.content,
            metadata=req.metadata,
            importance=req.importance,
            memory_type=req.memory_type,
        )

        logger.info(
            "Memory created",
            memory_id=str(memory.id),
            tenant_id=req.tenant_id,
            session_id=req.session_id,
        )

        return MemoryResponse(
            id=str(memory.id),
            tenant_id=memory.tenant_id,
            session_id=memory.session_id,
            user_id=memory.user_id,
            content=memory.content,
            metadata=memory.metadata_,
            importance=memory.importance,
            memory_type=memory.memory_type,
            created_at=memory.created_at.isoformat(),
            updated_at=memory.updated_at.isoformat(),
            expires_at=memory.expires_at.isoformat() if memory.expires_at else None,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to create memory", error=str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ErrorResponse(
                error_code=ErrorCode.INTERNAL_ERROR,
                message="Failed to create memory",
                correlation_id=getattr(request.state, "correlation_id", None),
            ).model_dump(),
        )


@router.get(
    "/memories/{memory_id}",
    response_model=MemoryResponse,
    summary="Get a memory by ID",
)
async def get_memory(
    memory_id: uuid.UUID,
    request: Request,
    claims: TokenPayload = Depends(get_current_user),
    memory_service: MemoryService = Depends(get_memory_service),
) -> MemoryResponse:
    """Retrieve a specific memory by its ID."""
    try:
        rbac_engine.authorize_read_request(claims)

        memory = await memory_service.get_memory(memory_id, claims.tenant_id)

        if not memory:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ErrorResponse(
                    error_code=ErrorCode.RESOURCE_NOT_FOUND,
                    message=f"Memory {memory_id} not found",
                    correlation_id=getattr(request.state, "correlation_id", None),
                ).model_dump(),
            )

        return MemoryResponse(
            id=str(memory.id),
            tenant_id=memory.tenant_id,
            session_id=memory.session_id,
            user_id=memory.user_id,
            content=memory.content,
            metadata=memory.metadata_,
            importance=memory.importance,
            memory_type=memory.memory_type,
            created_at=memory.created_at.isoformat(),
            updated_at=memory.updated_at.isoformat(),
            expires_at=memory.expires_at.isoformat() if memory.expires_at else None,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get memory", memory_id=str(memory_id), error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ErrorResponse(
                error_code=ErrorCode.INTERNAL_ERROR,
                message="Failed to retrieve memory",
                correlation_id=getattr(request.state, "correlation_id", None),
            ).model_dump(),
        )


@router.get(
    "/memories",
    response_model=PaginatedResponse,
    summary="List memories for a session",
)
async def list_session_memories(
    session_id: str = Query(..., description="Session identifier"),
    page: int = Query(default=1, ge=1, description="Page number"),
    size: int = Query(default=20, ge=1, le=100, description="Page size"),
    memory_type: str | None = Query(default=None, description="Filter by memory type"),
    request: Request = None,
    claims: TokenPayload = Depends(get_current_user),
    memory_service: MemoryService = Depends(get_memory_service),
) -> PaginatedResponse:
    """List memories for a session with pagination."""
    try:
        rbac_engine.authorize_read_request(claims)

        memories = await memory_service.get_session_memories(
            tenant_id=claims.tenant_id,
            session_id=session_id,
            limit=size,
            offset=(page - 1) * size,
            memory_type=memory_type,
        )

        total = await memory_service.count_session_memories(claims.tenant_id, session_id)

        items = [
            MemoryResponse(
                id=str(m.id),
                tenant_id=m.tenant_id,
                session_id=m.session_id,
                user_id=m.user_id,
                content=m.content,
                metadata=m.metadata_,
                importance=m.importance,
                memory_type=m.memory_type,
                created_at=m.created_at.isoformat(),
                updated_at=m.updated_at.isoformat(),
                expires_at=m.expires_at.isoformat() if m.expires_at else None,
            )
            for m in memories
        ]

        return PaginatedResponse(
            items=items,
            total=total,
            page=page,
            size=size,
            pages=(total + size - 1) // size if size > 0 else 1,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to list memories", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ErrorResponse(
                error_code=ErrorCode.INTERNAL_ERROR,
                message="Failed to list memories",
                correlation_id=getattr(request.state, "correlation_id", None) if request else None,
            ).model_dump(),
        )


@router.put(
    "/memories/{memory_id}",
    response_model=MemoryResponse,
    summary="Update a memory",
)
async def update_memory(
    memory_id: uuid.UUID,
    req: MemoryUpdateRequest,
    request: Request,
    claims: TokenPayload = Depends(get_current_user),
    memory_service: MemoryService = Depends(get_memory_service),
) -> MemoryResponse:
    """Update an existing memory's content or metadata."""
    try:
        rbac_engine.authorize_write_request(claims)

        if not req.content and not req.metadata and req.importance is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ErrorResponse(
                    error_code=ErrorCode.VALIDATION_ERROR,
                    message="At least one field must be provided for update",
                    correlation_id=getattr(request.state, "correlation_id", None),
                ).model_dump(),
            )

        memory = await memory_service.update_memory(
            memory_id=memory_id,
            tenant_id=claims.tenant_id,
            content=req.content,
            metadata=req.metadata,
            importance=req.importance,
        )

        if not memory:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ErrorResponse(
                    error_code=ErrorCode.RESOURCE_NOT_FOUND,
                    message=f"Memory {memory_id} not found",
                    correlation_id=getattr(request.state, "correlation_id", None),
                ).model_dump(),
            )

        return MemoryResponse(
            id=str(memory.id),
            tenant_id=memory.tenant_id,
            session_id=memory.session_id,
            user_id=memory.user_id,
            content=memory.content,
            metadata=memory.metadata_,
            importance=memory.importance,
            memory_type=memory.memory_type,
            created_at=memory.created_at.isoformat(),
            updated_at=memory.updated_at.isoformat(),
            expires_at=memory.expires_at.isoformat() if memory.expires_at else None,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to update memory", memory_id=str(memory_id), error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ErrorResponse(
                error_code=ErrorCode.INTERNAL_ERROR,
                message="Failed to update memory",
                correlation_id=getattr(request.state, "correlation_id", None),
            ).model_dump(),
        )


@router.delete(
    "/memories/{memory_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a memory",
)
async def delete_memory(
    memory_id: uuid.UUID,
    request: Request,
    claims: TokenPayload = Depends(get_current_user),
    memory_service: MemoryService = Depends(get_memory_service),
) -> Response:
    """Soft delete a memory."""
    try:
        rbac_engine.authorize_write_request(claims)

        deleted = await memory_service.delete_memory(memory_id, claims.tenant_id)
        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ErrorResponse(
                    error_code=ErrorCode.RESOURCE_NOT_FOUND,
                    message=f"Memory {memory_id} not found",
                    correlation_id=getattr(request.state, "correlation_id", None),
                ).model_dump(),
            )

        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to delete memory", memory_id=str(memory_id), error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ErrorResponse(
                error_code=ErrorCode.INTERNAL_ERROR,
                message="Failed to delete memory",
                correlation_id=getattr(request.state, "correlation_id", None),
            ).model_dump(),
        )


@router.post(
    "/memories/search",
    response_model=dict[str, Any],
    summary="Search memories semantically",
)
async def search_memories(
    req: SearchRequest,
    request: Request,
    claims: TokenPayload = Depends(get_current_user),
    memory_service: MemoryService = Depends(get_memory_service),
) -> dict[str, Any]:
    """Search for similar memories using semantic similarity."""
    try:
        rbac_engine.authorize_read_request(claims)

        if req.tenant_id != claims.tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ErrorResponse(
                    error_code=ErrorCode.TENANT_ISOLATION_VIOLATION,
                    message="Tenant ID mismatch",
                    correlation_id=getattr(request.state, "correlation_id", None),
                ).model_dump(),
            )

        results = await memory_service.search_similar(
            tenant_id=req.tenant_id,
            query=req.query,
            top_k=req.top_k,
            memory_type=req.memory_type,
        )

        return {
            "results": [
                {
                    "id": str(mem.id),
                    "content": mem.content,
                    "similarity_score": score,
                    "metadata": mem.metadata_,
                    "memory_type": mem.memory_type,
                    "created_at": mem.created_at.isoformat(),
                }
                for mem, score in results
            ],
            "query": req.query,
            "total": len(results),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to search memories", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ErrorResponse(
                error_code=ErrorCode.INTERNAL_ERROR,
                message="Failed to search memories",
                correlation_id=getattr(request.state, "correlation_id", None),
            ).model_dump(),
        )


@router.post(
    "/sessions/hydrate",
    response_model=dict[str, Any],
    summary="Hydrate session context",
)
async def hydrate_session(
    req: SessionHydrateRequest,
    request: Request,
    claims: TokenPayload = Depends(get_current_user),
    memory_service: MemoryService = Depends(get_memory_service),
    session_service: SessionService = Depends(get_session_service),
) -> dict[str, Any]:
    """Hydrate a session with relevant context memories."""
    try:
        rbac_engine.authorize_read_request(claims)

        if req.tenant_id != claims.tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ErrorResponse(
                    error_code=ErrorCode.TENANT_ISOLATION_VIOLATION,
                    message="Tenant ID mismatch",
                    correlation_id=getattr(request.state, "correlation_id", None),
                ).model_dump(),
            )

        hydrator = SessionHydrator(memory_service, session_service)
        result = await hydrator.hydrate(
            tenant_id=req.tenant_id,
            session_id=req.session_id,
            user_id=req.user_id,
            max_tokens=req.max_tokens,
        )
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to hydrate session", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ErrorResponse(
                error_code=ErrorCode.INTERNAL_ERROR,
                message="Failed to hydrate session",
                correlation_id=getattr(request.state, "correlation_id", None),
            ).model_dump(),
        )
