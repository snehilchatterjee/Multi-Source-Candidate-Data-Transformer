from candidate_transformer.core.entity_resolution import (
    UnionFind,
    resolve_candidate_clusters,
    strong_identity_key_for_observation,
)
from candidate_transformer.core.models import Observation, SourceRef


def make_observation(
    *,
    record_id: str,
    field_path: str,
    value: str,
) -> Observation:
    return Observation(
        record_id=record_id,
        field_path=field_path,
        raw_value=value,
        normalized_value=value,
        source=SourceRef(
            source_type="test",
            source_id="test_source",
            locator=None,
        ),
        method="test",
        confidence=0.9,
    )


def test_strong_identity_key_for_email():
    observation = make_observation(
        record_id="r1",
        field_path="emails",
        value="alex@example.com",
    )

    assert strong_identity_key_for_observation(observation) == "email:alex@example.com"


def test_same_record_observations_stay_in_one_cluster():
    observations = [
        make_observation(
            record_id="r1",
            field_path="full_name",
            value="Alex Chen",
        ),
        make_observation(
            record_id="r1",
            field_path="experience.company",
            value="Acme",
        ),
    ]

    clusters = resolve_candidate_clusters(observations)

    assert len(clusters) == 1
    assert clusters[0].record_ids == ("r1",)
    assert len(clusters[0].observations) == 2


def test_same_email_merges_two_records():
    observations = [
        make_observation(
            record_id="csv_row_1",
            field_path="emails",
            value="alex@example.com",
        ),
        make_observation(
            record_id="note_1",
            field_path="emails",
            value="alex@example.com",
        ),
    ]

    clusters = resolve_candidate_clusters(observations)

    assert len(clusters) == 1
    assert clusters[0].record_ids == ("csv_row_1", "note_1")
    assert clusters[0].identity_keys == ("email:alex@example.com",)


def test_same_phone_without_corrobation_does_not_merge():
    observations = [
        make_observation(
            record_id="r1",
            field_path="emails",
            value="alex.personal@example.com",
        ),
        make_observation(
            record_id="r1",
            field_path="phones",
            value="+919876543210",
        ),
        make_observation(
            record_id="r2",
            field_path="emails",
            value="someone.else@example.com",
        ),
        make_observation(
            record_id="r2",
            field_path="phones",
            value="+919876543210",
        ),
    ]

    clusters = resolve_candidate_clusters(observations)

    assert len(clusters) == 2
    assert clusters[0].cluster_id != clusters[1].cluster_id


def test_same_phone_with_compatible_name_merges_records():
    observations = [
        make_observation(
            record_id="r1",
            field_path="full_name",
            value="Alex Chen",
        ),
        make_observation(
            record_id="r1",
            field_path="phones",
            value="+919876543210",
        ),
        make_observation(
            record_id="r2",
            field_path="full_name",
            value="alex   chen",
        ),
        make_observation(
            record_id="r2",
            field_path="phones",
            value="+919876543210",
        ),
    ]

    clusters = resolve_candidate_clusters(observations)

    assert len(clusters) == 1
    assert clusters[0].record_ids == ("r1", "r2")
    assert clusters[0].identity_keys == ("phone:+919876543210",)


def test_same_phone_with_reordered_compatible_name_merges_records():
    observations = [
        make_observation(
            record_id="r1",
            field_path="full_name",
            value="Alex Chen",
        ),
        make_observation(
            record_id="r1",
            field_path="phones",
            value="+919876543210",
        ),
        make_observation(
            record_id="r2",
            field_path="full_name",
            value="Chen Alex",
        ),
        make_observation(
            record_id="r2",
            field_path="phones",
            value="+919876543210",
        ),
    ]

    clusters = resolve_candidate_clusters(observations)

    assert len(clusters) == 1
    assert clusters[0].record_ids == ("r1", "r2")


def test_same_name_without_strong_key_does_not_merge():
    observations = [
        make_observation(
            record_id="r1",
            field_path="full_name",
            value="Alex Chen",
        ),
        make_observation(
            record_id="r2",
            field_path="full_name",
            value="Alex Chen",
        ),
    ]

    clusters = resolve_candidate_clusters(observations)

    assert len(clusters) == 2


