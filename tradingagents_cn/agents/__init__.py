"""Downstream A-share agents.

Node factories follow upstream's contract (``create_x(llm) -> node(state)``) so
they can be wired into a graph that reuses upstream's nodes. Prompt text lives
beside the code as data, not as string literals inside a closure.
"""
