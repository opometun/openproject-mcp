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

### Output (Tool Responses)
To prevent overflowing the LLM context window, we distinguish between **Summary** and **Raw** views.

#### A. Summary View (Default)
Optimized for token efficiency. Returns only fields relevant to decision-making.
* **Format:** JSON or structured Text.
* **Example (Work Package):**
    ```json
    {
      "id": 123,
      "subject": "Fix login bug",
      "status": "In Progress",
      "priority": "High",
      "assignee": "Jane Doe",
      "link": "https://.../work_packages/123"
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

OpenProject uses **HAL+JSON** (Hypertext Application Language).

* **`_links`:** We must follow `_links` to discover valid actions or related resources (e.g., transitions).
* **`_embedded`:** Use embedded resources (e.g., `type`, `priority`) to avoid extra round-trip API calls when possible.
* **LockVersion:** When updating, we must handle optimistic locking (check `lockVersion`) or blindly overwrite if safe (decision: *blind overwrite for MVP, add locking logic if conflicts occur frequently*).

```python
# Example of expected HAL handling convention
def extract_link_id(payload, relation):
    """
    Extracts ID from payload['_links'][relation]['href']
    """
    pass