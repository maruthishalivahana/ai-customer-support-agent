"""Main FastAPI application entry point for Hiver AI Customer Support Agent.

Sets up application lifecycle, CORS, exception handlers, and base endpoints.
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.agent import get_support_agent
from src.classifier import get_classifier
from src.config import get_settings, logger
from src.database.mongodb import mongo_manager
from src.generator import get_response_generator
from src.retriever import get_retriever, get_semantic_retriever, get_tfidf_retriever
from src.schemas import (
    AgentRequest,
    AgentResponse,
    ClassificationResponse,
    ClassifyRequest,
    DatabaseHealth,
    HealthResponse,
    RetrievalResponse,
    RetrieveRequest,
)

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan context manager for startup and shutdown events."""
    logger.info("Starting up %s (version: %s)...", settings.APP_NAME, settings.APP_VERSION)
    # Attempt to initialize MongoDB indexes if DB is reachable
    is_healthy, _ = mongo_manager.ping()
    if is_healthy:
        logger.info("MongoDB is reachable. Initializing collection indexes...")
        mongo_manager.init_indexes()
    else:
        logger.warning("MongoDB ping failed on startup. Server will run with database offline.")

    # Warm up Semantic FAISS retrieval index if available
    semantic_retriever = get_semantic_retriever()
    if semantic_retriever and semantic_retriever.is_fitted:
        logger.info(
            "Semantic FAISS Retriever preloaded and ready (%d indexed vectors).",
            semantic_retriever.index.ntotal if semantic_retriever.index else 0,
        )
    else:
        logger.warning(
            "Semantic FAISS Retriever not loaded on startup. Run scripts/build_semantic_index.py to build it."
        )

    # Warm up TF-IDF retrieval index if available
    tfidf_retriever = get_tfidf_retriever()
    if tfidf_retriever and tfidf_retriever.is_fitted:
        logger.info("TF-IDF Retriever preloaded and ready (%d cases).", len(tfidf_retriever.cases))
    else:
        logger.warning(
            "TF-IDF Retriever not loaded on startup. Run scripts/build_retrieval_index.py to build it."
        )

    # Warm up intent classifier if available
    classifier = get_classifier()
    if classifier and classifier.is_trained:
        logger.info("Intent Classifier preloaded and ready.")
    else:
        logger.warning("Intent Classifier not loaded on startup. Run scripts/train_classifier.py to train it.")

    # Warm up Support Decision Agent & LLM Response Generator
    agent = get_support_agent()
    generator = get_response_generator()
    logger.info("Conversation Support Decision Agent & Response Generator preloaded and ready.")

    yield

    logger.info("Shutting down %s...", settings.APP_NAME)
    mongo_manager.close()


# Initialize FastAPI application
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description=(
        "Production-quality AI Customer Support Agent backend with grounded retrieval "
        "and confidence-based escalation for AppleSupport interactions."
    ),
    lifespan=lifespan,
)

# Enable CORS for React frontend (Vite default ports and standard dev ports)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "*",  # Adjust for strict production environments
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


from fastapi.encoders import jsonable_encoder


# ==============================================================================
# Global Exception Handlers
# ==============================================================================

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Handle request validation errors with clear, structured JSON."""
    logger.warning("Validation error on %s %s: %s", request.method, request.url.path, exc.errors())
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": "Validation Error",
            "message": "The request payload failed schema validation.",
            "details": jsonable_encoder(exc.errors()),
        },
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch unhandled server errors and prevent trace exposure in production."""
    logger.error("Unhandled error processing %s %s: %s", request.method, request.url.path, exc, exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "Internal Server Error",
            "message": "An unexpected error occurred while processing your request.",
        },
    )


# ==============================================================================
# Health & Status Endpoints
# ==============================================================================

