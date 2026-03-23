*** Begin Patch
*** Add File: /app/backend/storage.py
+import os
+import requests
+import logging
+
+STORAGE_URL = "https://integrations.emergentagent.com/objstore/api/v1/storage"
+EMERGENT_KEY = os.environ["EMERGENT_LLM_KEY"]
+APP_NAME = "global-connect-5812"
+
+logger = logging.getLogger(__name__)
+storage_key = None
+
+
+def init_storage():
+    global storage_key
+    if storage_key:
+        return storage_key
+    resp = requests.post(f"{STORAGE_URL}/init", json={"emergent_key": EMERGENT_KEY}, timeout=30)
+    resp.raise_for_status()
+    storage_key = resp.json()["storage_key"]
+    return storage_key
+
+
+def put_object(path: str, data: bytes, content_type: str) -> dict:
+    key = init_storage()
+    resp = requests.put(
+        f"{STORAGE_URL}/objects/{path}",
+        headers={"X-Storage-Key": key, "Content-Type": content_type},
+        data=data,
+        timeout=120,
+    )
+    resp.raise_for_status()
+    return resp.json()
+
+
+def get_object(path: str) -> tuple[bytes, str]:
+    key = init_storage()
+    resp = requests.get(
+        f"{STORAGE_URL}/objects/{path}",
+        headers={"X-Storage-Key": key},
+        timeout=60,
+    )
+    resp.raise_for_status()
+    return resp.content, resp.headers.get("Content-Type", "application/octet-stream")
*** End Patch