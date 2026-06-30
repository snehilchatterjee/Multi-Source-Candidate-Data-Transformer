from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable

from candidate_transformer.core.models import Observation


AUTO_MERGE_IDENTITY_FIELDS = {
    "candidate_ref": "candidate_ref",
    "emails": "email",
    "links.github": "github",
}

CONDITIONAL_IDENTITY_FIELDS = {
    "phones": "phone",
}

IDENTITY_FIELDS = {
    **AUTO_MERGE_IDENTITY_FIELDS,
    **CONDITIONAL_IDENTITY_FIELDS,
}

MAX_PHONE_NAME_MERGE_GROUP_SIZE = 3


@dataclass(frozen=True)
class CandidateCluster:
    """
    A group of source records that likely refer to the same real candidate.

    This is not the final canonical candidate yet.
    It is just the ER grouping result.
    """

    cluster_id: str
    record_ids: tuple[str, ...]
    observations: tuple[Observation, ...]
    identity_keys: tuple[str, ...]


class UnionFind:
    def __init__(self) -> None:
        self.parent: dict[str, str] = {}

    def add(self, item: str) -> None:
        if item not in self.parent:
            self.parent[item] = item

    def find(self, item: str) -> str:
        self.add(item)

        if self.parent[item] != item:
            self.parent[item] = self.find(self.parent[item])

        return self.parent[item]

    def union(self, left: str, right: str) -> None:
        left_root = self.find(left)
        right_root = self.find(right)

        if left_root == right_root:
            return

        # Deterministic parent choice.
        if left_root < right_root:
            self.parent[right_root] = left_root
        else:
            self.parent[left_root] = right_root


