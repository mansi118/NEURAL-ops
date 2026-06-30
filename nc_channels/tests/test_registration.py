"""AS-contract spike tests (offline). The registration the homeserver loads is GENERATED + VALIDATED here
against the Matrix AS-API spec shape — no Synapse needed. The live load + transaction round-trip stay
box-gated (service.serve / _cs_api_call)."""
import pytest

from nc_channels.service import ASRegistration
from nc_channels.registration import (
    registration_dict,
    validate_registration_dict,
    registration_yaml,
    REQUIRED_FIELDS,
)


URL = "https://nc-channels.neuraledge.in/"


def _reg(**kw):
    base = dict(
        id="neos-nc-channels-neuraledge",
        url=URL,
        tenant="neuraledge",
        sender_localpart="neos-bot",
        user_namespace_regex=r"@neop_.*:matrix\.neuraledge\.in",
        as_token="as-secret-token",
        hs_token="hs-secret-token",
    )
    base.update(kw)
    return ASRegistration(**base)


def test_registration_dict_has_all_required_spec_fields():
    d = registration_dict(_reg())
    for k in REQUIRED_FIELDS:
        assert d.get(k) not in (None, ""), f"missing {k}"
    assert d["url"] == "https://nc-channels.neuraledge.in"  # trailing slash stripped
    assert d["id"] == "neos-nc-channels-neuraledge"
    assert d["sender_localpart"] == "neos-bot"


def test_neop_user_namespace_is_exclusive():
    d = registration_dict(_reg())
    users = d["namespaces"]["users"]
    assert users == [{"exclusive": True, "regex": r"@neop_.*:matrix\.neuraledge\.in"}]
    # aliases/rooms present (spec wants the keys) but empty
    assert d["namespaces"]["aliases"] == [] and d["namespaces"]["rooms"] == []


def test_refuses_without_both_tokens():
    with pytest.raises(ValueError, match="as_token.*hs_token|both"):
        registration_dict(_reg(as_token=""))
    with pytest.raises(ValueError):
        registration_dict(_reg(hs_token=""))


def test_refuses_blank_url():
    with pytest.raises(ValueError, match="url"):
        registration_dict(_reg(url="   "))


def test_validate_rejects_non_exclusive_users_namespace():
    d = registration_dict(_reg())
    d["namespaces"]["users"][0]["exclusive"] = False
    with pytest.raises(ValueError, match="exclusive"):
        validate_registration_dict(d)


def test_validate_rejects_missing_field():
    d = registration_dict(_reg())
    del d["sender_localpart"]
    with pytest.raises(ValueError, match="sender_localpart"):
        validate_registration_dict(d)


def test_validate_rejects_tokens_leaked_into_id():
    d = registration_dict(_reg())
    d["id"] = f"id-with-{d['as_token']}"
    with pytest.raises(ValueError, match="as_token must not be embedded"):
        validate_registration_dict(d)


def test_yaml_round_trips_to_the_same_contract():
    pytest.importorskip("yaml")
    import yaml

    reg = _reg()
    text = registration_yaml(reg)
    parsed = yaml.safe_load(text)
    validate_registration_dict(parsed)  # the emitted YAML still satisfies the contract
    assert parsed == registration_dict(reg)
