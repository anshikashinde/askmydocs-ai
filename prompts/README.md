# Prompt Templates

Versioned LLM prompt templates for AskMyDocs AI.

## Rules

- All prompts are Jinja2 templates.
- No prompt is ever hardcoded in Python source.
- Naming: `{function}/{name}_v{major}.{minor}.jinja2`
- Major version bump = breaking change to output format or required variables.
- Minor version bump = refinement, rewording, or additional instructions.

## Directory Structure

```
prompts/
├── answer/        # Answer generation prompts
├── citation/      # Citation validation prompts
├── system/        # System-level instructions
└── evaluation/    # LLM-as-judge prompts for evaluation
```

## Template Variables

Each template documents its required variables in a header comment:

```jinja2
{# 
  Template: generate_answer_v1.0
  Variables:
    - query: str (user's question)
    - context: list[dict] (retrieved chunks with metadata)
    - company: str (target company, optional)
  Output: Answer text with inline [N] citations
#}
```

## Versioning Strategy

| When | Action |
|------|--------|
| Rewording for clarity | Minor bump (v1.0 → v1.1) |
| Adding instructions (e.g., "never speculate") | Minor bump |
| Changing output format (e.g., JSON → markdown) | Major bump (v1.x → v2.0) |
| Adding new required variable | Major bump |
| Removing a variable | Major bump |

## Testing

Prompts are tested by rendering them with sample inputs and verifying:
- No Jinja2 syntax errors
- All variables are used
- Output format matches expectations

This happens in unit tests (see `tests/unit/`).
