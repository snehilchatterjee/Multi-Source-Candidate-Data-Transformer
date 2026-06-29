from candidate_transformer.core.entity_resolution import (
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


def test_same_phone_merges_records_even_with_different_emails():
    observations = [
        make_observation(
            record_id="r1",
            field_path="emails",
            value="alex.personal@example.com",
        ),
        make_observation(
            record_id="r1",
            field_path="phones",
            value="+14155551212",
        ),
        make_observation(
            record_id="r2",
            field_path="emails",
            value="alex.work@example.com",
        ),
        make_observation(
            record_id="r2",
            field_path="phones",
            value="+14155551212",
        ),
    ]

    clusters = resolve_candidate_clusters(observations)

    assert len(clusters) == 1
    assert clusters[0].record_ids == ("r1", "r2")
    assert "phone:+14155551212" in clusters[0].identity_keys


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


def test_chain_merge():
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
            field_path="phones",
            value="+14155551212",
        ),
        make_observation(
            record_id="r3",
            field_path="phones",
            value="+14155551212",
        ),
    ]

    clusters = resolve_candidate_clusters(observations)

    assert len(clusters) == 1
    assert clusters[0].record_ids == ("r1", "r2", "r3")
    assert clusters[0].identity_keys == (
        "email:alex@example.com",
        "phone:+14155551212",
    )


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