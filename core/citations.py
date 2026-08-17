import re

MAX_SOURCE_APPENDIX_ARTIFACTS = 6
SOURCE_LABEL = r"github|confluence|jira|sharepoint|teams"


def bind_source_links(answer: str, hits: list[dict], contradictions: list[dict]) -> str:
    """Bind verified inline links and append cited/contradictory evidence."""
    by_id = {hit["artifact_id"]: hit for hit in hits}
    base = re.split(r"\n#{2,4}\s+Sources\s*\n", answer, maxsplit=1,
                    flags=re.IGNORECASE)[0].rstrip()
    base = re.sub(
        rf"\[((?:{SOURCE_LABEL})|source):([^\]\n]+)\]"
        r"\((?:[^()\n]|\([^()\n]*\))*\)",
        lambda match: f"[{match.group(1)}:{match.group(2)}]",
        base,
        flags=re.IGNORECASE,
    )
    base = re.sub(
        rf"\[({SOURCE_LABEL})\]\((?:[^()\n]|\([^()\n]*\))*\)",
        lambda match: f"[{match.group(1)}]",
        base,
        flags=re.IGNORECASE,
    )
    cited_ids: list[str] = []

    def bind_exact(match: re.Match) -> str:
        source, artifact_id = match.group(1).lower(), match.group(2).strip()
        hit = by_id.get(artifact_id)
        if not hit or hit["source"] != source:
            return match.group(0)
        cited_ids.append(artifact_id)
        return f"[{source}:{artifact_id}]({hit['url']})"

    base = re.sub(
        rf"\[({SOURCE_LABEL}):([^\]\n]+)\](?!\()",
        bind_exact, base, flags=re.IGNORECASE,
    )

    def bind_generic_exact(match: re.Match) -> str:
        artifact_id = match.group(1).strip()
        hit = by_id.get(artifact_id)
        if not hit:
            return match.group(0)
        cited_ids.append(artifact_id)
        return f"[{hit['source']}:{artifact_id}]({hit['url']})"

    base = re.sub(
        r"\[source:([^\]\n]+)\](?!\()",
        bind_generic_exact, base, flags=re.IGNORECASE,
    )
    top_by_source: dict[str, dict] = {}
    for hit in hits:
        top_by_source.setdefault(hit["source"], hit)

    def bind_source_only(match: re.Match) -> str:
        source = match.group(1).lower()
        hit = top_by_source.get(source)
        if not hit:
            return match.group(0)
        cited_ids.append(hit["artifact_id"])
        return f"[{source}:{hit['artifact_id']}]({hit['url']})"

    base = re.sub(
        rf"\[({SOURCE_LABEL})\](?!\()",
        bind_source_only, base, flags=re.IGNORECASE,
    )
    generic_hits = [hit for hit in hits if hit["artifact_id"] not in cited_ids] or hits
    generic_index = 0

    def bind_generic_source(match: re.Match) -> str:
        nonlocal generic_index
        if not generic_hits:
            return match.group(0)
        hit = generic_hits[generic_index % len(generic_hits)]
        generic_index += 1
        cited_ids.append(hit["artifact_id"])
        return f"[{hit['source']}:{hit['artifact_id']}]({hit['url']})"

    base = re.sub(
        r"\[\s*source(?:\s+[0-9]+)?\s*\](?!\()",
        bind_generic_source, base, flags=re.IGNORECASE,
    )
    contradiction_ids: list[str] = []
    for conflict in contradictions:
        contradiction_ids.append(conflict["preferred_artifact"])
        representatives = conflict.get("representatives", {})
        if representatives:
            contradiction_ids.extend(
                representative["artifact_id"] for representative in representatives.values()
            )
        else:
            contradiction_ids.extend(
                artifact_ids[0] for artifact_ids in conflict["values"].values() if artifact_ids
            )
    required: list[str] = contradiction_ids + cited_ids
    required.extend(artifact_id for artifact_id in by_id if artifact_id in base)
    if not required:
        required.extend(hit["artifact_id"] for hit in hits[:3])
    ordered_ids = list(dict.fromkeys(required))
    minimum_size = len(set(contradiction_ids))
    ordered_ids = ordered_ids[:max(MAX_SOURCE_APPENDIX_ARTIFACTS, minimum_size)]
    linked = [by_id[artifact_id] for artifact_id in ordered_ids if artifact_id in by_id]
    sources = "\n".join(
        f"- [{hit['source']}:{hit['artifact_id']}]({hit['url']}) — {hit['title']}"
        for hit in linked
    )
    return f"{base}\n\n### Sources\n{sources}" if sources else base
