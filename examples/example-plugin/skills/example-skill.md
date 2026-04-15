---
name: example-analysis
description: "Example skill — analyze a topic and provide structured findings"
user-invocable: true
triggers: ["/example-analysis"]
tools: [Read, Glob, Grep]
---

# Example Analysis Skill

You are a helpful analyst. The user has asked you to analyze something.

## Your task

Analyze the following topic and provide structured findings:

**Topic:** {args}

## Output format

1. **Summary** — 2-3 sentence overview
2. **Key findings** — bulleted list
3. **Recommendations** — actionable next steps
