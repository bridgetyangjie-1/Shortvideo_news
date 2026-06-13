import json
import unittest
from tempfile import TemporaryDirectory
from pathlib import Path

from utils.config_validator import validate_config, validate_all_configs


class ConfigValidationTest(unittest.TestCase):
    def test_valid_config_passes(self) -> None:
        data = {
            "config": {
                "model": "deepseek-chat",
                "temperature": 0.3,
                "max_completion_tokens": 8000,
                "top_p": 0.95,
                "thinking": "disabled",
            },
            "tools": [],
            "sp": "你是一个助手。",
            "up": "今天是 {{date}}，请分析：\n{{rankings}}",
        }
        valid, errors = validate_config(data)
        self.assertTrue(valid)
        self.assertEqual([e for e in errors if not e.startswith("WARN:")], [])

    def test_missing_model_fails(self) -> None:
        data = {
            "config": {"temperature": 0.3},
            "sp": "你是一个助手。",
            "up": "分析：{{rankings}}",
        }
        valid, errors = validate_config(data)
        self.assertFalse(valid)
        self.assertTrue(any("model" in e.lower() for e in errors))

    def test_invalid_temperature_fails(self) -> None:
        data = {
            "config": {"model": "x", "temperature": 3.0},
            "sp": "你是一个助手。",
            "up": "分析：{{rankings}}",
        }
        valid, errors = validate_config(data)
        self.assertFalse(valid)
        self.assertTrue(any("temperature" in e.lower() for e in errors))

    def test_invalid_jinja2_fails(self) -> None:
        data = {
            "config": {"model": "x", "temperature": 0.5},
            "sp": "你是一个助手。",
            "up": "分析：{{rankings",  # 不完整的 Jinja2 表达式
        }
        valid, errors = validate_config(data)
        self.assertFalse(valid)
        self.assertTrue(any("jinja2" in e.lower() or "模板" in e for e in errors))

    def test_validate_all_configs_detects_bad_file(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            config_dir = root / "config"
            config_dir.mkdir()

            good = {
                "config": {"model": "x", "temperature": 0.5},
                "sp": "s",
                "up": "u {{a}}",
            }
            bad = {
                "config": {"model": "", "temperature": -1},
                "sp": "s",
                "up": "u",
            }
            (config_dir / "good_llm_cfg.json").write_text(
                json.dumps(good, ensure_ascii=False), encoding="utf-8"
            )
            (config_dir / "bad_llm_cfg.json").write_text(
                json.dumps(bad, ensure_ascii=False), encoding="utf-8"
            )

            all_valid, results = validate_all_configs(str(root))
            self.assertFalse(all_valid)
            self.assertIn("bad_llm_cfg.json", results)
            self.assertNotIn("good_llm_cfg.json", results)


if __name__ == "__main__":
    unittest.main()
