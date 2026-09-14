"""Small GitHub REST client. Never follows redirects or prints credentials/bodies."""

from __future__ import annotations

import base64
import hashlib
import json
import re
import urllib.error
import urllib.request
from email.utils import parsedate_to_datetime


class APIError(RuntimeError):
    def __init__(self, status):
        self.status = status
        super().__init__(f"GitHub API returned HTTP {status}; response body omitted")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class GitHub:
    def __init__(self, repository, token):
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
            raise ValueError("Invalid repository name")
        self.repository = repository
        self._token = token
        self.opener = urllib.request.build_opener(NoRedirect())
        self.server_time = None

    def request(self, method, path, value=None):
        if ((path and not path.startswith("/")) or "#" in path
                or any(part in {".", ".."} for part in path.split("?", 1)[0].split("/"))):
            raise ValueError("Invalid repository API path")
        payload = None if value is None else json.dumps(value).encode("utf-8")
        request = urllib.request.Request(
            "https://api.github.com/repos/" + self.repository + path,
            headers={"Authorization": "Bearer " + self._token,
                     "Accept": "application/vnd.github+json",
                     "User-Agent": "goo-ai-arena"},
            data=payload, method=method)
        try:
            with self.opener.open(request, timeout=30) as response:
                if response.headers.get("Date"):
                    self.server_time = parsedate_to_datetime(response.headers["Date"]).isoformat().replace("+00:00", "Z")
                raw = response.read()
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as error:
            raise APIError(error.code) from None
        except (urllib.error.URLError, TimeoutError, OSError):
            raise APIError("unavailable") from None

    def get(self, path):
        return self.request("GET", path)

    def tree(self, sha):
        data = self.get("/git/trees/" + sha + "?recursive=1")
        if data.get("truncated"):
            raise APIError("tree_truncated")
        return {entry["path"]: entry for entry in data["tree"] if entry["type"] != "tree"}

    def blob(self, sha):
        data = self.get("/git/blobs/" + sha)
        if data.get("encoding") != "base64":
            raise APIError("unsupported_blob_encoding")
        raw = base64.b64decode(data["content"], validate=False)
        actual = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
        if actual != sha:
            raise APIError("blob_integrity")
        return raw

    def pages(self, path):
        page = 1
        while True:
            items = self.get(path + ("&" if "?" in path else "?") + f"per_page=100&page={page}")
            yield from items
            if len(items) < 100:
                break
            page += 1

    def commit_files(self, parent, files, message, *, blobs=None):
        """Create a commit, but do not move any ref. Caller performs a non-force CAS."""
        base = self.get("/git/commits/" + parent)["tree"]["sha"]
        entries = [{"path": path, "mode": "100644", "type": "blob", "sha": sha}
                   for path, sha in sorted((blobs or {}).items())]
        for path, raw in sorted(files.items()):
            blob = self.request("POST", "/git/blobs", {
                "content": base64.b64encode(raw).decode("ascii"), "encoding": "base64"})
            entries.append({"path": path, "mode": "100644", "type": "blob", "sha": blob["sha"]})
        tree = self.request("POST", "/git/trees", {"base_tree": base, "tree": entries})
        return self.request("POST", "/git/commits", {
            "message": message, "tree": tree["sha"], "parents": [parent]})["sha"]

    def advance(self, branch, commit):
        # Non-fast-forward failure is a retryable conflict, never force-push.
        return self.request("PATCH", "/git/refs/heads/" + branch,
                            {"sha": commit, "force": False})
