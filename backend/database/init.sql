-- ============================================================
-- I-Way Digital Twin — PostgreSQL Schema + Seed Data
-- ============================================================

-- Enable pgvector extension for embedding storage
CREATE EXTENSION IF NOT EXISTS vector;

-- ============================================================
-- ENUM TYPES
-- ============================================================

CREATE TYPE user_role AS ENUM ('Adherent', 'Prestataire', 'Agent', 'Admin');
CREATE TYPE session_status AS ENUM ('active', 'handoff_pending', 'agent_connected', 'resolved', 'expired');
CREATE TYPE message_role AS ENUM ('user', 'assistant', 'agent', 'system');
CREATE TYPE escalation_priority AS ENUM ('low', 'medium', 'high', 'critical');
CREATE TYPE source_type AS ENUM ('iway_api', 'hitl_validated');
CREATE TYPE correction_type AS ENUM ('factual_error', 'outdated', 'hallucination', 'incomplete');

-- ============================================================
-- TABLE: users
-- ============================================================

CREATE TABLE users (
    matricule       VARCHAR(20) PRIMARY KEY,
    nom             VARCHAR(100) NOT NULL,
    prenom          VARCHAR(100) NOT NULL,
    role            user_role NOT NULL DEFAULT 'Adherent',
    email           VARCHAR(255),
    specialite      VARCHAR(100),
    password_hash   VARCHAR(255) NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- TABLE: sessions
-- ============================================================

CREATE TABLE sessions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_matricule  VARCHAR(20) NOT NULL REFERENCES users(matricule),
    agent_matricule VARCHAR(20) REFERENCES users(matricule),
    status          session_status NOT NULL DEFAULT 'active',
    reason          TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    resolved_at     TIMESTAMPTZ
);

CREATE INDEX ix_sessions_status ON sessions(status);
CREATE INDEX ix_sessions_user ON sessions(user_matricule);
CREATE INDEX ix_sessions_created ON sessions(created_at DESC);

-- ============================================================
-- TABLE: messages
-- ============================================================

