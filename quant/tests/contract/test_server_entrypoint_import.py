from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


def test_server_entrypoint_can_import_http_app():
    server_path = Path(__file__).resolve().parents[2] / "bin" / "server.py"
    spec = spec_from_file_location("quant_bin_server", server_path)
    assert spec is not None
    assert spec.loader is not None

    module = module_from_spec(spec)
    spec.loader.exec_module(module)

    assert callable(module.create_app)
