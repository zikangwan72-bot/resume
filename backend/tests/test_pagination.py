import pytest

from app.core.pagination import PageParams, paginate_list

LIST_ENDPOINTS = [
    ("/api/v1/assets", {}),
    ("/api/v1/service-desk/tickets", {"scope": "all"}),
    ("/api/v1/recruitment/applications", {}),
    ("/api/v1/audit-logs", {}),
]


def test_paginate_list_slices_and_counts():
    items, meta = paginate_list(list(range(25)), PageParams(page=3, page_size=10))
    assert list(items) == [20, 21, 22, 23, 24]
    assert meta == {"page": 3, "page_size": 10, "total": 25}
    assert paginate_list([1, 2], None) == ([1, 2], None)


@pytest.mark.parametrize(("url", "params"), LIST_ENDPOINTS)
def test_unpaged_list_keeps_original_shape(client, admin_headers, url, params):
    response = client.get(url, params=params, headers=admin_headers)
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"data"}
    assert isinstance(body["data"], list)


def _add_applications(client, headers, count=3):
    jobs = client.get("/api/v1/recruitment/jobs?status=开放", headers=headers).json()["data"]
    job_id = jobs[0]["id"]
    for index in range(count):
        response = client.post(
            "/api/v1/recruitment/applications",
            json={
                "job_id": job_id,
                "name": f"分页候选人{index}",
                "email": f"page{index}@example.com",
                "phone": f"1770000000{index}",
                "school": "University of Malaya",
                "major": "Data Science",
                "graduation_year": 2027,
                "resume_text": "SQL; Python",
                "cover_note": "分页测试",
            },
            headers=headers,
        )
        assert response.status_code == 201


@pytest.mark.parametrize(("url", "params"), LIST_ENDPOINTS)
def test_paged_list_returns_slice_and_total(client, admin_headers, url, params):
    if "recruitment" in url:
        _add_applications(client, admin_headers)
    full = client.get(url, params=params, headers=admin_headers).json()["data"]
    assert full, f"seed data expected for {url}"

    first = client.get(url, params={**params, "page": 1, "page_size": 1}, headers=admin_headers)
    assert first.status_code == 200
    body = first.json()
    assert body["pagination"] == {"page": 1, "page_size": 1, "total": len(full)}
    assert [row["id"] for row in body["data"]] == [full[0]["id"]]

    collected = []
    for page in range(1, len(full) + 1):
        page_body = client.get(
            url, params={**params, "page": page, "page_size": 1}, headers=admin_headers
        ).json()
        collected.extend(row["id"] for row in page_body["data"])
    assert collected == [row["id"] for row in full]

    past_end = client.get(
        url, params={**params, "page": len(full) + 1, "page_size": 1}, headers=admin_headers
    ).json()
    assert past_end["data"] == []
    assert past_end["pagination"]["total"] == len(full)


@pytest.mark.parametrize("bad", [{"page": 0}, {"page": 1, "page_size": 0}, {"page": 1, "page_size": 101}])
def test_invalid_page_params_are_rejected(client, admin_headers, bad):
    assert client.get("/api/v1/assets", params=bad, headers=admin_headers).status_code == 422


def test_overdue_ticket_filter_is_paged_after_filtering(client, admin_headers):
    params = {"scope": "all", "status": "超时"}
    full = client.get("/api/v1/service-desk/tickets", params=params, headers=admin_headers).json()["data"]
    paged = client.get(
        "/api/v1/service-desk/tickets", params={**params, "page": 1, "page_size": 50}, headers=admin_headers
    ).json()
    assert paged["pagination"]["total"] == len(full)
    assert [row["id"] for row in paged["data"]] == [row["id"] for row in full]
