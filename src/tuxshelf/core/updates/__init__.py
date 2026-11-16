"""Update machinery (Phase 2): GitHub releases, version comparison, safe installation.

Everything here is Qt-free. Functions that talk to the network or the filesystem are pure
(no database access) so the UI can run them on worker threads; ``service.UpdateService``
applies their results to the database on the main thread.
"""
