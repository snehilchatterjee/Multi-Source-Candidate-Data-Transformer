from __future__ import annotations

import hashlib
from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable

from candidate_transformer.core.models import Observation


STRONG_IDENTITY_FIELDS = {
    "emails": "email",
    "phones": "phone",
    "links.github": "github",
}


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
) -> list[CandidateCluster]:
    """
    Group observations into candidate clusters using strong identity keys.

    Strong keys:
      emails
      phones
      links.github

    Every record_id becomes at least one cluster.
    Records sharing a strong key are merged.
    """

    observation_list = list(observations)

    if not observation_list:
        return []

    union_find = UnionFind()

    key_to_record_id: dict[str, str] = {}
    record_to_identity_keys: dict[str, set[str]] = defaultdict(set)

    for observation in observation_list:
        union_find.add(observation.record_id)

        identity_key = strong_identity_key_for_observation(observation)

        if identity_key is None:
            continue

        record_to_identity_keys[observation.record_id].add(identity_key)

        previous_record_id = key_to_record_id.get(identity_key)

        if previous_record_id is None:
            key_to_record_id[identity_key] = observation.record_id
        else:
            union_find.union(observation.record_id, previous_record_id)

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


def strong_identity_key_for_observation(
    observation: Observation,
) -> str | None:
    key_prefix = STRONG_IDENTITY_FIELDS.get(observation.field_path)

    if key_prefix is None:
        return None

    if observation.normalized_value is None:
        return None

    value = str(observation.normalized_value).strip()

    if not value:
        return None

    return f"{key_prefix}:{value}"


def make_cluster_id(
    *,
    identity_keys: tuple[str, ...],
    record_ids: tuple[str, ...],
) -> str:
    """
    Create a deterministic candidate cluster ID.

    Prefer identity keys. If no identity key exists, fall back to record IDs.
    """

    if identity_keys:
        base = "|".join(identity_keys)
    else:
        base = "|".join(f"record:{record_id}" for record_id in record_ids)

    digest = hashlib.sha256(base.encode("utf-8")).hexdigest()[:16]

    return f"cand_{digest}"


def _observation_sort_key(observation: Observation) -> tuple[str, str, str, str, str]:
    return (
        observation.record_id,
        observation.field_path,
        str(observation.normalized_value),
        observation.source.source_type,
        observation.source.locator or "",
    )