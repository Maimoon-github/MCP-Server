# Prompts Reference

> Auto-generated catalog of all built-in prompts available in the Universal MCP Server.

---

## Overview

Prompts are **reusable instruction templates** that the AI host can invoke with arguments. They standardize common workflows like code review, debugging, and project setup.

| Prompt | Purpose | Arguments |
|--------|---------|-----------|
| `code_review` | Security & quality code review | `language`, `code`, `focus` |
| `debug_analysis` | Stack trace & error analysis | `error_message`, `stack_trace`, `framework` |
| `project_setup` | Initialize a new project | `language`, `project_type`, `features` |
| `doc_generate` | Generate API documentation | `source_code`, `format`, `audience` |

---

## Prompt Model

Each prompt implements:

```python
class BasePrompt(ABC):
    name: str                     # Unique identifier
    description: str              # LLM-friendly description
    arguments: list[PromptArg]    # Expected arguments with types

    @abstractmethod
    def render(self, arguments: dict) -> str:
        """Return the rendered prompt string."""
        ...
```

---

## Built-in Prompts

### `code_review`

Perform a comprehensive code review focusing on security, performance, and maintainability.

**Arguments:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `language` | string | Yes | Programming language (python, javascript, rust, etc.) |
| `code` | string | Yes | Code to review |
| `focus` | string | No | Review focus: `security`, `performance`, `readability`, `all` (default: `all`) |
| `context` | string | No | Additional context (e.g., "This is a payment processing module") |

**Rendered Template:**

```
You are a senior software engineer performing a code review.

Language: {{language}}
Focus areas: {{focus}}

{% if context %}
Context: {{context}}
{% endif %}

Please review the following code and provide:
1. Security issues (injection, XSS, auth flaws, secrets exposure)
2. Performance concerns (inefficient algorithms, memory leaks, N+1 queries)
3. Maintainability (naming, complexity, test coverage, documentation)
4. Suggested improvements with refactored code examples

Code to review:
```{{language}}
{{code}}
```

Format your response as:
- 🔴 Critical issues
- 🟡 Warnings
- 🟢 Suggestions
- ✅ Positive findings
```

---

### `debug_analysis`

Analyze an error message and stack trace to identify root cause and suggest fixes.

**Arguments:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `error_message` | string | Yes | The error message or exception text |
| `stack_trace` | string | Yes | Full stack trace |
| `framework` | string | No | Framework/library (django, react, fastapi, etc.) |
| `recent_changes` | string | No | Recent code changes that might be related |

**Rendered Template:**

```
You are a debugging expert analyzing a runtime error.

{% if framework %}
Framework: {{framework}}
{% endif %}

Error Message:
```
{{error_message}}
```

Stack Trace:
```
{{stack_trace}}
```

{% if recent_changes %}
Recent Changes:
{{recent_changes}}
{% endif %}

Please analyze and provide:
1. Root cause identification
2. Likely file/line causing the issue
3. Step-by-step debugging strategy
4. Fix with corrected code
5. Prevention measures (tests, type hints, linting)
```

---

### `project_setup`

Generate a complete project initialization guide and scaffold.

**Arguments:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `language` | string | Yes | Primary language (python, typescript, go, rust) |
| `project_type` | string | Yes | Type: `web_api`, `cli`, `library`, `ml`, `microservice` |
| `features` | array | No | Features to include: `tests`, `linting`, `docker`, `ci_cd`, `docs` |
| `name` | string | Yes | Project name (snake_case or kebab-case) |

**Rendered Template:**

```
Generate a complete project setup for a {{language}} {{project_type}} named "{{name}}".

Required features: {{features | join(", ")}}

Please provide:
1. Directory structure (tree format)
2. Configuration files (pyproject.toml, package.json, Cargo.toml, etc.)
3. Dependency list with versions
4. Development environment setup (venv, nvm, etc.)
5. Testing setup (pytest, jest, cargo test, etc.)
6. Linting & formatting config (ruff, black, eslint, prettier, clippy)
7. CI/CD pipeline (GitHub Actions, GitLab CI)
8. Docker setup (Dockerfile, docker-compose.yml)
9. README.md template
10. .gitignore for {{language}}

Make all configs production-ready with security best practices.
```

---

### `doc_generate`

Generate API documentation from source code.

**Arguments:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `source_code` | string | Yes | Source code to document |
| `format` | string | No | Output format: `markdown`, `html`, `openapi`, `sphinx` (default: `markdown`) |
| `audience` | string | No | Target audience: `developers`, `end_users`, `ops` (default: `developers`) |
| `include_examples` | boolean | No | Include usage examples (default: `true`) |

**Rendered Template:**

```
Generate {{format}} documentation for the following code.

Target audience: {{audience}}
{% if include_examples %}Include practical usage examples.{% endif %}

Source Code:
```
{{source_code}}
```

Please include:
1. Overview / description
2. Function/class signatures with type annotations
3. Parameter descriptions
4. Return value descriptions
5. Exception/error handling
6. Usage examples
7. Related functions/classes
{% if format == "openapi" %}
8. OpenAPI 3.0 spec with paths, schemas, and examples
{% endif %}
```

---

## Prompt Registration API

```python
from universal_mcp.primitives.prompts.base import BasePrompt
from universal_mcp.primitives.prompts.registry import prompt_registry

class MyPrompt(BasePrompt):
    name = "my_prompt"
    description = "A reusable template"
    arguments = [
        {"name": "input", "description": "Input text", "required": True}
    ]

    def render(self, arguments: dict) -> str:
        return f"Process this: {arguments['input']}"

prompt_registry.register(MyPrompt())
```

---

## Prompt Discovery

The server exposes a `prompts/list` endpoint:

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "prompts/list",
  "result": {
    "prompts": [
      {
        "name": "code_review",
        "description": "Comprehensive code review for security and quality",
        "arguments": [
          {"name": "language", "description": "Programming language", "required": true},
          {"name": "code", "description": "Code to review", "required": true}
        ]
      }
    ]
  }
}
```

---

*Auto-generated from source. Last updated: 2026-06-01*