@app.get(
    "/health",
    response_model=HealthResponse,
    summary="Health check endpoint",
    description="Returns the status of the API service and MongoDB connectivity.",
    tags=["System"],
)
def get_health() -> HealthResponse:
    """Check API and MongoDB connection health."""
    db_healthy, msg = mongo_manager.ping()

    db_status = "connected" if db_healthy else "disconnected"

    return HealthResponse(
        status="healthy",
        app_name=settings.APP_NAME,
        version=settings.APP_VERSION,
        environment=settings.ENVIRONMENT,
        database=DatabaseHealth(
            status=db_status,
            details=msg,
        ),
    )


# ==============================================================================
# Retrieval Endpoints
# ==============================================================================

@app.post(
    "/api/v1/retrieve",
    response_model=RetrievalResponse,
    summary="Retrieve historically grounded support cases",
    description=(
        "Finds top-K similar past AppleSupport interactions based on dense FAISS semantic similarity "
        "or TF-IDF cosine similarity."
    ),
    tags=["Retrieval"],
)
def retrieve_support_cases(payload: RetrieveRequest) -> RetrievalResponse:
    """Retrieve grounded historical support cases using requested retrieval strategy."""
    requested_engine = (payload.retriever or settings.RETRIEVER_TYPE).lower()

    active_retriever = None
    resolved_engine = requested_engine

    if requested_engine == "semantic":
        active_retriever = get_semantic_retriever()
        if not active_retriever or not active_retriever.is_fitted:
            # If user explicitly requested semantic, give exact actionable error
            if payload.retriever == "semantic":
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Semantic FAISS retrieval index is unavailable. Please run scripts/build_semantic_index.py first.",
                )
            # Automatic fallback to TF-IDF if default was semantic
            active_retriever = get_tfidf_retriever()
            resolved_engine = "tfidf"
    elif requested_engine == "tfidf":
        active_retriever = get_tfidf_retriever()
        if not active_retriever or not active_retriever.is_fitted:
            if payload.retriever == "tfidf":
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="TF-IDF retrieval index is unavailable. Please run scripts/build_retrieval_index.py first.",
                )
            active_retriever = get_semantic_retriever()
            resolved_engine = "semantic"
    else:
        active_retriever = get_retriever()
        resolved_engine = settings.RETRIEVER_TYPE

    if not active_retriever or not active_retriever.is_fitted:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Retrieval index is unavailable. Please run scripts/build_semantic_index.py or scripts/build_retrieval_index.py.",
        )

    results = active_retriever.retrieve(payload.message, top_k=payload.top_k)
    effective_k = payload.top_k if payload.top_k is not None else settings.TOP_K_RETRIEVAL

    return RetrievalResponse(
        query=payload.message,
        top_k=effective_k,
        retriever=resolved_engine,
        results=results,
    )


# ==============================================================================
# Classification Endpoints
# ==============================================================================

@app.post(
    "/api/v1/classify",
    response_model=ClassificationResponse,
    summary="Classify customer message intent",
    description="Classifies an incoming customer message into one of 12 AppleSupport intents with confidence score.",
    tags=["Classification"],
)
def classify_intent(payload: ClassifyRequest) -> ClassificationResponse:
    """Classify intent and return ranked predictions with confidence."""
    classifier = get_classifier()
    if not classifier or not classifier.is_trained:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Intent classifier is unavailable. Please run scripts/train_classifier.py first.",
        )

    return classifier.classify(payload.message)


# ==============================================================================
# Decision Engine / Agent Endpoints (Phase 6)
# ==============================================================================

@app.post(
    "/api/v1/agent",
    response_model=AgentResponse,
    summary="Conversation-aware support decision engine",
    description=(
        "Evaluates conversation context, intent classification, semantic retrieval, "
        "ambiguity, and troubleshooting history to select an action: auto_handle, clarify, or escalate."
    ),
    tags=["Agent"],
)
def run_support_agent(payload: AgentRequest) -> AgentResponse:
    """Evaluate multi-turn conversation and produce an explainable action decision."""
    agent = get_support_agent()
    return agent.process(payload)


@app.get("/", tags=["System"])
def root_info():
    """Service metadata root endpoint."""
    return {
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "docs_url": "/docs",
        "health_check": "/health",
        "phase": "Phase 7 - Grounded LLM Response Generation with OpenRouter",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
