"""影子仓库：用独立 git 跟踪文件变化，生成 diff"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Awaitable, Callable

from skywalker.tools.base import DiffHunk, FileDiff, ToolError, ToolResult

logger = logging.getLogger("skywalker.tools")

_HUNK_HEADER_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")

# 全局锁注册表：同一目录共享一把锁
_repo_locks: dict[str, asyncio.Lock] = {}


def _get_repo_lock(repo_dir: str) -> asyncio.Lock:
    """获取仓库级别的全局锁，保证同一仓库只有一个实例能操作"""
    if repo_dir not in _repo_locks:
        _repo_locks[repo_dir] = asyncio.Lock()
    return _repo_locks[repo_dir]


class ShadowRepo:
    """影子仓库：用独立 git 跟踪文件变化"""

    def __init__(self, project_root: str):
        self._project_root = Path(project_root).resolve()
        self._repo_dir = self._derive_repo_dir()
        self._lock = _get_repo_lock(str(self._repo_dir))
        self._init_repo()

    # ---- 初始化

    def _derive_repo_dir(self) -> Path:
        """根据项目根目录生成唯一的影子仓库路径，避免多项目互相污染"""
        project_hash = hashlib.sha256(
            str(self._project_root).encode()
        ).hexdigest()[:12]
        return Path.home() / ".skywalker" / "shadow_repo" / project_hash

    def _init_repo(self):
        """初始化影子仓库"""
        self._repo_dir.mkdir(parents=True, exist_ok=True)
        git_dir = self._repo_dir / ".git"
        if not git_dir.exists():
            self._run_git("init")
            self._run_git("config", "user.email", "shadow@skywalker")
            self._run_git("config", "user.name", "ShadowRepo")
            (self._repo_dir / ".gitkeep").touch()
            self._run_git("add", ".gitkeep")
            self._run_git("commit", "-m", "init")


    def _run_git(self, *args: str) -> subprocess.CompletedProcess:
        """执行 git 命令，失败时抛出 CalledProcessError"""
        return subprocess.run(
            ["git"] + list(args),
            cwd=self._repo_dir,
            capture_output=True,
            text=True,
            check=True,  # 非零返回码直接抛异常
        )

    # ---- 快照与同步

    def _sync_project(self) -> None:
        """增量同步项目到影子仓库（只复制变化的文件）"""
        ignore_dirs = {".git", "__pycache__", ".skywalker", ".venv", "node_modules"}
        ignore_suffixes = {".pyc"}

        # 正向同步：复制新增/修改的文件
        for src_dir, dirs, files in os.walk(self._project_root):
            # 跳过忽略的目录
            rel_dir = os.path.relpath(src_dir, self._project_root)
            parts = Path(rel_dir).parts
            if any(p in ignore_dirs for p in parts):
                dirs.clear()  # 阻止 os.walk 递归进入
                continue

            dst_dir = self._repo_dir / rel_dir
            dst_dir.mkdir(parents=True, exist_ok=True)

            for file in files:
                if Path(file).suffix in ignore_suffixes:
                    continue

                src_file = Path(src_dir) / file
                dst_file = dst_dir / file

                try:
                    # 内容比对优于 mtime 比对
                    if not dst_file.exists() or not _files_equal(src_file, dst_file):
                        shutil.copy2(src_file, dst_file)
                except OSError as e:
                    logger.warning("Failed to sync %s: %s", src_file, e)

        # 反向清理：删除影子仓库中多余的文件和空目录
        for dst_dir, dirs, files in os.walk(self._repo_dir, topdown=False):
            if ".git" in Path(dst_dir).parts:
                continue

            rel_dir = os.path.relpath(dst_dir, self._repo_dir)
            src_dir_path = self._project_root / rel_dir

            # 删除文件
            for file in files:
                if file == ".gitkeep":
                    continue
                dst_file = Path(dst_dir) / file
                src_file = src_dir_path / file
                if not src_file.exists():
                    try:
                        dst_file.unlink()
                    except OSError as e:
                        logger.warning("Failed to remove stale file %s: %s", dst_file, e)

            # 删除空目录
            try:
                remaining = list(Path(dst_dir).iterdir())
                is_empty = all(p.name == ".gitkeep" for p in remaining) if remaining else True
                if is_empty and dst_dir != str(self._repo_dir):
                    Path(dst_dir).rmdir()
            except OSError:
                pass

    def _commit_snapshot(self, message: str) -> str:
        """提交当前快照，返回 commit hash。无变更时返回当前 HEAD。"""
        self._sync_project()

        try:
            self._run_git("add", "-A")
        except subprocess.CalledProcessError as e:
            logger.error("git add failed: %s", e.stderr)
            raise

        # 检查是否有变更
        try:
            status = self._run_git("status", "--porcelain")
        except subprocess.CalledProcessError as e:
            logger.error("git status failed: %s", e.stderr)
            raise

        if not status.stdout.strip():
            head = self._run_git("rev-parse", "HEAD")
            hash_val = head.stdout.strip()
            logger.debug("Snapshot no changes: %s | hash=%s", message, hash_val[:8])
            return hash_val

        try:
            self._run_git("commit", "-m", message)
        except subprocess.CalledProcessError as e:
            logger.error("git commit failed: %s", e.stderr)
            raise

        hash_result = self._run_git("rev-parse", "HEAD")
        hash_val = hash_result.stdout.strip()
        logger.debug("Snapshot committed: %s | hash=%s", message, hash_val[:8])
        return hash_val

    # ---- Diff 生成

    def _get_diff(self, before: str, after: str) -> list[FileDiff]:
        """获取两个 commit 之间的 diff，支持多文件"""
        if before == after:
            return []

        try:
            result = self._run_git("diff", before, after, "--unified=3")
        except subprocess.CalledProcessError as e:
            logger.error("git diff failed: %s", e.stderr)
            return []

        if not result.stdout.strip():
            return []

        return self._parse_diff(result.stdout)

    def _parse_diff(self, diff_text: str) -> list[FileDiff]:
        """解析 git diff 输出为 FileDiff 列表（支持多文件）"""
        lines = diff_text.splitlines()
        if not lines:
            return []

        # 按 "diff --git" 分割成每个文件的段落
        file_chunks: list[list[str]] = []
        current_chunk: list[str] = []

        for line in lines:
            if line.startswith("diff --git"):
                if current_chunk:
                    file_chunks.append(current_chunk)
                current_chunk = [line]
            elif current_chunk:
                current_chunk.append(line)

        if current_chunk:
            file_chunks.append(current_chunk)

        # 逐文件解析
        diffs: list[FileDiff] = []
        for chunk in file_chunks:
            parsed = self._parse_single_file_diff(chunk)
            if parsed is not None:
                diffs.append(parsed)

        return diffs

    def _parse_single_file_diff(self, lines: list[str]) -> FileDiff | None:
        """解析单个文件的 diff 段落"""
        path = ""
        hunks: list[DiffHunk] = []
        current_hunk: DiffHunk | None = None
        additions = 0
        deletions = 0
        is_new_file = False

        for line in lines:
            # 文件元信息
            if line.startswith("diff --git"):
                match = re.search(r"b/(.+)$", line)
                if match:
                    path = match.group(1)
                continue

            if line.startswith("new file"):
                is_new_file = True
                continue

            if line.startswith("---") or line.startswith("+++"):
                continue

            # hunk 头部
            if line.startswith("@@"):
                if current_hunk is not None:
                    hunks.append(current_hunk)
                match = _HUNK_HEADER_RE.match(line)
                if match:
                    current_hunk = DiffHunk(
                        old_start=int(match.group(1)),
                        new_start=int(match.group(3)),
                        lines=[],
                    )
                else:
                    logger.warning("Unexpected hunk header: %r", line)
                    current_hunk = None
                continue

            # 辅助行
            if line.startswith("\\"):
                continue

            # 内容行
            if current_hunk is None:
                continue

            if line.startswith("+"):
                current_hunk.lines.append(("+", line[1:]))
                additions += 1
            elif line.startswith("-"):
                current_hunk.lines.append(("-", line[1:]))
                deletions += 1
            else:
                content = line[1:] if line.startswith(" ") else line
                current_hunk.lines.append((" ", content))

        if current_hunk is not None:
            hunks.append(current_hunk)

        if not path:
            return None

        return FileDiff(
            path=path,
            is_new_file=is_new_file,
            additions=additions,
            deletions=deletions,
            hunks=hunks,
        )

    # ---- 公开接口

    async def track(
        self,
        fn: Callable[[], Awaitable[ToolResult | ToolError]],
        tool_call_id: str,
    ) -> tuple[ToolResult | ToolError, list[FileDiff]]:
        """包裹工具执行，记录 before/after 快照，生成 diff。

        整个 before → execute → after 序列在锁内串行执行，
        保证快照不被其他并发调用污染。
        """
        async with self._lock:
            before = self._commit_snapshot(f"before-{tool_call_id}")

            result = await fn()

            after = self._commit_snapshot(f"after-{tool_call_id}")
            diffs = self._get_diff(before, after)

        return result, diffs


def _files_equal(a: Path, b: Path) -> bool:
    """通过文件大小 + 内容 hash 比较两个文件是否相同"""
    try:
        if a.stat().st_size != b.stat().st_size:
            return False
        return a.read_bytes() == b.read_bytes()
    except OSError:
        return False