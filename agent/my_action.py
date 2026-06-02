import sys
from pathlib import Path
from maa.agent.agent_server import AgentServer
from maa.custom_action import CustomAction
from maa.context import Context
import json

_offset_state_map = {}

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
    """尝试从 argv 对象中获取节点名称，如果失败则返回 None"""
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

        # 解析参数
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

        # 当前 x = 初始 x + 累积 x 偏移
        current_x = state["initial_x"] + state["base_x_offset"]
        will_reset = (state["hit_count"] + 1) >= max_hits

        if will_reset:
            # 重置点击：x 用新偏移，y 回到初始 y
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
            # 重置后：y 回到初始 y，累积 x 偏移减 n，计数归零
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
        # 初始化参数字典
        param = {}
        # 如果有自定义动作参数，则解析JSON格式的参数
        if argv.custom_action_param:
            param = json.loads(argv.custom_action_param)
        
        # 确定要重置的节点名称
        target_node = param.get("node_name")
        if target_node is None:
            target_node = get_node_name_from_argv(argv)
        
        if target_node is None:
            print("[ResetOffset] 错误：无法确定要重置的节点名")
            return CustomAction.RunResult(success=False)
        
        # 删除该节点在两种偏移状态中可能存在的记录
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
        # 声明使用全局变量 _offset_state_map
        global _offset_state_map
        # 获取当前状态字典中的记录数量
        count = len(_offset_state_map)
        # 清空整个状态字典
        _offset_state_map.clear()
        # 打印已清空的记录数量信息
        print(f"[ResetAllOffsets] 已清空所有偏移状态，共 {count} 条记录")
        # 返回执行成功的结果
        return CustomAction.RunResult(success=True)
    
