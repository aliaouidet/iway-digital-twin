"""
Resilience Service — Circuit breaker, timeout handling, and graceful degradation.

Patterns implemented:
1. Circuit Breaker — Prevents cascading failures to external services
2. Timeout Guard — asyncio.wait_for with auto-escalation on timeout
3. Retry with Backoff — Exponential backoff for transient failures
4. Graceful Degradation — Fallback responses when services are down
"""

import time
import asyncio
import logging
from enum import Enum
from typing import Optional, Callable, Any
from dataclasses import dataclass, field
from datetime import datetime, timezone

logger = logging.getLogger("I-Way-Twin")


# ==============================================================
# CIRCUIT BREAKER
# ==============================================================

class CircuitState(Enum):
    CLOSED = "closed"       # Normal operation
    OPEN = "open"           # Failures exceeded threshold — blocking calls
    HALF_OPEN = "half_open" # Testing if service recovered


@dataclass
class CircuitBreaker:
    """
    Circuit breaker for external service calls (LLM, embedding model, APIs).
    
    States:
      CLOSED   → Normal. Track failures. If failures >= threshold → OPEN
      OPEN     → All calls rejected immediately. After cooldown → HALF_OPEN
      HALF_OPEN → Allow 1 test call. Success → CLOSED. Failure → OPEN
    """
    name: str
    failure_threshold: int = 5
    cooldown_seconds: float = 30.0
    
    # Internal state
    state: CircuitState = field(default=CircuitState.CLOSED)
    failure_count: int = field(default=0)
    success_count: int = field(default=0)
    last_failure_time: Optional[float] = field(default=None)
    last_state_change: Optional[str] = field(default=None)
    total_calls: int = field(default=0)
    total_failures: int = field(default=0)
    total_circuit_opens: int = field(default=0)

    def _transition(self, new_state: CircuitState):
        old = self.state
        self.state = new_state
        self.last_state_change = datetime.now(timezone.utc).isoformat()
        if new_state == CircuitState.OPEN:
            self.total_circuit_opens += 1
        logger.warning(f"⚡ Circuit [{self.name}]: {old.value} → {new_state.value} "
                      f"(failures={self.failure_count}/{self.failure_threshold})")

    def can_execute(self) -> bool:
        """Check if a call is allowed through the circuit."""
        if self.state == CircuitState.CLOSED:
            return True
        
        if self.state == CircuitState.OPEN:
            # Check if cooldown has elapsed
            if self.last_failure_time and (time.time() - self.last_failure_time) >= self.cooldown_seconds:
                self._transition(CircuitState.HALF_OPEN)
                return True
            return False
        
        # HALF_OPEN — allow one test call
        return True

    def record_success(self):
        """Record a successful call."""
        self.total_calls += 1
        self.success_count += 1
        if self.state == CircuitState.HALF_OPEN:
            self._transition(CircuitState.CLOSED)
            self.failure_count = 0
        elif self.state == CircuitState.CLOSED:
            self.failure_count = max(0, self.failure_count - 1)  # Decay failures on success

    def record_failure(self):
        """Record a failed call."""
        self.total_calls += 1
        self.total_failures += 1
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        if self.state == CircuitState.HALF_OPEN:
            self._transition(CircuitState.OPEN)
        elif self.state == CircuitState.CLOSED and self.failure_count >= self.failure_threshold:
            self._transition(CircuitState.OPEN)

    def get_status(self) -> dict:
        """Get circuit breaker status for monitoring."""
        return {
            "name": self.name,
            "state": self.state.value,
            "failure_count": self.failure_count,
            "failure_threshold": self.failure_threshold,
            "total_calls": self.total_calls,
            "total_failures": self.total_failures,
            "total_circuit_opens": self.total_circuit_opens,
            "cooldown_seconds": self.cooldown_seconds,
            "last_state_change": self.last_state_change,
        }


# --- Global Circuit Breakers ---
llm_circuit = CircuitBreaker(name="LLM", failure_threshold=3, cooldown_seconds=30)
embedding_circuit = CircuitBreaker(name="Embedding", failure_threshold=5, cooldown_seconds=60)
api_circuit = CircuitBreaker(name="IWay-API", failure_threshold=5, cooldown_seconds=15)


# ==============================================================
# TIMEOUT GUARD
# ==============================================================

class TimeoutError(Exception):
    """Raised when an operation exceeds its timeout."""
    pass