def test_strong_identifier_chain_still_merges():
    observations = [
        make_observation(
            record_id="r1",
            field_path="emails",
            value="alex@example.com",
        ),
        make_observation(
            record_id="r2",
            field_path="emails",
            value="alex@example.com",
        ),
        make_observation(
            record_id="r2",
            field_path="links.github",
            value="https://github.com/alexchen",
        ),
        make_observation(
            record_id="r3",
            field_path="links.github",
            value="https://github.com/alexchen",
        ),
    ]

    clusters = resolve_candidate_clusters(observations)

    assert len(clusters) == 1
    assert clusters[0].record_ids == ("r1", "r2", "r3")
    assert clusters[0].identity_keys == (
        "email:alex@example.com",
        "github:https://github.com/alexchen",
    )


def test_phone_bridge_with_incompatible_name_is_prevented():
    observations = [
        make_observation(
            record_id="r1",
            field_path="full_name",
            value="Alex Chen",
        ),
        make_observation(
            record_id="r1",
            field_path="phones",
            value="+919876543210",
        ),
        make_observation(
            record_id="r2",
            field_path="full_name",
            value="Blair Wu",
        ),
        make_observation(
            record_id="r2",
            field_path="phones",
            value="+919876543210",
        ),
        make_observation(
            record_id="r2",
            field_path="emails",
            value="blair@example.com",
        ),
        make_observation(
            record_id="r3",
            field_path="emails",
            value="blair@example.com",
        ),
    ]

    clusters = resolve_candidate_clusters(observations)

    record_groups = {cluster.record_ids for cluster in clusters}

    assert record_groups == {
        ("r1",),
        ("r2", "r3"),
    }

def test_large_shared_phone_group_does_not_name_merge():
    observations = []

    for index in range(4):
        record_id = f"r{index}"

        observations.append(
            make_observation(
                record_id=record_id,
                field_path="full_name",
                value="Alex Chen",
            )
        )
        observations.append(
            make_observation(
                record_id=record_id,
                field_path="phones",
                value="+919876543210",
            )
        )

    clusters = resolve_candidate_clusters(observations)

    assert len(clusters) == 4


def test_cluster_id_is_deterministic():
    observations = [
        make_observation(
            record_id="r2",
            field_path="emails",
            value="alex@example.com",
        ),
        make_observation(
            record_id="r1",
            field_path="emails",
            value="alex@example.com",
        ),
    ]

    first = resolve_candidate_clusters(observations)
    second = resolve_candidate_clusters(reversed(observations))

    assert first[0].cluster_id == second[0].cluster_id


def test_shared_email_does_not_merge_contradictory_candidate_refs():
    observations = [
        make_observation(
            record_id="r1",
            field_path="candidate_ref",
            value="C001",
        ),
        make_observation(
            record_id="r1",
            field_path="emails",
            value="shared@example.com",
        ),
        make_observation(
            record_id="r2",
            field_path="candidate_ref",
            value="C002",
        ),
        make_observation(
            record_id="r2",
            field_path="emails",
            value="shared@example.com",
        ),
    ]
    warnings: list[str] = []

    clusters = resolve_candidate_clusters(observations, warnings=warnings)

    assert {cluster.record_ids for cluster in clusters} == {("r1",), ("r2",)}
    assert len(warnings) == 1
    assert "contradictory candidate_ref" in warnings[0]


def test_shared_github_does_not_merge_contradictory_candidate_refs():
    observations = [
        make_observation(
            record_id="r1",
            field_path="candidate_ref",
            value="C001",
        ),
        make_observation(
            record_id="r1",
            field_path="links.github",
            value="https://github.com/shared",
        ),
        make_observation(
            record_id="r2",
            field_path="candidate_ref",
            value="C002",
        ),
        make_observation(
            record_id="r2",
            field_path="links.github",
            value="https://github.com/shared",
        ),
    ]

    clusters = resolve_candidate_clusters(observations)

    assert {cluster.record_ids for cluster in clusters} == {("r1",), ("r2",)}


