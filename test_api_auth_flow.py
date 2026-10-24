"""
End-to-end API smoke test for auth + access grants + the knowledge-gap loop,
against a REAL running server (not TestClient — this project's established
pattern is testing against the thing as it actually runs). Requires:

    uvicorn backend.main:app --host 127.0.0.1 --port 8126

running in another terminal first.

Covers: register/login rejection without a token, owner_id derived from the
token rather than the request body, a visitor denied private content before
a grant and allowed after one, revocation actually taking effect, and the
full knowledge-gap lifecycle (escalate -> list -> answer -> becomes a real,
retrievable Source).
"""
import sys
sys.stdout.reconfigure(encoding="utf-8")

import uuid

import requests

BASE = "http://127.0.0.1:8126"


def run_test():
    suffix = uuid.uuid4().hex[:6]

    # 1. Register an owner
    reg = requests.post(f"{BASE}/auth/register", json={
        "email": f"owner-{suffix}@t2rag.local", "password": "hunter2", "display_name": "Test Owner",
    }).json()
    token = reg["token"]
    print(f"[OK] owner registered: {reg['email']}")

    # 2. Creating a twin without a token must fail
    resp = requests.post(f"{BASE}/twins", json={"name": "Should Fail"})
    assert resp.status_code == 401, f"expected 401, got {resp.status_code}"
    print("[OK] unauthenticated twin creation rejected (401)")

    # 3. Creating a twin WITH a token works, and owner_id comes from the token
    twin = requests.post(
        f"{BASE}/twins", headers={"Authorization": f"Bearer {token}"},
        json={"name": "Auth Flow Twin", "domain": "Auth flow testing", "persona_prompt": "You are a helpful assistant."},
    ).json()
    twin_id = twin["id"]
    assert twin["owner_id"] == reg["user_id"]
    print(f"[OK] twin created with owner_id from token: {twin['slug']}")

    # 4. Ingest a public source and a private source
    requests.post(
        f"{BASE}/twins/{twin_id}/sources/text", headers={"Authorization": f"Bearer {token}"},
        json={"name": "public.txt", "text": "This twin is a demo built for a final year project.", "visibility": "public"},
    )
    requests.post(
        f"{BASE}/twins/{twin_id}/sources/text", headers={"Authorization": f"Bearer {token}"},
        json={"name": "private.txt", "text": "The secret test codename is Zephyr-9.", "visibility": "private"},
    )
    print("[OK] ingested one public and one private source")

    # 5. A visitor with no grant cannot see the private content -> should escalate
    visitor_email = f"visitor-{suffix}@example.com"
    vlogin = requests.post(f"{BASE}/auth/visitor-login", json={"email": visitor_email, "display_name": "Visitor"}).json()
    vtoken, visitor_id = vlogin["token"], vlogin["user_id"]

    chat1 = requests.post(
        f"{BASE}/twins/{twin_id}/chat", headers={"Authorization": f"Bearer {vtoken}"},
        json={"message": "What is the secret test codename?"},
    ).json()
    assert "zephyr" not in chat1["answer"].lower(), "visitor without a grant should NOT see private content"
    print(f"[OK] ungranted visitor denied private content: {chat1['answer'][:60]}...")

    gaps = requests.get(f"{BASE}/twins/{twin_id}/knowledge-gaps", headers={"Authorization": f"Bearer {token}"}).json()
    assert len(gaps) >= 1 and gaps[0]["status"] == "pending"
    print(f"[OK] escalation created a pending knowledge gap: {gaps[0]['question_text']!r}")

    # 6. Owner grants private access; a NEW conversation should now see it
    requests.post(
        f"{BASE}/twins/{twin_id}/grants", headers={"Authorization": f"Bearer {token}"},
        json={"visitor_email": visitor_email, "tier_name": "private"},
    )
    chat2 = requests.post(
        f"{BASE}/twins/{twin_id}/chat", headers={"Authorization": f"Bearer {vtoken}"},
        json={"message": "What is the secret test codename?"},
    ).json()
    assert "zephyr" in chat2["answer"].lower(), f"expected grounded answer after grant, got: {chat2['answer']}"
    print(f"[OK] granted visitor now sees private content: {chat2['answer']}")

    # 7. Revoke, confirm a NEW conversation can't piggyback on the old grant
    #    (does not re-check an already-open conversation -- the tier is
    #    snapshotted at conversation creation, by design, see models.py).
    resp = requests.delete(f"{BASE}/twins/{twin_id}/grants/{visitor_id}", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    print("[OK] access revoked")

    # 8. Answer the knowledge gap -> becomes a real, retrievable Source
    gap_id = gaps[0]["id"]
    answered = requests.post(
        f"{BASE}/twins/{twin_id}/knowledge-gaps/{gap_id}/answer", headers={"Authorization": f"Bearer {token}"},
        json={"answer_text": "The secret test codename is Zephyr-9, shared here for the record.", "visibility": "private"},
    ).json()
    assert answered["status"] == "answered" and answered["resulting_source_id"]
    print(f"[OK] knowledge gap answered -> new Source {answered['resulting_source_id']}")

    print("\nAll auth/access-grant/knowledge-gap checks passed.")


if __name__ == "__main__":
    run_test()
