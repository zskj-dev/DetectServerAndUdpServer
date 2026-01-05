import os
import shutil
import zipfile
from pathlib import Path
from datetime import datetime, timedelta
import logging
from typing import List, Tuple, Optional, Dict, Set
import psutil
import time
from dataclasses import dataclass
from collections import defaultdict

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('file_manager_enhanced.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


@dataclass
class FileInfo:
    """文件信息类"""
    path: Path
    mtime: datetime
    size: int
    relative_path: str = ""  # 相对于监控目录的路径


class EnhancedFileManager:
    def __init__(self,
                 target_dirs: List[str],
                 backup_dir: Optional[str] = None,
                 space_threshold: float = 20.0,
                 max_age_days: int = 30,
                 min_free_gb: float = 1.0,
                 recursive: bool = True,
                 preserve_structure: bool = True):
        """
        初始化增强版文件管理器
        
        参数:
            target_dirs: 要监控的目录列表
            backup_dir: 备份目录（可选）
            space_threshold: 磁盘空间不足的阈值（百分比）
            max_age_days: 文件最大保留天数
            min_free_gb: 最小保留空间（GB）
            recursive: 是否递归处理子目录
            preserve_structure: 是否保持目录结构
        """
        self.target_dirs = [Path(dir_path).resolve() for dir_path in target_dirs]
        self.backup_dir = Path(backup_dir).resolve() if backup_dir else None
        self.space_threshold = space_threshold
        self.max_age_days = max_age_days
        self.min_free_gb = min_free_gb
        self.recursive = recursive
        self.preserve_structure = preserve_structure
        
        # 支持的图片和告警文件格式
        self.supported_formats = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.log', '.txt', '.json', '.xml', '.csv'}
        
        # 排除的目录模式
        self.exclude_dirs = {'.git', '.svn', '__pycache__', 'node_modules', 'backup', '备份'}
        
        # 确保目标目录存在
        for dir_path in self.target_dirs:
            dir_path.mkdir(parents=True, exist_ok=True)
        
        if self.backup_dir:
            self.backup_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"初始化完成: 监控目录={[str(d) for d in self.target_dirs]}")
        logger.info(f"递归处理: {recursive}, 保持结构: {preserve_structure}")
    
    def check_disk_space(self, path: str = "/") -> Tuple[bool, float, float]:
        """
        检查磁盘剩余空间
        """
        try:
            disk_usage = psutil.disk_usage(path)
            free_percent = (disk_usage.free / disk_usage.total) * 100
            free_gb = disk_usage.free / (1024**3)
            is_low = free_percent < self.space_threshold or free_gb < self.min_free_gb
            
            return is_low, free_percent, free_gb
            
        except Exception as e:
            logger.error(f"检查磁盘空间失败: {e}")
            return False, 0.0, 0.0
    
    def is_directory_excluded(self, dir_path: Path) -> bool:
        """
        检查目录是否应该被排除
        
        参数:
            dir_path: 目录路径
            
        返回:
            bool: 是否排除
        """
        # 检查目录名是否在排除列表中
        if dir_path.name in self.exclude_dirs:
            return True
        
        # 检查是否为备份目录
        if self.backup_dir and self.backup_dir in dir_path.parents:
            return True
        
        # 检查是否为其他监控目录的子目录
        for target_dir in self.target_dirs:
            if target_dir != dir_path and target_dir in dir_path.parents:
                return True
        
        return False
    
    def get_old_files(self, base_dir: Path) -> List[FileInfo]:
        """
        获取目录中所有过期的文件（考虑子目录）
        
        参数:
            base_dir: 基础目录路径
            
        返回:
            List[FileInfo]: 过期文件列表，按修改时间排序
        """
        old_files = []
        current_time = datetime.now()
        
        try:
            # 确定扫描模式
            if self.recursive:
                scan_pattern = "**/*"
            else:
                scan_pattern = "*"
            
            for file_path in base_dir.glob(scan_pattern):
                # 跳过目录
                if file_path.is_dir():
                    continue
                
                # 检查文件格式
                if file_path.suffix.lower() not in self.supported_formats:
                    continue
                
                # 检查文件是否在排除的目录中
                if self.is_directory_excluded(file_path.parent):
                    continue
                
                try:
                    # 获取文件的修改时间
                    mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
                    age_days = (current_time - mtime).days
                    
                    if age_days > self.max_age_days:
                        # 计算相对路径
                        relative_path = str(file_path.relative_to(base_dir))
                        
                        file_info = FileInfo(
                            path=file_path,
                            mtime=mtime,
                            size=file_path.stat().st_size,
                            relative_path=relative_path
                        )
                        old_files.append(file_info)
                        
                except Exception as e:
                    logger.warning(f"获取文件信息失败 {file_path}: {e}")
                    continue
            
            # 按修改时间排序（从旧到新）
            old_files.sort(key=lambda x: x.mtime)
            
            logger.info(f"在目录 {base_dir} 中找到 {len(old_files)} 个过期文件")
            
        except Exception as e:
            logger.error(f"扫描目录失败 {base_dir}: {e}")
        
        return old_files
    
    def get_all_old_files_by_directory(self) -> Dict[Path, List[FileInfo]]:
        """
        按目录分组获取所有过期文件
        
        返回:
            字典：目录路径 -> 文件列表
        """
        all_files = {}
        
        for target_dir in self.target_dirs:
            if not target_dir.exists():
                logger.warning(f"目录不存在，跳过: {target_dir}")
                continue
            
            files = self.get_old_files(target_dir)
            if files:
                all_files[target_dir] = files
        
        return all_files
    
    def create_structured_zip(self, files: List[FileInfo], base_dir: Path, 
                            archive_name: str) -> Optional[Path]:
        """
        创建保持目录结构的压缩包
        
        参数:
            files: 要打包的文件列表
            base_dir: 基础目录
            archive_name: 压缩包名称
            
        返回:
            压缩包路径
        """
        if not files:
            return None
        
        try:
            archive_path = base_dir / archive_name
            
            # 如果压缩包已存在，添加序号
            counter = 1
            while archive_path.exists():
                name_parts = f"{archive_path.stem}_{counter:03d}{archive_path.suffix}"
                archive_path = base_dir / name_parts
                counter += 1
            
            total_size = 0
            with zipfile.ZipFile(archive_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for file_info in files:
                    try:
                        if self.preserve_structure:
                            # 保持目录结构
                            zipf.write(file_info.path, file_info.relative_path)
                        else:
                            # 扁平化存储（所有文件在根目录）
                            flat_name = file_info.path.name
                            # 处理重名文件
                            if flat_name in zipf.namelist():
                                name_parts = file_info.path.stem
                                counter = 1
                                while flat_name in zipf.namelist():
                                    flat_name = f"{name_parts}_{counter:03d}{file_info.path.suffix}"
                                    counter += 1
                            zipf.write(file_info.path, flat_name)
                        
                        total_size += file_info.size
                        
                    except Exception as e:
                        logger.warning(f"添加文件到压缩包失败 {file_info.path}: {e}")
                        continue
            
            archive_size = archive_path.stat().st_size
            compression_ratio = (1 - archive_size / total_size) * 100 if total_size > 0 else 0
            
            logger.info(f"创建压缩包成功: {archive_path.name}")
            logger.info(f"包含文件数: {len(files)}")
            logger.info(f"原始大小: {total_size/1024/1024:.2f}MB")
            logger.info(f"压缩后: {archive_size/1024/1024:.2f}MB")
            logger.info(f"压缩率: {compression_ratio:.1f}%")
            
            return archive_path
            
        except Exception as e:
            logger.error(f"创建压缩包失败: {e}")
            return None
    
    def archive_by_subdirectory(self, base_dir: Path, old_files: List[FileInfo]) -> Dict[str, Dict]:
        """
        按子目录分组归档文件
        
        参数:
            base_dir: 基础目录
            old_files: 过期文件列表
            
        返回:
            处理统计
        """
        stats = {
            'total_files': len(old_files),
            'archived_files': 0,
            'created_archives': 0,
            'failed_archives': 0,
            'by_directory': {}
        }
        
        if not old_files:
            return stats
        
        # 按子目录分组
        files_by_subdir = defaultdict(list)
        for file_info in old_files:
            # 获取子目录路径（相对于base_dir）
            subdir_path = Path(file_info.relative_path).parent
            
            if subdir_path == Path('.'):
                subdir_key = 'root'
            else:
                subdir_key = str(subdir_path)
            
            files_by_subdir[subdir_key].append(file_info)
        
        # 为每个子目录创建压缩包
        for subdir_key, subdir_files in files_by_subdir.items():
            if not subdir_files:
                continue
            
            # 计算时间范围
            start_time = min(f.mtime for f in subdir_files)
            end_time = max(f.mtime for f in subdir_files)
            
            # 生成压缩包名称
            start_str = start_time.strftime("%Y%m%d")
            end_str = end_time.strftime("%Y%m%d")
            
            if subdir_key == 'root':
                archive_name = f"archive_{start_str}_to_{end_str}.zip"
            else:
                # 在子目录名中包含目录信息
                dir_safe = subdir_key.replace('/', '_').replace('\\', '_')
                archive_name = f"archive_{dir_safe}_{start_str}_to_{end_str}.zip"
            
            # 创建压缩包
            archive_path = self.create_structured_zip(subdir_files, base_dir, archive_name)
            
            if archive_path:
                # 删除原始文件
                success_count = 0
                for file_info in subdir_files:
                    try:
                        # 备份（如果配置）
                        if self.backup_dir:
                            self._backup_file(file_info)
                        
                        # 删除原始文件
                        file_info.path.unlink()
                        success_count += 1
                        
                        # 尝试删除空目录
                        self._remove_empty_dirs(file_info.path.parent, base_dir)
                        
                    except Exception as e:
                        logger.error(f"删除文件失败 {file_info.path}: {e}")
                
                stats['archived_files'] += success_count
                stats['created_archives'] += 1
                
                # 记录子目录统计
                stats['by_directory'][subdir_key] = {
                    'files': len(subdir_files),
                    'archived': success_count,
                    'archive_name': archive_path.name
                }
                
                logger.info(f"子目录归档完成: {subdir_key}, "
                           f"文件数={len(subdir_files)}, 成功={success_count}")
            else:
                stats['failed_archives'] += 1
        
        return stats
    
    def _remove_empty_dirs(self, dir_path: Path, base_dir: Path, force_remove: bool = False):
        """
        递归删除空目录
        
        参数:
            dir_path: 要检查的目录
            base_dir: 基础目录（不会删除此目录）
            force_remove: 是否强制删除非空目录
        """
        try:
            # 确保不会删除基础目录
            if dir_path == base_dir:
                return
            
            # 检查目录是否为空
            has_files = False
            has_subdirs = False
            
            for item in dir_path.iterdir():
                if item.is_file():
                    has_files = True
                    break
                elif item.is_dir():
                    has_subdirs = True
                    # 递归检查子目录
                    self._remove_empty_dirs(item, base_dir, force_remove)
            
            # 如果目录为空，删除它
            if not has_files:
                try:
                    # 再次检查是否还有子目录
                    remaining_items = list(dir_path.iterdir())
                    if not remaining_items:
                        dir_path.rmdir()
                        logger.debug(f"删除空目录: {dir_path.relative_to(base_dir)}")
                except Exception as e:
                    logger.debug(f"无法删除目录 {dir_path}: {e}")
            
        except Exception as e:
            logger.warning(f"检查空目录失败 {dir_path}: {e}")
    
    def _backup_file(self, file_info: FileInfo):
        """
        备份文件到备份目录，保持目录结构
        """
        if not self.backup_dir:
            return
        
        try:
            # 创建相对路径结构
            backup_path = self.backup_dir / file_info.relative_path
            backup_path.parent.mkdir(parents=True, exist_ok=True)
            
            # 如果备份文件已存在，添加时间戳
            if backup_path.exists():
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                name_parts = f"{backup_path.stem}_{timestamp}{backup_path.suffix}"
                backup_path = backup_path.parent / name_parts
            
            shutil.copy2(file_info.path, backup_path)
            logger.debug(f"文件备份成功: {file_info.relative_path}")
            
        except Exception as e:
            logger.warning(f"文件备份失败 {file_info.path}: {e}")
    
    def delete_old_files_for_space(self) -> Dict[Path, Dict]:
        """
        释放磁盘空间：删除旧文件直到空间足够，考虑目录结构
        """
        logger.info("开始释放磁盘空间...")
        
        # 检查当前磁盘空间
        is_low, free_percent, free_gb = self.check_disk_space()
        
        if not is_low:
            logger.info(f"磁盘空间充足: {free_percent:.1f}% ({free_gb:.2f}GB)")
            return {}
        
        # 计算需要释放的空间
        disk_usage = psutil.disk_usage("/")
        current_free_gb = disk_usage.free / (1024**3)
        target_gb = self.min_free_gb + 1
        
        required_gb = target_gb - current_free_gb
        if required_gb <= 0:
            required_gb = 0.1  # 至少尝试释放100MB
        
        logger.warning(f"磁盘空间不足！需要释放 {required_gb:.2f}GB")
        
        # 获取所有过期文件（按目录分组）
        all_files_by_dir = self.get_all_old_files_by_directory()
        
        # 合并所有文件并排序（从最旧到最新）
        all_files = []
        for dir_path, files in all_files_by_dir.items():
            for file_info in files:
                all_files.append((dir_path, file_info))
        
        # 按修改时间排序
        all_files.sort(key=lambda x: x[1].mtime)
        
        # 统计
        stats = {}
        total_freed_bytes = 0
        required_bytes = required_gb * (1024**3)
        
        # 删除文件直到空间足够
        for dir_path, file_info in all_files:
            if total_freed_bytes >= required_bytes:
                break
            
            try:
                # 删除文件
                file_info.path.unlink()
                
                # 更新统计
                dir_name = str(dir_path)
                if dir_name not in stats:
                    stats[dir_name] = {
                        'deleted_files': 0,
                        'freed_bytes': 0,
                        'freed_mb': 0
                    }
                
                stats[dir_name]['deleted_files'] += 1
                stats[dir_name]['freed_bytes'] += file_info.size
                stats[dir_name]['freed_mb'] = stats[dir_name]['freed_bytes'] / (1024**2)
                
                total_freed_bytes += file_info.size
                
                logger.info(f"释放空间删除: {file_info.relative_path} "
                           f"(大小: {file_info.size/1024/1024:.2f}MB)")
                
                # 尝试删除空目录
                self._remove_empty_dirs(file_info.path.parent, dir_path)
                
                # 检查当前空间
                is_low_now, _, free_gb_now = self.check_disk_space()
                if not is_low_now:
                    logger.info(f"已释放足够空间！当前: {free_gb_now:.2f}GB")
                    break
                    
            except Exception as e:
                logger.error(f"删除文件失败 {file_info.path}: {e}")
                continue
        
        total_freed_gb = total_freed_bytes / (1024**3)
        
        # 最终检查
        is_low_final, free_percent_final, free_gb_final = self.check_disk_space()
        
        logger.info("=" * 50)
        logger.info("空间释放完成！")
        logger.info(f"总共释放空间: {total_freed_gb:.2f}GB")
        logger.info(f"最终磁盘空间: {free_percent_final:.1f}% ({free_gb_final:.2f}GB)")
        
        # 输出各目录统计
        for dir_name, dir_stats in stats.items():
            logger.info(f"  目录 {Path(dir_name).name}: "
                       f"删除 {dir_stats['deleted_files']} 个文件, "
                       f"释放 {dir_stats['freed_mb']:.1f}MB")
        
        logger.info("=" * 50)
        
        return stats
    
    def archive_old_files(self) -> Dict[str, Dict]:
        """
        归档过期的文件：按目录结构打包
        """
        logger.info("开始归档过期文件...")
        
        overall_stats = {
            'total_directories': 0,
            'total_files_found': 0,
            'total_files_archived': 0,
            'total_archives_created': 0,
            'directory_details': {}
        }
        
        # 按目录处理
        for target_dir in self.target_dirs:
            if not target_dir.exists():
                continue
            
            logger.info(f"处理目录: {target_dir}")
            
            # 获取该目录下的所有过期文件
            old_files = self.get_old_files(target_dir)
            
            if not old_files:
                logger.info(f"目录 {target_dir} 中没有过期文件")
                continue
            
            overall_stats['total_directories'] += 1
            overall_stats['total_files_found'] += len(old_files)
            
            # 按子目录分组并归档
            dir_stats = self.archive_by_subdirectory(target_dir, old_files)
            
            overall_stats['total_files_archived'] += dir_stats.get('archived_files', 0)
            overall_stats['total_archives_created'] += dir_stats.get('created_archives', 0)
            
            # 记录目录详情
            dir_key = str(target_dir)
            overall_stats['directory_details'][dir_key] = {
                'files_found': len(old_files),
                'files_archived': dir_stats.get('archived_files', 0),
                'archives_created': dir_stats.get('created_archives', 0),
                'by_subdirectory': dir_stats.get('by_directory', {})
            }
        
        return overall_stats
    
    def run(self) -> Dict[str, Dict]:
        """
        运行完整的文件管理流程
        """
        logger.info("=" * 60)
        logger.info("开始增强版文件管理流程")
        logger.info("=" * 60)
        
        all_stats = {
            'space_freeing': {},
            'archiving': {},
            'summary': {}
        }
        
        # 1. 检查并处理磁盘空间不足（紧急情况）
        is_low, free_percent, free_gb = self.check_disk_space()
        
        if is_low:
            logger.warning(f"检测到磁盘空间不足，优先处理！")
            logger.warning(f"当前空间: {free_percent:.1f}% ({free_gb:.2f}GB)")
            
            space_stats = self.delete_old_files_for_space()
            all_stats['space_freeing'] = space_stats
            
            # 重新检查空间
            is_low, free_percent, free_gb = self.check_disk_space()
        
        # 2. 处理过期文件归档（常规维护）
        logger.info("开始常规文件归档...")
        archive_stats = self.archive_old_files()
        all_stats['archiving'] = archive_stats
        
        # 3. 生成摘要
        summary = self._generate_summary(all_stats)
        all_stats['summary'] = summary
        
        # 4. 输出最终报告
        self._print_final_report(all_stats)
        
        return all_stats
    
    def _generate_summary(self, stats: Dict) -> Dict:
        """生成处理摘要"""
        summary = {
            'timestamp': datetime.now().isoformat(),
            'disk_status': {},
            'operations': {}
        }
        
        # 磁盘状态
        is_low, free_percent, free_gb = self.check_disk_space()
        summary['disk_status'] = {
            'free_percent': round(free_percent, 2),
            'free_gb': round(free_gb, 2),
            'is_low': is_low,
            'threshold': self.space_threshold,
            'min_free_gb': self.min_free_gb
        }
        
        # 空间释放操作
        space_stats = stats.get('space_freeing', {})
        if space_stats:
            total_deleted = sum(s.get('deleted_files', 0) for s in space_stats.values())
            total_freed_gb = sum(s.get('freed_bytes', 0) for s in space_stats.values()) / (1024**3)
            
            summary['operations']['space_freeing'] = {
                'directories_processed': len(space_stats),
                'files_deleted': total_deleted,
                'space_freed_gb': round(total_freed_gb, 2)
            }
        
        # 文件归档操作
        archive_stats = stats.get('archiving', {})
        if archive_stats:
            summary['operations']['archiving'] = {
                'directories_processed': archive_stats.get('total_directories', 0),
                'files_found': archive_stats.get('total_files_found', 0),
                'files_archived': archive_stats.get('total_files_archived', 0),
                'archives_created': archive_stats.get('total_archives_created', 0)
            }
        
        return summary
    
    def _print_final_report(self, stats: Dict):
        """打印最终报告"""
        logger.info("=" * 70)
        logger.info("增强版文件管理 - 处理完成报告")
        logger.info("=" * 70)
        
        summary = stats.get('summary', {})
        disk_status = summary.get('disk_status', {})
        operations = summary.get('operations', {})
        
        # 磁盘状态
        logger.info("[磁盘状态]")
        logger.info(f"  剩余空间: {disk_status.get('free_percent', 0):.1f}% "
                   f"({disk_status.get('free_gb', 0):.2f}GB)")
        logger.info(f"  状态: {'正常' if not disk_status.get('is_low', True) else '需要注意'}")
        
        # 空间释放结果
        space_op = operations.get('space_freeing')
        if space_op:
            logger.info("[空间释放]")
            logger.info(f"  处理目录数: {space_op.get('directories_processed', 0)}")
            logger.info(f"  删除文件数: {space_op.get('files_deleted', 0)}")
            logger.info(f"  释放空间: {space_op.get('space_freed_gb', 0):.2f}GB")
        
        # 文件归档结果
        archive_op = operations.get('archiving')
        if archive_op:
            logger.info("[文件归档]")
            logger.info(f"  处理目录数: {archive_op.get('directories_processed', 0)}")
            logger.info(f"  发现文件数: {archive_op.get('files_found', 0)}")
            logger.info(f"  归档文件数: {archive_op.get('files_archived', 0)}")
            logger.info(f"  创建压缩包: {archive_op.get('archives_created', 0)}")
        
        # 目录详情
        archive_stats = stats.get('archiving', {})
        dir_details = archive_stats.get('directory_details', {})
        
        if dir_details:
            logger.info("[目录详情]")
            for dir_path, details in dir_details.items():
                dir_name = Path(dir_path).name
                logger.info(f"  目录: {dir_name}")
                logger.info(f"    发现文件: {details.get('files_found', 0)}")
                logger.info(f"    归档文件: {details.get('files_archived', 0)}")
                logger.info(f"    压缩包数: {details.get('archives_created', 0)}")
                
                # 子目录详情
                subdir_details = details.get('by_subdirectory', {})
                if subdir_details:
                    for subdir, sub_stats in subdir_details.items():
                        if subdir == 'root':
                            logger.info(f"    根目录: {sub_stats.get('archived', 0)}个文件")
                        else:
                            logger.info(f"    子目录 {subdir}: {sub_stats.get('archived', 0)}个文件")
        
        logger.info("=" * 70)
        logger.info("处理完成！")
        logger.info("=" * 70)


def main():
    """
    主函数 - 配置和运行增强版文件管理器
    """
    # 配置参数
    CONFIG = {
        # 要监控的目录列表（根据实际情况修改）
        'target_dirs': [
            './runs/errorgifs',
            './runs/images',
        ],
        
        # 备份目录（可选）
        'backup_dir': '/var/backups/alarm_archive',
        
        # 磁盘空间阈值（百分比）
        'space_threshold': 20.0,
        
        # 最小保留空间（GB）
        'min_free_gb': 100.0,
        
        # 文件最大保留天数
        'max_age_days': 6,
        
        # 是否递归处理子目录
        'recursive': False,
        
        # 是否保持目录结构
        'preserve_structure': True,
        
        # 监控配置
        'monitor_interval': 3600,  # 秒
    }
    
    try:
        # 创建增强版文件管理器实例
        file_manager = EnhancedFileManager(
            target_dirs=CONFIG['target_dirs'],
            backup_dir=CONFIG['backup_dir'],
            space_threshold=CONFIG['space_threshold'],
            max_age_days=CONFIG['max_age_days'],
            min_free_gb=CONFIG['min_free_gb'],
            recursive=CONFIG['recursive'],
            preserve_structure=CONFIG['preserve_structure']
        )
        
        # 运行文件管理
        stats = file_manager.run()
        
        return stats
        
    except Exception as e:
        logger.error(f"程序执行失败: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    # 安装依赖（如果未安装）
    try:
        import psutil
    except ImportError:
        print("正在安装依赖...")
        import subprocess
        subprocess.run(['pip', 'install', 'psutil'])
        print("依赖安装完成，请重新运行程序")
        exit(1)
    
    # 运行主程序
    main()