# Implementation Plan v0.3.0 - Features #59, #57, #56

**Branch**: `feat/v0.3.0-event-validation-logging-night-mode` | **PR**: TBD

## Overview

Implement three new features:
- **#59**: Event timestamp validation with configurable threshold
- **#57**: Event log viewer in web UI with detailed information
- **#56**: Night mode with configurable hours and reduced notifications

## Phase 1: Core Services (Foundation)

### Step 1.1: Event Validation Service (`event_validator.py`)
**Files to change**: 
- Create `nukiblinker/event_validator.py`
- Update `nukiblinker/config.py` (add EventValidationConfig)
- Update `nukiblinker/__main__.py` (initialize service)

**Changes**:
- Implement ValidationResult dataclass
- Implement EventValidator class with timestamp extraction logic
- Handle Nuki callback timestamp parsing (check if timestamp field exists)
- Add timezone-aware datetime handling
- Add validation logging

**Edge cases**:
- Missing timestamp in callback payload
- Invalid timestamp format
- Timezone differences between Nuki Bridge and server
- Clock drift on server

### Step 1.2: Event Log Service (`event_log.py`)
**Files to change**:
- Create `nukiblinker/event_log.py`
- Update `nukiblinker/config.py` (add EventLogConfig)
- Update `nukiblinker/__main__.py` (initialize service)

**Changes**:
- Implement EventLogEntry dataclass with all required fields
- Implement EventLog class with in-memory storage
- Add file persistence (JSON format) for crash recovery
- Implement cleanup logic for retention
- Add CSV export functionality
- Add real-time event broadcasting for web UI

**Edge cases**:
- Disk space issues for log persistence
- Large payload serialization
- Concurrent access to log data
- Memory usage with many entries

### Step 1.3: Night Mode Service (`night_mode.py`)
**Files to change**:
- Create `nukiblinker/night_mode.py`
- Update `nukiblinker/config.py` (add NightModeConfig)
- Update `nukiblinker/__main__.py` (initialize service)

**Changes**:
- Implement NightMode class with time range logic
- Handle overnight time ranges (e.g., 22:00 to 07:00)
- Implement grace period logic
- Add rule modification for night mode
- Add night mode activation/deactivation logging

**Edge cases**:
- Time zone handling
- Daylight saving time transitions
- Invalid time format in config
- Midnight boundary conditions

### Step 1.4: Update Configuration Models
**Files to change**: `nukiblinker/config.py`

**Changes**:
- Add EventValidationConfig Pydantic model
- Add NightModeConfig Pydantic model  
- Add EventLogConfig Pydantic model
- Update AppConfig to include new sections
- Update config.example.yaml with new sections
- Add validation for time formats and ranges

### Step 1.5: Tests for Core Services
**Files to change**: Create test files
- `tests/test_event_validator.py`
- `tests/test_event_log.py` 
- `tests/test_night_mode.py`

**Tests to add**:
- Event validation with various timestamp scenarios
- Event log CRUD operations and persistence
- Night mode time range calculations
- Configuration validation

## Phase 2: Integration with Event Pipeline

### Step 2.1: Update Server Callback Handler
**Files to change**: `nukiblinker/server.py`

**Changes**:
- Import new services
- Add event validation before processing
- Add event logging for all events
- Add night mode rule application
- Update callback endpoint to handle validation failures

### Step 2.2: Update Event Router
**Files to change**: `nukiblinker/event_router.py`

**Changes**:
- Modify dispatch() to accept night mode rules
- Add validation result handling
- Add action tracking for event logging
- Return detailed processing results

### Step 2.3: Update Notifier
**Files to change**: `nukiblinker/notifier.py`

**Changes**:
- Return detailed action results instead of just exceptions
- Track which channels were triggered
- Pass action results back to event log

### Step 2.4: Integration Tests
**Files to change**: `tests/test_server.py`, `tests/test_event_router.py`, `tests/test_notifier.py`

**Tests to add**:
- End-to-end callback processing with validation
- Event logging integration
- Night mode rule application
- Error handling scenarios

## Phase 3: Web UI Implementation

### Step 3.1: Add New API Endpoints
**Files to change**: `nukiblinker/web_ui.py`

**Changes**:
- GET `/api/events/log` - Get recent events with pagination
- GET `/api/events/export` - Download CSV export
- POST `/api/events/clear` - Clear event log
- PUT `/api/config/event-validation` - Update validation config
- PUT `/api/config/night-mode` - Update night mode config
- PUT `/api/config/event-log` - Update event log config

### Step 3.2: Update Web UI Frontend
**Files to change**: `nukiblinker/static/index.html`

**Changes**:
- Add new "Event Log" tab with table view
- Add real-time event updates (WebSocket or polling)
- Add export and clear buttons
- Add "Event Validation" section in Settings tab
- Add "Night Mode" section in Settings tab
- Add time pickers for night mode configuration
- Add validation threshold input

### Step 3.3: Web UI Tests
**Files to change**: `tests/test_web_ui.py`

**Tests to add**:
- New API endpoints
- Event log retrieval and pagination
- CSV export functionality
- Configuration updates for new features

## Phase 4: Documentation and Finalization

### Step 4.1: Update Documentation
**Files to change**:
- `README.md` - Add new features description
- `CHANGELOG.md` - Add v0.3.0 entries
- `config.example.yaml` - Add new configuration sections

### Step 4.2: Final Testing
**Actions**:
- Run full test suite: `make test`
- Run linting: `make lint`
- Manual testing with real devices (if available)
- Performance testing with event log size

### Step 4.3: Deployment Preparation
**Actions**:
- Update Dockerfile if needed
- Test Docker build
- Verify configuration migration from v0.2.x

## Acceptance Criteria

### Issue #59 - Event Validation
- [ ] Events older than configurable threshold are rejected
- [ ] Rejected events are logged with warning
- [ ] Configuration is accessible via web UI
- [ ] Validation can be enabled/disabled per event type
- [ ] Tests cover edge cases (missing timestamp, timezone issues)

### Issue #57 - Event Log Viewer  
- [ ] Event log captures all events with full context
- [ ] Web UI displays chronological event list
- [ ] Real-time updates work for new events
- [ ] CSV export downloads correctly
- [ ] Log retention and cleanup work as expected
- [ ] Performance acceptable with 1000+ entries

### Issue #56 - Night Mode
- [ ] Night mode activates during configured hours
- [ ] Audio notifications are disabled during night mode
- [ ] Light brightness is reduced during night mode
- [ ] HomeKit notifications remain enabled
- [ ] Grace period handles edge times correctly
- [ ] Configuration changes apply immediately

## Risk Mitigation

1. **Performance**: Event log could grow large - implement size limits and cleanup
2. **Storage**: Log persistence could use disk space - monitor and rotate files
3. **Complexity**: Multiple new services increase complexity - thorough testing needed
4. **Backwards Compatibility**: Ensure existing configurations continue to work

## Dependencies

No new external dependencies required. All features use existing Python standard library and current project dependencies.
