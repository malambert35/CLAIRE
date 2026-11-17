"""Resolve existing Immich person labels locally; never infer identity from pixels."""

import re
import unicodedata

from .immich_mcp import MCPError


def normalized(value):
    value = unicodedata.normalize("NFKD", value.casefold())
    return " ".join(re.findall(r"\w+", "".join(c for c in value if not unicodedata.combining(c))))


def person_assets(client, question):
    people = {}
    complete = False
    for page in range(1, 6):
        result = client.call("immich_people_list", {"withHidden": False, "page": page, "size": 100})
        rows = result.get("people") if isinstance(result, dict) else None
        if not isinstance(rows, list):
            raise MCPError("Unsupported Immich people response")
        for person in rows[:100]:
            if not isinstance(person, dict) or person.get("isHidden") is not False:
                continue
            identifier, name = person.get("id"), person.get("name")
            if isinstance(identifier, str) and isinstance(name, str) and name.strip():
                people[identifier] = name[:160]
        if len(rows) < 100:
            complete = True
            break
    # Never select a unique person from an incomplete directory: later pages may contain namesakes.
    if not complete:
        return [], {"status": "people_limit_reached"}
    query = " " + normalized(question) + " "
    matches = [
        (identifier, name) for identifier, name in people.items() if " " + normalized(name) + " " in query
    ]
    if not matches:
        matches = [
            (identifier, name)
            for identifier, name in people.items()
            if any(" " + word + " " in query for word in normalized(name).split() if len(word) >= 3)
        ]
    if len(matches) != 1:
        return [], {
            "status": "ambiguous_person" if matches else "person_not_found",
            "candidates": [name for _, name in matches[:10]],
        }
    identifier, name = matches[0]
    assets = client.call("immich_people_assets", {"personId": identifier, "page": 1, "size": 25})
    return assets, {
        "status": "available",
        "person": name,
        "identity_source": "Existing Immich person label; not independently verified",
    }
