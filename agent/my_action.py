import sys
from pathlib import Path
from maa.agent.agent_server import AgentServer
from maa.custom_action import CustomAction
from maa.context import Context
import json
from PIL import Image

_offset_state_map = {}

# 植物计数状态：{ "植物名称": { "level": int, "counts": {1: int, 2: int, 3: int, 4: int} } }
_plant_states = {}

SCREENSHOT_DIR = Path("./screenshots")


def _get_plant_state(name: str) -> dict:
    """获取或初始化指定植物的计数状态"""
    if name not in _plant_states:
        _plant_states[name] = {
            "level": 1,
            "counts": {1: 0, 2: 0, 3: 0, 4: 0},
        }
    return _plant_states[name]


@AgentServer.custom_action("CleanupMaafwBakLogs")
class CleanupMaafwBakLogs(CustomAction):
    def run(self, context: Context, argv: CustomAction.RunArg) -> CustomAction.RunResult:
        try:
            keep_count = 3
            if argv.custom_action_param:
                param_dict = json.loads(argv.custom_action_param)
                count_value = param_dict.get("save_log_count", "")
                if count_value and str(count_value).isdigit():
                    keep_count = int(count_value)
            cleanup_maafw_bak_logs(context, keep_count=keep_count)
            return CustomAction.RunResult(success=True)
        except Exception as e:
            print(f"日志清理执行异常: {e}")
            return CustomAction.RunResult(success=False)


def cleanup_maafw_bak_logs(context=None, keep_count: int = 3):
    root = Path(__file__).parent.parent
    try:
        debug_folder = root / "debug"
        if not debug_folder.exists():
            print("[日志清理] debug文件夹不存在")
            return
        log_files = list(debug_folder.glob("maafw.bak.*.log"))
        if not log_files:
            print("[日志清理] 无符合格式的日志")
            return
        log_files.sort(reverse=True)
        to_delete = log_files[keep_count:]
        for f in to_delete:
            f.unlink()
        print(f"[日志清理] 完成!保留最新 {keep_count} 个日志")
    except Exception as e:
        print(f"[日志清理] 异常:{e}")


def get_node_name_from_argv(argv):
    candidates = ['node', 'node_name', 'name', 'task_node', 'current_node', 'recognition_name']
    for attr in candidates:
        if hasattr(argv, attr):
            val = getattr(argv, attr)
            if val is not None and isinstance(val, str):
                return val
    attrs = [a for a in dir(argv) if not a.startswith('_')]
    print(f"[DEBUG] argv 属性: {attrs}")
    return None


@AgentServer.custom_action("OffsetClick_y")
class OffsetClick(CustomAction):
    """原版：每次点击 x 增加 dx，每 max_hits 次后重置，重置时 y 减去 n，x 回到初始值+dx"""
    def run(self, context: Context, argv: CustomAction.RunArg) -> CustomAction.RunResult:
        try:
            node_name = get_node_name_from_argv(argv)
            if node_name is None:
                print("[OffsetClick] 警告：无法获取节点名称，使用固定键'DefaultNode'，状态可能串扰")
                node_name = "DefaultNode"
            
            key = f"OffsetState_{node_name}"
            state = _offset_state_map.get(key)

            param = {}
            if argv.custom_action_param:
                try:
                    param = json.loads(argv.custom_action_param)
                except:
                    pass

            initial_x = param.get("initial_x")
            initial_y = param.get("initial_y")
            if initial_x is None or initial_y is None:
                print(f"[OffsetClick][{node_name}] 缺少 initial_x 或 initial_y")
                return CustomAction.RunResult(success=False)

            dx = param.get("dx", 50)
            max_hits = param.get("max_hits", 3)
            n = param.get("n", 100)

            if state is None:
                state = {
                    "current_x": initial_x,
                    "base_y_offset": 0,
                    "hit_count": 0,
                    "initial_x": initial_x,
                    "initial_y": initial_y
                }
                _offset_state_map[key] = state
                print(f"[OffsetClick][{node_name}] 初始化: x={initial_x}, y基={initial_y}, dx={dx}, max_hits={max_hits}, n={n}")

            current_y = state["initial_y"] + state["base_y_offset"]
            will_reset = (state["hit_count"] + 1) >= max_hits

            if will_reset:
                new_offset = state["base_y_offset"] - n
                click_y = state["initial_y"] + new_offset
                click_x = state["initial_x"]
                print(f"[OffsetClick][{node_name}] 重置点击 ({click_x}, {click_y}) (第{state['hit_count']+1}次)")
            else:
                click_x = state["current_x"]
                click_y = current_y
                print(f"[OffsetClick][{node_name}] 正常点击 ({click_x}, {click_y}) (第{state['hit_count']+1}次)")

            context.tasker.controller.post_click(click_x, click_y, contact=0)

            if will_reset:
                state["current_x"] = state["initial_x"] + dx
                state["base_y_offset"] -= n
                state["hit_count"] = 0
                print(f"[OffsetClick][{node_name}] 重置后: y偏移={state['base_y_offset']}, x起点={state['current_x']}")
            else:
                state["current_x"] += dx
                state["hit_count"] += 1

            return CustomAction.RunResult(success=True)
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"OffsetClick 异常: {e}")
            return CustomAction.RunResult(success=False)


