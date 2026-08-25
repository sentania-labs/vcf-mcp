import hashlib
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

logger = logging.getLogger(__name__)

@dataclass(frozen=True, slots=True)
class SkillMetadata:
    slug: str
    version: str
    title: str
    summary: str
    maturity: str
    source_provenance: str
    content_sha256: str


@dataclass(frozen=True, slots=True)
class Skill:
    metadata: SkillMetadata
    content: str


@dataclass(frozen=True, slots=True)
class SkillCatalog:
    skills: tuple[Skill, ...]
    current: Mapping[str, str]

    def get_skill(self, slug: str, version: str | None = None) -> Skill | None:
        if not version or version == "current":
            version = self.current.get(slug)
        if not version:
            return None
        for skill in self.skills:
            if skill.metadata.slug == slug and skill.metadata.version == version:
                return skill
        return None

    def list_skills(self) -> list[dict[str, str]]:
        return [
            {
                "slug": s.metadata.slug,
                "version": s.metadata.version,
                "title": s.metadata.title,
                "summary": s.metadata.summary,
                "maturity": s.metadata.maturity,
                "is_current": self.current.get(s.metadata.slug) == s.metadata.version,
            }
            for s in self.skills
        ]

    # --- Render paths for MCP ---

    def get_resource_uris(self) -> list[str]:
        """Return all skill resource URIs."""
        uris = []
        for skill in self.skills:
            uris.append(f"skill://{skill.metadata.slug}/{skill.metadata.version}")
        for slug in self.current:
            if self.get_skill(slug):
                uris.append(f"skill://{slug}/current")
        return uris

    def read_resource(self, uri: str) -> str | None:
        """Read a skill resource by URI."""
        if not uri.startswith("skill://"):
            return None
        path = uri[len("skill://"):]
        parts = path.split("/")
        if len(parts) != 2:
            return None
        slug, version = parts
        skill = self.get_skill(slug, version)
        return skill.content if skill else None

    def get_prompts(self) -> list[dict[str, str]]:
        """Return all skill prompts."""
        prompts = []
        for slug in self.current:
            skill = self.get_skill(slug)
            if skill:
                prompts.append({
                    "name": f"use_{slug}",
                    "description": skill.metadata.summary,
                })
        return prompts

    def read_prompt(self, name: str) -> str | None:
        """Read a skill prompt by name."""
        if not name.startswith("use_"):
            return None
        slug = name[len("use_"):]
        skill = self.get_skill(slug)
        return skill.content if skill else None


class SkillLoadError(Exception):
    """Raised when skills fail to load or validate."""
    pass


def _calculate_sha256(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def load_catalog(
    skills_dir: Path,
    dev_path: Path | None = None,
    is_any_target_actions_enabled: bool = False,
) -> SkillCatalog:
    """Load and validate the skills catalog from the given directory.

    If dev_path is provided, it replaces skills_dir, BUT only if no target
    is actions-enabled.
    """
    if dev_path:
        if is_any_target_actions_enabled:
            raise SkillLoadError(
                "Cannot load SKILLS_DEV_PATH overlay when any target is actions-enabled."
            )
        target_dir = dev_path
    else:
        target_dir = skills_dir

    index_file = target_dir / "index.json"
    if not index_file.exists():
        raise SkillLoadError(f"Skills index not found at {index_file}")

    with index_file.open("r", encoding="utf-8") as f:
        try:
            index_data = json.load(f)
        except json.JSONDecodeError as e:
            raise SkillLoadError(f"Failed to parse index JSON: {e}")

    raw_skills = index_data.get("skills", [])
    current = index_data.get("current", {})

    skills = []
    for raw in raw_skills:
        meta = SkillMetadata(
            slug=raw["slug"],
            version=raw["version"],
            title=raw["title"],
            summary=raw["summary"],
            maturity=raw["maturity"],
            source_provenance=raw["source_provenance"],
            content_sha256=raw["content_sha256"],
        )

        skill_md_path = target_dir / meta.slug / meta.version / "SKILL.md"
        if not skill_md_path.exists():
            raise SkillLoadError(
                f"Missing content file for {meta.slug}@{meta.version}: {skill_md_path}"
            )

        content = skill_md_path.read_text(encoding="utf-8")
        actual_digest = _calculate_sha256(content)

        if actual_digest != meta.content_sha256:
            raise SkillLoadError(
                f"Digest mismatch for {meta.slug}@{meta.version}. "
                f"Expected {meta.content_sha256}, got {actual_digest}"
            )

        if meta.maturity == "placeholder":
            continue

        skills.append(Skill(metadata=meta, content=content))

    return SkillCatalog(skills=tuple(skills), current=current)


def build_index_data(skills_dir: Path) -> dict:
    """Build the index data dictionary directly from the skills directory tree."""
    catalog = []
    current_map = {}

    for slug_dir in skills_dir.iterdir():
        if not slug_dir.is_dir():
            continue
        slug = slug_dir.name
        versions = []
        for version_dir in slug_dir.iterdir():
            if not version_dir.is_dir():
                continue
            version = version_dir.name
            skill_md = version_dir / "SKILL.md"
            metadata_json = version_dir / "metadata.json"

            if not skill_md.exists() or not metadata_json.exists():
                continue

            with metadata_json.open("r", encoding="utf-8") as f:
                meta = json.load(f)

            content = skill_md.read_text(encoding="utf-8")
            digest = _calculate_sha256(content)

            catalog.append({
                "slug": slug,
                "version": version,
                "title": meta["title"],
                "summary": meta["summary"],
                "maturity": meta["maturity"],
                "source_provenance": meta["source_provenance"],
                "content_sha256": digest,
            })
            versions.append(version)

        if versions:
            versions.sort(key=lambda v: [int(x) if x.isdigit() else x for x in v.replace('-', '.').split('.')])
            current_map[slug] = versions[-1]

    catalog.sort(key=lambda x: (x["slug"], x["version"]))
    return {"skills": catalog, "current": current_map}


def check_index_exact_regeneration(skills_dir: Path) -> None:
    """Verify that the index exactly matches what would be generated from metadata."""
    index_file = skills_dir / "index.json"
    if not index_file.exists():
        raise SkillLoadError(f"Index file missing: {index_file}")

    with index_file.open("r", encoding="utf-8") as f:
        existing_index = json.load(f)

    expected_index = build_index_data(skills_dir)

    existing_catalog = existing_index.get("skills", [])
    existing_catalog.sort(key=lambda x: (x["slug"], x["version"]))

    if expected_index["skills"] != existing_catalog:
        raise SkillLoadError("Skills catalog in index.json does not match metadata on disk.")
    if expected_index["current"] != existing_index.get("current", {}):
        raise SkillLoadError("Current mapping in index.json does not match metadata on disk.")