CREATE TABLE messages (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id      UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    role            message_role NOT NULL,
    content         TEXT NOT NULL,
    confidence      FLOAT,
    model_used      VARCHAR(50),
    timestamp       TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX ix_messages_session ON messages(session_id);
CREATE INDEX ix_messages_timestamp ON messages(timestamp);

-- ============================================================
-- TABLE: escalation_tickets
-- ============================================================

CREATE TABLE escalation_tickets (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id      UUID NOT NULL UNIQUE REFERENCES sessions(id),
    priority        escalation_priority NOT NULL DEFAULT 'medium',
    reason          TEXT,
    status          VARCHAR(30) NOT NULL DEFAULT 'open',
    assigned_agent  VARCHAR(20) REFERENCES users(matricule),
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    resolved_at     TIMESTAMPTZ
);

CREATE INDEX ix_escalation_status ON escalation_tickets(status);

-- ============================================================
-- TABLE: knowledge_embeddings
-- ============================================================

CREATE TABLE knowledge_embeddings (
    id              SERIAL PRIMARY KEY,
    source_id       VARCHAR(100) NOT NULL,
    source_type     source_type NOT NULL DEFAULT 'iway_api',
    chunk_text      TEXT NOT NULL,
    embedding       vector(384),
    metadata        JSONB,
    last_synced_at  TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(source_id, source_type)
);

CREATE INDEX ix_knowledge_source ON knowledge_embeddings(source_id, source_type);

-- ============================================================
-- TABLE: ai_corrections
-- ============================================================

CREATE TABLE ai_corrections (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id      UUID NOT NULL REFERENCES sessions(id),
    wrong_message_id UUID REFERENCES messages(id),
    correct_answer  TEXT NOT NULL,
    agent_matricule VARCHAR(20) NOT NULL REFERENCES users(matricule),
    correction_type correction_type NOT NULL DEFAULT 'factual_error',
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- TABLE: audit_log
-- ============================================================

CREATE TABLE audit_log (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    trace_id        VARCHAR(100) NOT NULL,
    session_id      UUID REFERENCES sessions(id),
    event_type      VARCHAR(50) NOT NULL,
    outcome         VARCHAR(30),
    latency_ms      INTEGER,
    model_used      VARCHAR(50),
    confidence      FLOAT,
    events          JSONB,
    timestamp       TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX ix_audit_session ON audit_log(session_id);
CREATE INDEX ix_audit_timestamp ON audit_log(timestamp DESC);
CREATE INDEX ix_audit_trace ON audit_log(trace_id);

-- ============================================================
-- SEED DATA: 4 Personas
-- ============================================================

INSERT INTO users (matricule, nom, prenom, role, email, specialite, password_hash) VALUES
    ('12345', 'Mansour',  'Nadia',  'Adherent',     'nadia.mansour@email.com', NULL,           'pass'),
    ('99999', 'Zaid',     'Amine',  'Prestataire',  'amine.zaid@clinique.tn',  'Cardiologie',  'med'),
    ('88888', 'Belhadj',  'Karim',  'Agent',        'karim.belhadj@iway.tn',   NULL,           'agent'),
    ('77777', 'Toumi',    'Sara',   'Admin',        'sara.toumi@iway.tn',      NULL,           'admin');

-- ============================================================
-- SEED DATA: System logs (initial dashboard data)
-- ============================================================

INSERT INTO audit_log (trace_id, event_type, outcome, latency_ms, model_used, confidence, events, timestamp) VALUES
    ('L001', 'user_query', 'RAG_RESOLVED',     820,  'gemini-2.5-flash', 0.94, '{"query": "Comment ajouter un beneficiaire ?"}',        '2026-04-13 19:07:12+00'),
    ('L002', 'user_query', 'RAG_RESOLVED',     750,  'gemini-2.5-flash', 0.88, '{"query": "Quel est le delai de remboursement ?"}',      '2026-04-13 19:06:55+00'),
    ('L003', 'user_query', 'AI_FALLBACK',      1140, 'gemini-2.5-flash', 0.71, '{"query": "Comment facturer un acte hors nomenclature ?"}', '2026-04-13 19:05:30+00'),
    ('L004', 'user_query', 'HUMAN_ESCALATED',  2310, 'gemini-2.5-flash', 0.38, '{"query": "Je veux parler a un humain"}',                '2026-04-13 19:04:01+00'),
    ('L005', 'user_query', 'RAG_RESOLVED',     610,  'gemini-2.5-flash', 0.96, '{"query": "Prise en charge hospitaliere urgence"}',      '2026-04-13 19:03:44+00'),
    ('L006', 'user_query', 'ERROR',            3100, 'gemini-2.5-flash', 0.15, '{"query": "Erreur de connexion au portail prestataire"}','2026-04-13 19:02:18+00'),
    ('L007', 'user_query', 'RAG_RESOLVED',     690,  'gemini-2.5-flash', 0.92, '{"query": "Quel est le plafond pour les soins dentaires ?"}', '2026-04-13 19:01:05+00'),
    ('L008', 'user_query', 'RAG_RESOLVED',     870,  'gemini-2.5-flash', 0.91, '{"query": "Quelle est la prime de naissance ?"}',        '2026-04-13 19:00:22+00'),
    ('L009', 'user_query', 'AGENT_RESOLVED',   1250, 'gemini-2.5-flash', 0.90, '{"query": "Quels sont mes dossiers en cours ?", "tools_called": ["get_personal_dossiers"]}', '2026-04-14 10:15:30+00'),
    ('L010', 'user_query', 'RAG_RESOLVED',     580,  'gemini-2.5-flash', 0.95, '{"query": "Les vaccins sont-ils couverts ?"}',           '2026-04-14 10:20:45+00'),
    ('L011', 'user_query', 'RAG_RESOLVED',     720,  'gemini-2.5-flash', 0.89, '{"query": "Comment obtenir ma carte adherent ?"}',       '2026-04-14 11:05:12+00'),
    ('L012', 'user_query', 'AGENT_RESOLVED',   2100, 'gemini-2.5-flash', 0.92, '{"query": "Combien de seances de kine sont couvertes ?", "tools_called": ["search_knowledge_base"]}', '2026-04-14 11:30:00+00'),
    ('L013', 'user_query', 'HUMAN_ESCALATED',  1800, 'gemini-2.5-flash', 0.25, '{"query": "Mon remboursement est incorrect je veux un humain"}', '2026-04-14 14:22:33+00'),
    ('L014', 'user_query', 'RAG_RESOLVED',     650,  'gemini-2.5-flash', 0.93, '{"query": "Les IRM sont-elles couvertes ?"}',            '2026-04-14 15:10:18+00'),
    ('L015', 'user_query', 'RAG_RESOLVED',     780,  'gemini-2.5-flash', 0.87, '{"query": "La FIV est-elle prise en charge ?"}',         '2026-04-14 16:45:55+00'),
    ('L016', 'user_query', 'DEGRADED',         5000, 'gemini-2.5-flash', 0.00, '{"query": "Quelles formules proposez-vous ?", "failure_type": "timeout"}', '2026-04-14 17:00:01+00');
