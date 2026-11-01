"""Web shell for the downstream research kernel.

A thin FastAPI layer: validate, queue, stream progress from SQLite, serve the
artifacts the kernel already writes. No analysis logic lives here.
"""