def resolve_candidate_clusters(
    observations: Iterable[Observation],
    *,
    warnings: list[str] | None = None,
) -> list[CandidateCluster]:
    """
    Group observations into candidate clusters.

    Automatic merge keys:
      candidate references
      emails
      links.github

    Conditional merge keys:
      phones

    Phone-only merging is intentionally conservative. Two records with the
    same phone are merged only when there is corroboration, currently a
    compatible full_name or a second shared automatic identity key.

    A merge is rejected when both current clusters contain non-null,
    contradictory candidate references. Candidate references are currently
    treated as belonging to one global namespace.
    """

    observation_list = list(observations)

    if not observation_list:
        return []

    union_find = UnionFind()

    auto_key_to_record_ids: dict[str, set[str]] = defaultdict(set)
    phone_key_to_record_ids: dict[str, set[str]] = defaultdict(set)

    record_to_identity_keys: dict[str, set[str]] = defaultdict(set)
    record_to_auto_keys: dict[str, set[str]] = defaultdict(set)
    record_to_candidate_refs: dict[str, set[str]] = defaultdict(set)
    record_to_names: dict[str, set[str]] = defaultdict(set)

    for observation in observation_list:
        record_id = observation.record_id
        union_find.add(record_id)

        if observation.field_path == "full_name":
            name = _observation_value(observation)
            if name is not None:
                record_to_names[record_id].add(name)

        identity_key = identity_key_for_observation(observation)

        if identity_key is None:
            continue

        record_to_identity_keys[record_id].add(identity_key)

        if observation.field_path in AUTO_MERGE_IDENTITY_FIELDS:
            record_to_auto_keys[record_id].add(identity_key)
            auto_key_to_record_ids[identity_key].add(record_id)

            if observation.field_path == "candidate_ref":
                candidate_ref = _observation_value(observation)
                if candidate_ref is not None:
                    record_to_candidate_refs[record_id].add(candidate_ref)

        elif observation.field_path == "phones":
            phone_key_to_record_ids[identity_key].add(record_id)

    # Candidate-reference metadata follows union-find roots so every merge is
    # checked against all references already present in both current clusters.
    root_to_candidate_refs = {
        record_id: set(record_to_candidate_refs.get(record_id, set()))
        for record_id in union_find.parent
    }
    emitted_conflicts: set[tuple[str, str, str]] = set()

    # Process automatic identity evidence deterministically, with explicit
    # candidate-reference matches first. Buckets use representative unions
    # instead of comparing every pair. When one email/GitHub bucket contains
    # contradictory reference-bearing components, reference-free components
    # remain in their own ambiguous cluster rather than being attached to an
    # arbitrary referenced component.
    for identity_key in sorted(auto_key_to_record_ids, key=_auto_merge_key_sort_key):
        _merge_auto_identity_bucket(
            identity_key=identity_key,
            record_ids=auto_key_to_record_ids[identity_key],
            union_find=union_find,
            root_to_candidate_refs=root_to_candidate_refs,
            warnings=warnings,
            emitted_conflicts=emitted_conflicts,
        )

    # Conditional phone merges.
    for phone_key, phone_record_ids in sorted(phone_key_to_record_ids.items()):
        sorted_record_ids = sorted(phone_record_ids)
        phone_group_size = len(sorted_record_ids)

        # The policy permits name-corroborated phone merges only in small
        # buckets. A second shared automatic key has already been processed
        # above (or blocked by contradictory references), so a large phone
        # bucket cannot contribute any new valid merge.
        if phone_group_size > MAX_PHONE_NAME_MERGE_GROUP_SIZE:
            continue

        for left_index, left_record_id in enumerate(sorted_record_ids):
            for right_record_id in sorted_record_ids[left_index + 1 :]:
                if _can_merge_on_phone(
                    left_record_id=left_record_id,
                    right_record_id=right_record_id,
                    phone_group_size=phone_group_size,
                    record_to_auto_keys=record_to_auto_keys,
                    record_to_names=record_to_names,
                ):
                    _union_if_candidate_refs_compatible(
                        left_record_id=left_record_id,
                        right_record_id=right_record_id,
                        merge_key=phone_key,
                        union_find=union_find,
                        root_to_candidate_refs=root_to_candidate_refs,
                        warnings=warnings,
                        emitted_conflicts=emitted_conflicts,
                    )

    root_to_observations: dict[str, list[Observation]] = defaultdict(list)
    root_to_record_ids: dict[str, set[str]] = defaultdict(set)
    root_to_identity_keys: dict[str, set[str]] = defaultdict(set)

    for observation in observation_list:
        root = union_find.find(observation.record_id)

        root_to_observations[root].append(observation)
        root_to_record_ids[root].add(observation.record_id)
        root_to_identity_keys[root].update(
            record_to_identity_keys.get(observation.record_id, set())
        )

    clusters: list[CandidateCluster] = []

    for root in sorted(root_to_observations):
        record_ids = tuple(sorted(root_to_record_ids[root]))
        identity_keys = tuple(sorted(root_to_identity_keys[root]))
        sorted_observations = tuple(
            sorted(root_to_observations[root], key=_observation_sort_key)
        )

        clusters.append(
            CandidateCluster(
                cluster_id=make_cluster_id(
                    identity_keys=identity_keys,
                    record_ids=record_ids,
                ),
                record_ids=record_ids,
                observations=sorted_observations,
                identity_keys=identity_keys,
            )
        )

    return sorted(clusters, key=lambda cluster: cluster.cluster_id)


def _auto_merge_key_sort_key(identity_key: str) -> tuple[int, str]:
    if identity_key.startswith("candidate_ref:"):
        priority = 0
    elif identity_key.startswith("github:"):
        priority = 1
    else:
        priority = 2

    return priority, identity_key


