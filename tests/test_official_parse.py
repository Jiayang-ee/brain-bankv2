from faculty_spider_v3.official.parse_html import extract_people_from_list_page, extract_person_profile, should_trigger_llm


PROFILE_HTML = """
<html>
  <head><title>Yifan Chen</title></head>
  <body>
    <main>
      <h1>Yifan Chen</h1>
      <p class="job-title">Assistant Professor</p>
      <p class="department">Department of Management Science</p>
      <a href="mailto:yifan.chen@example.edu">Email</a>
      <img class="profile" src="/photos/yifan.jpg" alt="Yifan Chen portrait" />
      <h2>Research Interests</h2>
      <p>Decision analytics and platform operations.</p>
      <h2>Biography</h2>
      <p>Yifan Chen is an assistant professor.</p>
      <h2>Education</h2>
      <p>PhD, Tsinghua University.</p>
      <p>Advisor: Wei Zhang.</p>
    </main>
  </body>
</html>
"""


def test_extract_person_profile_fields():
    profile = extract_person_profile(PROFILE_HTML, "https://example.edu/people/yifan-chen", school="Example University")

    assert profile.name == "Yifan Chen"
    assert profile.title == "Assistant Professor"
    assert profile.email == "yifan.chen@example.edu"
    assert profile.department == "Department of Management Science"
    assert profile.photo_url == "https://example.edu/photos/yifan.jpg"
    assert "Decision analytics" in profile.research_interests
    assert "Tsinghua" in profile.education
    assert profile.confidence_score >= 0.7


def test_extract_person_profile_from_label_blocks_and_obfuscated_email():
    html = """
    <html><body>
      <h1 class="sr-only">Chen, Yifan (yc1234)</h1>
      <h2 class="fic-name h3">Yifan Chen</h2>
      <div class="fic-title h5">Assistant Professor</div>
      <a class="fic-contact-email" data-user="yc1234" data-domain="example.edu" href="#"></a>
      <div class="fic-affiliations"><h3 class="h5">TC Affiliations:</h3> Management Science</div>
      <div class="fic-expertise"><h3 class="h5">Faculty Expertise:</h3> Operations Analytics</div>
      <div class="faculty-section active">
        <h3>Educational Background</h3>
        <p>PhD, Tsinghua University.</p>
        <h3>Scholarly Interests</h3>
        <p>Platform operations and decision analytics.</p>
        <h3>Selected Publications</h3>
        <p>Chen, Y. (2026). Analytics paper.</p>
      </div>
      <div class="faculty-section">
        <a><h3 class="panel-heading">Biographical Information</h3></a>
        <div><p>Yifan Chen studies digital platforms.</p></div>
      </div>
    </body></html>
    """

    profile = extract_person_profile(html, "https://example.edu/faculty/yc1234/", school="Example University")

    assert profile.name == "Yifan Chen"
    assert profile.email == "yc1234@example.edu"
    assert profile.department == "Management Science"
    assert "Platform operations" in profile.research_interests
    assert "Tsinghua" in profile.education
    assert "Analytics paper" in profile.publications
    assert "digital platforms" in profile.biography


def test_should_trigger_llm_for_sparse_profile():
    html = "<html><body><h1>Yifan Chen</h1><p>Biography Research Education</p></body></html>"
    profile = extract_person_profile(html, "https://example.edu/people/yifan-chen")

    trigger, reason = should_trigger_llm(html, profile)

    assert trigger
    assert reason in {"likely_profile_with_fewer_than_3_useful_fields", "target_labels_present_but_sections_not_isolated", "low_html_parser_confidence"}


def test_extract_people_from_list_page_cards():
    html = """
    <html><body>
      <div class="faculty-card">
        <a href="/people/yifan-chen">Yifan Chen</a>
        <p>Assistant Professor</p>
        <p>Department of Management Science</p>
        <a href="mailto:yifan.chen@example.edu">Email</a>
      </div>
      <div class="faculty-card">
        <a href="/people/john-smith">John Smith</a>
        <p>Professor</p>
      </div>
    </body></html>
    """

    profiles = extract_people_from_list_page(html, "https://example.edu/faculty", school="Example University")

    assert len(profiles) == 2
    assert profiles[0].name == "Yifan Chen"
    assert profiles[0].source_url == "https://example.edu/people/yifan-chen"
    assert profiles[0].email == "yifan.chen@example.edu"


def test_extract_people_from_fd_content_json():
    html = """
    <html><body>
      <script class="fd-content-json" type="application/json">
      [
        {
          "template": "<li data-type=\\"compact\\"><div class=\\"fd-list-item\\"><div><a href=\\"/faculty/hc2158/\\"><span>Henan</span> <span><strong>Cheng</strong></span></a></div><div>Deputy Director of the Center on Chinese Education</div></div></li>",
          "search": "henan cheng deputy director of the center on chinese education",
          "name": "Henan Cheng",
          "departmentCode": "ITS"
        }
      ]
      </script>
    </body></html>
    """

    profiles = extract_people_from_list_page(html, "https://example.edu/faculty", school="Example University")

    assert len(profiles) == 1
    assert profiles[0].name == "Henan Cheng"
    assert profiles[0].source_url == "https://example.edu/faculty/hc2158/"
