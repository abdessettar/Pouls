"""The coach: summaries of the warehouse, a local journal and an MCP server for Claude.

See docs/decisions/0007-coach.md. Nothing here sends data anywhere: the MCP client (Claude Code or Claude
Desktop) receives tool results, after redact.safe() has removed anything that must not leave.
"""
