# Threat Model

## Security Assumptions

This is a **play-money** poker engine. For real-money, additional security measures would be required.

## Threat Categories

### 1. Command Injection / Validation

**Threat**: Malicious client sends invalid commands.

**Mitigation**:
- All commands validated server-side
- Reducer validates command legality
- Invalid commands rejected with error messages
- Commands are idempotent (duplicates ignored)

**Status**: ✅ Implemented

### 2. Cheating / Client Manipulation

**Threat**: Client tries to cheat by manipulating state or commands.

**Mitigation**:
- **Server Authoritative**: All game logic on server
- **State Never Sent**: Clients never receive full state
- **Hole Cards Server-Only**: Player cards never exposed to other clients
- **Command Validation**: All actions validated against current state
- **Optimistic Concurrency**: Version checks prevent race conditions

**Status**: ✅ Implemented

### 3. Replay Attacks

**Threat**: Attacker replays old commands.

**Mitigation**:
- **Idempotency Keys**: Duplicate commands ignored
- **Version Tracking**: Commands include expected_version
- **Optimistic Concurrency**: Version mismatches rejected

**Status**: ✅ Implemented

### 4. Race Conditions

**Threat**: Concurrent commands cause inconsistent state.

**Mitigation**:
- **Optimistic Concurrency**: Version-based conflict detection
- **Event Store**: Append-only with version checking
- **Idempotent Commands**: Duplicate commands safe

**Status**: ✅ Implemented

### 5. Information Disclosure

**Threat**: Players see other players' hole cards.

**Mitigation**:
- **Hole Cards Excluded**: `hole_cards` field excluded from serialization
- **Public State Only**: Only public state sent to clients
- **Server-Only Fields**: Sensitive data never leaves server

**Status**: ✅ Implemented

### 6. Denial of Service

**Threat**: Attacker floods server with commands.

**Mitigation**:
- **Rate Limiting**: (Not implemented - would be needed for production)
- **Command Validation**: Invalid commands rejected early
- **Idempotency**: Duplicate commands don't cause extra work

**Status**: ⚠️ Partial (rate limiting not implemented)

### 7. Database Attacks

**Threat**: SQL injection, unauthorized access.

**Mitigation**:
- **SQLAlchemy ORM**: Parameterized queries
- **Connection Pooling**: (Would be configured in production)
- **Access Control**: (Would be configured in production)

**Status**: ✅ Basic (ORM prevents SQL injection)

## Authentication & Authorization

### Current Implementation (Stub)

- **Auth**: Minimal stub (`server/services/auth.py`)
- **Player ID**: Extracted from token (stub)
- **Authorization**: All actions allowed (play-money)

### Production Requirements

For real-money, would need:

1. **Strong Authentication**: JWT tokens, session management
2. **Authorization**: Verify player owns seat before acting
3. **Rate Limiting**: Prevent command flooding
4. **Audit Logging**: Log all commands and events
5. **Encryption**: TLS for all communications

## Attack Vectors

### Command Replay
- **Risk**: Low (idempotency prevents duplicate effects)
- **Mitigation**: ✅ Idempotency keys

### State Manipulation
- **Risk**: None (state never sent to client)
- **Mitigation**: ✅ Server authoritative

### Hole Card Disclosure
- **Risk**: None (cards server-only)
- **Mitigation**: ✅ Field exclusion

### Race Conditions
- **Risk**: Low (optimistic concurrency)
- **Mitigation**: ✅ Version tracking

### Invalid Commands
- **Risk**: Low (server validation)
- **Mitigation**: ✅ Reducer validation

## Security Checklist

- ✅ Server authoritative
- ✅ Command validation
- ✅ Idempotent commands
- ✅ Optimistic concurrency
- ✅ Hole cards protected
- ✅ SQL injection prevention (ORM)
- ⚠️ Rate limiting (not implemented)
- ⚠️ Strong authentication (stub only)
- ⚠️ Audit logging (events logged, but not security audit)

## Recommendations for Production

1. **Implement rate limiting** per player/IP
2. **Strong authentication** (JWT, OAuth, etc.)
3. **Authorization checks** (verify player owns seat)
4. **Audit logging** (security events, not just game events)
5. **TLS/HTTPS** for all communications
6. **Input sanitization** (additional layer beyond Pydantic)
7. **Monitoring & alerting** for suspicious activity
