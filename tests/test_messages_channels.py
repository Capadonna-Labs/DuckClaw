"""Messages: channels are visible to and writable by their members only; a DM has exactly two people."""

import json

import duckdb
import pytest

from duckclaw.schema_migrations import _M043_MESSAGES
from duckclaw.write_commands import CreateChannelCommand, PostChannelMessageCommand
from duckclaw.write_handlers.messages import _apply_create_channel, _apply_post_channel_message


@pytest.fixture()
def conn():
    c = duckdb.connect()
    for ddl in _M043_MESSAGES:
        c.execute(ddl)
    return c


def _payload(cmd):
    return json.loads(cmd.model_dump_json())


def test_group_members_post_and_outsider_is_refused(conn):
    cmd = CreateChannelCommand(actor_email="Ana@x.com", name="Equipo", members=["bo@x.com"])
    _apply_create_channel(conn, _payload(cmd))
    members = json.loads(conn.execute("SELECT members_json FROM main.admin_channels").fetchone()[0])
    assert members == ["ana@x.com", "bo@x.com"]   # creator always included, emails lowercased
    _apply_post_channel_message(conn, _payload(PostChannelMessageCommand(actor_email="bo@x.com", channel_id=cmd.channel_id, body="hola",
                                                                        author_label="Claude (Bo)")))
    assert conn.execute("SELECT author_label, body FROM main.admin_channel_messages").fetchone() == ("Claude (Bo)", "hola")
    with pytest.raises(ValueError):
        _apply_post_channel_message(conn, _payload(PostChannelMessageCommand(actor_email="eve@x.com", channel_id=cmd.channel_id, body="x")))


def test_dm_needs_exactly_two(conn):
    with pytest.raises(ValueError):
        _apply_create_channel(conn, _payload(CreateChannelCommand(actor_email="ana@x.com", kind="dm", members=["bo@x.com", "cy@x.com"])))


def test_bad_email_rejected():
    with pytest.raises(ValueError):
        CreateChannelCommand(actor_email="ana@x.com", members=["not-an-email"])


def _contacts_conn():
    from duckclaw.schema_migrations import _M044_CONTACTS

    c = duckdb.connect()
    for ddl in _M043_MESSAGES + _M044_CONTACTS:
        c.execute(ddl)
    c.execute("CREATE TABLE main.admin_console_users (email VARCHAR, nombre VARCHAR)")
    c.execute("INSERT INTO main.admin_console_users VALUES ('juan@x.com', 'Juan')")
    return c


def test_invite_is_single_use_and_cannot_impersonate_a_local_user():
    from duckclaw.write_commands import AcceptContactInviteCommand, CreateContactInviteCommand
    from duckclaw.write_handlers.messages import _apply_accept_contact_invite, _apply_create_contact_invite

    c = _contacts_conn()
    h = "a" * 64
    inv = CreateContactInviteCommand(actor_email="juan@x.com", secret_hash=h, expires_at="2099-01-01 00:00:00")
    _apply_create_contact_invite(c, _payload(inv))
    with pytest.raises(ValueError):   # a contact claiming a local user's email
        _apply_accept_contact_invite(c, _payload(AcceptContactInviteCommand(invite_id=inv.invite_id, secret_hash=h, remote_email="juan@x.com",
                                                                            token_hash="b" * 64)))
    ok = AcceptContactInviteCommand(invite_id=inv.invite_id, secret_hash=h, remote_email="sam@y.com", token_hash="b" * 64)
    _apply_accept_contact_invite(c, _payload(ok))
    assert c.execute("SELECT owner_email, role, remote_email FROM main.admin_contacts").fetchone() == ("juan@x.com", "host", "sam@y.com")
    with pytest.raises(ValueError):   # second use
        _apply_accept_contact_invite(c, _payload(AcceptContactInviteCommand(invite_id=inv.invite_id, secret_hash=h, remote_email="eve@y.com",
                                                                            token_hash="c" * 64)))


def test_expired_invite_refused():
    from duckclaw.write_commands import AcceptContactInviteCommand, CreateContactInviteCommand
    from duckclaw.write_handlers.messages import _apply_accept_contact_invite, _apply_create_contact_invite

    c = _contacts_conn()
    inv = CreateContactInviteCommand(actor_email="juan@x.com", secret_hash="a" * 64, expires_at="2000-01-01 00:00:00")
    _apply_create_contact_invite(c, _payload(inv))
    with pytest.raises(ValueError):
        _apply_accept_contact_invite(c, _payload(AcceptContactInviteCommand(invite_id=inv.invite_id, secret_hash="a" * 64,
                                                                            remote_email="sam@y.com", token_hash="b" * 64)))
