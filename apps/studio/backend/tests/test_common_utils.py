from app.common import utils


def test_generate_id_uses_cli_safe_alphanumeric_alphabet(monkeypatch) -> None:
    call: dict[str, object] = {}

    def fake_generate(alphabet: str, size: int) -> str:
        call.update(alphabet=alphabet, size=size)
        return "A" * size

    monkeypatch.setattr(utils, "nanoid_generate", fake_generate)

    assert utils.generate_id(size=22) == "A" * 22
    assert call == {"alphabet": utils.ID_ALPHABET, "size": 22}
    assert utils.ID_ALPHABET.isalnum()