def _merge_auto_identity_bucket(
    *,
    identity_key: str,
    record_ids: Iterable[str],
    union_find: UnionFind,
    root_to_candidate_refs: dict[str, set[str]],
    warnings: list[str] | None,
    emitted_conflicts: set[tuple[str, str, str]],
) -> None:
    """Merge one automatic-key bucket with a linear number of union attempts.

    Candidate-reference buckets are intrinsically compatible because every
    member contains the reference named by the bucket. For email and GitHub
    buckets, current DSU components are divided into reference-bearing and
    reference-free components:

    * zero referenced components: merge the whole bucket;
    * one referenced component: merge neutral components into it;
    * multiple referenced components: keep those components separate and
      merge neutral components only with one another.

    The final case avoids inventing which contradictory candidate reference a
    neutral record belongs to. Candidate-reference keys are processed first,
    so distinct reference-bearing roots at this point have disjoint reference
    sets.
    """

    roots = sorted({union_find.find(record_id) for record_id in record_ids})

    if len(roots) < 2:
        return

    if identity_key.startswith("candidate_ref:"):
        _merge_roots_with_representative(
            roots=roots,
            merge_key=identity_key,
            union_find=union_find,
            root_to_candidate_refs=root_to_candidate_refs,
            warnings=warnings,
            emitted_conflicts=emitted_conflicts,
        )
        return

    referenced_roots = [
        root for root in roots if root_to_candidate_refs.get(root, set())
    ]
    neutral_roots = [
        root for root in roots if not root_to_candidate_refs.get(root, set())
    ]

    if len(referenced_roots) <= 1:
        representative = referenced_roots[0] if referenced_roots else neutral_roots[0]
        _merge_roots_with_representative(
            roots=[representative, *(root for root in roots if root != representative)],
            merge_key=identity_key,
            union_find=union_find,
            root_to_candidate_refs=root_to_candidate_refs,
            warnings=warnings,
            emitted_conflicts=emitted_conflicts,
        )
        return

    if len(neutral_roots) > 1:
        _merge_roots_with_representative(
            roots=neutral_roots,
            merge_key=identity_key,
            union_find=union_find,
            root_to_candidate_refs=root_to_candidate_refs,
            warnings=warnings,
            emitted_conflicts=emitted_conflicts,
        )

    if warnings is not None:
        reference_groups = sorted(
            tuple(sorted(root_to_candidate_refs[root]))
            for root in referenced_roots
        )
        preview = reference_groups[:5]
        omitted_count = len(reference_groups) - len(preview)
        preview_text = repr(preview)
        if omitted_count:
            preview_text += f" (+{omitted_count} more)"

        neutral_message = (
            f" {len(neutral_roots)} reference-free component(s) remain separate "
            "because their referenced identity is ambiguous."
            if neutral_roots
            else ""
        )
        warnings.append(
            "Entity resolution blocked merge on "
            f"{identity_key!r}: contradictory candidate_ref groups "
            f"{preview_text}.{neutral_message}"
        )


def _merge_roots_with_representative(
    *,
    roots: Iterable[str],
    merge_key: str,
    union_find: UnionFind,
    root_to_candidate_refs: dict[str, set[str]],
    warnings: list[str] | None,
    emitted_conflicts: set[tuple[str, str, str]],
) -> None:
    root_list = list(roots)
    if len(root_list) < 2:
        return

    representative = root_list[0]
    for root in root_list[1:]:
        _union_if_candidate_refs_compatible(
            left_record_id=representative,
            right_record_id=root,
            merge_key=merge_key,
            union_find=union_find,
            root_to_candidate_refs=root_to_candidate_refs,
            warnings=warnings,
            emitted_conflicts=emitted_conflicts,
        )


def _union_if_candidate_refs_compatible(
    *,
    left_record_id: str,
    right_record_id: str,
    merge_key: str,
    union_find: UnionFind,
    root_to_candidate_refs: dict[str, set[str]],
    warnings: list[str] | None,
    emitted_conflicts: set[tuple[str, str, str]],
) -> bool:
    left_root = union_find.find(left_record_id)
    right_root = union_find.find(right_record_id)

    if left_root == right_root:
        return True

    left_refs = root_to_candidate_refs.get(left_root, set())
    right_refs = root_to_candidate_refs.get(right_root, set())

    if left_refs and right_refs and left_refs.isdisjoint(right_refs):
        conflict_key = tuple(sorted((left_root, right_root))) + (merge_key,)

        if warnings is not None and conflict_key not in emitted_conflicts:
            warnings.append(
                "Entity resolution blocked merge on "
                f"{merge_key!r} between records {left_record_id!r} and "
                f"{right_record_id!r}: contradictory candidate_ref values "
                f"{sorted(left_refs)!r} and {sorted(right_refs)!r}."
            )

        emitted_conflicts.add(conflict_key)
        return False

    combined_refs = left_refs | right_refs
    union_find.union(left_root, right_root)
    merged_root = union_find.find(left_root)

    root_to_candidate_refs.pop(left_root, None)
    root_to_candidate_refs.pop(right_root, None)
    root_to_candidate_refs[merged_root] = combined_refs
    return True


