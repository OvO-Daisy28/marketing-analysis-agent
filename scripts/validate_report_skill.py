import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "report"


def validate():
    manifest = json.loads((SKILL / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["id"] and manifest["version"]
    ids = [template["id"] for template in manifest["templates"]]
    assert len(ids) == len(set(ids)), "duplicate template id"
    for template_id in ids:
        path = SKILL / "templates" / f"{template_id}.md"
        assert path.is_file(), f"missing template: {template_id}"
        assert path.read_text(encoding="utf-8").strip(), f"empty template: {template_id}"
    assert (SKILL / "SKILL.md").is_file()
    return len(ids)


if __name__ == "__main__":
    print(f"Validated {validate()} report templates")
