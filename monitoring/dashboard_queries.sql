-- ============================================================
-- I-Way Digital Twin — pgAdmin Dashboard Queries
-- ============================================================
-- You can copy-paste these queries into pgAdmin's Query Tool
-- to build custom monitoring dashboards or run quick checks.

-- 1. AI Message Pipeline & Accuracy
-- Shows how many messages have been answered and the average AI confidence.
SELECT 
    role,
    COUNT(*) as total_messages,
    ROUND(AVG(confidence)::numeric, 2) as average_confidence,
    model_used
FROM message
WHERE role = 'assistant'
GROUP BY role, model_used
ORDER BY total_messages DESC;

-- 2. Escalation & Handoff Analytics
-- Shows active sessions that have been escalated to human agents.
SELECT 
    id AS session_id,
    status,
    reason AS escalation_reason,
    created_at
FROM session
WHERE status IN ('handoff_pending', 'agent_connected')
ORDER BY created_at DESC;

-- 3. Vector Knowledge Base Growth
-- Monitor how many documents have been embedded into PostgreSQL pgvector by source type.
SELECT 
    source_type,
    COUNT(*) as embedded_chunks,
    MAX(last_synced_at) as last_sync_time
FROM knowledge_embedding
GROUP BY source_type;

-- 4. Audit Log Outcomes (Pipeline Success/Failure rates)
-- Checks if LangGraph agents are timing out, degrading, or successfully fulfilling requests.
SELECT 
    event_type,
    outcome,
    COUNT(*) as total_events,
    ROUND(AVG(latency_ms)::numeric, 0) as avg_latency_ms
FROM audit_log
GROUP BY event_type, outcome
ORDER BY total_events DESC;

-- 5. Human-in-the-Loop AI Corrections
-- View facts corrected by agents to see where the AI struggles.
SELECT 
    correction_type,
    COUNT(*) as num_corrections,
    MAX(created_at) as latest_correction
FROM ai_correction
GROUP BY correction_type;
