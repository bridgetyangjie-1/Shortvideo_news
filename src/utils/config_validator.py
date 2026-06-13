"""
LLM 配置文件校验器。

用于在启动/测试阶段验证 config/*_llm_cfg.json 的格式、模型参数和 Jinja2 模板语法。
"""
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Tuple

from jinja2 import Environment, meta
from pydantic import BaseModel, Field, field_validator


class LLMConfigModel(BaseModel):
    """config 字段模型"""
    model: str = Field(..., min_length=1, description="模型名称")
    temperature: float = Field(..., ge=0.0, le=2.0, description="采样温度")
    max_completion_tokens: Optional[int] = Field(None, ge=1, description="最大输出 token 数")
    max_tokens: Optional[int] = Field(None, ge=1, description="最大输出 token 数（兼容字段）")
    top_p: Optional[float] = Field(None, ge=0.0, le=1.0, description="核采样概率")
    thinking: Optional[Literal["enabled", "disabled"]] = Field(None, description="思考模式开关")


class LLMConfigFile(BaseModel):
    """单个 *_llm_cfg.json 的完整结构"""
    config: LLMConfigModel = Field(..., description="模型参数")
    tools: List[Any] = Field(default_factory=list, description="工具列表")
    sp: str = Field(..., min_length=1, description="system prompt")
    up: str = Field(..., min_length=1, description="user prompt 模板（Jinja2）")

    @field_validator("up")
    @classmethod
    def _check_jinja2_syntax(cls, v: str) -> str:
        try:
            Environment().parse(v)
        except Exception as exc:
            raise ValueError(f"user prompt 模板 Jinja2 语法错误: {exc}") from exc
        return v


def load_config(path: str) -> Dict[str, Any]:
    """加载单个配置文件。"""
    with open(path, "r", encoding="utf-8") as fd:
        return json.load(fd)


def validate_config(data: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """
    校验单个配置字典。

    Returns:
        (is_valid, error_messages)
    """
    errors: List[str] = []
    try:
        LLMConfigFile(**data)
    except Exception as exc:
        errors.append(str(exc))
        return False, errors

    # 额外检查：up 模板中使用的变量是否常见/合法（仅告警，不失败）
    try:
        env = Environment()
        ast = env.parse(data["up"])
        undeclared = meta.find_undeclared_variables(ast)
        if not undeclared:
            errors.append("WARN: user prompt 模板未使用任何变量")
    except Exception:
        pass

    return len(errors) == 0 or all(e.startswith("WARN:") for e in errors), errors


def validate_all_configs(workspace_path: str = "") -> Tuple[bool, Dict[str, List[str]]]:
    """
    校验 workspace/config/ 目录下所有 *_llm_cfg.json。

    Returns:
        (all_valid, {filename: [errors]})
    """
    workspace = Path(
        workspace_path
        or os.getenv("COZE_WORKSPACE_PATH")
        or Path(__file__).resolve().parents[2]
    )
    config_dir = workspace / "config"

    results: Dict[str, List[str]] = {}
    all_valid = True

    if not config_dir.exists():
        results["config_dir"] = [f"配置目录不存在: {config_dir}"]
        return False, results

    for cfg_file in sorted(config_dir.glob("*_llm_cfg.json")):
        try:
            data = load_config(str(cfg_file))
        except Exception as exc:
            results[cfg_file.name] = [f"JSON 加载失败: {exc}"]
            all_valid = False
            continue

        is_valid, errors = validate_config(data)
        if errors:
            results[cfg_file.name] = errors
        if not is_valid:
            all_valid = False

    return all_valid, results


def main() -> None:
    """命令行入口：打印校验结果。"""
    all_valid, results = validate_all_configs()
    for filename, errors in results.items():
        status = "✅" if not errors else ("⚠️" if all(e.startswith("WARN:") for e in errors) else "❌")
        print(f"{status} {filename}")
        for error in errors:
            print(f"   {error}")
    if not all_valid:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
