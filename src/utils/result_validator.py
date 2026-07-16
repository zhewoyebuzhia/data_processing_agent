"""
结果验证工具
负责：判断执行结果是否满意，验证输出文件内容
"""
import re
import json
from pathlib import Path
from typing import List, Tuple, Optional


class ResultValidator:
    """执行结果验证工具"""
    
    def __init__(self, project_root: Optional[Path] = None):
        """
        初始化结果验证器
        
        Args:
            project_root: 项目根目录，用于验证文件路径
        """
        if project_root is None:
            # 自动检测项目根目录
            self.project_root = Path(__file__).resolve().parent.parent.parent
        else:
            self.project_root = project_root
    
    def check_output_satisfied(self, output: str, new_files: List[str], code: str) -> Tuple[bool, str]:
        """
        基于规则判断执行结果是否满意
        
        Args:
            output: 代码执行输出
            new_files: 新生成的文件列表
            code: 执行的代码
            
        Returns:
            (是否满意, 理由)
        """
        reasons = []
        issues = []
        
        # 1. 检查是否是数据处理任务
        is_processing = self._is_data_processing_task(code)
        
        # 2. 检查是否有新文件生成（数据处理任务必须有输出文件）
        if is_processing:
            if new_files:
                reasons.append(f"✅ 生成了 {len(new_files)} 个新文件")
                # 2.1 进一步验证文件内容
                valid_files, invalid_files = self._validate_new_files(new_files)
                if invalid_files:
                    issues.append(f"以下文件为空或格式无效: {invalid_files}")
                if valid_files:
                    reasons.append(f"✅ {len(valid_files)} 个文件有效")
            else:
                return False, "未生成任何新文件，数据处理任务需要输出结果文件"
        else:
            # 非处理任务，有文件生成也可以
            if new_files:
                reasons.append(f"✅ 生成了 {len(new_files)} 个新文件")
        
        # 3. 检查输出是否包含成功标记
        success_markers = ["成功", "完成", "✅", "success", "completed", "finished", "saved", "保存"]
        has_success = any(marker in output.lower() for marker in success_markers)
        if has_success:
            reasons.append("✅ 输出包含成功标记")
        else:
            # 如果生成了文件但没有成功标记，也算可以接受
            if new_files:
                reasons.append("ℹ️ 虽无成功标记，但生成了文件")
        
        # 4. 检查输出是否有数据统计信息
        stat_markers = ["条", "行", "记录", "平均", "最大", "最小", "count", "avg", "max", "min", "总计", "total", "共"]
        has_stats = any(marker in output.lower() for marker in stat_markers)
        if has_stats:
            reasons.append("✅ 输出包含统计信息")
        else:
            if is_processing:
                issues.append("输出缺少统计信息（如记录数、行数等）")
        
        # 5. 检查输出是否包含错误或警告
        error_markers = ["error", "exception", "traceback", "失败", "异常"]
        has_errors = any(marker in output.lower() for marker in error_markers)
        if has_errors:
            issues.append("输出中包含错误或异常信息")
        
        # 6. 🔥 新增：检查代码中是否包含写入操作（从执行结果角度）
        if is_processing:
            has_write_in_code = self._has_write_operation(code)
            if not has_write_in_code:
                issues.append("代码中未检测到写入操作（如 open().write、json.dump）")
        
        # 7. 🔥 新增：检查文件大小是否合理（对于数据处理任务）
        if is_processing and new_files:
            large_enough, size_msg = self._check_file_sizes(new_files)
            if large_enough:
                reasons.append(f"✅ {size_msg}")
            else:
                issues.append(size_msg)
        
        # 判断是否满意
        # 对于非处理任务，有成功标记或生成了文件就算满意
        if not is_processing:
            if has_success or new_files:
                return True, "非处理任务执行成功"
            else:
                return True, "非处理任务已执行"
        
        # 对于处理任务，必须满足：
        # 1. 有新文件生成
        # 2. 没有严重错误
        # 3. 有统计信息 或 文件内容有效
        if is_processing:
            # 必须有文件生成
            if not new_files:
                return False, "未生成任何新文件"
            
            # 如果有严重错误，不满意
            if has_errors:
                return False, f"输出包含错误: {output[:200]}"
            
            # 检查是否有有效文件（不为空且格式正确）
            valid_files, invalid_files = self._validate_new_files(new_files)
            if invalid_files and not valid_files:
                return False, f"生成的文件都为空或格式无效: {invalid_files}"
            
            # 如果有有效文件，即使没有统计信息也认为满意
            if valid_files:
                return True, f"✅ 生成了 {len(new_files)} 个新文件，其中 {len(valid_files)} 个有效"
            
            # 如果有统计信息，满意
            if has_stats:
                return True, f"✅ 生成了 {len(new_files)} 个新文件，且输出包含统计信息"
            
            # 有文件生成但没有统计信息，给出警告但算满意
            if new_files:
                return True, f"✅ 生成了 {len(new_files)} 个新文件（但缺少统计信息，建议补充）"
            
            return False, f"未能满足满意条件。新文件: {new_files}, 统计信息: {has_stats}"
        
        # 默认满意
        return True, "执行完成"
    
    def _validate_new_files(self, new_files: List[str]) -> Tuple[List[str], List[str]]:
        """
        验证新生成的文件是否有效
        
        Args:
            new_files: 新生成的文件列表（相对路径）
            
        Returns:
            (有效文件列表, 无效文件列表)
        """
        valid = []
        invalid = []
        
        for file_path_str in new_files:
            file_path = self.project_root / file_path_str
            
            if not file_path.exists():
                invalid.append(f"{file_path_str} (不存在)")
                continue
            
            if file_path.is_dir():
                # 如果是目录，检查是否有文件
                if any(file_path.rglob('*')):
                    valid.append(file_path_str)
                else:
                    invalid.append(f"{file_path_str} (空目录)")
                continue
            
            # 检查文件大小
            size = file_path.stat().st_size
            if size == 0:
                invalid.append(f"{file_path_str} (文件为空，大小0字节)")
                continue
            
            # 根据文件类型验证内容
            if file_path_str.endswith(('.jsonl', '.json')):
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read(1024)  # 只读前1KB验证格式
                        if file_path_str.endswith('.jsonl'):
                            # 验证 JSONL：至少有一行有效的 JSON
                            lines = content.split('\n')
                            has_valid_json = False
                            for line in lines:
                                if line.strip():
                                    try:
                                        json.loads(line)
                                        has_valid_json = True
                                        break
                                    except json.JSONDecodeError:
                                        pass
                            if not has_valid_json:
                                invalid.append(f"{file_path_str} (JSONL 格式无效)")
                                continue
                        else:
                            # 验证 JSON
                            try:
                                json.loads(content)
                            except json.JSONDecodeError:
                                invalid.append(f"{file_path_str} (JSON 格式无效)")
                                continue
                    valid.append(file_path_str)
                except Exception as e:
                    invalid.append(f"{file_path_str} (读取失败: {str(e)[:50]})")
            else:
                # 其他文件类型，只要有内容就算有效
                if size > 0:
                    valid.append(file_path_str)
                else:
                    invalid.append(f"{file_path_str} (文件为空)")
        
        return valid, invalid
    
    def _check_file_sizes(self, new_files: List[str]) -> Tuple[bool, str]:
        """
        检查新生成的文件大小是否合理
        
        Args:
            new_files: 新生成的文件列表
            
        Returns:
            (是否足够大, 信息)
        """
        if not new_files:
            return False, "没有文件可检查"
        
        total_size = 0
        file_info = []
        
        for file_path_str in new_files:
            file_path = self.project_root / file_path_str
            if file_path.exists() and file_path.is_file():
                size = file_path.stat().st_size
                total_size += size
                file_info.append(f"{file_path.name}: {size} 字节")
        
        if total_size == 0:
            return False, "所有文件大小均为 0 字节"
        
        # 如果总大小超过 100 字节，认为合理
        if total_size > 100:
            return True, f"总大小 {total_size} 字节，合理"
        else:
            return False, f"文件总大小仅 {total_size} 字节，可能内容过少"
    
    def _has_write_operation(self, code: str) -> bool:
        """
        检查代码中是否包含写入操作
        
        Args:
            code: Python代码字符串
            
        Returns:
            是否包含写入操作
        """
        write_patterns = [
            r'\.write\s*\(',
            r'json\.dump\s*\(',
            r'to_json\s*\(',
            r'\.save\s*\(',
            r'w\+?\'\s*[,)]',
            r'wb\'?\s*[,)]',
            r'dump\s*\([^,]+,\s*open\s*\(',
        ]
        for pattern in write_patterns:
            if re.search(pattern, code, re.IGNORECASE):
                return True
        return False
    
    def _is_data_processing_task(self, text: str) -> bool:
        """
        判断是否是数据处理任务（需要创建工具）
        
        Args:
            text: 代码或用户输入文本
            
        Returns:
            是否是数据处理任务
        """
        keywords = [
            "清洗", "聚合", "分析", "创建工具", "处理", "转换",
            "clean", "aggregate", "analyze", "process", "transform",
            "jsonl", "json", "传感器", "sensor", "可穿戴", "wearable"
        ]
        return any(kw in text.lower() for kw in keywords)