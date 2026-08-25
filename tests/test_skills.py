import json
from pathlib import Path
import pytest
from vcf_mcp.skills import (
    load_catalog,
    check_index_exact_regeneration,
    SkillLoadError,
    _calculate_sha256
)

def test_load_catalog_and_verify(tmp_path: Path):
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()

    slug = "test-skill"
    version = "1.0.0"
    skill_dir = skills_dir / slug / version
    skill_dir.mkdir(parents=True)

    content = "# Test Skill"
    (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")

    metadata = {
        "title": "Test Title",
        "summary": "Test Summary",
        "maturity": "seed",
        "source_provenance": "test"
    }
    (skill_dir / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")

    index_data = {
        "skills": [{
            "slug": slug,
            "version": version,
            "title": metadata["title"],
            "summary": metadata["summary"],
            "maturity": metadata["maturity"],
            "source_provenance": metadata["source_provenance"],
            "content_sha256": _calculate_sha256(content)
        }],
        "current": {slug: version}
    }
    (skills_dir / "index.json").write_text(json.dumps(index_data), encoding="utf-8")

    catalog = load_catalog(skills_dir)
    assert len(catalog.skills) == 1

    # Test tool paths
    assert catalog.get_skill(slug).content == content
    assert catalog.get_skill(slug, "1.0.0").content == content
    assert catalog.get_skill(slug, "current").content == content
    assert catalog.get_skill("missing") is None

    listing = catalog.list_skills()
    assert len(listing) == 1

    # Test resource paths
    uris = catalog.get_resource_uris()
    assert f"skill://{slug}/{version}" in uris
    assert f"skill://{slug}/current" in uris

    assert catalog.read_resource(f"skill://{slug}/{version}") == content
    assert catalog.read_resource(f"skill://{slug}/current") == content
    assert catalog.read_resource("skill://missing/current") is None
    assert catalog.read_resource("invalid://uri") is None

    # Test prompt paths
    prompts = catalog.get_prompts()
    assert len(prompts) == 1
    assert prompts[0]["name"] == f"use_{slug}"
    assert prompts[0]["description"] == metadata["summary"]

    assert catalog.read_prompt(f"use_{slug}") == content
    assert catalog.read_prompt("use_missing") is None
    assert catalog.read_prompt("invalid") is None

    # Test regeneration check
    check_index_exact_regeneration(skills_dir)

def test_load_catalog_digest_mismatch(tmp_path: Path):
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()

    slug = "test-skill"
    version = "1.0.0"
    skill_dir = skills_dir / slug / version
    skill_dir.mkdir(parents=True)

    content = "# Test Skill"
    (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")

    index_data = {
        "skills": [{
            "slug": slug,
            "version": version,
            "title": "T",
            "summary": "S",
            "maturity": "seed",
            "source_provenance": "p",
            "content_sha256": "bad_digest"
        }],
        "current": {slug: version}
    }
    (skills_dir / "index.json").write_text(json.dumps(index_data), encoding="utf-8")

    with pytest.raises(SkillLoadError, match="Digest mismatch"):
        load_catalog(skills_dir)

def test_dev_overlay(tmp_path: Path):
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    (skills_dir / "index.json").write_text("{}", encoding="utf-8")

    dev_dir = tmp_path / "dev_skills"
    dev_dir.mkdir()

    slug = "dev-skill"
    version = "1.0.0"
    skill_dir = dev_dir / slug / version
    skill_dir.mkdir(parents=True)

    content = "# Dev Skill"
    (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")

    index_data = {
        "skills": [{
            "slug": slug,
            "version": version,
            "title": "T",
            "summary": "S",
            "maturity": "seed",
            "source_provenance": "p",
            "content_sha256": _calculate_sha256(content)
        }],
        "current": {slug: version}
    }
    (dev_dir / "index.json").write_text(json.dumps(index_data), encoding="utf-8")

    # Should load dev dir
    catalog = load_catalog(skills_dir, dev_path=dev_dir)
    assert len(catalog.skills) == 1
    assert catalog.get_skill(slug).content == content

    # Should refuse if actions enabled
    with pytest.raises(SkillLoadError, match="Cannot load SKILLS_DEV_PATH"):
        load_catalog(skills_dir, dev_path=dev_dir, is_any_target_actions_enabled=True)


def test_load_catalog_excludes_placeholder(tmp_path: Path):
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()

    slug = "test-skill"
    version = "1.0.0"
    skill_dir = skills_dir / slug / version
    skill_dir.mkdir(parents=True)

    content = "# Test Skill"
    (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")

    metadata = {
        "title": "Test Title",
        "summary": "Test Summary",
        "maturity": "placeholder",
        "source_provenance": "test"
    }
    (skill_dir / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")

    index_data = {
        "skills": [{
            "slug": slug,
            "version": version,
            "title": metadata["title"],
            "summary": metadata["summary"],
            "maturity": metadata["maturity"],
            "source_provenance": metadata["source_provenance"],
            "content_sha256": _calculate_sha256(content)
        }],
        "current": {slug: version}
    }
    (skills_dir / "index.json").write_text(json.dumps(index_data), encoding="utf-8")

    catalog = load_catalog(skills_dir)
    assert len(catalog.skills) == 0
    assert catalog.get_skill(slug) is None
    assert catalog.read_resource(f"skill://{slug}/{version}") is None
    assert len(catalog.list_skills()) == 0
    assert len(catalog.get_resource_uris()) == 0
    assert len(catalog.get_prompts()) == 0


def test_load_catalog_content_tamper(tmp_path: Path):
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()

    slug = "test-skill"
    version = "1.0.0"
    skill_dir = skills_dir / slug / version
    skill_dir.mkdir(parents=True)

    content = "# Test Skill"
    (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")

    index_data = {
        "skills": [{
            "slug": slug,
            "version": version,
            "title": "T",
            "summary": "S",
            "maturity": "seed",
            "source_provenance": "p",
            "content_sha256": _calculate_sha256(content)
        }],
        "current": {slug: version}
    }
    (skills_dir / "index.json").write_text(json.dumps(index_data), encoding="utf-8")

    # Tamper the content
    (skill_dir / "SKILL.md").write_text("# Tampered", encoding="utf-8")

    with pytest.raises(SkillLoadError, match="Digest mismatch"):
        load_catalog(skills_dir)


def test_check_index_exact_regeneration_tampered(tmp_path: Path):
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()

    slug = "test-skill"
    version = "1.0.0"
    skill_dir = skills_dir / slug / version
    skill_dir.mkdir(parents=True)

    content = "# Test Skill"
    (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")

    metadata = {
        "title": "Test Title",
        "summary": "Test Summary",
        "maturity": "seed",
        "source_provenance": "test"
    }
    (skill_dir / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")

    # generate a valid index.json
    from vcf_mcp.skills import build_index_data
    index_data = build_index_data(skills_dir)
    (skills_dir / "index.json").write_text(json.dumps(index_data), encoding="utf-8")

    # Check passes initially
    check_index_exact_regeneration(skills_dir)

    # Tamper metadata
    metadata["title"] = "Tampered Title"
    (skill_dir / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")

    with pytest.raises(SkillLoadError, match="does not match metadata on disk"):
        check_index_exact_regeneration(skills_dir)


def test_check_index_exact_regeneration_real_repo():
    repo_root = Path(__file__).parent.parent
    skills_dir = repo_root / "skills"
    if skills_dir.exists():
        check_index_exact_regeneration(skills_dir)


def test_build_index_data_is_sorted(tmp_path: Path, monkeypatch):
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()

    # Create z-skill and a-skill to test sorting
    for slug in ["z-skill", "a-skill"]:
        skill_dir = skills_dir / slug / "1.0.0"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("content", encoding="utf-8")
        metadata = {
            "title": slug,
            "summary": "sum",
            "maturity": "seed",
            "source_provenance": "test"
        }
        (skill_dir / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")

    original_iterdir = Path.iterdir

    def mock_iterdir(self):
        results = list(original_iterdir(self))
        if self == skills_dir:
            # Sort in reverse to ensure the actual function sorts it correctly
            return iter(sorted(results, key=lambda p: p.name, reverse=True))
        return iter(results)

    monkeypatch.setattr(Path, "iterdir", mock_iterdir)

    from vcf_mcp.skills import build_index_data
    index_data = build_index_data(skills_dir)

    # Should be sorted by slug
    assert index_data["skills"][0]["slug"] == "a-skill"
    assert index_data["skills"][1]["slug"] == "z-skill"