@AgentServer.custom_action("OffsetClick_x")
class OffsetClickSwapped(CustomAction):
    """
    交换版：每次点击 y 增加 dy，每 max_hits 次后重置，重置时 x 减去 n，y 回到初始值
    参数：
        initial_x, initial_y: 初始坐标（必需）
        dy: 每次点击 y 的增加量（默认 50）
        max_hits: 触发重置的点击次数（默认 3）
        n: 重置时 x 的减少量（默认 100）
    """
    def run(self, context: Context, argv: CustomAction.RunArg) -> CustomAction.RunResult:
        node_name = get_node_name_from_argv(argv)
        if node_name is None:
            print("[OffsetClick_x] 警告：无法获取节点名称，使用固定键'DefaultNode'，状态可能串扰")
            node_name = "DefaultNode"
        
        key = f"OffsetSwapped_{node_name}"
        state = _offset_state_map.get(key)

        param = {}
        if argv.custom_action_param:
            param = json.loads(argv.custom_action_param)

        initial_x = param.get("initial_x")
        initial_y = param.get("initial_y")
        if initial_x is None or initial_y is None:
            print(f"[OffsetClick_x][{node_name}] 缺少 initial_x 或 initial_y")
            return CustomAction.RunResult(success=False)

        dy = param.get("dy", 50)
        max_hits = param.get("max_hits", 3)
        n = param.get("n", 100)

        if state is None:
            state = {
                "current_y": initial_y,
                "base_x_offset": 0,
                "hit_count": 0,
                "initial_x": initial_x,
                "initial_y": initial_y
            }
            _offset_state_map[key] = state
            print(f"[OffsetClick_x][{node_name}] 初始化: x基={initial_x}, y基={initial_y}, dy={dy}, max_hits={max_hits}, n={n}")

        current_x = state["initial_x"] + state["base_x_offset"]
        will_reset = (state["hit_count"] + 1) >= max_hits

        if will_reset:
            new_x_offset = state["base_x_offset"] - n
            click_x = state["initial_x"] + new_x_offset
            click_y = state["initial_y"]
            print(f"[OffsetClick_x][{node_name}] 重置点击 ({click_x}, {click_y}) (第{state['hit_count']+1}次)")
        else:
            click_x = current_x
            click_y = state["current_y"]
            print(f"[OffsetClick_x][{node_name}] 正常点击 ({click_x}, {click_y}) (第{state['hit_count']+1}次)")

        context.tasker.controller.post_click(click_x, click_y, contact=0)

        if will_reset:
            state["current_y"] = state["initial_y"]
            state["base_x_offset"] -= n
            state["hit_count"] = 0
            print(f"[OffsetClick_x][{node_name}] 重置后: x偏移={state['base_x_offset']}, y起点={state['current_y']}")
        else:
            state["current_y"] += dy
            state["hit_count"] += 1

        return CustomAction.RunResult(success=True)

    
@AgentServer.custom_action("ResetOffset")
class ResetOffset(CustomAction):
    """
    重置指定节点的偏移状态（使其下次点击时从初始值重新开始）
    参数（custom_action_param）可选：
    {
        "node_name": "节点名"   // 如果不提供，则使用当前执行此动作的节点名
    }
    """
    def run(self, context: Context, argv: CustomAction.RunArg) -> CustomAction.RunResult:
        param = {}
        if argv.custom_action_param:
            param = json.loads(argv.custom_action_param)
        
        target_node = param.get("node_name")
        if target_node is None:
            target_node = get_node_name_from_argv(argv)
        
        if target_node is None:
            print("[ResetOffset] 错误：无法确定要重置的节点名")
            return CustomAction.RunResult(success=False)
        
        key_y = f"OffsetState_{target_node}"
        key_x = f"OffsetSwapped_{target_node}"
        
        removed_y = _offset_state_map.pop(key_y, None) is not None
        removed_x = _offset_state_map.pop(key_x, None) is not None
        
        if removed_y or removed_x:
            print(f"[ResetOffset] 已重置节点 '{target_node}' 的状态")
        else:
            print(f"[ResetOffset] 节点 '{target_node}' 没有偏移状态记录，无需重置")
        
        return CustomAction.RunResult(success=True)


