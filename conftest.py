"""Test-session setup.

Points AVATAR_SHIELD_DB at a throwaway path before `bot` (and therefore
`settings_store`) is ever imported, so `pytest` never creates or touches a
real ./avatar-shield.db in the repo working directory.
"""
import os
import tempfile

os.environ.setdefault("AVATAR_SHIELD_DB", os.path.join(tempfile.mkdtemp(prefix="avatar-shield-test-"), "test.db"))