def identity_key_for_observation(
    observation: Observation,
) -> str | None:
    key_prefix = IDENTITY_FIELDS.get(observation.field_path)

    if key_prefix is None:
        return None

    value = _observation_value(observation)

    if value is None:
        return None

    return f"{key_prefix}:{value}"


def strong_identity_key_for_observation(
    observation: Observation,
) -> str | None:
    """
    Backwards-compatible wrapper.

    Historically this returned email, phone, and GitHub keys. The merge policy
    now treats phone as conditional, but callers/tests may still use this helper
    to inspect identity keys.
    """

    return identity_key_for_observation(observation)


def make_cluster_id(
    *,
    identity_keys: tuple[str, ...],
    record_ids: tuple[str, ...],
) -> str:
    """
    Create a deterministic candidate cluster ID.

    Email and GitHub are treated as globally strong enough for the ID base.
    Phone is not, because two unmerged records may share the same phone.
    If the cluster has no email/GitHub identity key, include record IDs.
    """

    globally_unique_keys = tuple(
        key
        for key in identity_keys
        if (
            key.startswith("candidate_ref:")
            or key.startswith("email:")
            or key.startswith("github:")
        )
    )

    if globally_unique_keys:
        base = "|".join(globally_unique_keys)
    else:
        base = "|".join(f"record:{record_id}" for record_id in record_ids)

    digest = hashlib.sha256(base.encode("utf-8")).hexdigest()[:16]

    return f"cand_{digest}"


def _can_merge_on_phone(
    *,
    left_record_id: str,
    right_record_id: str,
    phone_group_size: int,
    record_to_auto_keys: dict[str, set[str]],
    record_to_names: dict[str, set[str]],
) -> bool:
    # If there is already a second shared automatic identity key, phone is safe.
    if record_to_auto_keys[left_record_id] & record_to_auto_keys[right_record_id]:
        return True

    # Avoid name-only phone merges for phone numbers shared by many records.
    # This guards against office lines, placeholder numbers, and bad exports.
    if phone_group_size > MAX_PHONE_NAME_MERGE_GROUP_SIZE:
        return False

    return _records_have_compatible_name(
        left_record_id=left_record_id,
        right_record_id=right_record_id,
        record_to_names=record_to_names,
    )


def _records_have_compatible_name(
    *,
    left_record_id: str,
    right_record_id: str,
    record_to_names: dict[str, set[str]],
) -> bool:
    left_names = record_to_names.get(left_record_id, set())
    right_names = record_to_names.get(right_record_id, set())

    if not left_names or not right_names:
        return False

    for left_name in left_names:
        for right_name in right_names:
            if _names_are_compatible(left_name, right_name):
                return True

    return False


def _names_are_compatible(left_name: str, right_name: str) -> bool:
    left_tokens = _name_tokens(left_name)
    right_tokens = _name_tokens(right_name)

    if not left_tokens or not right_tokens:
        return False

    if left_tokens == right_tokens:
        return True

    # Handles "Alex Chen" vs "Chen Alex" without fuzzy matching.
    if len(left_tokens) == len(right_tokens) and sorted(left_tokens) == sorted(right_tokens):
        return True

    return False


def _name_tokens(name: str) -> tuple[str, ...]:
    normalized = re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()

    if not normalized:
        return ()

    return tuple(normalized.split())


def _observation_value(observation: Observation) -> str | None:
    if observation.normalized_value is None:
        return None

    value = str(observation.normalized_value).strip()

    if not value:
        return None

    return value


def _observation_sort_key(observation: Observation) -> tuple[str, str, str, str, str]:
    return (
        observation.record_id,
        observation.field_path,
        str(observation.normalized_value),
        observation.source.source_type,
        observation.source.locator or "",
    )