def test_missing_candidate_ref_is_neutral_for_shared_email_merge():
    observations = [
        make_observation(
            record_id="r1",
            field_path="candidate_ref",
            value="C001",
        ),
        make_observation(
            record_id="r1",
            field_path="emails",
            value="alex@example.com",
        ),
        make_observation(
            record_id="r2",
            field_path="emails",
            value="alex@example.com",
        ),
    ]

    clusters = resolve_candidate_clusters(observations)

    assert len(clusters) == 1
    assert clusters[0].record_ids == ("r1", "r2")


def test_transitive_bridge_cannot_join_contradictory_candidate_refs():
    observations = [
        make_observation(
            record_id="r1",
            field_path="candidate_ref",
            value="C001",
        ),
        make_observation(
            record_id="r1",
            field_path="emails",
            value="bridge@example.com",
        ),
        make_observation(
            record_id="r2",
            field_path="emails",
            value="bridge@example.com",
        ),
        make_observation(
            record_id="r2",
            field_path="links.github",
            value="https://github.com/bridge",
        ),
        make_observation(
            record_id="r3",
            field_path="candidate_ref",
            value="C002",
        ),
        make_observation(
            record_id="r3",
            field_path="links.github",
            value="https://github.com/bridge",
        ),
    ]

    clusters = resolve_candidate_clusters(observations)

    assert len(clusters) == 2
    assert not any(
        {"candidate_ref:C001", "candidate_ref:C002"}.issubset(
            cluster.identity_keys
        )
        for cluster in clusters
    )


def test_reference_free_records_remain_ambiguous_between_conflicting_refs():
    observations = [
        make_observation(
            record_id="r1",
            field_path="candidate_ref",
            value="C001",
        ),
        make_observation(
            record_id="r1",
            field_path="emails",
            value="shared@example.com",
        ),
        make_observation(
            record_id="r2",
            field_path="candidate_ref",
            value="C002",
        ),
        make_observation(
            record_id="r2",
            field_path="emails",
            value="shared@example.com",
        ),
        make_observation(
            record_id="r3",
            field_path="emails",
            value="shared@example.com",
        ),
        make_observation(
            record_id="r4",
            field_path="emails",
            value="shared@example.com",
        ),
    ]
    first_warnings: list[str] = []
    second_warnings: list[str] = []

    first = resolve_candidate_clusters(observations, warnings=first_warnings)
    second = resolve_candidate_clusters(
        reversed(observations),
        warnings=second_warnings,
    )

    expected_groups = {("r1",), ("r2",), ("r3", "r4")}
    assert {cluster.record_ids for cluster in first} == expected_groups
    assert {cluster.record_ids for cluster in second} == expected_groups
    assert first_warnings == second_warnings
    assert len(first_warnings) == 1
    assert "contradictory candidate_ref" in first_warnings[0]
    assert "reference-free" in first_warnings[0]


def test_large_shared_email_uses_linear_representative_unions(monkeypatch):
    record_count = 2_000
    observations = [
        make_observation(
            record_id=f"r{index:04d}",
            field_path="emails",
            value="shared@example.com",
        )
        for index in range(record_count)
    ]
    union_count = 0
    original_union = UnionFind.union

    def counting_union(self, left, right):
        nonlocal union_count
        union_count += 1
        return original_union(self, left, right)

    monkeypatch.setattr(UnionFind, "union", counting_union)

    clusters = resolve_candidate_clusters(observations)

    assert len(clusters) == 1
    assert len(clusters[0].record_ids) == record_count
    assert union_count == record_count - 1


def test_oversized_shared_phone_bucket_skips_union_attempts(monkeypatch):
    record_count = 1_000
    observations: list[Observation] = []
    for index in range(record_count):
        record_id = f"r{index:04d}"
        observations.extend(
            [
                make_observation(
                    record_id=record_id,
                    field_path="full_name",
                    value="Alex Chen",
                ),
                make_observation(
                    record_id=record_id,
                    field_path="phones",
                    value="+919876543210",
                ),
            ]
        )

    union_count = 0
    original_union = UnionFind.union

    def counting_union(self, left, right):
        nonlocal union_count
        union_count += 1
        return original_union(self, left, right)

    monkeypatch.setattr(UnionFind, "union", counting_union)

    clusters = resolve_candidate_clusters(observations)

    assert len(clusters) == record_count
    assert union_count == 0
