# OpenProject MCP Server: Conventions & Scope

This document defines the architectural standards, supported scope, and interface contracts for the OpenProject Model Context Protocol (MCP) server.

## 1. Supported Scope

The server focuses on "Day-to-Day Developer Operations." It is not intended to be a full administrative client.

### Core Modules (Priority 1)
| Module | Capabilities | Notes |
| :--- | :--- | :--- |
| **Projects** | List, Filter, Read | Read-only access to project context. |
| **Work Packages** | List, Search, Create, Read, Update | Focus on status, assignee, priority, and subject. |
| **Metadata** | List Types, Statuses, Priorities | Essential for ID lookups to validate inputs. |

### Extended Modules (Priority 2)
| Module | Capabilities | Notes |
| :--- | :--- | :--- |
| **Time Entries** | Log Time | Simple "2h 30m" format support. |
| **Wiki** | Search, Read | Read-only retrieval of documentation. |

### Out of Scope
* User management (Creating/Deleting users).
* System administration (Settings, plugins).
* Complex Gantt chart manipulation.

---

## 2. Naming Conventions

### Tool Naming
Tools exposed to the LLM must follow `snake_case` with a standard `verb_noun` structure to ensure clarity for the model.

* **Pattern:** `{action}_{entity}`
* **Examples:**
    * `list_projects` (not `get_projects` for lists)
    * `get_work_package` (for retrieving a single item by ID)
    * `create_work_package`
    * `update_work_package_status` (Specific updates are preferred over generic `update_` to reduce schema complexity)

### Code Structure
* **Module Naming:** `src/openproject_mcp/tools/{entity}.py` (e.g., `work_packages.py`).
* **Class Naming:** Pydantic models use `PascalCase` (e.g., `WorkPackage`, `ProjectSummary`).

---

## 3. Data Formatting (Input/Output)

### Input (Tool Arguments)
* **IDs:** Always expect `integer` for IDs (Project ID, Work Package ID).
* **Dates:** ISO 8601 (`YYYY-MM-DD`).
* **Duration:** ISO 8601 duration (`PT2H`) or simple string (`2h`) if handled by a helper.

### Output Format Decision

**For Collections (list_projects, list_work_packages):**
Return **array of summary objects** + metadata:
```json
{
  "items": [...],
  "total": 37,
  "showing": 20,
  "hasMore": true
}
```

**For Single Items (get_work_package):**
Return **summary object** directly.

#### A. Summary View (Default)
**Work Package Summary:**
```json
{
  "id": 12345,
  "subject": "Implement user authentication feature",
  "status": "In Progress",           // From _links.status.title
  "priority": "High",                 // From _links.priority.title
  "assignee": "John Doe" | null,      // From _links.assignee.title
  "project": "Project Alpha",
  "version": "Sprint 3",              // From _links.version.title
  "storyPoints": 5,
  "dueDate": "2025-08-12",
  "link": "https://{base}/work_packages/12345"
}
```

**Project Summary:**
```json
{
  "id": 1001,
  "name": "Project Alpha",
  "identifier": "project-alpha",
  "active": true,
  "parent": "Program Beta" | null,
  "link": "https://{base}/projects/1001"
}
```

#### B. Error Responses
Errors must be descriptive to allow the LLM to self-correct.
* **Format:** `Error: [Category] - Human readable description.`

---

## 4. Error Taxonomy & Mapping

We map OpenProject HTTP status codes to specific user-facing messages.

| HTTP Status | Category | Internal Handling | Message to LLM |
| :--- | :--- | :--- | :--- |
| **400** | Bad Request | Validation Error | "Invalid input: {details}. Please check parameters." |
| **401** | Auth | Auth Middleware | "Authentication failed. Please check your API key." |
| **403** | Permission | Permission Error | "You do not have permission to access this resource." |
| **404** | Not Found | Resource Error | "Resource {id} not found. It may not exist or is restricted." |
| **422** | Unprocessable | Semantic Error | "Update failed: {openproject_error_message}. Check logic." |
| **5xx** | Server Error | Retry/Log | "OpenProject is currently unavailable. Please try again later." |

---

## 5. HAL & API Interaction Standards

### Embedded Resources
OpenProject embeds related entities to reduce API calls:
* `_embedded.elements[]` - Main collection items
* `_embedded.schemas` - Schema definitions (work packages)
* Within items: `_links.{relation}.title` often contains display names

**Convention:** 
* Extract IDs from `_links.{relation}.href` (e.g., `/api/v3/projects/1001` → `1001`)
* Use `_links.{relation}.title` for display names when available
* Handle `"href": null` gracefully (missing relations)

### Undisclosed Resources
Some parent projects may show:
```json
"href": "urn:openproject-org:api:v3:undisclosed"
```
This indicates **permission restrictions**. Display as "Restricted" to user.


## 6. Pagination & Collection Responses

All list endpoints return paginated `Collection` types with:
* `total`: Total available items
* `count`: Items in current page
* `pageSize`: Items per page
* `offset`: Current page offset

**Pagination Links:**
```json
"_links": {
  "nextByOffset": { "href": "..." },
  "jumpTo": { "href": "...", "templated": true }
}
```

**Default Strategy:** Fetch first page only for MVP. Add pagination support if needed based on user feedback.

## 7. Custom Fields

OpenProject instances may have custom fields (e.g., `customField16`).

**Convention:**
* Document known custom fields per deployment in a separate config
* For MVP: Ignore custom fields unless explicitly requested
* If surfacing to LLM, use generic names: `custom_field_16: 12345`