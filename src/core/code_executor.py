"""
代码执行器
负责：安全执行Python代码和Bash命令
"""
import os
import sys
import re
import ast
import subprocess
import tempfile
from pathlib import Path
from typing import List, Tuple, Optional

# 获取项目根目录 - 使用绝对路径解析，确保正确
_project_root = Path(__file__).resolve().parent.parent.parent
project_root = _project_root

from config.settings import TOOLS_DIR


class CodeExecutor:
    """代码执行器 - 安全执行Python和Bash代码"""
    
    def __init__(self):
        """初始化代码执行器"""
        self.project_root = project_root
        self.logger = None
    
    def set_logger(self, logger):
        """设置日志记录器"""
        self.logger = logger
    
    def check_syntax(self, code: str) -> Tuple[bool, str]:
        """
        使用 ast 检查 Python 代码语法
        
        Args:
            code: Python代码字符串
            
        Returns:
            (是否有效, 错误信息)
        """
        try:
            ast.parse(code)
            return True, None
        except SyntaxError as e:
            # 提取错误行号和上下文
            error_msg = f"语法错误 (行 {e.lineno}): {e.msg}\n"
            # 显示错误行附近的代码
            lines = code.split('\n')
            if e.lineno and 1 <= e.lineno <= len(lines):
                error_line = lines[e.lineno - 1]
                error_msg += f"错误行: {error_line}\n"
                # 显示前后各2行
                start = max(0, e.lineno - 3)
                end = min(len(lines), e.lineno + 2)
                error_msg += "附近代码:\n"
                for i in range(start, end):
                    prefix = ">>> " if i == e.lineno - 1 else "    "
                    error_msg += f"{prefix}{i+1}: {lines[i]}\n"
            return False, error_msg
        except Exception as e:
            return False, str(e)
    
    def check_path_safety(self, code: str) -> Tuple[bool, str]:
        """
        检查代码中是否包含危险的路径操作
        
        Args:
            code: 代码字符串
            
        Returns:
            (是否安全, 安全信息)
        """
        absolute_path_patterns = [
            r'["\']C:[/\\]',
            r'["\']D:[/\\]',
            r'["\']/home/',
            r'["\']/Users/',
            r'["\']/root/',
            r'["\']/etc/',
            r'["\']/var/',
            r'["\']/tmp/',
        ]
        
        for pattern in absolute_path_patterns:
            if re.search(pattern, code, re.IGNORECASE):
                return False, f"代码中包含绝对路径模式 '{pattern}'。请使用相对路径（基于项目根目录）。"
        
        if re.search(r'\.\.[/\\]', code):
            return False, "代码中包含 '..' 父目录跳转，禁止访问项目外路径。"
        
        dangerous_functions = [
            (r'os\.chdir\s*\(', 'os.chdir() 切换目录'),
            (r'subprocess\.', 'subprocess 执行外部命令'),
            (r'eval\s*\(', 'eval() 执行任意代码'),
            (r'exec\s*\(', 'exec() 执行任意代码'),
            (r'__import__\s*\(', '__import__() 动态导入'),
            (r'compile\s*\(', 'compile() 编译代码'),
        ]
        
        for pattern, name in dangerous_functions:
            if re.search(pattern, code, re.IGNORECASE):
                return False, f"代码中包含危险函数 '{name}'，已阻止执行。"
        
        return True, "路径安全检查通过"
    
    def has_write_operation(self, code: str) -> Tuple[bool, str]:
        """
        检查代码中是否包含文件写入操作
        
        Args:
            code: Python代码字符串
            
        Returns:
            (是否包含写入操作, 检测到的写入方式)
        """
        write_patterns = [
            (r'\.write\s*\(', 'open().write()'),
            (r'json\.dump\s*\(', 'json.dump()'),
            (r'json\.dumps\s*\(.*,\s*open\s*\(', 'json.dumps() + open()'),
            (r'to_json\s*\(', 'to_json()'),
            (r'save\s*\(', 'save()'),
            (r'w\+?\'\s*[,)]', 'open() with "w" mode'),
            (r'wb\'?\s*[,)]', 'open() with "wb" mode'),
        ]
        
        detected = []
        for pattern, desc in write_patterns:
            if re.search(pattern, code, re.IGNORECASE):
                detected.append(desc)
        
        if detected:
            return True, f"检测到写入操作: {', '.join(detected)}"
        else:
            return False, "未检测到任何文件写入操作（如 open().write、json.dump、to_json、save 等）"
    
    def _fix_path_definitions(self, code: str) -> str:
        """
        修复代码中的路径定义，将 Path(__file__) 替换为 PROJECT_ROOT
        
        核心问题：在临时文件中 __file__ 指向 /tmp/xxx.py，
        导致 Path(__file__).resolve().parent.parent 解析为 /
        这个方法会强制替换所有使用 __file__ 的路径定义为使用 PROJECT_ROOT
        """
        # 1. 替换各种 PROJECT_ROOT 类定义
        patterns = [
            # PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
            (r'(PROJECT_ROOT)\s*=\s*Path\(__file__\)\.resolve\(\)\.parent\.parent\.parent', r'\1 = PROJECT_ROOT'),
            # PROJECT_ROOT = Path(__file__).resolve().parent.parent
            (r'(PROJECT_ROOT)\s*=\s*Path\(__file__\)\.resolve\(\)\.parent\.parent', r'\1 = PROJECT_ROOT'),
            # PROJECT_ROOT = Path(__file__).resolve().parent
            (r'(PROJECT_ROOT)\s*=\s*Path\(__file__\)\.resolve\(\)\.parent', r'\1 = PROJECT_ROOT'),
            # PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            (r'(PROJECT_ROOT)\s*=\s*os\.path\.dirname\(os\.path\.dirname\(os\.path\.abspath\(__file__\)\)\)', r'\1 = PROJECT_ROOT'),
            # PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
            (r'(PROJECT_ROOT)\s*=\s*os\.path\.dirname\(os\.path\.abspath\(__file__\)\)', r'\1 = PROJECT_ROOT'),
            
            # ROOT_DIR 变体
            (r'(ROOT_DIR)\s*=\s*Path\(__file__\)\.resolve\(\)\.parent\.parent\.parent', r'\1 = PROJECT_ROOT'),
            (r'(ROOT_DIR)\s*=\s*Path\(__file__\)\.resolve\(\)\.parent\.parent', r'\1 = PROJECT_ROOT'),
            (r'(ROOT_DIR)\s*=\s*Path\(__file__\)\.resolve\(\)\.parent', r'\1 = PROJECT_ROOT'),
            (r'(ROOT_DIR)\s*=\s*os\.path\.dirname\(os\.path\.dirname\(os\.path\.abspath\(__file__\)\)\)', r'\1 = PROJECT_ROOT'),
            
            # BASE_DIR 变体
            (r'(BASE_DIR)\s*=\s*Path\(__file__\)\.resolve\(\)\.parent\.parent\.parent', r'\1 = PROJECT_ROOT'),
            (r'(BASE_DIR)\s*=\s*Path\(__file__\)\.resolve\(\)\.parent\.parent', r'\1 = PROJECT_ROOT'),
            (r'(BASE_DIR)\s*=\s*Path\(__file__\)\.resolve\(\)\.parent', r'\1 = PROJECT_ROOT'),
            (r'(BASE_DIR)\s*=\s*os\.path\.dirname\(os\.path\.dirname\(os\.path\.abspath\(__file__\)\)\)', r'\1 = PROJECT_ROOT'),
            
            # project_root 变体（小写）
            (r'(project_root)\s*=\s*Path\(__file__\)\.resolve\(\)\.parent\.parent\.parent', r'\1 = PROJECT_ROOT'),
            (r'(project_root)\s*=\s*Path\(__file__\)\.resolve\(\)\.parent\.parent', r'\1 = PROJECT_ROOT'),
            (r'(project_root)\s*=\s*Path\(__file__\)\.resolve\(\)\.parent', r'\1 = PROJECT_ROOT'),
            (r'(project_root)\s*=\s*os\.path\.dirname\(os\.path\.dirname\(os\.path\.abspath\(__file__\)\)\)', r'\1 = PROJECT_ROOT'),
            
            # base_dir 变体（小写）
            (r'(base_dir)\s*=\s*Path\(__file__\)\.resolve\(\)\.parent\.parent\.parent', r'\1 = PROJECT_ROOT'),
            (r'(base_dir)\s*=\s*Path\(__file__\)\.resolve\(\)\.parent\.parent', r'\1 = PROJECT_ROOT'),
            (r'(base_dir)\s*=\s*Path\(__file__\)\.resolve\(\)\.parent', r'\1 = PROJECT_ROOT'),
            
            # root_dir 变体（小写）
            (r'(root_dir)\s*=\s*Path\(__file__\)\.resolve\(\)\.parent\.parent\.parent', r'\1 = PROJECT_ROOT'),
            (r'(root_dir)\s*=\s*Path\(__file__\)\.resolve\(\)\.parent\.parent', r'\1 = PROJECT_ROOT'),
            (r'(root_dir)\s*=\s*Path\(__file__\)\.resolve\(\)\.parent', r'\1 = PROJECT_ROOT'),
        ]
        
        for pattern, replacement in patterns:
            code = re.sub(pattern, replacement, code)
        
        # 2. 替换路径拼接中的 Path(__file__) 模式
        # 例如：Path(__file__).resolve().parent.parent / "data" -> PROJECT_ROOT / "data"
        code = re.sub(
            r'Path\(__file__\)\.resolve\(\)\.parent\.parent\.parent\s*[/]',
            'PROJECT_ROOT /',
            code
        )
        code = re.sub(
            r'Path\(__file__\)\.resolve\(\)\.parent\.parent\s*[/]',
            'PROJECT_ROOT /',
            code
        )
        code = re.sub(
            r'Path\(__file__\)\.resolve\(\)\.parent\s*[/]',
            'PROJECT_ROOT /',
            code
        )
        code = re.sub(
            r'Path\(__file__\)\.resolve\(\)\.parents\[1\]\s*[/]',
            'PROJECT_ROOT /',
            code
        )
        code = re.sub(
            r'Path\(__file__\)\.resolve\(\)\.parents\[2\]\s*[/]',
            'PROJECT_ROOT /',
            code
        )
        
        # 3. 替换 os.path 风格的路径定义
        # os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
        code = re.sub(
            r'os\.path\.join\(os\.path\.dirname\(os\.path\.dirname\(os\.path\.abspath\(__file__\)\)\)\s*,\s*["\']',
            'os.path.join(str(PROJECT_ROOT), "',
            code
        )
        code = re.sub(
            r'os\.path\.join\(os\.path\.dirname\(os\.path\.abspath\(__file__\)\)\s*,\s*["\']',
            'os.path.join(str(PROJECT_ROOT), "',
            code
        )
        
        # 4. 替换 os.path.dirname 风格的路径定义
        # os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        code = re.sub(
            r'os\.path\.dirname\(os\.path\.dirname\(os\.path\.abspath\(__file__\)\)\)',
            'str(PROJECT_ROOT)',
            code
        )
        code = re.sub(
            r'os\.path\.dirname\(os\.path\.abspath\(__file__\)\)',
            'str(PROJECT_ROOT)',
            code
        )
        
        return code
    
    def inject_base_dir(self, code: str) -> str:
        """
        在代码开头注入项目根目录配置，并强制覆盖 LLM 可能错误定义的路径变量
        
        核心策略：
        1. 先修复代码中的 __file__ 路径定义
        2. 定义正确的 PROJECT_ROOT
        3. 强制 os.chdir 到项目根目录
        4. 覆盖 LLM 代码中可能使用 Path(__file__).resolve().parent.parent 的错误定义
        
        Args:
            code: 原始代码
            
        Returns:
            注入后的代码
        """
        # 首先修复代码中的路径定义
        fixed_code = self._fix_path_definitions(code)
        
        # 将路径转换为字符串，确保在注入代码中正确渲染
        root_str = str(self.project_root)
        
        injected_code = f'''import os
import sys
from pathlib import Path

# ===== Agent 自动注入：路径安全配置 =====
# 正确的项目根目录（由 Agent 强制执行，不可被 LLM 覆盖）
PROJECT_ROOT = Path(r"{root_str}")

# 强制切换工作目录到项目根目录
os.chdir(PROJECT_ROOT)

# 检查当前工作目录
_current_cwd = os.getcwd()
if str(_current_cwd) != str(PROJECT_ROOT):
    print(f"⚠️ 工作目录已从 {{_current_cwd}} 强制切换至 {{PROJECT_ROOT}}")
    os.chdir(PROJECT_ROOT)

# ⚠️ 重要：覆盖 LLM 可能错误定义的路径变量
# 许多 LLM 生成的代码会使用 Path(__file__).resolve().parent.parent，
# 但在临时文件中 __file__ 指向 /tmp/xxx.py，这会导致路径解析错误。
# 我们已经通过 _fix_path_definitions 替换了这些定义，这里再强制覆盖一次。
# 注意：使用 try/except 避免变量未定义的错误
try:
    # 覆盖常见的路径变量名
    BASE_DIR = PROJECT_ROOT
    base_dir = PROJECT_ROOT
    project_root = PROJECT_ROOT
    ROOT_DIR = PROJECT_ROOT
    root_dir = PROJECT_ROOT
    _project_root = PROJECT_ROOT
    PROJECT_ROOT_DIR = PROJECT_ROOT
    ROOT = PROJECT_ROOT
    root = PROJECT_ROOT
except NameError:
    pass

# 定义一个安全的路径解析函数，确保路径在项目内
def safe_path(path_str: str) -> Path:
    """将相对路径解析为项目内的绝对路径，确保不越界"""
    p = Path(path_str)
    if p.is_absolute():
        try:
            p.relative_to(PROJECT_ROOT)
            return p
        except ValueError:
            raise ValueError(f"绝对路径 {{p}} 不在项目根目录 {{PROJECT_ROOT}} 下")
    resolved = (PROJECT_ROOT / p).resolve()
    try:
        resolved.relative_to(PROJECT_ROOT)
        return resolved
    except ValueError:
        raise ValueError(f"路径 {{resolved}} 超出项目根目录范围")

# 打印调试信息，帮助定位路径问题
print(f"✅ 项目根目录: {{PROJECT_ROOT}}")
print(f"✅ 当前工作目录: {{Path.cwd()}}")
# ===== 路径安全配置结束 =====

# 用户代码开始
{fixed_code}
# 用户代码结束
'''
        return injected_code
    
    def verify_files_exist(self, expected_outputs: List[str]) -> Tuple[bool, List[str]]:
        """
        验证预期文件是否真实存在
        
        Args:
            expected_outputs: 预期的输出路径列表
            
        Returns:
            (是否全部存在, 缺失的文件列表)
        """
        if not expected_outputs:
            return True, []
        
        missing = []
        for path_str in expected_outputs:
            p = Path(path_str)
            if not p.is_absolute():
                p = self.project_root / p
            
            # 检查文件是否存在
            if not p.exists():
                missing.append(str(path_str))
            elif p.is_file() and p.stat().st_size == 0:
                # 文件存在但为空，也算缺失
                missing.append(f"{path_str} (文件为空)")
        
        if missing and self.logger:
            self.logger.warning(f"⚠️ 以下预期输出不存在或为空: {missing}")
        
        return len(missing) == 0, missing
    
    def execute_python_code(self, code: str, expected_outputs: List[str] = None) -> Tuple[bool, str, List[str]]:
        """
        在临时文件中执行 Python 代码
        
        Args:
            code: Python代码
            expected_outputs: 预期的输出路径列表
            
        Returns:
            (是否成功, 输出信息, 实际生成的文件列表)
        """
        # 1. 语法检查
        is_valid, syntax_error = self.check_syntax(code)
        if not is_valid:
            if self.logger:
                self.logger.error(f"❌ 语法检查失败:\n{syntax_error}")
            return False, f"❌ 语法错误：\n{syntax_error}", []
        
        # 2. 路径安全检查
        is_safe, safe_msg = self.check_path_safety(code)
        if not is_safe:
            if self.logger:
                self.logger.error(f"❌ {safe_msg}")
            return False, f"❌ 路径安全检查失败：{safe_msg}", []
        
        # 3. 检查是否有写入操作
        has_write, write_msg = self.has_write_operation(code)
        if not has_write:
            warning_msg = f"⚠️ {write_msg}。数据处理任务必须包含文件写入操作，请添加 open().write() 或 json.dump() 等写入代码。"
            if self.logger:
                self.logger.warning(warning_msg)
        else:
            if self.logger:
                self.logger.info(f"✅ {write_msg}")
        
        safe_code = self.inject_base_dir(code)
        
        # 创建临时文件
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8') as f:
            f.write(safe_code)
            temp_file = f.name
        
        # 记录执行前的文件状态（用于检测新生成的文件）
        before_files = set()
        for pattern in ['data/**/*.jsonl', 'data/**/*.json', 'data/**/*.csv', 'tools/**/*.py']:
            for p in self.project_root.glob(pattern):
                before_files.add(str(p.relative_to(self.project_root)))
        
        try:
            if self.logger:
                self.logger.debug(f"临时文件: {temp_file}")
            
            result = subprocess.run(
                [sys.executable, temp_file],
                capture_output=True,
                text=True,
                timeout=120,
                cwd=str(self.project_root)
            )
            
            # 检测执行后新生成的文件
            after_files = set()
            for pattern in ['data/**/*.jsonl', 'data/**/*.json', 'data/**/*.csv', 'tools/**/*.py']:
                for p in self.project_root.glob(pattern):
                    after_files.add(str(p.relative_to(self.project_root)))
            
            new_files = list(after_files - before_files)
            
            if result.returncode == 0:
                # 如果有预期输出，验证是否生成
                if expected_outputs:
                    success, missing = self.verify_files_exist(expected_outputs)
                    if not success:
                        return False, f"执行成功但以下文件未生成或为空：{missing}\n\n输出：{result.stdout}", new_files
                
                # 检查：如果没有新文件生成，但代码是数据处理任务，发出警告
                if not new_files and not has_write:
                    return True, f"{result.stdout}\n\n⚠️ 警告：代码执行成功，但未检测到任何文件写入操作，也没有生成新文件。请确保使用 open().write() 或 json.dump() 保存结果。", new_files
                elif not new_files and has_write:
                    # 有写入操作但没检测到新文件，可能是写入到了已存在的文件
                    return True, f"{result.stdout}\n\nℹ️ 代码包含写入操作，但未检测到新文件（可能覆盖了已有文件）。", new_files
                
                return True, result.stdout, new_files
            else:
                return False, result.stderr, new_files
                
        except subprocess.TimeoutExpired:
            return False, "执行超时（120秒）", []
        except Exception as e:
            return False, str(e), []
        finally:
            try:
                os.unlink(temp_file)
            except:
                pass
    
    def execute_bash_command(self, command: str) -> Tuple[bool, str]:
        """
        执行 Bash 命令
        
        Args:
            command: Bash命令
            
        Returns:
            (是否成功, 输出信息)
        """
        if self.logger:
            self.logger.info(f"🔧 执行 Bash 命令: {command}")
        
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=30,
                cwd=str(self.project_root)
            )
            if result.returncode == 0:
                return True, result.stdout
            else:
                return False, result.stderr
        except subprocess.TimeoutExpired:
            return False, "Bash 命令执行超时（30秒）"
        except Exception as e:
            return False, str(e)