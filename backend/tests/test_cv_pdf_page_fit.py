import io

import pdfplumber

from app.routes import generate as generate_routes


def _profile(project_count: int) -> dict:
    long_description = (
        "A synthetic project description repeated to occupy enough vertical "
        "space that including all of these projects pushes the resume past "
        "a single page during the test. "
    ) * 12
    return {
        "name": "Jane Doe",
        "email": "jane@example.com",
        "phone": None,
        "location": None,
        "linkedin": None,
        "github": None,
        "portfolio": None,
        "summary": None,
        "work_experience": [],
        "education": [],
        "skills": [],
        "skill_categories": None,
        "projects": [
            {
                "name": f"Project {i}",
                "description": long_description,
                "tech_stack": ["Python"],
                "link": None,
            }
            for i in range(project_count)
        ],
        "certifications": [],
    }


def _page_count(pdf_bytes: bytes) -> int:
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        return len(pdf.pages)


def test_render_cv_pdf_keeps_all_projects_when_they_fit_one_page():
    response = generate_routes._render_cv_pdf(_profile(project_count=2))

    assert _page_count(response.body) == 1


def test_render_cv_pdf_trims_to_top_projects_when_they_would_overflow():
    profile = _profile(project_count=8)

    unrimmed_html = generate_routes.render_cv_template(profile)
    assert _page_count(generate_routes.html_to_pdf(unrimmed_html)) > 1, (
        "test fixture must actually overflow one page before trimming for "
        "this test to prove anything"
    )

    response = generate_routes._render_cv_pdf(profile)

    assert _page_count(response.body) == 1
    with pdfplumber.open(io.BytesIO(response.body)) as pdf:
        text = pdf.pages[0].extract_text()
    kept = [f"Project {i}" for i in range(generate_routes.MAX_PROJECTS_WHEN_TRIMMED)]
    dropped = [
        f"Project {i}"
        for i in range(generate_routes.MAX_PROJECTS_WHEN_TRIMMED, 8)
    ]
    assert all(name in text for name in kept)
    assert not any(name in text for name in dropped)
