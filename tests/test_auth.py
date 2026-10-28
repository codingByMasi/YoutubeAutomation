import json

from studio.youtube import auth


class FakeCreds:
    def __init__(self, valid=True):
        self.valid = valid

    def to_json(self):
        return json.dumps({"token": "t"})


def test_revoked_token_is_deleted_and_flow_rerun(ctx, monkeypatch):
    from google.auth.exceptions import RefreshError
    from google.oauth2.credentials import Credentials

    token = ctx.settings.token_path
    token.write_text("{}")

    class Expired:
        valid, expired, refresh_token = False, True, "r"

        def refresh(self, request):
            raise RefreshError("revoked")

    monkeypatch.setattr(Credentials, "from_authorized_user_file", classmethod(lambda cls, *a, **k: Expired()))
    flows = []

    def flow(settings):
        flows.append(1)
        assert not token.exists()  # deleted before re-auth
        return FakeCreds()

    creds = auth.get_credentials(ctx.settings, run_flow=flow)
    assert flows == [1] and isinstance(creds, FakeCreds) and json.loads(token.read_text()) == {"token": "t"}


def test_first_run_starts_flow_and_caches_token(ctx):
    creds = auth.get_credentials(ctx.settings, run_flow=lambda s: FakeCreds())
    assert creds.valid and ctx.settings.token_path.exists()