async def with_timeout(coro, timeout_seconds: float, operation_name: str = "operation"):
    """
    Execute a coroutine with a timeout.
    
    Args:
        coro: The coroutine to execute
        timeout_seconds: Maximum execution time
        operation_name: Name for logging
    
    Returns:
        The coroutine result
    
    Raises:
        TimeoutError if the operation exceeds the timeout
    """
    try:
        result = await asyncio.wait_for(coro, timeout=timeout_seconds)
        return result
    except asyncio.TimeoutError:
        logger.error(f"⏰ TIMEOUT: {operation_name} exceeded {timeout_seconds}s limit")
        raise TimeoutError(f"{operation_name} timed out after {timeout_seconds}s")


# ==============================================================
# RETRY WITH BACKOFF
# ==============================================================

async def retry_with_backoff(
    func: Callable,
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    operation_name: str = "operation",
    circuit: Optional[CircuitBreaker] = None,
):
    """
    Retry an async function with exponential backoff.
    
    Args:
        func: Async callable to retry
        max_retries: Maximum number of attempts
        base_delay: Initial delay between retries
        max_delay: Maximum delay cap
        operation_name: Name for logging
        circuit: Optional circuit breaker to check/update
    
    Returns:
        The function result
    
    Raises:
        The last exception if all retries fail
    """
    last_exception = None
    
    for attempt in range(max_retries):
        # Check circuit breaker
        if circuit and not circuit.can_execute():
            logger.warning(f"🔌 Circuit [{circuit.name}] is OPEN — skipping {operation_name}")
            raise Exception(f"Circuit breaker [{circuit.name}] is open")
        
        try:
            result = await func()
            if circuit:
                circuit.record_success()
            return result
        except Exception as e:
            last_exception = e
            if circuit:
                circuit.record_failure()
            
            if attempt < max_retries - 1:
                delay = min(base_delay * (2 ** attempt), max_delay)
                logger.warning(
                    f"🔄 Retry {attempt + 1}/{max_retries} for {operation_name}: {e}. "
                    f"Waiting {delay:.1f}s..."
                )
                await asyncio.sleep(delay)
            else:
                logger.error(f"❌ All {max_retries} retries failed for {operation_name}: {e}")
    
    raise last_exception


# ==============================================================
# GRACEFUL DEGRADATION
# ==============================================================

FALLBACK_RESPONSES = {
    "default": (
        "Je suis temporairement indisponible. Votre demande a été enregistrée "
        "et un agent humain vous contactera dans les plus brefs délais. "
        "Vous pouvez aussi appeler le support I-Way au 71 800 800."
    ),
    "timeout": (
        "Le temps de réponse est trop long en ce moment. "
        "Je vous transfère vers un agent humain qui pourra vous aider immédiatement."
    ),
    "circuit_open": (
        "Le service d'intelligence artificielle est temporairement indisponible. "
        "Un agent humain va prendre en charge votre conversation."
    ),
    "embedding_failure": (
        "La recherche dans la base de connaissances est momentanément indisponible. "
        "Un agent humain va vous assister directement."
    ),
}


def get_fallback_response(failure_type: str = "default") -> dict:
    """Get a graceful degradation response for a given failure type."""
    text = FALLBACK_RESPONSES.get(failure_type, FALLBACK_RESPONSES["default"])
    return {
        "text": text,
        "confidence": 0,
        "degraded": True,
        "failure_type": failure_type,
    }


# ==============================================================
# SESSION RESILIENCE
# ==============================================================

def handle_agent_disconnect(session: dict, sessions_store: dict):
    """
    Handle agent WebSocket disconnection.
    
    If session was agent_connected, re-queue it to handoff_pending
    so another agent can pick it up.
    """
    session_id = session["id"]
    
    if session["status"] == "agent_connected":
        session["status"] = "handoff_pending"
        session["agent_ws"] = None
        session["reason"] = f"Agent disconnected — re-queued for pickup"
        session["history"].append({
            "role": "system",
            "content": "L'agent a été déconnecté. Votre conversation est remise en file d'attente.",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        logger.warning(f"🔄 Agent disconnected from session {session_id} — re-queued")
        return "re_queued"
    else:
        session["agent_ws"] = None
        return "cleared"


def handle_user_disconnect(session: dict):
    """
    Handle user WebSocket disconnection.
    
    Preserves session state for reconnection within TTL.
    """
    session["user_ws"] = None
    logger.info(f"👤 User disconnected from session {session['id']} — state preserved for reconnection")
    return "preserved"


# ==============================================================
# MONITORING — All Circuit Breakers Status
# ==============================================================

def get_resilience_status() -> dict:
    """Get the status of all resilience components for dashboard monitoring."""
    return {
        "circuit_breakers": {
            "llm": llm_circuit.get_status(),
            "embedding": embedding_circuit.get_status(),
            "iway_api": api_circuit.get_status(),
        },
        "fallback_responses_available": list(FALLBACK_RESPONSES.keys()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