@AgentServer.custom_action("ResetAllOffsets")
class ResetAllOffsets(CustomAction):
    """
    重置所有节点的偏移状态（清空整个状态字典）
    不需要任何参数
    """
    def run(self, context: Context, argv: CustomAction.RunArg) -> CustomAction.RunResult:
        global _offset_state_map
        count = len(_offset_state_map)
        _offset_state_map.clear()
        print(f"[ResetAllOffsets] 已清空所有偏移状态，共 {count} 条记录")
        return CustomAction.RunResult(success=True)


@AgentServer.custom_action("ClickAndCount")
class ClickAndCount(CustomAction):
    """
    识别模板并点击，同时对指定植物的当前阶数点击次数+1。
    参数：
        template: 模板图片路径（必需）
        name: 植物名称，用于区分不同植物（必需）
        level: （可选）指定点击对应的阶数，默认为状态中记录的当前阶数
    """
    def run(self, context: Context, argv: CustomAction.RunArg) -> CustomAction.RunResult:
        param = {}
        if argv.custom_action_param:
            try:
                param = json.loads(argv.custom_action_param)
            except Exception as e:
                print(f"[ClickAndCount] 参数解析失败: {e}")
                return CustomAction.RunResult(success=False)

        template = param.get("template", "")
        plant_name = param.get("name", "")
        specified_level = param.get("level", None)

        if not template or not plant_name:
            print("[ClickAndCount] 缺少 template 或 name 参数")
            return CustomAction.RunResult(success=False)

        state = _get_plant_state(plant_name)
        level = specified_level if specified_level is not None else state["level"]

        if level not in (1, 2, 3, 4):
            print(f"[ClickAndCount] 无效的阶数 {level}，仅支持 1~4")
            return CustomAction.RunResult(success=False)

        reco = context.run_recognition(
            "click_and_count_recog",
            context.tasker.controller.cached_image,
            {
                "click_and_count_recog": {
                    "recognition": "TemplateMatch",
                    "param": {"template": template}
                }
            }
        )
        if reco is None or not reco.hit:
            print(f"[ClickAndCount] 未识别到 {plant_name} 的模板")
            return CustomAction.RunResult(success=False)

        box = reco.best_result.box
        x = box[0] + box[2] // 2
        y = box[1] + box[3] // 2

        context.tasker.controller.post_click(x, y).wait()

        state["counts"][level] += 1
        if specified_level is None:
            state["level"] = level

        print(f"[ClickAndCount] 点击 {plant_name} {level}阶，当前该阶次数: {state['counts'][level]}")
        return CustomAction.RunResult(success=True)


@AgentServer.custom_action("TakeCountScreenshot")
class TakeCountScreenshot(CustomAction):
    """
    根据植物的各阶点击次数生成叠加文件名并保存截图。
    文件夹名：植物名称（参数 name）
    文件名：一阶X次_二阶X次_三阶X次_四阶X次.png
    参数：
        name: 植物名称（必需）
    """
    def run(self, context: Context, argv: CustomAction.RunArg) -> CustomAction.RunResult:
        param = {}
        if argv.custom_action_param:
            try:
                param = json.loads(argv.custom_action_param)
            except Exception as e:
                print(f"[TakeCountScreenshot] 参数解析失败: {e}")
                return CustomAction.RunResult(success=False)

        plant_name = param.get("name", "")
        if not plant_name:
            print("[TakeCountScreenshot] 缺少 name 参数")
            return CustomAction.RunResult(success=False)

        state = _get_plant_state(plant_name)
        counts = state["counts"]
        total = sum(counts.values())
        if total == 0:
            print(f"[TakeCountScreenshot] {plant_name} 尚未点击过，不保存截图")
            return CustomAction.RunResult(success=True)

        # 文件夹名直接使用植物名称
        folder_path = SCREENSHOT_DIR / plant_name
        folder_path.mkdir(parents=True, exist_ok=True)

        filename = (
            f"一阶{counts[1]}次_"
            f"二阶{counts[2]}次_"
            f"三阶{counts[3]}次_"
            f"四阶{counts[4]}次.png"
        )
        filepath = folder_path / filename

        image = context.tasker.controller.cached_image
        if image is None:
            print("[TakeCountScreenshot] 截图失败：cached_image 为空")
            return CustomAction.RunResult(success=False)

        Image.fromarray(image).save(str(filepath))
        print(f"[TakeCountScreenshot] 截图已保存: {filepath}")
        return CustomAction.RunResult(success=True)


@AgentServer.custom_action("ResetPlantCount")
class ResetPlantCount(CustomAction):
    """
    重置所有点击计数状态，清空所有记录。
    不需要任何参数。
    """
    def run(self, context: Context, argv: CustomAction.RunArg) -> CustomAction.RunResult:
        count = len(_plant_states)
        _plant_states.clear()
        print(f"[ResetPlantCount] 已清空所有植物计数器，共 {count} 条记录")
        return CustomAction.RunResult(success=True)